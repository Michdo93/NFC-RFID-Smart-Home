"""
mqttreader.py – ESP32-Leser (PN532 oder RC522) über MQTT (Kapitel 16, 17, 21).

Der ESP32 veröffentlicht Rohdaten unter nfc/raw/<leser>:

  {"uid": "5A3F9C21", "type": "classic1k", "data": "<32 Byte hex>"}   MIFARE Classic, Sektor 1
  {"uid": "04…", "type": "ntag215", "mem": "<Nutzspeicher ab Seite 4, hex>"}   NTAG
  {"removed": true}                                                   Karte abgenommen

Schreiben (rollierender Zähler) geht als Befehl an nfc/<leser>/cmd. Der Schlüssel bzw.
das Passwort DIESER Karte kommt mit dem Befehl – der ESP32 kennt nur den Lese-Schlüssel
der Installation. Das Ergebnis meldet er unter nfc/<leser>/cmd/result.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from typing import AsyncIterator, Dict, Optional

from .. import hexs, unhex
from ..events import ReaderEvent, TagRead
from ..keys import KeyRing
from ..mqtt import NfcMqtt
from ..ntag import ndef_bytes, parse_user_memory
from ..verify import replace_nfh
from .base import Reader
from .common import changed_blocks

log = logging.getLogger("nfcmqttreader")


def parse_raw(reader: str, payload: str) -> ReaderEvent:
    d = json.loads(payload)
    if d.get("removed"):
        return ReaderEvent("removed", reader)
    read = TagRead(reader, unhex(d["uid"]), d.get("type", "unbekannt"))
    if d.get("data"):
        read.payload = unhex(d["data"])
    if d.get("mem"):
        read.records = parse_user_memory(unhex(d["mem"]))
    return ReaderEvent("present", reader, read)


def write_command(cmd_id: int, read: TagRead, keyring: KeyRing, payload: bytes) -> Dict:
    """Schreibbefehl für den ESP32 bauen – mit dem Schlüssel genau dieser Karte."""
    cmd = {"id": cmd_id, "op": "write", "uid": read.uid_hex, "type": read.tag_type}
    if read.tag_type == "classic1k":
        cmd["key_b"] = hexs(keyring.classic_key_b(read.uid))
        cmd["blocks"] = {str(b): hexs(d) for b, d in changed_blocks(read.payload, payload).items()}
    elif read.tag_type.startswith("ntag"):
        cmd["pwd"] = hexs(keyring.ntag_pwd(read.uid))
        cmd["pack"] = hexs(keyring.ntag_pack(read.uid))
        cmd["start"] = 4
        cmd["pages"] = hexs(ndef_bytes(replace_nfh(read.records, payload)))
    else:
        raise ValueError(f"Typ {read.tag_type} kann der ESP32 nicht schreiben")
    return cmd


class MqttReaders(Reader):
    """Alle ESP32-Leser auf einmal: abonniert nfc/raw/+."""

    can_write = True

    def __init__(self, mqtt: NfcMqtt, keyring: Optional[KeyRing] = None, timeout: float = 2.0):
        self.mqtt = mqtt
        self.keyring = keyring
        self.timeout = timeout
        self._ids = itertools.count(1)
        self._pending: Dict[int, asyncio.Future] = {}
        self._queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_raw(self, topic: str, payload: str) -> None:
        reader = topic.rsplit("/", 1)[-1]
        try:
            ev = parse_raw(reader, payload)
        except (ValueError, KeyError) as exc:
            log.warning("Ungültige Rohdaten von %s: %s", reader, exc)
            return
        ev.t = time.monotonic()
        if ev.read:
            ev.read.t = ev.t
        self._loop.call_soon_threadsafe(self._queue.put_nowait, ev)

    def _on_result(self, topic: str, payload: str) -> None:
        try:
            d = json.loads(payload)
        except ValueError:
            return
        fut = self._pending.pop(int(d.get("id", -1)), None)
        if fut is not None:
            self._loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(bool(d.get("ok"))))

    async def events(self) -> AsyncIterator[ReaderEvent]:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        t = self.mqtt.topics
        self.mqtt.on(t.raw("+"), self._on_raw)
        self.mqtt.on(t.reader("+", "cmd", "result"), self._on_result)
        while True:
            yield await self._queue.get()

    async def write(self, read: TagRead, payload: bytes) -> bool:
        if self.keyring is None:
            return False
        cmd_id = next(self._ids)
        try:
            cmd = write_command(cmd_id, read, self.keyring, payload)
        except ValueError as exc:
            log.warning("%s", exc)
            return False
        fut = self._loop.create_future()
        self._pending[cmd_id] = fut
        self.mqtt.send([(self.mqtt.topics.reader(read.reader, "cmd"), json.dumps(cmd), False)])
        try:
            return await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            self._pending.pop(cmd_id, None)
            log.warning("Leser %s: keine Antwort auf Schreibbefehl %d", read.reader, cmd_id)
            return False

    async def signal(self, reader: str, name: str) -> None:
        self.mqtt.send([(self.mqtt.topics.reader(reader, "set", "signal"), name, False)])
