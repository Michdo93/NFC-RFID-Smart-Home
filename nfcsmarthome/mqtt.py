"""
mqtt.py – Ansatz A: Topics und Verbindung (paho-mqtt >= 2.0, Kapitel 20–24).

Topic-Schema (base = "nfc"):

  ESP32 -> Gateway (Rohdaten, NICHT für openHAB)
    nfc/raw/<leser>              {"uid": ..., "type": ..., "data"|"mem": ...} oder {"removed": true}
    nfc/<leser>/status           online | offline            retained, Last Will des ESP32
    nfc/<leser>/cmd/result       {"id": 7, "ok": true}        Ergebnis eines Schreibbefehls

  Gateway -> ESP32
    nfc/<leser>/cmd              {"id": 7, "op": "write", ...} Zähler schreiben (Kapitel 17)

  Gateway -> openHAB (geprüfte Ereignisse)
    nfc/gateway/status           online | offline            retained, Last Will
    nfc/<leser>/event            <karte>:<geste>              z. B. michael:present – Trigger
    nfc/<leser>/gesture          JSON: Karte, Rolle, Wert, Geste, Dauer    Trigger (Kapitel 23)
    nfc/<leser>/card             Name der liegenden Karte | NONE        retained
    nfc/<leser>/last             JSON: Name, Rolle, Status, Zeit          retained
    nfc/<leser>/security         JSON: unknown, invalid, clone ...         Ereignis

  openHAB -> Gateway/Leser
    nfc/<leser>/set/signal       ok | deny | unknown | alarm | learn | idle
    nfc/gateway/learn            {"name": ..., "role": ..., "leser": ...}  Anlernmodus
    nfc/gateway/block            <kartenname>   bzw.  nfc/gateway/unblock

UIDs gehen nur über nfc/raw/ (zwischen ESP32 und Gateway), nicht an openHAB.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .logic import Gesture
from .verify import Decision

log = logging.getLogger("nfcmqtt")

Message = Tuple[str, str, bool]          # (Topic, Payload, retained)


class Topics:
    def __init__(self, base: str = "nfc"):
        self.base = base.rstrip("/")

    def raw(self, reader: str = "+") -> str:
        return f"{self.base}/raw/{reader}"

    def reader(self, reader: str, *parts: str) -> str:
        return "/".join((self.base, reader) + parts)

    @property
    def gateway_status(self) -> str:
        return f"{self.base}/gateway/status"

    @property
    def learn(self) -> str:
        return f"{self.base}/gateway/learn"


class GatewayEncoder:
    """Prüfergebnisse und Gesten -> MQTT-Nachrichten (ohne Netzwerk, testbar)."""

    def __init__(self, base: str = "nfc"):
        self.t = Topics(base)

    def gesture(self, g: Gesture) -> List[Message]:
        """
        Reihenfolge: erst Zustände (card, last, security), dann die Ereignisse – so sind
        die Zustände schon aktuell, wenn eine Regel auf das Ereignis reagiert.
        """
        out: List[Message] = []
        accepted = g.decision is not None and g.decision.ok
        if g.kind == "present":
            out.append((self.t.reader(g.reader, "card"), g.who if accepted else "NONE", True))
            if g.decision is not None:
                out.append((self.t.reader(g.reader, "last"), json.dumps(self.last(g.decision)), True))
                if not accepted:
                    out.append((self.t.reader(g.reader, "security"),
                                json.dumps(self.security(g.decision)), False))
        elif g.kind == "removed" and accepted:
            out.append((self.t.reader(g.reader, "card"), "NONE", True))
        if accepted:
            out.append((self.t.reader(g.reader, "event"), str(g), False))
            out.append((self.t.reader(g.reader, "gesture"), json.dumps(self.details(g)), False))
        return out

    @staticmethod
    def details(g: Gesture) -> Dict[str, Any]:
        """Alles, was eine Regel braucht, in EINER Nachricht (Kapitel 23)."""
        c = g.decision.card
        return {"card": c.name, "label": c.label, "role": c.role, "value": c.value,
                "gesture": g.kind, "reader": g.reader, "duration": round(g.duration, 1)}

    @staticmethod
    def last(d: Decision) -> Dict[str, Any]:
        c = d.card
        return {"name": c.name if (c and d.ok) else None, "label": c.label if (c and d.ok) else None,
                "role": c.role if (c and d.ok) else None, "status": d.status,
                "time": datetime.now().isoformat(timespec="seconds")}

    @staticmethod
    def security(d: Decision) -> Dict[str, Any]:
        return {"status": d.status, "message": d.message,
                "card": d.card.name if d.card else None,
                "time": datetime.now().isoformat(timespec="seconds")}


class NfcMqtt:
    """Verbindung zum Broker mit Last Will, Reconnect und Abos (wie im Gamepad-Band)."""

    def __init__(self, host: str = "localhost", port: int = 1883,
                 username: Optional[str] = None, password: Optional[str] = None,
                 base_topic: str = "nfc", client_id: str = "nfc-gateway", tls: bool = False,
                 status_topic: Optional[str] = None, ca_file: Optional[str] = None):
        import paho.mqtt.client as mqtt
        self.topics = Topics(base_topic)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            self.client.username_pw_set(username, password)
        if tls:                                  # Kapitel 20: Port 8883, eigene CA in ca_file
            self.client.tls_set(ca_certs=ca_file)
        self.status_topic = status_topic or self.topics.gateway_status
        self.client.will_set(self.status_topic, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._host, self._port = host, port
        self._handlers: List[Tuple[str, Callable[[str, str], None]]] = []
        self.connected = False

    @classmethod
    def from_config(cls, cfg: Dict[str, Any], client_id: Optional[str] = None) -> "NfcMqtt":
        return cls(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 1883)),
                   username=cfg.get("username"), password=cfg.get("password"),
                   base_topic=cfg.get("base_topic", "nfc"),
                   client_id=client_id or cfg.get("client_id", "nfc-gateway"),
                   tls=bool(cfg.get("tls", False)), ca_file=cfg.get("ca_file"))

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self.connected = True
            log.info("MQTT verbunden")
            client.publish(self.status_topic, "online", qos=1, retain=True)
            for pattern, _ in self._handlers:
                client.subscribe(pattern, qos=1)
        else:
            log.error("MQTT-Verbindung abgelehnt: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        if getattr(self, "_stopping", False):
            log.info("MQTT abgemeldet")
        else:
            log.warning("MQTT getrennt (%s) – automatischer Reconnect", reason_code)

    def _on_message(self, client, userdata, msg):
        import paho.mqtt.client as mqtt
        payload = msg.payload.decode("utf-8", "replace").strip()
        for pattern, handler in self._handlers:
            if mqtt.topic_matches_sub(pattern, msg.topic):
                try:
                    handler(msg.topic, payload)
                except Exception:
                    log.exception("Fehler beim Verarbeiten von %s", msg.topic)

    def on(self, pattern: str, handler: Callable[[str, str], None]) -> None:
        self._handlers.append((pattern, handler))
        if self.client.is_connected():
            self.client.subscribe(pattern, qos=1)

    def start(self) -> "NfcMqtt":
        self.client.connect_async(self._host, self._port, keepalive=30)
        self.client.loop_start()
        return self

    def stop(self) -> None:
        self._stopping = True
        info = self.client.publish(self.status_topic, "offline", qos=1, retain=True)
        try:
            info.wait_for_publish(timeout=2)
        except (RuntimeError, ValueError):          # nicht verbunden – Last Will übernimmt
            pass
        self.client.disconnect()
        self.client.loop_stop()

    def send(self, messages: List[Message]) -> None:
        for topic, payload, retain in messages:
            self.client.publish(topic, payload, qos=1, retain=retain)
