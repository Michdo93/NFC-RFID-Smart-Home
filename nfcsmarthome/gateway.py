"""
gateway.py – das NFC-Gateway (Kapitel 21, 23, 24).

Für jedes Auflegen:
  1. prüfen           Verifier: angenommen, unbekannt, gefälscht, Klon ...
  2. melden           Gesten und Status an MQTT (bzw. jede andere „Senke“)
  3. Zähler schreiben bei Stufe „rolling“: neuer Zähler auf die Karte; erst nach
                      erfolgreichem Zurücklesen gilt er im Register (commit)
  4. Rückmeldung      LED/Summer am Leser

Dazu: tick() für hold/tap/removed, Anlernmodus (nächste unbekannte Karte an einem
lokalen Leser wird angelernt) und Sperren/Entsperren per Befehl aus openHAB.
"""

from __future__ import annotations

import asyncio
import json
import re
import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from . import personalize
from .events import ReaderEvent
from .feedback import STATUS_SIGNAL
from .keys import KeyRing
from .logic import Gesture, TagLogic
from .mqtt import GatewayEncoder, Message
from .readers.base import Reader
from .cardformat import ROLE_CODES
from .verify import Decision, Verifier, nfh_payload

log = logging.getLogger("nfcgateway")


@dataclass
class LearnRequest:
    name: str
    role: str
    reader: Optional[str] = None
    label: str = ""
    value: Optional[str] = None
    uri: Optional[str] = None
    expires: float = 0.0


class PrintSink:
    """Nachrichten nur ausgeben (--dry-run)."""

    def __init__(self, out=print):
        self.out = out
        self.sent: List[Message] = []

    def send(self, messages: List[Message]) -> None:
        for topic, payload, retain in messages:
            self.sent.append((topic, payload, retain))
            self.out(f"{topic:<26} {payload}{'   (retained)' if retain else ''}")


