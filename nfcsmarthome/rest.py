"""
rest.py – Ansatz B: direkte Item-Steuerung über die openHAB-REST-API
          mit python-openhab-rest-client (AsyncOpenHABClient / AsyncItems).

OpenHABSender ergänzt den Client um das, was bei NFC-Steuerung wichtig ist:
  * nur senden, wenn sich der Wert geändert hat (sonst Befehlsflut)
  * Mindestabstand pro Item (z. B. Hue-Bridge verträgt nur ~10 Befehle/s)
  * Fehler protokollieren statt das Programm zu beenden
  * watch_states(): Rückkanal über Server-Sent Events (SSE)

Authentifizierung bevorzugt per API-Token (openHAB-UI -> Profil -> API-Tokens).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, Iterable, Optional, Tuple

from openhab.AsyncClient import AsyncOpenHABClient
from openhab.AsyncItems import AsyncItems

log = logging.getLogger("nfcrest")


class OpenHABSender:
    def __init__(self, url: str, token: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 min_interval: float = 0.1):
        self.client = AsyncOpenHABClient(url=url, username=username, password=password, token=token)
        self.items: Optional[AsyncItems] = None
        self.min_interval = min_interval
        self._last: Dict[str, str] = {}
        self._time: Dict[str, float] = {}

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "OpenHABSender":
        return cls(url=cfg["url"], token=cfg.get("token"), username=cfg.get("username"),
                   password=cfg.get("password"), min_interval=float(cfg.get("min_interval", 0.1)))

    async def __aenter__(self) -> "OpenHABSender":
        await self.client.__aenter__()
        if not self.client.isLoggedIn:
            log.warning("openHAB unter %s nicht erreichbar oder Login fehlgeschlagen", self.client.url)
        self.items = AsyncItems(self.client)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.client.__aexit__(*exc)

    # -- Senden --------------------------------------------------------------
    async def send(self, item: str, command: Any, force: bool = False) -> bool:
        """sendCommand mit Duplikat- und Ratenfilter. True = gesendet."""
        value = str(command)
        now = time.monotonic()
        if not force:
            if self._last.get(item) == value:
                return False
            if now - self._time.get(item, 0.0) < self.min_interval:
                return False
        self._last[item] = value
        self._time[item] = now
        try:
            res = await self.items.sendCommand(item, value)
        except Exception as exc:  # Netzwerkfehler, Timeout ...
            log.error("sendCommand %s=%s fehlgeschlagen: %s", item, value, exc)
            self._last.pop(item, None)
            return False
        if isinstance(res, dict) and "error" in res:
            log.error("sendCommand %s=%s: %s", item, value, res["error"])
            return False
        return True

    async def update(self, item: str, state: Any) -> None:
        """postUpdate – Zustand setzen ohne Befehl an das Gerät."""
        await self.items.updateItemState(item, str(state))

    async def state(self, item: str) -> Optional[str]:
        res = await self.items.getItemState(item)
        if isinstance(res, str):
            return res.strip()
        log.warning("Zustand von %s nicht lesbar: %s", item, res)
        return None

    async def toggle(self, item: str) -> Optional[str]:
        """Switch umschalten: Zustand lesen, Gegenteil senden. Liefert den neuen Befehl."""
        state = await self.state(item)
        value = "OFF" if state == "ON" else "ON"
        await self.send(item, value, force=True)
        return value

    def forget(self, item: Optional[str] = None) -> None:
        """Duplikatfilter zurücksetzen (z. B. wenn der Zustand extern geändert wurde)."""
        if item is None:
            self._last.clear()
        else:
            self._last.pop(item, None)

    # -- Rückkanal -----------------------------------------------------------
    async def watch_states(self, item_names: Iterable[str]) -> AsyncIterator[Tuple[str, str]]:
        """
        Liefert (Item, neuer Zustand) über SSE /rest/events.
        Hinweis: Wir nutzen die aiohttp-Session des Clients direkt, da wir einen
        dauerhaften Stream mit Reconnect brauchen.
        """
        names = list(item_names)
        topics = ",".join(f"openhab/items/{n}/statechanged" for n in names)
        url = f"{self.client.url}/rest/events?topics={topics}"
        while True:
            try:
                async with self.client.session.get(
                        url, headers={"Accept": "text/event-stream"}, timeout=None) as resp:
                    resp.raise_for_status()
                    async for raw in resp.content:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                            item = event["topic"].split("/")[2]
                            payload = json.loads(event["payload"])
                            yield item, str(payload.get("value"))
                        except (KeyError, IndexError, ValueError):
                            continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("SSE-Verbindung unterbrochen (%s) – neuer Versuch in 3 s", exc)
                await asyncio.sleep(3)
