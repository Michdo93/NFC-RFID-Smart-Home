"""
base.py – was jeder Leser kann (Kapitel 9).

  events()          asynchroner Strom von ReaderEvent (present/removed)
  can_write         True, wenn der Leser Karten beschreiben kann (rollierender Zähler)
  write(read, p)    NFH-Nutzdaten p auf die gerade aufgelegte Karte schreiben
  signal(leser, s)  LED/Summer am Leser (ok, deny, unknown, alarm, learn, idle)
  with_card(l, fn)  fn(acr, atr) auf der aufgelegten Karte ausführen (Anlernen, nur lokal)
"""

from __future__ import annotations

from typing import AsyncIterator

from ..events import ReaderEvent, TagRead


class Reader:
    can_write = False

    async def events(self) -> AsyncIterator[ReaderEvent]:      # pragma: no cover - Schnittstelle
        raise NotImplementedError
        yield  # noqa

    async def write(self, read: TagRead, payload: bytes) -> bool:
        return False

    async def signal(self, reader: str, name: str) -> None:
        return None

    async def with_card(self, reader: str, fn):
        """fn(acr, atr) mit exklusivem Zugriff auf die aufgelegte Karte (nur lokale Leser)."""
        raise NotImplementedError(f"Leser {reader} erlaubt keinen direkten Kartenzugriff")

    def close(self) -> None:
        return None
