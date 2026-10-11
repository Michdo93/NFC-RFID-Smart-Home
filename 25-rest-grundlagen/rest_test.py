#!/usr/bin/env python3
"""
Kapitel 25 – Erste Schritte mit python-openhab-rest-client (synchron).

Liest einen Zustand, sendet einen Befehl, liest erneut und misst die Zeit.
Ohne openHAB:  python3 00-virtuelle-geraete/mini_openhab.py  (zweites Terminal)

Aufruf:  python3 25-rest-grundlagen/rest_test.py [--item iSmartHome_Hue_Lampen_Schalter]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.config import try_load_config   # noqa: E402

from openhab import Items, OpenHABClient              # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="REST-Grundlagen")
    ap.add_argument("--item", default="iSmartHome_Hue_Lampen_Schalter")
    ap.add_argument("--url", help="überschreibt openhab.url aus config.yaml")
    args = ap.parse_args()
    oh = try_load_config().section("openhab")
    url = args.url or oh.get("url", "http://127.0.0.1:8080")

    client = OpenHABClient(url=url, token=oh.get("token"))
    items = Items(client)

    t0 = time.perf_counter()
    vorher = items.getItemState(args.item)
    t1 = time.perf_counter()
    neu = "OFF" if str(vorher).strip() == "ON" else "ON"
    items.sendCommand(args.item, neu)
    t2 = time.perf_counter()
    nachher = items.getItemState(args.item)
    t3 = time.perf_counter()

    print(f"openHAB:  {url}")
    print(f"vorher:   {args.item} = {vorher}   ({(t1 - t0) * 1000:.0f} ms)")
    print(f"Befehl:   {neu}                       ({(t2 - t1) * 1000:.0f} ms)")
    print(f"nachher:  {args.item} = {nachher}   ({(t3 - t2) * 1000:.0f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