class NfcGateway:
    def __init__(self, verifier: Verifier, logic: TagLogic, readers: Reader, sink,
                 encoder: Optional[GatewayEncoder] = None, keyring: Optional[KeyRing] = None,
                 signals: bool = True, on_gesture: Optional[Callable[[Gesture], None]] = None):
        self.verifier = verifier
        self.logic = logic
        self.readers = readers
        self.sink = sink
        self.encoder = encoder or GatewayEncoder()
        self.keyring = keyring
        self.signals = signals
        self.on_gesture = on_gesture
        self.learn: Optional[LearnRequest] = None
        self.decisions: List[Decision] = []             # Protokoll (Ausgabe und Tests)
        self._pending: Dict[str, asyncio.Task] = {}     # laufende Schreibvorgänge je Leser

    # -- Ereignisse ------------------------------------------------------------------------
    async def handle(self, ev: ReaderEvent) -> None:
        if ev.kind != "present" or ev.read is None:
            self._publish(self.logic.feed(ev))
            return
        pending = self._pending.get(ev.reader)
        if pending is not None:                         # derselbe Leser schreibt noch
            await pending
        if self.learn and await self._try_learn(ev):
            return
        d = self.verifier.verify(ev.read)
        self.decisions.append(d)
        log.info("%s", d.summary())
        self._publish(self.logic.feed(ev, d))           # sofort melden – nicht auf das Schreiben warten
        # Schreiben und Signal im Hintergrund: Ein langsamer Leser hält die anderen nicht auf.
        task = asyncio.create_task(self._write_and_signal(ev, d))
        self._pending[ev.reader] = task
        task.add_done_callback(lambda t, r=ev.reader: self._pending.get(r) is t and self._pending.pop(r))

    async def _write_and_signal(self, ev: ReaderEvent, d: Decision) -> None:
        if d.next_payload is not None:
            if await self.readers.write(ev.read, d.next_payload):
                self.verifier.commit(d)
                log.info("%-10s Zähler -> %d geschrieben", ev.reader, d.data.counter + 1)
            else:
                log.warning("%-10s Zähler NICHT geschrieben (Karte zu früh weg oder Leser kann nicht schreiben)",
                            ev.reader)
        if self.signals:
            await self.readers.signal(ev.reader, STATUS_SIGNAL.get(d.status, "deny"))

    async def drain(self) -> None:
        """Auf alle laufenden Schreibvorgänge warten."""
        while self._pending:
            await asyncio.gather(*list(self._pending.values()), return_exceptions=True)

    def tick(self, now: Optional[float] = None) -> None:
        self._publish(self.logic.tick(time.monotonic() if now is None else now))
        if self.learn and self.learn.expires and time.monotonic() > self.learn.expires:
            log.info("Anlernmodus abgelaufen")
            self.learn = None

    def _publish(self, gestures: List[Gesture]) -> None:
        for g in gestures:
            if self.on_gesture:
                self.on_gesture(g)
            msgs = self.encoder.gesture(g)
            if msgs:
                self.sink.send(msgs)

    # -- Anlernen ---------------------------------------------------------------------------
    def start_learning(self, req: LearnRequest, seconds: float = 60.0) -> None:
        req.expires = time.monotonic() + seconds
        self.learn = req
        log.info("Anlernmodus: nächste neue Karte%s wird %r (%s)",
                 f" am Leser {req.reader}" if req.reader else "", req.name, req.role)

    async def _try_learn(self, ev: ReaderEvent) -> bool:
        req = self.learn
        if req.reader and req.reader != ev.reader:
            return False
        if nfh_payload(ev.read) is not None or self.verifier.registry.by_uid(ev.read.uid_hex):
            return False                                 # schon eine Karte von uns: normal prüfen
        if self.keyring is None:
            log.warning("Anlernen braucht das Installationsgeheimnis")
            return False

        def work(acr, atr):
            return personalize.personalize(acr, atr, self.keyring, self.verifier.registry,
                                           req.name, req.role, req.label, req.value, req.uri)

        try:
            card = await self.readers.with_card(ev.reader, work)
        except Exception as exc:
            log.warning("Anlernen fehlgeschlagen: %s", exc)
            if self.signals:
                await self.readers.signal(ev.reader, "deny")
            return True
        self.learn = None
        log.info("Angelernt: %s (%s) an %s", card.name, card.role, ev.reader)
        self.sink.send([(self.encoder.t.reader(ev.reader, "last"),
                         json.dumps({"name": card.name, "label": card.label, "role": card.role,
                                     "status": "learned"}), True)])
        if self.signals:
            await self.readers.signal(ev.reader, "ok")
        return True

    # -- Befehle aus openHAB ---------------------------------------------------------------
    def command(self, topic: str, payload: str) -> None:
        """nfc/gateway/learn | block | unblock – JSON bzw. Kartenname."""
        what = topic.rsplit("/", 1)[-1]
        if what == "learn":
            try:
                d = json.loads(payload)
                if not re.fullmatch(r"[a-z0-9_]{1,24}", str(d.get("name", ""))):
                    raise ValueError(f"Name {d.get('name')!r} ungültig (a–z, 0–9, _)")
                if d.get("role", "bewohner") not in ROLE_CODES:
                    raise ValueError(f"Rolle {d.get('role')!r} unbekannt")
                self.start_learning(LearnRequest(d["name"], d.get("role", "bewohner"), d.get("leser"),
                                                 d.get("label", ""), d.get("value"), d.get("uri")))
            except (ValueError, KeyError) as exc:
                log.warning("Anlern-Befehl ungültig: %s", exc)
        elif what in ("block", "unblock"):
            try:
                card = self.verifier.registry.block(payload.strip(), what == "block")
                log.info("Karte %s %s", card.name, "gesperrt" if card.blocked else "entsperrt")
            except KeyError:
                log.warning("Karte %r unbekannt", payload)

    # -- Hauptschleife ------------------------------------------------------------------------
    async def run(self, tick: float = 0.05) -> None:
        async def ticker():
            while True:
                await asyncio.sleep(tick)
                self.tick()

        t = asyncio.create_task(ticker())
        try:
            async for ev in self.readers.events():
                await self.handle(ev)
            await self.drain()
            await asyncio.sleep(max(self.logic.absent_time, 0) + 2 * tick)   # letzte Gesten
            self.tick()
        finally:
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)
