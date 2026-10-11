"""
check.py – Kartenprofile gegen Items prüfen (Kapitel 30).

Für jeden Eintrag eines Profils werden alle Leser und – bei Rollen-Einträgen – alle
Karten dieser Rolle aus dem Register eingesetzt. Jedes Ziel-Item muss existieren und
den Befehl annehmen; offene Platzhalter wie {wert} fallen als Fehler auf.
"""

from __future__ import annotations

import re
from typing import Dict, Iterator, List, Optional, Tuple

from .actions import CardProfile
from .feedback import SIGNALS
from .logic import Gesture
from .registry import Card
from .verify import Decision

PERCENT = lambda v: bool(re.fullmatch(r"\d{1,3}", v)) and 0 <= int(v) <= 100   # noqa: E731

ACCEPTS = {
    "Switch":        lambda v: v in ("ON", "OFF"),
    "Dimmer":        lambda v: v in ("ON", "OFF", "INCREASE", "DECREASE") or PERCENT(v),
    "Color":         lambda v: v in ("ON", "OFF", "INCREASE", "DECREASE") or PERCENT(v)
                     or bool(re.fullmatch(r"\d{1,3},\d{1,3},\d{1,3}", v)),
    "Rollershutter": lambda v: v in ("UP", "DOWN", "STOP", "MOVE") or PERCENT(v),
    "Player":        lambda v: v in ("PLAY", "PAUSE", "NEXT", "PREVIOUS", "REWIND", "FASTFORWARD"),
    "Number":        lambda v: bool(re.fullmatch(r"-?\d+(\.\d+)?", v)),
    "Contact":       lambda v: v in ("OPEN", "CLOSED"),   # nur per update, nicht per Befehl
    "String":        lambda v: True,
    "DateTime":      lambda v: True,
}


def _fake_gesture(reader: str, key: str, card: Optional[Card]) -> Gesture:
    who, kind = key.rsplit(":", 1)
    d = Decision("accepted" if card else who, reader, "", "signed", card)
    return Gesture(reader, card.name if card else who, kind, d)


def targets(profile: CardProfile, cards: List[Card]) -> Iterator[Tuple[str, str, str, str]]:
    """(Item, Wert, Art, Herkunft) für alle Kombinationen aus Leser und Karte."""
    readers = sorted(set(profile.readers) | set(profile.reader_actions)) or ["leser"]
    tables = [(None, profile.actions)] + [(r, t) for r, t in profile.reader_actions.items()]
    for scope, table in tables:
        for key, spec in table.items():
            who = key.rsplit(":", 1)[0]
            if who.startswith("#"):
                matching = [c for c in cards if c.role == who[1:]] or [None]
            elif who == "*":
                matching = cards or [None]
            else:
                matching = [c for c in cards if c.name == who] or [None]
            for reader in ([scope] if scope else readers):
                for card in matching:
                    g = _fake_gesture(reader, key, card)
                    specs = spec if isinstance(spec, list) else [spec]
                    v = profile.variables(g)
                    for s in specs:
                        for op in profile._run(s, v, reader):
                            if op.kind != "feedback":
                                yield op.item, op.value, op.kind, f"{reader}/{key}"


def check_profile(profile: CardProfile, items: Dict[str, dict], cards: List[Card]) -> Tuple[List[str], int]:
    errors, seen = [], set()
    count = 0
    for item, value, kind, origin in targets(profile, cards):
        count += 1
        if (item, value, kind) in seen:
            continue
        seen.add((item, value, kind))
        if "{" in item or "{" in value:
            errors.append(f"{item}={value}: Platzhalter nicht aufgelöst ({origin})")
            continue
        if item not in items:
            errors.append(f"{item}: Item existiert nicht ({origin})")
            continue
        typ = items[item]["type"].split(":")[0]
        if typ == "Group":
            typ = (items[item].get("groupType") or "String").split(":")[0]
        if kind == "toggle":
            value = "ON"
        if kind == "increment":
            value = "1"
        check = ACCEPTS.get(typ)
        if kind == "command" and typ == "Contact":
            errors.append(f"{item}: Contact nimmt keine Befehle an ({origin})")
        elif check and not check(value):
            errors.append(f"{item}: {typ} nimmt '{value}' nicht an ({origin})")
    # Rückkanal (Kapitel 27): beobachtete Items, Leser und Signale
    readers = set(profile.readers) | set(profile.reader_actions)
    for item, states in profile.watch.items():
        count += 1
        if item not in items:
            errors.append(f"{item}: Item existiert nicht (watch)")
        for state in states or {}:
            for reader, signal in profile.signals_for(item, state):
                if signal not in SIGNALS:
                    errors.append(f"{item}={state}: Signal {signal!r} unbekannt (watch)")
                if reader != "*" and readers and reader not in readers:
                    errors.append(f"{item}={state}: Leser {reader!r} nicht im Profil (watch)")
    return errors, count
