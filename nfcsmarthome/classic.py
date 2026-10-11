"""
classic.py – MIFARE Classic 1K (S50): Sektoren, Schlüssel, Zugriffsbits (Kapitel 8).

  16 Sektoren × 4 Blöcke × 16 Byte = 1024 Byte
  Block 0 (Sektor 0)        Herstellerblock: UID, BCC, SAK, ATQA – nur lesbar
  letzter Block je Sektor   Sektor-Trailer: Key A (6) | Zugriffsbits (3) | GPB (1) | Key B (6)

Die Zugriffsbits legen je Block fest, mit welchem Schlüssel gelesen und geschrieben
werden darf. Jedes Bit steht zweimal im Trailer – einmal normal, einmal invertiert.
Passen die beiden nicht zusammen, ist der Sektor für immer gesperrt. Deshalb baut
dieses Modul Trailer nur aus geprüften Bedingungen (make_trailer) und weigert sich,
ungültige zu schreiben.

Werkszustand: Key A = Key B = FF FF FF FF FF FF, Zugriffsbits FF 07 80 (Transportkonfiguration).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

FACTORY_KEY = b"\xFF" * 6
FACTORY_ACCESS = bytes([0xFF, 0x07, 0x80])

# Bedeutung der Bedingungen (C1 C2 C3) für Datenblöcke: (lesen, schreiben)
DATA_RULES: Dict[Tuple[int, int, int], Tuple[str, str]] = {
    (0, 0, 0): ("A|B", "A|B"),     # Transportkonfiguration
    (0, 1, 0): ("A|B", "-"),
    (1, 0, 0): ("A|B", "B"),        # lesen mit A oder B, schreiben nur mit B
    (1, 1, 0): ("A|B", "B"),        # (+ Wertblock-Funktionen)
    (0, 0, 1): ("A|B", "-"),        # (Wertblock: nur abbuchen)
    (0, 1, 1): ("B", "B"),
    (1, 0, 1): ("B", "-"),
    (1, 1, 1): ("-", "-"),
}

# Sektor-Trailer: (Key A schreiben, Zugriffsbits lesen, Zugriffsbits schreiben, Key B lesen, Key B schreiben)
TRAILER_RULES: Dict[Tuple[int, int, int], Tuple[str, str, str, str, str]] = {
    (0, 0, 0): ("A", "A", "-", "A", "A"),
    (0, 1, 0): ("-", "A", "-", "A", "-"),
    (1, 0, 0): ("B", "A|B", "-", "-", "B"),
    (1, 1, 0): ("-", "A|B", "-", "-", "-"),
    (0, 0, 1): ("A", "A", "A", "A", "A"),    # Transportkonfiguration
    (0, 1, 1): ("B", "A|B", "B", "-", "B"),  # Schlüssel und Bits nur mit Key B änderbar
    (1, 0, 1): ("-", "A|B", "B", "-", "-"),
    (1, 1, 1): ("-", "A|B", "-", "-", "-"),
}

# Unsere Standardbelegung für den Datensektor (Kapitel 12):
#   Datenblöcke 100: lesen mit A oder B, schreiben nur mit B
#   Trailer     011: Key B nicht lesbar, Schlüssel und Bits nur mit B änderbar
HOUSE_CONDITIONS = [(1, 0, 0), (1, 0, 0), (1, 0, 0), (0, 1, 1)]


class ClassicError(Exception):
    pass


def sector_of(block: int) -> int:
    return block // 4


def trailer_of(sector: int) -> int:
    return sector * 4 + 3


def is_trailer(block: int) -> bool:
    return block % 4 == 3


def encode_access_bits(conditions: List[Tuple[int, int, int]]) -> bytes:
    """[(C1,C2,C3) für Block 0, 1, 2, Trailer] -> 3 Byte (Byte 6–8 des Trailers)."""
    if len(conditions) != 4:
        raise ValueError("vier Bedingungen: drei Datenblöcke und der Trailer")
    c1 = sum(c[0] << i for i, c in enumerate(conditions))
    c2 = sum(c[1] << i for i, c in enumerate(conditions))
    c3 = sum(c[2] << i for i, c in enumerate(conditions))
    b6 = ((~c2 & 0xF) << 4) | (~c1 & 0xF)
    b7 = (c1 << 4) | (~c3 & 0xF)
    b8 = (c3 << 4) | c2
    return bytes([b6, b7, b8])


def decode_access_bits(access: bytes) -> List[Tuple[int, int, int]]:
    """3 Byte -> Bedingungen. Wirft ClassicError, wenn normale und invertierte Bits nicht passen."""
    b6, b7, b8 = access[0], access[1], access[2]
    c1, c2, c3 = b7 >> 4, b8 & 0xF, b8 >> 4
    if (~b6 & 0xF) != c1 or ((~b6 >> 4) & 0xF) != c2 or (~b7 & 0xF) != c3:
        raise ClassicError(f"Zugriffsbits {access.hex()} sind inkonsistent – Sektor wäre gesperrt")
    return [((c1 >> i) & 1, (c2 >> i) & 1, (c3 >> i) & 1) for i in range(4)]


def make_trailer(key_a: bytes, key_b: bytes,
                 conditions: List[Tuple[int, int, int]] = HOUSE_CONDITIONS, gpb: int = 0x69) -> bytes:
    if len(key_a) != 6 or len(key_b) != 6:
        raise ValueError("Schlüssel haben 6 Byte")
    access = encode_access_bits(conditions)
    decode_access_bits(access)                  # Selbstprüfung
    return key_a + access + bytes([gpb]) + key_b


def describe_access(access: bytes) -> List[str]:
    cond = decode_access_bits(access)
    lines = []
    for i, c in enumerate(cond[:3]):
        r, w = DATA_RULES[c]
        lines.append(f"Block {i}: {c[0]}{c[1]}{c[2]}  lesen {r:<3}  schreiben {w}")
    ka_w, ac_r, ac_w, kb_r, kb_w = TRAILER_RULES[cond[3]]
    lines.append(f"Trailer: {cond[3][0]}{cond[3][1]}{cond[3][2]}  Key A schreiben {ka_w}, "
                 f"Bits lesen {ac_r}/schreiben {ac_w}, Key B lesen {kb_r}/schreiben {kb_w}")
    return lines


def allowed(rule: str, key_type: str) -> bool:
    """rule wie 'A|B', 'B' oder '-'; key_type 'A' oder 'B'."""
    return rule != "-" and key_type in rule.split("|")


def check_data_access(access: bytes, index: int, key_type: str, write: bool) -> bool:
    cond = decode_access_bits(access)[index]
    r, w = DATA_RULES[cond]
    return allowed(w if write else r, key_type)


@dataclass
class ManufacturerBlock:
    uid: bytes
    bcc_ok: bool
    sak: int
    atqa: bytes

    @staticmethod
    def parse(block0: bytes) -> "ManufacturerBlock":
        uid = block0[0:4]
        bcc = uid[0] ^ uid[1] ^ uid[2] ^ uid[3]
        return ManufacturerBlock(uid, bcc == block0[4], block0[5], block0[6:8])


def value_block(value: int, address: int) -> bytes:
    """Wertblock: Wert, invertierter Wert, Wert (je 4 Byte, little endian), Adresse 4×."""
    v = value.to_bytes(4, "little", signed=True)
    inv = bytes(b ^ 0xFF for b in v)
    a = address & 0xFF
    return v + inv + v + bytes([a, a ^ 0xFF, a, a ^ 0xFF])


# -- Operationen mit einem Leser (apdu.Acr122u oder Simulator) -----------------------------
def read_sector(reader, sector: int, key: bytes, key_type: int = 0x60) -> List[bytes]:
    first = sector * 4
    if not reader.login(first, key, key_type):
        raise ClassicError(f"Anmeldung an Sektor {sector} fehlgeschlagen (falscher Schlüssel?)")
    return [reader.read_block(first + i) for i in range(4)]


def write_trailer(reader, sector: int, current_key: bytes, current_type: int, trailer: bytes) -> None:
    """Trailer schreiben – nur mit geprüften Zugriffsbits. Danach gelten die neuen Schlüssel."""
    if len(trailer) != 16:
        raise ValueError("Trailer hat 16 Byte")
    decode_access_bits(trailer[6:9])            # wirft bei ungültigen Bits
    block = trailer_of(sector)
    if not reader.login(block, current_key, current_type):
        raise ClassicError(f"Anmeldung an Sektor {sector} fehlgeschlagen")
    reader.write_block(block, trailer)
