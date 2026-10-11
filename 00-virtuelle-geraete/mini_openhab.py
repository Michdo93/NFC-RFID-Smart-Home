#!/usr/bin/env python3
"""
Ein Mini-openHAB zum Ausprobieren und Testen (Kapitel 25).

Liest alle Items-Dateien aus openhab/items/ und bietet den Ausschnitt der REST-API
an, den die Programme dieses Buchs benutzen:

  GET  /rest/                          Serverinfo
  GET  /rest/items                     alle Items
  GET  /rest/items/<name>              Item als JSON
  POST /rest/items/<name>              Befehl (text/plain) – mit Autoupdate
  GET  /rest/items/<name>/state        Zustand (text/plain)
  PUT  /rest/items/<name>/state        Zustand setzen (text/plain)
  GET  /rest/events?topics=...         Server-Sent Events (ItemStateChangedEvent)

Autoupdate wie bei virtuellen Items in openHAB – zusätzlich rechnet der Server
INCREASE/DECREASE für Dimmer in 10er-Schritten um, so wie es die Hilfsregel
openhab/rules/virtuelle_geraete.rules im echten openHAB tut.

Das ist KEIN Ersatz für openHAB: keine Regeln, keine Oberfläche, keine Bindings.

Aufruf:
  python3 00-virtuelle-geraete/mini_openhab.py [--port 8080] [--token GEHEIM] [--latenz 0.3]
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, Response, abort, jsonify, request

HERE = Path(__file__).resolve().parent
ITEMS_DIR = HERE / "openhab" / "items"

ITEM_RE = re.compile(
    r'^(?P<type>[A-Za-z]+(?::[A-Za-z]+)?(?::[A-Z]+(?:\([^)]*\))?)?)\s+(?P<name>\w+)'
    r'(?:\s+"(?P<label>[^"]*)")?(?:\s+<(?P<icon>[^>]*)>)?'
    r'(?:\s+\((?P<groups>[^)]*)\))?(?:\s+\[(?P<tags>[^\]]*)\])?')


def parse_items(text: str) -> Dict[str, dict]:
    items: Dict[str, dict] = {}
    for raw in text.splitlines():
        m = ITEM_RE.match(raw.split("//")[0].strip())
        if not m:
            continue
        full = m["type"]
        items[m["name"]] = {
            "type": "Group" if full.startswith("Group") else full,
            "groupType": full.split(":")[1] if full.startswith("Group:") else None,
            "name": m["name"],
            "label": (m["label"] or "").split("[")[0].strip(),
            "category": m["icon"] or "",
            "groupNames": [g.strip() for g in (m["groups"] or "").split(",") if g.strip()],
            "tags": [t.strip().strip('"') for t in (m["tags"] or "").split(",") if t.strip()],
            "state": "NULL",
        }
    return items


def convert(item: dict, cmd: str) -> Optional[str]:
    """Befehl -> neuer Zustand (None = Zustand bleibt)."""
    t, v, old = item["type"], cmd.strip(), item["state"]
    if t == "Dimmer":
        if v in ("INCREASE", "DECREASE"):
            n = int(float(old)) if re.fullmatch(r"-?\d+(\.\d+)?", old) else 0
            return str(min(100, n + 10) if v == "INCREASE" else max(0, n - 10))
        return {"ON": "100", "OFF": "0"}.get(v, v)
    if t == "Rollershutter":
        return {"UP": "0", "DOWN": "100", "STOP": None, "MOVE": None}.get(v, v)
    if t == "Player":
        return {"PLAY": "PLAY", "PAUSE": "PAUSE"}.get(v)    # NEXT/PREVIOUS ändern nichts
    if t == "Color" and v in ("ON", "OFF"):
        parts = old.split(",") if old.count(",") == 2 else ["0", "0", "0"]
        return ",".join(parts[:2] + ["100" if v == "ON" else "0"])
    return v


# Zustandstypen wie in openHAB-Ereignissen (vereinfacht)
_STATE_TYPES = {"Switch": "OnOff", "Dimmer": "Percent", "Rollershutter": "Percent", "Color": "HSB",
                "Number": "Decimal", "Contact": "OpenClosed", "String": "String",
                "DateTime": "DateTime", "Player": "PlayPause"}


def state_type(it: dict, value: str) -> str:
    if value in ("NULL", "UNDEF"):
        return "UnDef"
    base = it["type"].split(":")[0]
    if base == "Group":
        parts = it["type"].split(":")
        base = parts[1] if len(parts) > 1 else "String"
    return _STATE_TYPES.get(base, "String")


class Server:
    def __init__(self, items: Dict[str, dict], token: Optional[str] = None, latency: float = 0.0):
        self.items = items
        self.token = token
        self.latency = latency                  # künstliche Antwortzeit (Kapitel 27)
        self.commands: List[tuple] = []          # (Item, Befehl) – für Tests
        self._clients: List[queue.Queue] = []
        self._lock = threading.Lock()

    def members(self, group: str) -> List[dict]:
        return [i for i in self.items.values() if group in i["groupNames"]]

    def set_state(self, it: dict, new: Optional[str]) -> None:
        if new is None or new == it["state"]:
            return
        old, it["state"] = it["state"], new
        event = {"topic": f"openhab/items/{it['name']}/statechanged",
                 "type": "ItemStateChangedEvent",
                 "payload": json.dumps({"type": state_type(it, new), "value": new,
                                        "oldType": state_type(it, old), "oldValue": old})}
        with self._lock:
            for q in self._clients:
                q.put(event)

    def item_json(self, it: dict) -> dict:
        j = {k: it[k] for k in ("name", "type", "label", "category", "groupNames", "tags", "state")}
        if it.get("groupType"):
            j["groupType"] = it["groupType"]
        return j

    def app(self) -> Flask:
        app = Flask("mini_openhab")

        @app.before_request
        def auth():
            if self.latency and request.path != "/rest/events":
                time.sleep(self.latency)
            if self.token and request.headers.get("Authorization") != f"Bearer {self.token}":
                return Response("Unauthorized", 401)

        @app.get("/rest/")
        def root():
            return jsonify({"version": "8", "runtimeInfo": {"version": "5.0.0 (mini_openhab)"}})

        @app.get("/rest/items")
        def all_items():
            return jsonify([self.item_json(i) for i in self.items.values()])

        def get_item(name):
            if name not in self.items:
                abort(Response(f"Item {name} does not exist!", 404))
            return self.items[name]

        @app.get("/rest/items/<name>")
        def item(name):
            return jsonify(self.item_json(get_item(name)))

        @app.post("/rest/items/<name>")
        def command(name):
            it = get_item(name)
            cmd = request.get_data(as_text=True)
            self.commands.append((name, cmd))
            targets = [m for m in self.members(name) if m["type"] != "Group"] if it["type"] == "Group" else [it]
            for t in targets:
                self.set_state(t, convert(t, cmd))
            return Response(status=200)

        @app.get("/rest/items/<name>/state")
        def state(name):
            return Response(get_item(name)["state"], mimetype="text/plain")

        @app.put("/rest/items/<name>/state")
        def update(name):
            self.set_state(get_item(name), request.get_data(as_text=True))
            return Response(status=202)

        @app.get("/rest/events")
        def events():
            topics = request.args.get("topics", "")
            wanted = {t.split("/")[2] for t in topics.split(",") if t.count("/") >= 2}
            q: queue.Queue = queue.Queue()
            with self._lock:
                self._clients.append(q)

            def stream():
                try:
                    yield ": verbunden\n\n"
                    while True:
                        try:
                            ev = q.get(timeout=1.0)
                        except queue.Empty:
                            yield ": ping\n\n"
                            continue
                        if not wanted or ev["topic"].split("/")[2] in wanted:
                            yield f"event: message\ndata: {json.dumps(ev)}\n\n"
                finally:
                    with self._lock:
                        self._clients.remove(q)

            return Response(stream(), mimetype="text/event-stream")

        return app


def create_server(token: Optional[str] = None, items_dir: Path = ITEMS_DIR,
                  latency: float = 0.0) -> Server:
    items: Dict[str, dict] = {}
    for p in sorted(Path(items_dir).glob("*.items")):
        items.update(parse_items(p.read_text(encoding="utf-8")))
    return Server(items, token, latency)


def main():
    ap = argparse.ArgumentParser(description="Mini-openHAB für die Beispiele des Buchs")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--token", help="erwarteter API-Token (Standard: keine Prüfung)")
    ap.add_argument("--latenz", type=float, default=0.0,
                    help="künstliche Antwortzeit je Anfrage in Sekunden (Kapitel 27)")
    args = ap.parse_args()
    srv = create_server(args.token, latency=args.latenz)
    print(f"{len(srv.items)} Items – http://{args.host}:{args.port}/rest/")
    srv.app().run(args.host, args.port, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
