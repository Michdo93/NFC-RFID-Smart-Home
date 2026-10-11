"""
esp32sim.py – die ESP32-Firmware in Python nachgebildet (Kapitel 16 und 17).

Verhält sich am Broker wie ein ESP32 mit PN532 oder RC522:

  nfc/<leser>/status       online/offline (Last Will)
  nfc/raw/<leser>          Rohdaten beim Auflegen, {"removed": true} beim Abnehmen
  nfc/<leser>/cmd          Schreibbefehle des Gateways ausführen
  nfc/<leser>/cmd/result   Ergebnis zurückmelden
  nfc/<leser>/set/signal   Signal anzeigen (hier: ausgeben)

Damit lassen sich Gateway, Regeln und openHAB-Things testen, bevor der erste ESP32
gelötet ist. Die Karten kommen aus dem Simulator (readers.sim).
"""

from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional

from . import apdu as ap
from . import hexs, ntag, unhex
from .readers.common import DATA_BLOCKS, card_type
from .readers.sim import SimulatedAcr122u

log = logging.getLogger("esp32sim")


class Esp32Sim:
    def __init__(self, name: str, key_a: bytes, host: str = "localhost", port: int = 1883,
                 username: Optional[str] = None, password: Optional[str] = None,
                 base: str = "nfc", on_signal: Optional[Callable[[str], None]] = None):
        import paho.mqtt.client as mqtt
        self.name, self.key_a, self.base = name, key_a, base.rstrip("/")
        self.sim = SimulatedAcr122u()          # steht hier für PN532/RC522
        self.acr = ap.Acr122u(self.sim)
        self.signals: List[str] = []
        self.on_signal = on_signal
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"esp32-{name}")
        if username:
            self.client.username_pw_set(username, password)
        self.status = f"{self.base}/{name}/status"
        self.client.will_set(self.status, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._host, self._port = host, port

    # -- Verbindung ---------------------------------------------------------------------------
    def start(self) -> "Esp32Sim":
        self.client.connect(self._host, self._port, 30)
        self.client.loop_start()
        return self

    def stop(self) -> None:
        self.client.publish(self.status, "offline", qos=1, retain=True)
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.publish(self.status, "online", qos=1, retain=True)
        client.subscribe(f"{self.base}/{self.name}/cmd", qos=1)
        client.subscribe(f"{self.base}/{self.name}/set/signal", qos=1)

    def _on_message(self, client, userdata, msg):
        text = msg.payload.decode("utf-8", "replace")
        if msg.topic.endswith("/set/signal"):
            self.signals.append(text)
            if self.on_signal:
                self.on_signal(text)
            return
        try:
            cmd = json.loads(text)
            ok = self.execute(cmd)
        except Exception as exc:                 # wie die Firmware: nie abstürzen
            log.warning("Befehl fehlgeschlagen: %s", exc)
            cmd, ok = {"id": -1}, False
        client.publish(f"{self.base}/{self.name}/cmd/result",
                       json.dumps({"id": cmd.get("id"), "ok": ok}), qos=1)

    # -- Karte -------------------------------------------------------------------------------
    def place(self, card) -> dict:
        self.sim.place(card)
        raw = self.read_raw()
        self.client.publish(f"{self.base}/raw/{self.name}", json.dumps(raw), qos=1)
        return raw

    def remove(self) -> None:
        self.sim.remove()
        self.client.publish(f"{self.base}/raw/{self.name}", json.dumps({"removed": True}), qos=1)

    def read_raw(self) -> dict:
        """Was die Firmware liest: UID, Typ und Sektor 1 bzw. den NDEF-Bereich."""
        card = self.sim.card
        kind = card_type(card.atr, self.acr)
        raw = {"uid": hexs(self.acr.uid()), "type": kind}
        if kind == "classic1k" and self.acr.login(DATA_BLOCKS[0], self.key_a, ap.KEY_A):
            raw["data"] = hexs(b"".join(self.acr.read_block(b) for b in DATA_BLOCKS))
        elif kind.startswith("ntag"):
            head = ntag.read_pages(self.acr, 4, 4)
            if head[0] == 0x03 and head[1] != 0xFF:
                n = head[1] + 3                                # 03 <Länge> … FE
            elif head[0] == 0x03:
                n = int.from_bytes(head[2:4], "big") + 5       # 03 FF <Länge 2 Byte> … FE
            else:
                n = 16
            raw["mem"] = hexs(ntag.read_pages(self.acr, 4, (n + 3) // 4))
        return raw

    def execute(self, cmd: dict) -> bool:
        if cmd.get("op") != "write" or self.sim.card is None:
            return False
        if hexs(self.acr.uid()) != cmd["uid"]:
            return False                                       # andere Karte aufgelegt
        if cmd["type"] == "classic1k":
            if not self.acr.login(DATA_BLOCKS[0], unhex(cmd["key_b"]), ap.KEY_B):
                return False
            for block, data in cmd["blocks"].items():
                self.acr.write_block(int(block), unhex(data))
            return all(self.acr.read_block(int(b)) == unhex(d) for b, d in cmd["blocks"].items())
        if cmd["type"].startswith("ntag"):
            if self.acr.ntag_pwd_auth(unhex(cmd["pwd"])) != unhex(cmd["pack"]):
                return False
            data, start = unhex(cmd["pages"]), int(cmd.get("start", 4))
            for i in range(0, len(data), 4):
                self.acr.write_page(start + i // 4, data[i:i + 4])
            return ntag.read_pages(self.acr, start, len(data) // 4) == data
        return False
