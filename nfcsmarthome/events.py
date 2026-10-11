"""
events.py – was ein Leser meldet (Kapitel 9).

TagRead      eine gelesene Karte: Leser, UID, Typ, NFH-Nutzdaten, NDEF-Records
ReaderEvent  „aufgelegt“ (present, mit TagRead) oder „entfernt“ (removed)

Alle Leser – ACR122U, Simulator, Aufzeichnung, ESP32 über MQTT – liefern dieselben
Ereignisse. Alles Weitere (Prüfung, Gesten, openHAB) hängt nicht vom Leser ab.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import hexs, unhex
from .ndef import Record, decode_message, encode_message


@dataclass
class TagRead:
    reader: str
    uid: bytes
    tag_type: str = "unbekannt"          # classic1k, ntag213, ntag215, ntag216, ultralight ...
    payload: Optional[bytes] = None      # 32 Byte im NFH-Format, falls vorhanden
    records: List[Record] = field(default_factory=list)
    t: float = field(default_factory=time.monotonic)

    @property
    def uid_hex(self) -> str:
        return hexs(self.uid)

    def to_json(self) -> str:
        d = {"uid": self.uid_hex, "type": self.tag_type}
        if self.payload is not None:
            d["data"] = hexs(self.payload)
        if self.records:
            d["ndef"] = hexs(encode_message(self.records))
        return json.dumps(d)

    @staticmethod
    def from_json(reader: str, text: str, t: Optional[float] = None) -> "TagRead":
        d = json.loads(text)
        payload = unhex(d["data"]) if d.get("data") else None
        records = decode_message(unhex(d["ndef"])) if d.get("ndef") else []
        return TagRead(reader, unhex(d["uid"]), d.get("type", "unbekannt"), payload, records,
                       time.monotonic() if t is None else t)


@dataclass
class ReaderEvent:
    kind: str                            # present | removed
    reader: str
    read: Optional[TagRead] = None
    t: float = field(default_factory=time.monotonic)

    def __str__(self) -> str:
        if self.kind == "present" and self.read:
            return f"{self.reader:<10} aufgelegt  {self.read.tag_type:<10} UID {self.read.uid_hex}"
        return f"{self.reader:<10} entfernt"
