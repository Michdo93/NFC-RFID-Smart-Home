"""
sim.py – ein simulierter ACR122U mit virtuellen Karten (Kapitel 9).

Der Simulator beantwortet dieselben APDUs wie ein echter ACR122U (siehe apdu.py) und
bildet die Karten so nach, wie das Datenblatt sie beschreibt:

  VirtualClassic   MIFARE Classic 1K: Sektoren, Key A/B, Zugriffsbits – inklusive
                   „Sektor gesperrt“, wenn jemand ungültige Zugriffsbits schreibt
  VirtualNtag      NTAG213/215/216: Seiten, CC, GET_VERSION, PWD_AUTH, AUTH0/PROT,
                   statische Lock-Bits, NFC-Zähler, Originalitätssignatur

Karten werden als JSON-Datei gespeichert (data/sim/<name>.json). Was ein Skript auf eine
virtuelle Karte schreibt, liest das nächste Skript wieder – wie bei einer echten Karte.
Vorlagen im Werkszustand liegen in sim/vorlagen/.

Das ersetzt keine Hardware: Funkverhalten, Zeitverhalten und Eigenheiten einzelner
Kartenchargen bildet der Simulator nicht ab.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import hexs, unhex
from ..classic import DATA_RULES, TRAILER_RULES, ClassicError, allowed, decode_access_bits
from ..config import REPO_ROOT

TEMPLATES = REPO_ROOT / "sim" / "vorlagen"
SIM_DIR = REPO_ROOT / "data" / "sim"

OK = (0x90, 0x00)
FAIL = (0x63, 0x00)


def atr_for(nn: Tuple[int, int]) -> bytes:
    """ATR nach PC/SC Teil 3 für kontaktlose Speicherkarten (ISO 14443A Teil 3)."""
    body = bytes([0x8F, 0x80, 0x01, 0x80, 0x4F, 0x0C, 0xA0, 0x00, 0x00, 0x03, 0x06, 0x03,
                  nn[0], nn[1], 0x00, 0x00, 0x00, 0x00])
    tck = 0                                  # Prüfbyte: XOR über alles nach dem ersten Byte (3B)
    for b in body:
        tck ^= b
    return bytes([0x3B]) + body + bytes([tck])


class SimCardError(Exception):
    pass


# ======================================================================================
class VirtualClassic:
    kind = "classic1k"
    atr = atr_for((0x00, 0x01))

    def __init__(self, uid: bytes, blocks: List[bytes], dead: Optional[List[int]] = None):
        self.uid = uid
        self.blocks = [bytearray(b) for b in blocks]
        self.dead = set(dead or [])           # Sektoren mit kaputten Zugriffsbits
        self.auth: Optional[Tuple[int, str]] = None

    @staticmethod
    def factory(uid: bytes) -> "VirtualClassic":
        bcc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
        block0 = uid + bytes([bcc, 0x08, 0x04, 0x00]) + bytes.fromhex("62636465666768 69")
        blocks = [block0[:16].ljust(16, b"\x00")]
        for b in range(1, 64):
            if b % 4 == 3:
                blocks.append(b"\xFF" * 6 + bytes([0xFF, 0x07, 0x80, 0x69]) + b"\xFF" * 6)
            else:
                blocks.append(bytes(16))
        return VirtualClassic(uid, blocks)

    def reset_session(self) -> None:
        self.auth = None

    def _access(self, sector: int) -> bytes:
        return bytes(self.blocks[sector * 4 + 3][6:9])

    def authenticate(self, block: int, key_type: str, key: bytes) -> bool:
        sector = block // 4
        self.auth = None
        if sector in self.dead or not 0 <= block < 64:
            return False
        trailer = self.blocks[sector * 4 + 3]
        stored = bytes(trailer[0:6]) if key_type == "A" else bytes(trailer[10:16])
        if key_type == "B":
            # Ist Key B lesbar, taugt er laut Datenblatt nicht zur Anmeldung
            cond = decode_access_bits(self._access(sector))[3]
            if TRAILER_RULES[cond][3] != "-":
                return False
        if stored != key:
            return False
        self.auth = (sector, key_type)
        return True

    def _check(self, block: int) -> str:
        if self.auth is None or self.auth[0] != block // 4:
            raise SimCardError("nicht angemeldet")
        return self.auth[1]

    def read(self, block: int) -> bytes:
        kt = self._check(block)
        sector, idx = block // 4, block % 4
        data = bytearray(self.blocks[block])
        if idx == 3:
            cond = decode_access_bits(self._access(sector))[3]
            _, ac_r, _, kb_r, _ = TRAILER_RULES[cond]
            data[0:6] = bytes(6)                          # Key A ist nie lesbar
            if not allowed(ac_r, kt):
                data[6:10] = bytes(4)
            if not allowed(kb_r, kt):
                data[10:16] = bytes(6)
            return bytes(data)
        r, _ = DATA_RULES[decode_access_bits(self._access(sector))[idx]]
        if not allowed(r, kt):
            raise SimCardError("Lesen nicht erlaubt")
        return bytes(data)

    def write(self, block: int, data: bytes) -> None:
        kt = self._check(block)
        if len(data) != 16:
            raise SimCardError("Block hat 16 Byte")
        if block == 0:
            raise SimCardError("Herstellerblock ist schreibgeschützt")
        sector, idx = block // 4, block % 4
        cond = decode_access_bits(self._access(sector))
        if idx == 3:
            ka_w, _, ac_w, _, kb_w = TRAILER_RULES[cond[3]]
            old = self.blocks[block]
            new = bytearray(old)
            if allowed(ka_w, kt):
                new[0:6] = data[0:6]
            if allowed(ac_w, kt):
                new[6:10] = data[6:10]
            if allowed(kb_w, kt):
                new[10:16] = data[10:16]
            if new == old and data != old:
                raise SimCardError("Trailer schreiben nicht erlaubt")
            self.blocks[block] = new
            try:
                decode_access_bits(bytes(new[6:9]))
            except ClassicError:
                self.dead.add(sector)                       # wie bei der echten Karte: Sektor tot
            return
        _, w = DATA_RULES[cond[idx]]
        if not allowed(w, kt):
            raise SimCardError("Schreiben nicht erlaubt")
        self.blocks[block] = bytearray(data)

    def to_dict(self) -> dict:
        return {"type": self.kind, "uid": hexs(self.uid), "dead_sectors": sorted(self.dead),
                "blocks": [hexs(b) for b in self.blocks]}

    @staticmethod
    def from_dict(d: dict) -> "VirtualClassic":
        return VirtualClassic(unhex(d["uid"]), [unhex(b) for b in d["blocks"]], d.get("dead_sectors"))


# ======================================================================================
NTAG_LAYOUT = {  # Typ: (Seiten gesamt, CFG0, Größenbyte GET_VERSION, CC-Größe)
    "ntag213": (45, 0x29, 0x0F, 0x12),
    "ntag215": (135, 0x83, 0x11, 0x3E),
    "ntag216": (231, 0xE3, 0x13, 0x6D),
}


class VirtualNtag:
    atr = atr_for((0x00, 0x03))               # erscheint wie MIFARE Ultralight

    def __init__(self, kind: str, uid: bytes, pages: List[bytes], signature: bytes,
                 nfc_counter: int = 0):
        self.kind = kind
        self.uid = uid
        self.pages = [bytearray(p) for p in pages]
        self.signature = signature
        self.nfc_counter = nfc_counter
        self.total, self.cfg0, self.size_byte, _ = NTAG_LAYOUT[kind]
        self.authenticated = False
        self.halted = False
        self._counted = False

    @staticmethod
    def factory(kind: str, uid: bytes, signature: Optional[bytes] = None) -> "VirtualNtag":
        total, cfg0, _, cc_size = NTAG_LAYOUT[kind]
        bcc0 = 0x88 ^ uid[0] ^ uid[1] ^ uid[2]
        bcc1 = uid[3] ^ uid[4] ^ uid[5] ^ uid[6]
        pages = [bytes(4)] * total
        pages[0] = uid[0:3] + bytes([bcc0])
        pages[1] = uid[3:7]
        pages[2] = bytes([bcc1, 0x48, 0x00, 0x00])
        pages[3] = bytes([0xE1, 0x10, cc_size, 0x00])
        pages[4] = bytes([0x03, 0x00, 0xFE, 0x00])          # leere NDEF-Nachricht
        pages[cfg0 - 1] = bytes([0x00, 0x00, 0x00, 0xBD])    # dynamische Lock-Bytes
        pages[cfg0] = bytes([0x04, 0x00, 0x00, 0xFF])        # CFG0: AUTH0 = FF (kein Schutz)
        pages[cfg0 + 1] = bytes([0x00, 0x05, 0x00, 0x00])    # CFG1: ACCESS
        pages[cfg0 + 2] = b"\xFF\xFF\xFF\xFF"                # PWD (Werkszustand)
        pages[cfg0 + 3] = bytes(4)                           # PACK
        sig = signature if signature else bytes((b * 7 + 3) & 0xFF for b in uid * 5)[:32]
        return VirtualNtag(kind, uid, pages, sig)

    def reset_session(self) -> None:
        self.authenticated = False
        self.halted = False
        self._counted = False

    @property
    def auth0(self) -> int:
        return self.pages[self.cfg0][3]

    @property
    def access(self) -> int:
        return self.pages[self.cfg0 + 1][0]

    def _locked_static(self, page: int) -> bool:
        lock0, lock1 = self.pages[2][2], self.pages[2][3]
        if 3 <= page <= 7:
            return bool(lock0 >> page & 1)
        if 8 <= page <= 15:
            return bool(lock1 >> (page - 8) & 1)
        return False

    def read(self, page: int) -> bytes:
        if self.halted:
            raise SimCardError("Tag im Ruhezustand (nach falschem Passwort neu auflegen)")
        if not 0 <= page < self.total:
            raise SimCardError("Seite außerhalb des Speichers")
        if self.access & 0x80 and page >= self.auth0 and not self.authenticated:
            raise SimCardError("Lesen geschützt (PROT=1)")
        if self.access & 0x10 and not self._counted:
            self.nfc_counter = (self.nfc_counter + 1) & 0xFFFFFF
            self._counted = True
        out = bytearray()
        for i in range(4):
            p = (page + i) % self.total
            if p in (self.cfg0 + 2, self.cfg0 + 3):           # PWD und PACK lesen sich als 00
                out += bytes(4)
            elif self.access & 0x80 and p >= self.auth0 and not self.authenticated:
                out += bytes(4)
            else:
                out += self.pages[p]
        return bytes(out)

    def write(self, page: int, data: bytes) -> None:
        if self.halted:
            raise SimCardError("Tag im Ruhezustand")
        if len(data) != 4 or not 2 <= page < self.total:
            raise SimCardError("ungültige Seite")
        if page >= self.auth0 and not self.authenticated:
            raise SimCardError("Schreiben geschützt (Passwort nötig)")
        if self._locked_static(page):
            raise SimCardError(f"Seite {page} ist gesperrt (Lock-Bit)")
        if page == 2:                                        # nur Lock-Bytes, und nur setzen
            old = self.pages[2]
            self.pages[2] = bytearray([old[0], old[1], old[2] | data[2], old[3] | data[3]])
            return
        if page == 3:                                        # CC ist OTP
            old = self.pages[3]
            self.pages[3] = bytearray(o | n for o, n in zip(old, data))
            return
        self.pages[page] = bytearray(data)

    def transceive(self, raw: bytes) -> bytes:
        if self.halted:
            raise SimCardError("Tag im Ruhezustand")
        cmd = raw[0]
        if cmd == 0x60:                                      # GET_VERSION
            return bytes([0x00, 0x04, 0x04, 0x02, 0x01, 0x00, self.size_byte, 0x03])
        if cmd == 0x1B:                                      # PWD_AUTH
            pwd = bytes(self.pages[self.cfg0 + 2])
            if raw[1:5] == pwd:
                self.authenticated = True
                return bytes(self.pages[self.cfg0 + 3][0:2])
            self.halted = True                               # NAK – Tag geht in den Ruhezustand
            raise SimCardError("NAK")
        if cmd == 0x3C:                                      # READ_SIG
            return self.signature
        if cmd == 0x39:                                      # READ_CNT
            return self.nfc_counter.to_bytes(3, "little")
        if cmd == 0x30:                                      # READ
            return self.read(raw[1])
        if cmd == 0xA2:                                      # WRITE
            self.write(raw[1], raw[2:6])
            return bytes([0x0A])
        raise SimCardError(f"Befehl {cmd:02X} nicht unterstützt")

    def to_dict(self) -> dict:
        return {"type": self.kind, "uid": hexs(self.uid), "signature": hexs(self.signature),
                "nfc_counter": self.nfc_counter, "pages": [hexs(p) for p in self.pages]}

    @staticmethod
    def from_dict(d: dict) -> "VirtualNtag":
        return VirtualNtag(d["type"], unhex(d["uid"]), [unhex(p) for p in d["pages"]],
                           unhex(d["signature"]), int(d.get("nfc_counter", 0)))


def card_from_dict(d: dict):
    return VirtualClassic.from_dict(d) if d["type"] == "classic1k" else VirtualNtag.from_dict(d)


# ======================================================================================
class SimulatedAcr122u:
    """Eine „Verbindung“ mit transmit() wie bei pyscard – für apdu.Acr122u."""

    FIRMWARE = b"ACR122U215"

    def __init__(self, card=None):
        self.card = card
        self.keys: Dict[int, bytes] = {}
        self.led = (False, False)                # (rot, grün)
        self.beeps = 0
        self.buzzer_on_detect = True
        self.signals: List[Tuple[int, int, int, int, int]] = []   # Mitschnitt der LED-APDUs

    # -- Karte auflegen/abnehmen ------------------------------------------------------------
    def place(self, card) -> None:
        self.card = card
        card.reset_session()
        if self.buzzer_on_detect:
            self.beeps += 1

    def remove(self) -> None:
        self.card = None

    def get_atr(self) -> bytes:
        if self.card is None:
            raise SimCardError("keine Karte aufgelegt")
        return self.card.atr

    # -- APDUs ------------------------------------------------------------------------------
    def transmit(self, apdu: List[int]):
        a = bytes(apdu)
        if a[:2] == b"\xFF\x00" and a[2] == 0x48:                       # Firmware
            return list(self.FIRMWARE[:-2]), self.FIRMWARE[-2], self.FIRMWARE[-1]
        if a[:3] == b"\xFF\x00\x40":                                    # LED/Summer
            p2 = a[3]
            red = bool(p2 & 0x01) if p2 & 0x04 else self.led[0]
            green = bool(p2 & 0x02) if p2 & 0x08 else self.led[1]
            self.led = (red, green)
            if a[8] if len(a) > 8 else 0:
                self.beeps += a[7]
            self.signals.append((p2, a[5], a[6], a[7], a[8]))
            return [], 0x90, (1 if red else 0) | (2 if green else 0)
        if a[:3] == b"\xFF\x00\x52":                                    # Summer bei Erkennung
            self.buzzer_on_detect = a[3] == 0xFF
            return [], 0x90, 0x00
        if a[:2] == b"\xFF\x82":                                        # Schlüssel laden
            self.keys[a[3]] = a[5:11]
            return [], *OK
        if self.card is None:
            raise SimCardError("keine Karte aufgelegt")
        try:
            return self._card_apdu(a)
        except SimCardError:
            return [], *FAIL

    def _card_apdu(self, a: bytes):
        c = self.card
        if a[:2] == b"\xFF\xCA":
            if a[2] == 0x00:
                return list(c.uid), *OK
            return [], 0x6A, 0x81                                        # kein ATS (nicht ISO 14443-4)
        if a[:2] == b"\xFF\x86":
            block, key_type, slot = a[7], a[8], a[9]
            if not isinstance(c, VirtualClassic) or slot not in self.keys:
                return [], *FAIL
            ok = c.authenticate(block, "A" if key_type == 0x60 else "B", self.keys[slot])
            return ([], *OK) if ok else ([], *FAIL)
        if a[:2] == b"\xFF\xB0":
            block, length = a[3], a[4]
            data = c.read(block)
            return list(data[:length]), *OK
        if a[:2] == b"\xFF\xD6":
            block, length = a[3], a[4]
            data = a[5:5 + length]
            if isinstance(c, VirtualClassic):
                c.write(block, data)
            else:
                if length != 4:
                    raise SimCardError("NTAG: 4 Byte je Seite")
                c.write(block, data)
            return [], *OK
        if a[:4] == b"\xFF\x00\x00\x00":                                # Direkt an den PN532
            cmd = a[5:5 + a[4]]
            if cmd[:2] == b"\xD4\x42":
                if not isinstance(c, VirtualNtag):
                    return [0xD5, 0x43, 0x01], *OK
                try:
                    resp = c.transceive(cmd[2:])
                except SimCardError:
                    return [0xD5, 0x43, 0x01], *OK
                return [0xD5, 0x43, 0x00] + list(resp), *OK
            return [], 0x6A, 0x81
        return [], 0x6A, 0x81


# ======================================================================================
def sim_path(name: str) -> Path:
    """data/sim/<name>.json – beim ersten Zugriff aus sim/vorlagen/ kopiert."""
    p = Path(name)
    if p.suffix == ".json" and p.exists():
        return p
    target = SIM_DIR / f"{p.stem}.json"
    if not target.exists():
        template = TEMPLATES / f"{p.stem}.json"
        if not template.exists():
            choices = ", ".join(sorted(t.stem for t in TEMPLATES.glob("*.json")))
            raise FileNotFoundError(f"Virtuelle Karte {name!r} unbekannt. Vorhanden: {choices}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(template, target)
    return target


def load_card(name: str):
    return card_from_dict(json.loads(sim_path(name).read_text(encoding="utf-8")))


def save_card(name: str, card) -> None:
    p = sim_path(name)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(card.to_dict(), indent=1), encoding="utf-8")
    os.replace(tmp, p)


def reset_card(name: str) -> Path:
    """Virtuelle Karte auf den Werkszustand der Vorlage zurücksetzen."""
    target = SIM_DIR / f"{Path(name).stem}.json"
    if target.exists():
        target.unlink()
    return sim_path(name)
