#!/usr/bin/env python3
"""
Kapitel 15 – include/secrets.h für die ESP32-Firmware anlegen.

Trägt den Lese-Schlüssel (Key A) der Installation ein und fragt WLAN- und MQTT-Daten
ab. Passwörter werden verdeckt eingegeben. Die Datei ist gitignored.

Aufruf:  python3 15-esp32-hardware/secrets_erzeugen.py --leser flur [--broker 192.168.0.10]
         mit TLS:  ... --port 8883 --ca /etc/mosquitto/certs/ca.crt
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.cli import config, keyring                    # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware" / "nfc-leser" / "include" / "secrets.h"


def c_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    ap = argparse.ArgumentParser(description="secrets.h erzeugen")
    ap.add_argument("--leser", required=True, help="Name des Lesers = MQTT-Benutzer, z. B. flur")
    ap.add_argument("--broker", default="192.168.0.10")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--ssid")
    ap.add_argument("--ca", help="CA-Zertifikat des Brokers (PEM) – schaltet TLS ein")
    ap.add_argument("--ausgabe", default=str(TARGET))
    ap.add_argument("--config")
    args = ap.parse_args()
    out = Path(args.ausgabe)
    if out.exists():
        sys.exit(f"{out} gibt es schon – bitte zuerst löschen")
    kr = keyring(config(args))
    ssid = args.ssid or input("WLAN-Name (SSID): ")
    wlan = getpass.getpass("WLAN-Passwort: ")
    mqtt = getpass.getpass(f"MQTT-Passwort für Benutzer '{args.leser}': ")
    key = ", ".join(f"0x{b:02X}" for b in kr.classic_key_a())
    ca = ""
    if args.ca:
        lines = Path(args.ca).read_text(encoding="ascii").strip().splitlines()
        ca = "#define MQTT_CA_PEM    \\\n" + " \\\n".join(f'  "{ln}\\n"' for ln in lines) + "\n"
    text = f"""// Erzeugt von 15-esp32-hardware/secrets_erzeugen.py – NICHT einchecken
#pragma once
#define WIFI_SSID      {c_str(ssid)}
#define WIFI_PASS      {c_str(wlan)}
#define MQTT_HOST      {c_str(args.broker)}
#define MQTT_PORT      {args.port}
#define MQTT_USER      {c_str(args.leser)}
#define MQTT_PASS      {c_str(mqtt)}
#define MQTT_BASE      "nfc"
#define LESER_NAME     {c_str(args.leser)}
#define KEY_A          {{ {key} }}
{ca}"""
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"{out} angelegt (Rechte 600). Bauen und flashen:")
    print("  cd firmware/nfc-leser && pio run -e pn532 -t upload    # bzw. -e rc522")
    return 0


if __name__ == "__main__":
    sys.exit(main())
