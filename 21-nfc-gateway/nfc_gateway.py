#!/usr/bin/env python3
"""
Kapitel 21 – Das NFC-Gateway (Ansatz A).

Liest alle Leser (ACR122U am Pi, ESP32 über MQTT oder ein Szenario aus dem Simulator),
prüft jede Karte, schreibt bei Stufe „rolling“ den neuen Zähler und meldet geprüfte
Ereignisse an MQTT. openHAB sieht nur nfc/<leser>/event, card, last, security.

Aufruf:  python3 21-nfc-gateway/nfc_gateway.py                       (Leser aus config.yaml)
         python3 21-nfc-gateway/nfc_gateway.py --sim sim/szenarien/rundgang.yaml --dry-run
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.config import try_load_config                 # noqa: E402
from nfcsmarthome.gateway import NfcGateway, PrintSink          # noqa: E402
from nfcsmarthome.mqtt import GatewayEncoder, NfcMqtt           # noqa: E402
from nfcsmarthome.runtime import base_parser, setup_logging     # noqa: E402
from nfcsmarthome.source import add_source_args, build          # noqa: E402

log = logging.getLogger("nfc_gateway")


async def main_async(args) -> None:
    cfg = try_load_config(args.config)
    m = cfg.section("mqtt")
    bus = None if args.dry_run else NfcMqtt.from_config(m)
    setup = build(args, cfg, bus)
    sink = PrintSink() if args.dry_run else bus
    gw = NfcGateway(setup.verifier, setup.logic, setup.readers, sink,
                    GatewayEncoder(m.get("base_topic", "nfc")), setup.keyring)
    if bus is not None:
        loop = asyncio.get_running_loop()
        local = {n for n, rc in (cfg.get("readers") or {}).items() if rc.get("type") == "acr122u"}
        t = bus.topics

        def on_command(topic, payload):
            loop.call_soon_threadsafe(gw.command, topic, payload)

        def on_signal(topic, payload):           # openHAB -> ACR122U am Pi (ESP32 lesen selbst mit)
            reader = topic.split("/")[-3]
            if reader in local:
                asyncio.run_coroutine_threadsafe(setup.readers.signal(reader, payload), loop)

        for what in ("learn", "block", "unblock"):
            bus.on(f"{t.base}/gateway/{what}", on_command)
        bus.on(t.reader("+", "set", "signal"), on_signal)
        bus.start()
    stufe = setup.verifier.level
    log.info("Gateway läuft – Stufe %s, %d Karte(n) im Register", stufe, len(setup.registry.cards))
    try:
        await gw.run()
    finally:
        if bus is not None:
            bus.stop()


def main() -> int:
    ap = base_parser("NFC-Gateway")
    add_source_args(ap)
    ap.add_argument("--dry-run", action="store_true", help="nur ausgeben, nicht an MQTT senden")
    args = ap.parse_args()
    setup_logging(args.verbose)
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
