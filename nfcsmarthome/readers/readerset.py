"""
readerset.py – mehrere Leser zu einem Ereignisstrom zusammenfassen (Kapitel 21, 31).

Im Gesamtsystem laufen gleichzeitig ein ACR122U am Pi, ESP32-Leser über MQTT und
vielleicht ein Szenario aus dem Simulator. ReaderSet mischt ihre Ereignisse und merkt
sich, welcher Leser zu welcher Quelle gehört – damit write(), signal() und with_card()
an der richtigen Stelle landen.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, List, Optional

from ..events import ReaderEvent, TagRead
from .base import Reader


class ReaderSet(Reader):
    def __init__(self, sources: List[Reader]):
        self.sources = sources
        self.owner: Dict[str, Reader] = {}
        self.can_write = any(s.can_write for s in sources)

    async def events(self) -> AsyncIterator[ReaderEvent]:
        queue: asyncio.Queue = asyncio.Queue()
        done = object()

        async def pump(src: Reader) -> None:
            try:
                async for ev in src.events():
                    self.owner[ev.reader] = src
                    await queue.put(ev)
            finally:
                await queue.put(done)

        tasks = [asyncio.create_task(pump(s)) for s in self.sources]
        running = len(tasks)
        try:
            while running:
                item = await queue.get()
                if item is done:
                    running -= 1
                    continue
                yield item
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _src(self, reader: str) -> Optional[Reader]:
        return self.owner.get(reader)

    async def write(self, read: TagRead, payload: bytes) -> bool:
        src = self._src(read.reader)
        return await src.write(read, payload) if src and src.can_write else False

    async def signal(self, reader: str, name: str) -> None:
        src = self._src(reader)
        if src is not None:
            await src.signal(reader, name)
        else:                                   # Leser noch nie gesehen: alle fragen
            for s in self.sources:
                await s.signal(reader, name)

    async def with_card(self, reader: str, fn):
        src = self._src(reader)
        if src is None:
            raise RuntimeError(f"Leser {reader} unbekannt")
        return await src.with_card(reader, fn)

    def close(self) -> None:
        for s in self.sources:
            s.close()
