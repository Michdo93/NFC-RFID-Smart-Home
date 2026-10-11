"""
registry.py – das Kartenregister (Kapitel 12).

Eine JSON-Datei (Standard: data/karten.json – gitignored), die das Gateway führt:

  {"next_id": 4,
   "cards": {"1": {"name": "michael", "label": "Michaels Karte", "role": "bewohner",
                   "uid": "A1B2C3D4", "type": "classic1k", "counter": 17, "blocked": false,
                   "value": null, "readers": null, "created": "...", "last_seen": "..."}}}

Das Register ist die „Wahrheit“ über Karten: Name und Rolle, Sperre und der Zähler,
den die Karte beim nächsten Auflegen mindestens tragen muss. UIDs stehen nur hier,
nie in openHAB und nie im Repository.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Card:
    id: int
    name: str
    role: str
    uid: str
    type: str
    label: str = ""
    counter: int = 0                     # erwarteter Mindest-Zähler
    blocked: bool = False
    value: Optional[str] = None          # z. B. Sender einer Medienkarte
    readers: Optional[List[str]] = None  # nur an diesen Lesern gültig (None = überall)
    created: str = field(default_factory=now_iso)
    last_seen: Optional[str] = None
    last_reader: Optional[str] = None
    alarms: int = 0                      # Zahl der Klon-/Fälschungsverdachte


class Registry:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.next_id = 1
        self.cards: Dict[int, Card] = {}
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self._load()

    # -- Datei --------------------------------------------------------------------------
    def _load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.next_id = int(data.get("next_id", 1))
        self.cards = {int(k): Card(**v) for k, v in data.get("cards", {}).items()}

    def save(self) -> None:
        """Atomar speichern: erst in eine Hilfsdatei, dann umbenennen."""
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"next_id": self.next_id, "cards": {str(k): asdict(c) for k, c in self.cards.items()}}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".karten-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # -- Abfragen ----------------------------------------------------------------------
    def get(self, card_id: int) -> Optional[Card]:
        return self.cards.get(card_id)

    def by_name(self, name: str) -> Optional[Card]:
        return next((c for c in self.cards.values() if c.name == name), None)

    def by_uid(self, uid_hex: str) -> Optional[Card]:
        """Nur für Stufe 1 (UID-Liste) und zum Anzeigen – NICHT zur Prüfung signierter Karten."""
        return next((c for c in self.cards.values() if c.uid == uid_hex.upper()), None)

    # -- Ändern ------------------------------------------------------------------------
    def add(self, name: str, role: str, uid_hex: str, tag_type: str, label: str = "",
            value: Optional[str] = None, readers: Optional[List[str]] = None) -> Card:
        with self._lock:
            if self.by_name(name):
                raise ValueError(f"Eine Karte namens {name!r} gibt es schon")
            card = Card(self.next_id, name, role, uid_hex.upper(), tag_type, label or name,
                        value=value, readers=readers)
            self.cards[card.id] = card
            self.next_id += 1
            self.save()
            return card

    def commit_counter(self, card_id: int, new_counter: int) -> None:
        with self._lock:
            card = self.cards[card_id]
            if new_counter > card.counter:
                card.counter = new_counter
            self.save()

    def seen(self, card_id: int, reader: str) -> None:
        with self._lock:
            card = self.cards[card_id]
            card.last_seen, card.last_reader = now_iso(), reader
            self.save()

    def alarm(self, card_id: int) -> None:
        with self._lock:
            self.cards[card_id].alarms += 1
            self.save()

    def block(self, name_or_id, blocked: bool = True) -> Card:
        with self._lock:
            card = self.get(name_or_id) if isinstance(name_or_id, int) else self.by_name(name_or_id)
            if card is None:
                raise KeyError(name_or_id)
            card.blocked = blocked
            self.save()
            return card
