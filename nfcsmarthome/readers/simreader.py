"""
simreader.py – Leser-Szenarien mit virtuellen Karten (Kapitel 9).

Ein Szenario (YAML) beschreibt, wann welche Karte auf welchen Leser gelegt wird:

  leser: nachttisch                 # Standard-Leser
  schritte:
    - {nach: 0.5, karte: s50_karte_1}               # auflegen
    - {nach: 2.0, entfernen: true}                  # abnehmen (nach 2 s)
    - {nach: 0.5, karte: ntag215_karte_1, leser: flur}

Jeder Leser ist ein eigener simulierter ACR122U. Schreibt das Gateway (rollierender
Zähler), landet das in der virtuellen Karte unter data/sim/ – genau wie bei einer
echten Karte, die man danach wieder in die Hand nimmt.

open_single() liefert für Einzelskripte (Kapitel 6–8) einen Acr122u – mit Simulator
(--sim KARTE) oder echtem Leser.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import AsyncIterator, Callable, Dict, List, Optional, Tuple

import yaml

from .. import apdu as ap
from ..events import ReaderEvent, TagRead
from ..feedback import signal_apdu
from ..keys import KeyRing
from .base import Reader
from .common import read_tag, write_payload
from .sim import SimulatedAcr122u, load_card, save_card


class SimReader(Reader):
    can_write = True

    def __init__(self, steps: List[dict], default_reader: str = "labor",
                 keyring: Optional[KeyRing] = None, speed: float = 1.0, persist: bool = True):
        self.steps = steps
        self.default_reader = default_reader
        self.keyring = keyring
        self.speed = speed
        self.persist = persist
        self.sims: Dict[str, SimulatedAcr122u] = {}
        self.names: Dict[str, str] = {}             # Leser -> Name der virtuellen Karte
        self.signals: List[Tuple[str, str]] = []    # (Leser, Signal) – für Ausgabe und Tests
        self.writes: List[Tuple[str, bool]] = []

    @classmethod
    def from_file(cls, path, keyring: Optional[KeyRing] = None, speed: float = 1.0) -> "SimReader":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls(list(data.get("schritte", [])), str(data.get("leser", "labor")), keyring, speed)

    def _sim(self, reader: str) -> SimulatedAcr122u:
        if reader not in self.sims:
            self.sims[reader] = SimulatedAcr122u()
        return self.sims[reader]

    async def events(self) -> AsyncIterator[ReaderEvent]:
        for step in self.steps:
            await asyncio.sleep(float(step.get("nach", 0.0)) / self.speed)
            reader = str(step.get("leser", self.default_reader))
            sim = self._sim(reader)
            if step.get("entfernen"):
                if sim.card is not None:
                    self._save(reader)
                    sim.remove()
                    yield ReaderEvent("removed", reader, t=time.monotonic())
                continue
            name = str(step["karte"])
            if sim.card is not None:                         # liegt noch eine: erst weg
                self._save(reader)
                sim.remove()
                yield ReaderEvent("removed", reader, t=time.monotonic())
            card = load_card(name)
            sim.place(card)
            self.names[reader] = name
            read = read_tag(ap.Acr122u(sim), reader, card.atr, self.keyring)
            yield ReaderEvent("present", reader, read, time.monotonic())
        await asyncio.sleep(0.5 / self.speed)                # Ende: kurz liegen lassen, dann abnehmen
        for reader, sim in self.sims.items():
            if sim.card is not None:
                self._save(reader)
                sim.remove()
                yield ReaderEvent("removed", reader, t=time.monotonic())

    def _save(self, reader: str) -> None:
        sim = self.sims.get(reader)
        if self.persist and sim and sim.card is not None and reader in self.names:
            save_card(self.names[reader], sim.card)

    async def write(self, read: TagRead, payload: bytes) -> bool:
        sim = self.sims.get(read.reader)
        if sim is None or sim.card is None or self.keyring is None:
            return False
        ok = write_payload(ap.Acr122u(sim), read, self.keyring, payload)
        self.writes.append((read.reader, ok))
        self._save(read.reader)
        return ok

    async def with_card(self, reader: str, fn):
        sim = self.sims.get(reader)
        if sim is None or sim.card is None:
            raise RuntimeError("keine Karte aufgelegt")
        result = fn(ap.Acr122u(sim), sim.card.atr)
        self._save(reader)
        return result

    async def signal(self, reader: str, name: str) -> None:
        sim = self._sim(reader)
        sim.transmit(signal_apdu(name))
        self.signals.append((reader, name))


# -- Einzelskripte -------------------------------------------------------------------------
class Single:
    """Eine aufgelegte Karte für Einzelskripte: acr, atr und save() (nur beim Simulator)."""

    def __init__(self, acr: ap.Acr122u, atr: bytes, save: Callable[[], None], sim=None):
        self.acr, self.atr, self.save, self.sim = acr, atr, save, sim


def open_single(sim_card: Optional[str] = None, match: str = "ACR122") -> Single:
    if sim_card:
        card = load_card(sim_card)
        sim = SimulatedAcr122u()
        sim.place(card)
        return Single(ap.Acr122u(sim), card.atr, lambda: save_card(sim_card, card), sim)
    from .pcsc import connect_first
    acr, atr = connect_first(match)
    return Single(acr, atr, lambda: None)
