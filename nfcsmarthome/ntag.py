"""
ntag.py – NTAG213/215/216 (NFC Forum Typ 2) lesen, beschreiben und schützen (Kapitel 7).

Speicher in Seiten zu je 4 Byte:

  Seite 0–1   UID (7 Byte) und Prüfbytes                       nur lesbar
  Seite 2     Prüfbyte, intern, Lock-Bytes (statisch)           Lock-Bits: einmalig setzbar
  Seite 3     Capability Container (CC) E1 10 <Größe> 00         OTP: Bits nur setzbar
  Seite 4 …   Nutzspeicher (hier steht die NDEF-Nachricht)
  danach      dynamische Lock-Bytes, CFG0, CFG1, PWD, PACK

  CFG0 Byte 3 = AUTH0  erste geschützte Seite (FF = kein Schutz)
  CFG1 Byte 0 = ACCESS Bit 7 PROT (0 = nur Schreiben geschützt, 1 = auch Lesen)
                       Bit 6 CFGLCK, Bit 4 NFC_CNT_EN, Bit 2–0 AUTHLIM
  PWD  4 Byte Passwort (liest sich immer als 00 00 00 00)
  PACK 2 Byte Bestätigung, die das Tag nach richtigem Passwort zurückgibt

Alle Funktionen bekommen einen „Leser“ mit read_pages(p) -> 16 Byte, write_page(p, 4 Byte)
und transceive(roh) – also apdu.Acr122u oder den Simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from . import ndef


@dataclass(frozen=True)
class NtagType:
    name: str
    storage: int          # Byte 6 von GET_VERSION
    user_bytes: int
    last_user_page: int
    dyn_lock: int
    cfg0: int
    total_pages: int
    cc_size: int          # Byte 2 des CC laut Datenblatt (Werkszustand)

    @property
    def cfg1(self) -> int:
        return self.cfg0 + 1

    @property
    def pwd(self) -> int:
        return self.cfg0 + 2

    @property
    def pack(self) -> int:
        return self.cfg0 + 3

    @property
    def cc(self) -> bytes:
        """Capability Container: NDEF-Magie E1, Version 1.0, Größe/8, Lese-/Schreibrecht 00."""
        return bytes([0xE1, 0x10, self.cc_size, 0x00])


NTAG213 = NtagType("NTAG213", 0x0F, 144, 0x27, 0x28, 0x29, 45, 0x12)
NTAG215 = NtagType("NTAG215", 0x11, 504, 0x81, 0x82, 0x83, 135, 0x3E)
NTAG216 = NtagType("NTAG216", 0x13, 888, 0xE1, 0xE2, 0xE3, 231, 0x6D)
TYPES = {t.storage: t for t in (NTAG213, NTAG215, NTAG216)}


class NtagError(Exception):
    pass


def identify(reader) -> NtagType:
    """GET_VERSION: 00 04 04 02 01 00 <Größe> 03 – Hersteller NXP (04), Produkt NTAG (04)."""
    v = reader.ntag_get_version()
    if len(v) < 8 or v[1] != 0x04 or v[2] != 0x04:
        raise NtagError(f"kein NTAG (GET_VERSION {v.hex()})")
    if v[6] not in TYPES:
        raise NtagError(f"unbekannte NTAG-Größe {v[6]:02X}")
    return TYPES[v[6]]


def read_pages(reader, first: int, count: int) -> bytes:
    """count Seiten ab first lesen (READ liefert immer vier Seiten auf einmal)."""
    out = bytearray()
    page = first
    while len(out) < count * 4:
        out += reader.read_pages(page)
        page += 4
    return bytes(out[:count * 4])


def read_user_memory(reader, t: NtagType, max_bytes: Optional[int] = None) -> bytes:
    n = t.user_bytes if max_bytes is None else min(max_bytes, t.user_bytes)
    return read_pages(reader, 4, (n + 3) // 4)[:n]


def parse_user_memory(memory: bytes) -> List[ndef.Record]:
    """Nutzspeicher -> NDEF-Records (leer, wenn kein NDEF-Block gefunden wurde)."""
    msg = ndef.find_ndef_tlv(memory)
    return ndef.decode_message(msg) if msg else []


def read_ndef(reader, t: NtagType) -> List[ndef.Record]:
    """Erst den Kopf lesen, dann nur so viel, wie die Nachricht lang ist."""
    head = read_pages(reader, 4, 4)
    if head[0] == 0x03 and head[1] != 0xFF:
        need = 2 + head[1] + 1
    elif head[0] == 0x03:
        need = 4 + int.from_bytes(head[2:4], "big") + 1
    else:
        need = t.user_bytes                      # andere TLVs davor: alles lesen
    return parse_user_memory(read_user_memory(reader, t, need))


def ndef_bytes(records: List[ndef.Record]) -> bytes:
    data = ndef.wrap_tlv(ndef.encode_message(records))
    return data + bytes(-len(data) % 4)          # auf ganze Seiten auffüllen


def write_ndef(reader, t: NtagType, records: List[ndef.Record], check_cc: bool = True) -> int:
    """NDEF-Nachricht ab Seite 4 schreiben. Liefert die Zahl der geschriebenen Seiten."""
    data = ndef_bytes(records)
    if len(data) > t.user_bytes:
        raise NtagError(f"Nachricht zu groß: {len(data)} Byte, {t.name} hat {t.user_bytes}")
    if check_cc:
        cc = read_pages(reader, 3, 1)
        if cc[0] != 0xE1:
            raise NtagError("Tag ist nicht NDEF-formatiert (CC fehlt) – zuerst format_cc()")
        if cc[3] & 0x0F:                          # untere 4 Bit: Schreibzugriff (0 = erlaubt)
            raise NtagError("Tag ist laut CC schreibgeschützt")
    for i in range(0, len(data), 4):
        reader.write_page(4 + i // 4, data[i:i + 4])
    return len(data) // 4


def format_cc(reader, t: NtagType) -> None:
    """Capability Container schreiben. Achtung: Seite 3 ist OTP – Bits lassen sich nur setzen."""
    cc = read_pages(reader, 3, 1)
    if cc == t.cc:
        return
    if any(c & ~n for c, n in zip(cc, t.cc)):
        raise NtagError(f"CC {cc.hex()} lässt sich nicht mehr auf {t.cc.hex()} ändern (OTP)")
    reader.write_page(3, t.cc)


# -- Passwortschutz -------------------------------------------------------------------------
def read_config(reader, t: NtagType) -> Dict[str, int]:
    cfg = read_pages(reader, t.cfg0, 2)
    access = cfg[4]
    return {"auth0": cfg[3], "prot": access >> 7 & 1, "cfglck": access >> 6 & 1,
            "nfc_cnt_en": access >> 4 & 1, "authlim": access & 0x07}


def set_password(reader, t: NtagType, pwd: bytes, pack: bytes, auth0: int = 4,
                 prot: bool = False, authlim: int = 0, nfc_counter: bool = False) -> None:
    """
    Passwortschutz einrichten. Reihenfolge ist wichtig: erst PWD und PACK, dann ACCESS,
    zuletzt AUTH0 – erst damit wird der Schutz aktiv.
    Ist schon ein Passwort gesetzt, muss vorher authenticate() erfolgreich gewesen sein.
    """
    if len(pwd) != 4 or len(pack) != 2:
        raise ValueError("PWD hat 4 Byte, PACK 2 Byte")
    if not 0 <= authlim <= 7:
        raise ValueError("AUTHLIM 0..7")
    cfg = bytearray(read_pages(reader, t.cfg0, 2))
    reader.write_page(t.pwd, pwd)
    reader.write_page(t.pack, pack + b"\x00\x00")
    access = (0x80 if prot else 0) | (0x10 if nfc_counter else 0) | authlim
    reader.write_page(t.cfg1, bytes([access]) + bytes(cfg[5:8]))
    reader.write_page(t.cfg0, bytes(cfg[0:3]) + bytes([auth0]))


def authenticate(reader, pwd: bytes, expected_pack: Optional[bytes] = None) -> bytes:
    pack = reader.ntag_pwd_auth(pwd)
    if expected_pack is not None and pack != expected_pack:
        raise NtagError("PACK stimmt nicht – das Tag ist nicht das erwartete")
    return pack


def remove_password(reader, t: NtagType, pwd: bytes) -> None:
    authenticate(reader, pwd)
    cfg = read_pages(reader, t.cfg0, 1)
    reader.write_page(t.cfg0, cfg[0:3] + b"\xFF")


def lock_permanently(reader, t: NtagType, confirm: str = "") -> None:
    """
    Tag DAUERHAFT schreibschützen: statische und dynamische Lock-Bits setzen, CC auf
    „nur lesen“. Das ist nicht umkehrbar – deshalb muss confirm = "UNWIDERRUFLICH" sein.
    """
    if confirm != "UNWIDERRUFLICH":
        raise NtagError("lock_permanently braucht confirm='UNWIDERRUFLICH'")
    # Reihenfolge: erst CC, dann die Lock-Bits – danach ist auch das CC gesperrt
    cc = read_pages(reader, 3, 1)
    reader.write_page(3, cc[0:3] + b"\x0F")               # CC: Schreibzugriff „keiner“
    reader.write_page(t.dyn_lock, b"\xFF\xFF\xFF\x00")   # dynamische Lock-Bytes (Seiten ab 16)
    p2 = read_pages(reader, 2, 1)
    reader.write_page(2, p2[0:2] + b"\xFF\xFF")          # statische Lock-Bytes (Seiten 3–15)
