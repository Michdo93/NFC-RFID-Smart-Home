"""Ansatz A Ende zu Ende: ESP32-Simulator -> Broker -> Gateway -> Broker -> „openHAB“."""
import asyncio
import json
import time

import paho.mqtt.client as mqtt

from nfcsmarthome.esp32sim import Esp32Sim
from nfcsmarthome.gateway import NfcGateway
from nfcsmarthome.logic import TagLogic
from nfcsmarthome.mqtt import NfcMqtt
from nfcsmarthome.personalize import personalize
from nfcsmarthome.readers.mqttreader import MqttReaders, parse_raw
from nfcsmarthome.readers.readerset import ReaderSet
from nfcsmarthome.readers.sim import VirtualClassic, VirtualNtag
from nfcsmarthome.registry import Registry
from nfcsmarthome.verify import Verifier
from conftest import acr_for


def test_parse_raw():
    ev = parse_raw("flur", json.dumps({"uid": "5A3F9C21", "type": "classic1k", "data": "00" * 32}))
    assert ev.kind == "present" and ev.read.payload == bytes(32)
    assert parse_raw("flur", '{"removed": true}').kind == "removed"


def test_end_to_end(broker, keyring):
    reg = Registry(None)
    classic = VirtualClassic.factory(bytes.fromhex("5A3F9C21"))
    band = VirtualNtag.factory("ntag216", bytes.fromhex("04A731529D6181"))
    for c, n in ((classic, "michael"), (band, "lea")):
        acr, _ = acr_for(c)
        personalize(acr, c.atr, keyring, reg, n, "bewohner")

    seen = []
    obs = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="openhab-test")
    obs.on_message = lambda c, u, m: seen.append((m.topic, m.payload.decode()))
    obs.connect("127.0.0.1", broker)
    obs.subscribe("nfc/#")
    obs.loop_start()

    async def main():
        bus = NfcMqtt(port=broker, client_id="gw").start()
        readers = MqttReaders(bus, keyring)
        gw = NfcGateway(Verifier(keyring, reg, "rolling"), TagLogic(0.3, 0.05),
                        ReaderSet([readers]), bus, keyring=keyring)
        task = asyncio.create_task(gw.run(tick=0.02))
        for _ in range(50):
            if bus.connected:
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        esp = Esp32Sim("flur", keyring.classic_key_a(), port=broker).start()
        await asyncio.sleep(0.3)
        for card in (classic, band, classic):
            esp.place(card)
            await asyncio.sleep(0.6)
            esp.remove()
            await asyncio.sleep(0.3)
        task.cancel()
        esp.stop()
        bus.stop()
        return gw, esp

    gw, esp = asyncio.run(main())
    obs.loop_stop()
    assert [d.status for d in gw.decisions] == ["accepted", "accepted", "accepted"]
    assert [d.data.counter for d in gw.decisions] == [0, 0, 1]      # Zähler wurde geschrieben
    assert reg.by_name("michael").counter == 2 and reg.by_name("lea").counter == 1
    assert ("nfc/flur/event", "michael:present") in seen
    assert ("nfc/flur/event", "lea:hold") in seen
    assert ("nfc/flur/status", "online") in seen
    assert esp.signals.count("ok") == 3
