#!/usr/bin/env python3
"""
Kapitel 26 – Ansatz B: Karten lösen Aktionen direkt über die REST-API aus.

Prüfen, Zähler schreiben und Rückmeldung übernimmt dasselbe NfcGateway wie in
Kapitel 21 – nur gehen die Gesten nicht an MQTT, sondern an ein Kartenprofil (YAML).
Der Executor sendet die Befehle der Reihe nach an openHAB.

  --mqtt     zusätzlich alle Ereignisse an MQTT melden (Hybrid, Kapitel 32)
  --esp32    ESP32-Leser über MQTT einbinden (Leser mit type esp32 in config.yaml)

Steht im Profil ein Abschnitt „watch“, beobachtet die Fernbedienung diese Items über
Server-Sent Events und gibt die passenden Signale an den Lesern aus (Kapitel 27).

Aufruf:  python3 26-kartenaktionen/nfc_fernbedienung.py --profil 26-kartenaktionen/profile/erste_karten.yaml
         python3 26-kartenaktionen/nfc_fernbedienung.py --url http://127.0.0.1:8080 \
                 --profil 31-labor-szenarien/profile/labor.yaml --sim sim/szenarien/labor_tag.yaml
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.actions import CardProfile                    # noqa: E402
from nfcsmarthome.config import REPO_ROOT, try_load_config      # noqa: E402
from nfcsmarthome.gateway import NfcGateway                     # noqa: E402
from nfcsmarthome.mqtt import GatewayEncoder, NfcMqtt           # noqa: E402
from nfcsmarthome.rest import OpenHABSender                     # noqa: E402
from nfcsmarthome.runtime import Executor, base_parser, setup_logging   # noqa: E402
from nfcsmarthome.source import add_source_args, build          # noqa: E402

log = logging.getLogger("nfc_fernbedienung")


class NullSink:
    def send(self, messages):
        pass


async def rueckkanal(sender, profile, readers, reader_names) -> None:
    """Kapitel 27: Zustände aus openHAB (SSE) als Signale an die Leser – ohne Regeln."""
    if not profile.watch:
        return
    log.info("Rückkanal: beobachte %s", ", ".join(profile.watch))
    async for item, state in sender.watch_states(profile.watch):
        for reader, signal in profile.signals_for(item, state):
            for r in (reader_names if reader == "*" else [reader]):
                log.info("%-10s Signal %-7s (%s = %s)", r, signal, item, state)
                await readers.signal(r, signal)


async def main_async(args) -> None:
    cfg = try_load_config(args.config)
    oh = cfg.section("openhab")
    if args.url:
        oh["url"], oh["token"] = args.url, None
    profile_path = Path(args.profil or cfg.get("profile") or "31-labor-szenarien/profile/labor.yaml")
    if not profile_path.is_absolute() and not profile_path.exists():
        profile_path = REPO_ROOT / profile_path
    profile = CardProfile.load(profile_path)
    bus = NfcMqtt.from_config(cfg.section("mqtt"), "nfc-fernbedienung") if (args.mqtt or args.esp32) else None
    setup = build(args, cfg, bus if args.esp32 else None)
    log.info("Profil: %s (%s) – Stufe %s", profile.name, profile_path.name, setup.verifier.level)

    async with OpenHABSender.from_config(oh) as sender:
        ex = Executor(sender, feedback=setup.readers.signal).start()

        def on_gesture(g):
            ops = profile.handle(g)
            if ops:
                log.info("%-10s %-22s -> %d Aktion(en)", g.reader, str(g), len(ops))
            ex.submit(ops)

        sink = bus if args.mqtt else NullSink()
        gw = NfcGateway(setup.verifier, setup.logic, setup.readers, sink,
                        GatewayEncoder(cfg.section("mqtt").get("base_topic", "nfc")), setup.keyring,
                        on_gesture=on_gesture)
        if bus is not None:
            bus.start()
        watcher = asyncio.create_task(rueckkanal(sender, profile, setup.readers, list(cfg.get("readers") or {})))
        try:
            await gw.run()
            await ex.drain()
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            await ex.stop()
            if bus is not None:
                bus.stop()


def main() -> int:
    ap = base_parser("NFC-Fernbedienung (Ansatz B)")
    add_source_args(ap)
    ap.add_argument("--profil", help="Kartenprofil (Standard: profile aus config.yaml)")
    ap.add_argument("--url", help="openHAB-URL (überschreibt config.yaml, ohne Token)")
    ap.add_argument("--mqtt", action="store_true", help="Ereignisse zusätzlich an MQTT (Hybrid)")
    ap.add_argument("--esp32", action="store_true", help="ESP32-Leser über MQTT einbinden")
    args = ap.parse_args()
    setup_logging(args.verbose)
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
