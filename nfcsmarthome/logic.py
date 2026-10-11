"""
logic.py – aus „aufgelegt“ und „entfernt“ werden Gesten (Kapitel 9).

  present   Karte aufgelegt (sofort – für Aktionen, die nicht warten sollen)
  hold      Karte liegt seit hold_time Sekunden (einmal je Auflegen)
  tap       Karte wurde vor Ablauf von hold_time wieder abgenommen („antippen“)
  removed   Karte abgenommen (immer, nach tap bzw. hold)

Entprellung: Manche Leser verlieren eine Karte für einen Augenblick, besonders am Rand
des Feldes. Ein „entfernt“ gilt erst, wenn die Karte absent_time Sekunden fehlt; kommt
dieselbe Karte vorher zurück, ist nichts geschehen.

Jede Geste trägt die Prüfentscheidung (verify.Decision) des Auflegens mit sich. Als
Text heißt eine Geste <wer>:<art>, z. B. „gute_nacht:present“ oder „unknown:present“.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .events import ReaderEvent
from .verify import Decision


@dataclass
class Gesture:
    reader: str
    who: str                    # Kartenname oder Status (unknown, invalid, clone ...)
    kind: str                   # present | hold | tap | removed
    decision: Optional[Decision] = None
    t: float = 0.0
    duration: float = 0.0       # bei tap/removed: wie lange die Karte lag

    def __str__(self) -> str:
        return f"{self.who}:{self.kind}"


@dataclass
class _Slot:
    uid: bytes
    decision: Decision
    since: float
    hold_sent: bool = False
    removed_at: Optional[float] = None


class TagLogic:
    def __init__(self, hold_time: float = 1.5, absent_time: float = 0.6):
        self.hold_time = hold_time
        self.absent_time = absent_time
        self.slots: Dict[str, _Slot] = {}          # je Leser höchstens eine Karte

    @classmethod
    def from_config(cls, cfg: dict) -> "TagLogic":
        return cls(float(cfg.get("hold_time", 1.5)), float(cfg.get("absent_time", 0.6)))

    def feed(self, ev: ReaderEvent, decision: Optional[Decision] = None) -> List[Gesture]:
        out: List[Gesture] = []
        slot = self.slots.get(ev.reader)
        if ev.kind == "present" and ev.read is not None:
            if slot and slot.uid == ev.read.uid and slot.removed_at is not None:
                slot.removed_at = None              # nur kurz weg gewesen – entprellt
                return out
            if slot:                                 # andere Karte: alte sofort abschließen
                out += self._finish(ev.reader, slot, ev.t)
            d = decision or Decision("unknown", ev.reader, ev.read.uid_hex, "uid")
            self.slots[ev.reader] = _Slot(ev.read.uid, d, ev.t)
            out.append(Gesture(ev.reader, d.who, "present", d, ev.t))
        elif ev.kind == "removed" and slot and slot.removed_at is None:
            slot.removed_at = ev.t
        return out

    def tick(self, now: float) -> List[Gesture]:
        out: List[Gesture] = []
        for reader, slot in list(self.slots.items()):
            if slot.removed_at is not None:
                if now - slot.removed_at >= self.absent_time:
                    out += self._finish(reader, slot, slot.removed_at)
            elif not slot.hold_sent and now - slot.since >= self.hold_time:
                slot.hold_sent = True
                out.append(Gesture(reader, slot.decision.who, "hold", slot.decision, now,
                                   now - slot.since))
        return out

    def _finish(self, reader: str, slot: _Slot, t: float) -> List[Gesture]:
        self.slots.pop(reader, None)
        dur = t - slot.since
        out = []
        if not slot.hold_sent:
            out.append(Gesture(reader, slot.decision.who, "tap", slot.decision, t, dur))
        out.append(Gesture(reader, slot.decision.who, "removed", slot.decision, t, dur))
        return out

    def present(self, reader: str) -> Optional[Decision]:
        """Welche Karte liegt gerade (für Präsenz-Items)? None = keine."""
        slot = self.slots.get(reader)
        return slot.decision if slot and slot.removed_at is None else None
