#!/usr/bin/env python3
"""
Kapitel 16 – Ein ESP32-Leser ohne ESP32: verhält sich am Broker wie die Firmware.

Legt nacheinander virtuelle Karten auf und nimmt sie wieder ab. Schreibbefehle des
Gateways (rollierender Zähler) führt der Simulator aus und speichert die Karten.

Aufruf:  python3 16-esp32-firmware/esp32_simulator.py --leser flur \
                 --karten s50_karte_1 ntag216_armband [--liegen 2.0] [--pause 1.0]
"""

import argparse
import getpass
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.cli import config, keyring                    # noqa: E402
from nfcsmarthome.esp32sim import Esp32Sim                      # noqa: E402
from nfcsmarthome.readers.sim import load_card, save_card       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="ESP32-Simulator")
    ap.add_argument("--leser", default="flur")
    ap.add_argument("--karten", nargs="+", required=True)
    ap.add_argument("--liegen", type=float, default=2.0, help="Sekunden je Karte")
    ap.add_argument("--pause", type=float, default=1.0)
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--passwort", action="store_true", help="MQTT-Passwort abfragen (Benutzer = Leser)")
    ap.add_argument("--config")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg = config(args)
    m = cfg.section("mqtt")
    pw = getpass.getpass("MQTT-Passwort: ") if args.passwort else None
    esp = Esp32Sim(args.leser, keyring(cfg).classic_key_a(), args.host or m.get("host", "localhost"),
                   args.port or int(m.get("port", 1883)), args.leser if pw else None, pw,
                   m.get("base_topic", "nfc"), on_signal=lambda s: print(f"           Signal: {s}"))
    esp.start()
    time.sleep(0.5)
    for name in args.karten:
        card = load_card(name)
        raw = esp.place(card)
        print(f"aufgelegt  {name:<16} {raw['type']:<10} UID {raw['uid']}")
        time.sleep(args.liegen)
        save_card(name, card)                      # was das Gateway geschrieben hat, behalten
        esp.remove()
        print(f"entfernt   {name}")
        time.sleep(args.pause)
    esp.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
