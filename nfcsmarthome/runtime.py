"""
runtime.py – Logging, Kommandozeile und der Executor für Ansatz B (Kapitel 26).

Executor führt Operationen aus actions.CardProfile gegen openHAB aus – der Reihe nach
über eine Warteschlange. Die Leseschleife wartet nie auf das Netzwerk: Sie legt Befehle
nur ab; gesendet wird in einer eigenen Task. So kann der Leser schon die nächste Karte
melden (und den Zähler schreiben), während openHAB noch antwortet.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Awaitable, Callable, List, Optional

from .actions import Op

log = logging.getLogger("nfcruntime")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")


def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--config", help="Pfad zur config.yaml (Standard: config/config.yaml)")
    p.add_argument("-v", "--verbose", action="store_true", help="ausführliche Ausgabe")
    return p


class Executor:
    """sender braucht send(item, value, force), toggle(item), update(item, value) und state(item)."""

    def __init__(self, sender, feedback: Optional[Callable[[str, str], Awaitable[None]]] = None):
        self.sender = sender
        self.feedback = feedback
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self.done: List[Op] = []

    def submit(self, ops: List[Op]) -> None:
        for op in ops:
            self.queue.put_nowait(op)

    async def _work(self) -> None:
        while True:
            op: Op = await self.queue.get()
            try:
                if op.kind == "toggle":
                    new = await self.sender.toggle(op.item)
                    log.info("%-40s -> %s (umgeschaltet)", op.item, new)
                elif op.kind == "update":
                    await self.sender.update(op.item, op.value)
                    log.info("%-40s := %s", op.item, op.value)
                elif op.kind == "increment":
                    old = await self.sender.state(op.item)
                    try:
                        n = int(float(old)) + 1
                    except (TypeError, ValueError):       # NULL, UNDEF: von vorn
                        n = 1
                    await self.sender.update(op.item, n)
                    log.info("%-40s := %s (gezählt)", op.item, n)
                elif op.kind == "feedback":
                    if self.feedback:
                        await self.feedback(op.item, op.value)
                    log.info("%-40s ~> Signal %s", op.item, op.value)
                else:
                    await self.sender.send(op.item, op.value, force=True)
                    log.info("%-40s -> %s", op.item, op.value)
                self.done.append(op)
            except Exception as exc:
                log.error("Befehl %s fehlgeschlagen: %s", op, exc)
            finally:
                self.queue.task_done()

    def start(self) -> "Executor":
        self._task = asyncio.create_task(self._work())
        return self

    async def drain(self, timeout: float = 3.0) -> None:
        try:
            await asyncio.wait_for(self.queue.join(), timeout)
        except asyncio.TimeoutError:
            log.warning("Nicht alle Befehle gesendet")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
