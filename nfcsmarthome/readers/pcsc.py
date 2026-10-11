"""
pcsc.py – der ACR122U über pcscd und pyscard (Kapitel 5, 6 und 9).

pyscard meldet über einen CardMonitor, wann eine Karte aufgelegt oder entfernt wird
(eigener Thread). PcscReader macht daraus ReaderEvents in der asyncio-Schleife, liest
die Karte aus und hält die Verbindung offen, solange sie liegt – so kann das Gateway
noch schreiben (rollierender Zähler).

Voraussetzungen (Kapitel 5):
  sudo apt install pcscd libccid pcsc-tools swig libpcsclite-dev
  Kernel-Modul pn533_usb sperren (es belegt den ACR122U sonst selbst)
  pip install pyscard

LED und Summer OHNE aufgelegte Karte gehen nur per SCardControl („Escape“, 3500). Der
CCID-Treiber erlaubt das erst, wenn in seiner Info.plist ifdDriverOptions 0x0001 steht.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import AsyncIterator, List, Optional

from .. import apdu as ap
from ..events import ReaderEvent, TagRead
from ..feedback import signal_apdu
from ..keys import KeyRing
from .base import Reader
from .common import read_tag, write_payload

log = logging.getLogger("nfcpcsc")


def list_readers() -> List[str]:
    from smartcard.System import readers
    return [str(r) for r in readers()]


def connect_first(match: str = "ACR122"):
    """Für Einzelskripte: Verbindung zur aufgelegten Karte -> (Acr122u, ATR)."""
    from smartcard.System import readers
    for r in readers():
        if match.lower() in str(r).lower():
            conn = r.createConnection()
            conn.connect()                         # wirft NoCardException ohne Karte
            return ap.Acr122u(conn), bytes(conn.getATR())
    raise RuntimeError(f"Kein Leser mit {match!r} gefunden – läuft pcscd? (pcsc_scan)")


def control_without_card(apdu_bytes: List[int], match: str = "ACR122") -> bytes:
    """Pseudo-APDU per Escape an den Leser (ohne Karte), z. B. für LED oder Summer."""
    from smartcard.System import readers
    from smartcard.scard import SCARD_CTL_CODE, SCARD_SHARE_DIRECT
    for r in readers():
        if match.lower() in str(r).lower():
            conn = r.createConnection()
            conn.connect(mode=SCARD_SHARE_DIRECT)
            try:
                return bytes(conn.control(SCARD_CTL_CODE(3500), apdu_bytes))
            finally:
                conn.disconnect()
    raise RuntimeError("Kein ACR122U gefunden")


class PcscReader(Reader):
    can_write = True

    def __init__(self, name: str, match: str = "ACR122", keyring: Optional[KeyRing] = None,
                 buzzer_on_detect: bool = False):
        self.name = name
        self.match = match
        self.keyring = keyring
        self.buzzer_on_detect = buzzer_on_detect
        self._conn = None
        self._acr: Optional[ap.Acr122u] = None
        self._read: Optional[TagRead] = None
        self._atr = b""
        self._io = threading.Lock()
        self._queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._monitor = None
        self._observer = None

    # -- CardMonitor (läuft in einem eigenen Thread von pyscard) --------------------------
    def _update(self, observable, actions):
        added, removed = actions
        for card in added:
            if self.match.lower() not in str(card.reader).lower():
                continue
            try:
                conn = card.createConnection()
                conn.connect()
                acr = ap.Acr122u(conn)
                with self._io:
                    if not self.buzzer_on_detect:
                        try:
                            acr.buzzer_on_detect(False)
                        except ap.ApduError:
                            pass
                    read = read_tag(acr, self.name, bytes(card.atr), self.keyring)
                self._conn, self._acr, self._read, self._atr = conn, acr, read, bytes(card.atr)
                self._emit(ReaderEvent("present", self.name, read))
            except Exception as exc:                 # Karte zu schnell wieder weg o. Ä.
                log.warning("Karte nicht lesbar: %s", exc)
        for card in removed:
            if self.match.lower() not in str(card.reader).lower():
                continue
            with self._io:
                self._conn, self._acr, self._read = None, None, None
            self._emit(ReaderEvent("removed", self.name))

    def _emit(self, ev: ReaderEvent) -> None:
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, ev)

    async def events(self) -> AsyncIterator[ReaderEvent]:
        from smartcard.CardMonitoring import CardMonitor, CardObserver

        reader = self

        class Observer(CardObserver):
            def update(self, observable, actions):
                reader._update(observable, actions)

        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._monitor = CardMonitor()
        self._observer = Observer()
        self._monitor.addObserver(self._observer)
        log.info("Warte auf Karten am Leser %s (%s)", self.name, self.match)
        try:
            while True:
                yield await self._queue.get()
        finally:
            self.close()

    # -- Schreiben und Rückmeldung -------------------------------------------------------------
    async def write(self, read: TagRead, payload: bytes) -> bool:
        if self.keyring is None:
            return False

        def work() -> bool:
            with self._io:
                if self._acr is None:
                    return False
                return write_payload(self._acr, read, self.keyring, payload)

        return await asyncio.to_thread(work)

    async def signal(self, reader: str, name: str) -> None:
        if reader != self.name:
            return

        def work() -> None:
            with self._io:
                try:
                    if self._acr is not None:
                        self._acr.transmit(signal_apdu(name), check=False)
                    else:
                        control_without_card(signal_apdu(name), self.match)
                except Exception as exc:
                    log.debug("Signal %s nicht möglich: %s", name, exc)

        await asyncio.to_thread(work)

    async def with_card(self, reader: str, fn):
        def work():
            with self._io:
                if self._acr is None:
                    raise RuntimeError("keine Karte aufgelegt")
                return fn(self._acr, self._atr)

        return await asyncio.to_thread(work)

    def close(self) -> None:
        if self._monitor and self._observer:
            self._monitor.deleteObserver(self._observer)
            self._monitor = None
