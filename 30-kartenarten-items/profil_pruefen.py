#!/usr/bin/env python3
"""
Kapitel 30 – Ein Kartenprofil gegen die Items prüfen – vor dem ersten Auflegen.

Setzt für jeden Eintrag alle Leser und alle Karten der passenden Rolle aus dem
Kartenregister ein und prüft jedes Ziel-Item auf Existenz und passenden Befehl.

Aufruf:  python3 30-kartenarten-items/profil_pruefen.py 31-labor-szenarien/profile/labor.yaml \
                 --items 00-virtuelle-geraete/openhab/items
         python3 30-kartenarten-items/profil_pruefen.py PROFIL --url http://openhab.local:8080
         python3 30-kartenarten-items/profil_pruefen.py        (Profil und openHAB aus config.yaml)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.actions import CardProfile                    # noqa: E402
from nfcsmarthome.check import check_profile                    # noqa: E402
from nfcsmarthome.config import try_load_config                 # noqa: E402
from nfcsmarthome.source import load_registry                   # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00-virtuelle-geraete"))


def items_from_dir(path):
    from mini_openhab import parse_items
    items = {}
    for p in sorted(Path(path).glob("*.items")):
        items.update(parse_items(p.read_text(encoding="utf-8")))
    return items


def items_from_rest(url, token):
    from openhab import Items, OpenHABClient
    data = Items(OpenHABClient(url=url, token=token)).getItems()
    return {i["name"]: i for i in data}


def main() -> int:
    ap = argparse.ArgumentParser(description="Kartenprofil prüfen")
    ap.add_argument("profil", nargs="?", help="Kartenprofil (Standard: profile aus config.yaml)")
    ap.add_argument("--items", help="Verzeichnis mit .items-Dateien (offline)")
    ap.add_argument("--url", help="openHAB-URL (sonst openhab.url aus config.yaml)")
    ap.add_argument("--config")
    args = ap.parse_args()
    cfg = try_load_config(args.config)
    if args.items:
        items = items_from_dir(args.items)
    else:
        oh = cfg.section("openhab")
        url = args.url or oh.get("url")
        if not url:
            sys.exit("Weder --items noch --url angegeben, und config.yaml hat keine openhab.url")
        items = items_from_rest(url, None if args.url else oh.get("token"))
    cards = list(load_registry(cfg).cards.values())
    path = args.profil or cfg.get("profile")
    if not path:
        sys.exit("Kein Profil angegeben und keins in config.yaml (profile:)")
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).resolve().parents[1] / path
    profile = CardProfile.load(path)
    errors, n = check_profile(profile, items, cards)
    for e in errors:
        print(f"FEHLER {e}")
    print(f"{profile.name}: {n} Ziele mit {len(cards)} Karten, {len(errors)} Fehler")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
