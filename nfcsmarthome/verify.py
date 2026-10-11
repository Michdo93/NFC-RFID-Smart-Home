"""
verify.py – ist diese Karte eine von uns, und darf sie hier etwas auslösen? (Kapitel 11–13)

Stufen (security.level in der config.yaml, je Leser überschreibbar):

  uid       Stufe 1: nur die UID muss im Register stehen. Einfach – und leicht zu klonen.
  signed    Stufe 3: NFH-Nutzdaten mit gültigem MAC, Karte im Register, nicht gesperrt.
  rolling   Stufe 4: wie signed, zusätzlich schreibt der Leser nach jedem Auflegen einen
            neuen Zähler. Eine Kopie mit altem Zähler fällt auf (Status „clone“).

Ergebnis (Decision.status):

  accepted     angenommen
  unknown      keine Karte von uns (oder nicht im Register)
  foreign      NFH-Karte einer ANDEREN Installation
  invalid      Nutzdaten manipuliert oder auf eine andere Karte kopiert (MAC falsch)
  blocked      gesperrt (verloren, abgegeben)
  clone        Zähler kleiner als erwartet – Kopie einer älteren Fassung der Karte
  not_allowed  gültige Karte, aber an diesem Leser nicht zugelassen
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import cardformat
from .cardformat import CardData, FormatError
from .events import TagRead
from .keys import KeyRing
from .ndef import TNF_EXTERNAL, Record
from .registry import Card, Registry

log = logging.getLogger("nfcverify")

LEVELS = ("uid", "signed", "rolling")


@dataclass
class Decision:
    status: str
    reader: str
    uid_hex: str
    level: str
    card: Optional[Card] = None
    data: Optional[CardData] = None
    next_payload: Optional[bytes] = None     # bei „rolling“: das, was der Leser schreiben soll
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "accepted"

    @property
    def who(self) -> str:
        """Name für Gesten: Kartenname, sonst der Status (unknown, invalid ...)."""
        return self.card.name if (self.ok and self.card) else self.status

    def summary(self) -> str:
        name = self.card.name if self.card else "-"
        extra = f"  Zähler {self.data.counter}" if self.data else ""
        return f"{self.reader:<10} {self.status:<11} {name:<12} [{self.level}]{extra}  {self.message}".rstrip()


def nfh_payload(read: TagRead) -> Optional[bytes]:
    """NFH-Nutzdaten aus einem TagRead holen – direkt (Classic) oder aus dem NDEF-Record (NTAG)."""
    if read.payload is not None:
        return read.payload
    for r in read.records:
        if r.tnf == TNF_EXTERNAL and r.type_name == cardformat.NDEF_TYPE:
            return r.payload
    return None


def replace_nfh(records: List[Record], payload: bytes) -> List[Record]:
    """NDEF-Records mit neuem NFH-Record (andere Records bleiben erhalten)."""
    out, done = [], False
    for r in records:
        if r.tnf == TNF_EXTERNAL and r.type_name == cardformat.NDEF_TYPE:
            out.append(Record.external(cardformat.NDEF_TYPE, payload))
            done = True
        else:
            out.append(r)
    if not done:
        out.append(Record.external(cardformat.NDEF_TYPE, payload))
    return out


class Verifier:
    def __init__(self, keyring: Optional[KeyRing], registry: Registry,
                 level: str = "signed", readers: Optional[Dict[str, Dict[str, Any]]] = None):
        if level not in LEVELS:
            raise ValueError(f"Stufe {level!r} unbekannt – erlaubt: {', '.join(LEVELS)}")
        if level != "uid" and keyring is None:
            raise ValueError(f"Stufe {level!r} braucht das Installationsgeheimnis")
        self.keyring = keyring
        self.registry = registry
        self.level = level
        self.readers = readers or {}
        self._inst = keyring.installation_id() if keyring else None
        self._mac_key = keyring.mac_key() if keyring else None

    def level_for(self, reader: str) -> str:
        return str(self.readers.get(reader, {}).get("level", self.level))

    def _allowed_here(self, card: Card, reader: str) -> bool:
        if card.readers and reader not in card.readers:
            return False
        roles = self.readers.get(reader, {}).get("roles")
        return not roles or card.role in roles

    def verify(self, read: TagRead) -> Decision:
        level = self.level_for(read.reader)
        d = Decision("unknown", read.reader, read.uid_hex, level)
        raw = nfh_payload(read)

        # Stufe 1: nur die UID ------------------------------------------------------------
        if level == "uid":
            card = self.registry.by_uid(read.uid_hex)
            if card is None:
                d.message = "UID nicht im Register"
                return d
            return self._finish(d, card, None, read)

        # Stufe 3/4: Kartenformat prüfen -------------------------------------------------------
        if raw is None:
            d.message = "keine NFH-Daten"
            return d
        try:
            data = cardformat.parse(raw)
        except FormatError as exc:
            d.status, d.message = "invalid", str(exc)
            return d
        if data is None:
            d.message = "keine NFH-Daten"
            return d
        d.data = data
        if data.installation != self._inst:
            d.status, d.message = "foreign", "Karte einer anderen Installation"
            return d
        if not cardformat.verify_mac(raw, read.uid, self._mac_key):
            d.status, d.message = "invalid", "MAC falsch – manipuliert oder kopiert"
            return d
        card = self.registry.get(data.card_id)
        if card is None:
            d.message = f"Karten-ID {data.card_id} nicht im Register"
            return d
        if card.uid != read.uid_hex:
            d.status, d.message = "invalid", "UID passt nicht zum Register"
            d.card = card
            return d
        if data.rolling and data.counter < card.counter:
            d.status, d.card = "clone", card
            d.message = f"Zähler {data.counter} < erwartet {card.counter} – Klonverdacht"
            self.registry.alarm(card.id)
            log.warning("Klonverdacht: Karte %s an %s (Zähler %d, erwartet %d)",
                        card.name, read.reader, data.counter, card.counter)
            return d
        return self._finish(d, card, data, read)

    def _finish(self, d: Decision, card: Card, data: Optional[CardData], read: TagRead) -> Decision:
        d.card = card
        if card.blocked:
            d.status, d.message = "blocked", "Karte gesperrt"
            return d
        if not self._allowed_here(card, read.reader):
            d.status, d.message = "not_allowed", "an diesem Leser nicht zugelassen"
            return d
        d.status = "accepted"
        if data is not None:
            if data.counter > card.counter:                  # Register nachziehen
                self.registry.commit_counter(card.id, data.counter)
            if d.level == "rolling" and data.rolling:          # Zähler + 1 vorbereiten
                d.next_payload = cardformat.encode(data.next(), read.uid, self._mac_key)
        self.registry.seen(card.id, read.reader)
        return d

    def commit(self, d: Decision) -> None:
        """Nach ERFOLGREICHEM Schreiben von d.next_payload: Register auf den neuen Zähler setzen."""
        if d.card and d.next_payload:
            new = cardformat.parse(d.next_payload)
            self.registry.commit_counter(d.card.id, new.counter)
