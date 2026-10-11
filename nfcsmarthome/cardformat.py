"""
cardformat.py – das hauseigene Kartenformat „NFH“ (NFC For Home, Kapitel 12).

32 Byte – genau zwei Blöcke einer MIFARE-Classic-Karte oder die Nutzdaten eines
NDEF-Records vom Typ „home.arpa:nfh“ auf einem NTAG:

  Byte  0–2   Magie „NFH“
  Byte  3     Formatversion (1)
  Byte  4–7   Installations-ID (aus dem Geheimnis abgeleitet, öffentlich)
  Byte  8–11  Karten-ID (Nummer im Kartenregister)
  Byte 12     Rolle (1 Bewohner, 2 Gast, 3 Szene, 4 Medien, 5 Admin)
  Byte 13     Flags (Bit 0: rollierender Zähler aktiv)
  Byte 14–17  Zähler
  Byte 18–31  MAC: HMAC-SHA256 über Byte 0–17 und die UID, auf 14 Byte gekürzt

Die UID steht nicht im Format, geht aber in den MAC ein: Wer die 32 Byte auf eine
andere Karte kopiert, erzeugt eine ungültige Karte. Wer ohne den MAC-Schlüssel
Rolle, Karten-ID oder Zähler ändert, ebenso.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass, replace
from typing import Optional

MAGIC = b"NFH"
VERSION = 1
SIZE = 32
MAC_LEN = 14
NDEF_TYPE = "home.arpa:nfh"      # home.arpa: für Heimnetze reservierte Domain (RFC 8375)

FLAG_ROLLING = 0x01

ROLES = {1: "bewohner", 2: "gast", 3: "szene", 4: "medien", 5: "admin"}
ROLE_CODES = {v: k for k, v in ROLES.items()}

_HEAD = struct.Struct(">3sB4sIBBI")             # 18 Byte


class FormatError(Exception):
    pass


@dataclass(frozen=True)
class CardData:
    installation: bytes
    card_id: int
    role: str
    counter: int = 0
    rolling: bool = True
    version: int = VERSION

    def head(self) -> bytes:
        code = ROLE_CODES.get(self.role)
        if code is None:
            raise FormatError(f"unbekannte Rolle {self.role!r}")
        flags = FLAG_ROLLING if self.rolling else 0
        return _HEAD.pack(MAGIC, self.version, self.installation, self.card_id, code, flags,
                          self.counter)

    def next(self) -> "CardData":
        return replace(self, counter=self.counter + 1)


def mac(mac_key: bytes, head: bytes, uid: bytes) -> bytes:
    return hmac.new(mac_key, head + uid, hashlib.sha256).digest()[:MAC_LEN]


def encode(card: CardData, uid: bytes, mac_key: bytes) -> bytes:
    head = card.head()
    return head + mac(mac_key, head, uid)


def parse(raw: bytes) -> Optional[CardData]:
    """Kopf lesen OHNE Prüfung. None, wenn es nicht nach NFH aussieht."""
    if len(raw) < SIZE or raw[:3] != MAGIC:
        return None
    magic, version, inst, card_id, code, flags, counter = _HEAD.unpack(raw[:18])
    if version != VERSION:
        raise FormatError(f"Formatversion {version} wird nicht unterstützt")
    return CardData(inst, card_id, ROLES.get(code, f"rolle{code}"), counter,
                    bool(flags & FLAG_ROLLING), version)


def verify_mac(raw: bytes, uid: bytes, mac_key: bytes) -> bool:
    if len(raw) < SIZE:
        return False
    expected = mac(mac_key, raw[:18], uid)
    return hmac.compare_digest(expected, raw[18:SIZE])
