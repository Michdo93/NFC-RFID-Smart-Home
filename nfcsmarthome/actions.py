"""
actions.py – Kartenprofile für Ansatz B (Kapitel 26, 30, 31).

Ein Profil (YAML) ordnet Gesten Aktionen zu. Eine Geste heißt <wer>:<art>:

  michael:present     die Karte „michael“ wurde aufgelegt
  #medien:removed     irgendeine Karte mit Rolle „medien“ wurde abgenommen
  *:hold              irgendeine angenommene Karte liegt seit hold_time

  name: Labor
  readers:                      # Variablen je Leser – z. B. der Raum
    nachttisch: {raum: iSmartHome}
    kueche:     {raum: iKueche}
  actions:                      # gilt an allen Lesern
    "gute_nacht:present":
      - {command: gLichter, value: "OFF"}
      - {command: gRollladen, value: DOWN}
    "#medien:present": {command: "{raum}_Webradio_{wert}", value: "ON"}
    "#medien:removed": {command: "{raum}_Webradio_{wert}", value: "OFF"}
  reader_actions:               # nur an einem Leser – hat Vorrang
    nachttisch:
      "#bewohner:tap": {toggle: "{raum}_Hue_Lampen_Schalter"}

ALLE passenden Einträge werden ausgeführt – vom speziellsten zum allgemeinsten:
Leser+Karte, Leser+Rolle, Leser+„*“, Karte, Rolle, „*“. So kann „*:present“ an einem
Leser z. B. immer ein Präsenz-Item setzen, während „gute_nacht:present“ die Szene startet.
„*“ passt nur auf angenommene Karten; für andere heißt <wer> wie der Status (unknown ...).

Platzhalter: {leser} {karte} {label} {rolle} {wert} und alle Variablen des Lesers.

Rückkanal (Kapitel 27): Zustände in openHAB -> Signale an Lesern

  watch:
    iSmartHome_Alarm: {"ON": {leser: "*", signal: alarm}}
    iSmartHome_Alarmanlage_Scharf:
      "ON":  {leser: flur, signal: deny}
      "OFF": {leser: flur, signal: ok}

Aktionen:
  {command: Item, value: Wert}   Befehl senden
  {toggle: Item}                 Zustand lesen, Gegenteil senden
  {update: Item, value: Wert}    Zustand setzen (postUpdate), z. B. „Karte liegt“
  {increment: Item}              Zahl lesen, um 1 erhöht als Zustand setzen (Zähler)
  {feedback: signal, value: ok}  LED/Summer am Leser
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import load_yaml
from .logic import Gesture


@dataclass(frozen=True)
class Op:
    kind: str            # command | toggle | update | increment | feedback
    item: str            # bei feedback: der Leser
    value: str = ""

    def __str__(self) -> str:
        return f"{self.kind} {self.item} {self.value}".strip()


class _Vars(dict):
    def __missing__(self, key):
        return "{" + key + "}"            # unbekannte Platzhalter stehen lassen (fällt in check auf)


class CardProfile:
    def __init__(self, data: Dict[str, Any], path: str = ""):
        self.path = path
        self.name = str(data.get("name", path or "Profil"))
        self.readers: Dict[str, Dict[str, Any]] = data.get("readers") or {}
        self.actions: Dict[str, Any] = data.get("actions") or {}
        self.reader_actions: Dict[str, Dict[str, Any]] = data.get("reader_actions") or {}
        self.watch: Dict[str, Dict[str, Any]] = data.get("watch") or {}

    @classmethod
    def load(cls, path) -> "CardProfile":
        return cls(load_yaml(path), str(path))

    # -- Suche ---------------------------------------------------------------------------
    def lookup(self, g: Gesture) -> List[Any]:
        """Alle passenden Einträge, vom speziellsten zum allgemeinsten."""
        d = g.decision
        accepted = d is not None and d.ok
        role = d.card.role if (accepted and d.card) else None
        found = []
        ra = self.reader_actions.get(g.reader, {})
        for table in (ra, self.actions):
            keys = [f"{g.who}:{g.kind}"]
            if role:
                keys.append(f"#{role}:{g.kind}")
            if accepted:
                keys.append(f"*:{g.kind}")
            found += [table[k] for k in keys if k in table]
        return found

    def variables(self, g: Gesture) -> _Vars:
        v = _Vars(self.readers.get(g.reader, {}))
        v["leser"] = g.reader
        card = g.decision.card if (g.decision and g.decision.ok) else None
        v["karte"] = card.name if card else g.who
        v["label"] = card.label if card else g.who
        v["rolle"] = card.role if card else ""
        v["wert"] = (card.value or "") if card else ""
        return v

    def signals_for(self, item: str, state: str) -> List[Tuple[str, str]]:
        """Rückkanal: (Leser, Signal) für einen neuen Zustand eines beobachteten Items."""
        spec = (self.watch.get(item) or {}).get(str(state))
        if spec is None:
            return []
        return [(str(s.get("leser", "*")), str(s.get("signal", "ok")))
                for s in (spec if isinstance(spec, list) else [spec])]

    # -- Aktionen ausführen -----------------------------------------------------------------
    def handle(self, g: Gesture) -> List[Op]:
        v = self.variables(g)
        ops: List[Op] = []
        for spec in self.lookup(g):
            for s in (spec if isinstance(spec, list) else [spec]):
                ops += self._run(s, v, g.reader)
        return ops

    @staticmethod
    def _fill(text: Any, v: _Vars) -> str:
        return str(text).format_map(v)

    def _run(self, s: Dict[str, Any], v: _Vars, reader: str) -> List[Op]:
        if "command" in s:
            return [Op("command", self._fill(s["command"], v), self._fill(s.get("value", ""), v))]
        if "toggle" in s:
            return [Op("toggle", self._fill(s["toggle"], v))]
        if "increment" in s:
            return [Op("increment", self._fill(s["increment"], v))]
        if "update" in s:
            return [Op("update", self._fill(s["update"], v), self._fill(s.get("value", ""), v))]
        if "feedback" in s:
            return [Op("feedback", reader, self._fill(s.get("value", "ok"), v))]
        raise ValueError(f"Unbekannte Aktion {s}")
