#!/usr/bin/env python3
"""
Kapitel 31 – Den Kartensatz des Labors anlernen.

  s50_karte_1      michael      bewohner   (Wert „Michael“ -> iAnwesend_Michael)
  s50_karte_2      gute_nacht   szene
  s50_karte_3      kinoabend    szene
  s50_karte_4      admin        admin
  ntag215_karte_1  radio_swr3   medien     (Wert „SWR3“)
  ntag215_karte_2  radio_dasding medien    (Wert „DASDING“)
  ntag216_armband  gast_lea     gast       (nur an flur und kueche)
  ntag213_sticker  – bleibt unbekannt (für die Vorführung)

Mit --sim werden die virtuellen Karten zuerst auf den Werkszustand gesetzt.
Ohne --sim fordert das Skript nacheinander jede Karte am ACR122U an.

Aufruf:  python3 31-labor-szenarien/labor_karten_anlernen.py --sim
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.cli import config, keyring                    # noqa: E402
from nfcsmarthome.personalize import PersonalizeError, personalize   # noqa: E402
from nfcsmarthome.readers.sim import reset_card                 # noqa: E402
from nfcsmarthome.readers.simreader import open_single          # noqa: E402
from nfcsmarthome.source import load_registry                    # noqa: E402

KARTEN = [
    ("s50_karte_1", "michael", "bewohner", "Michael", "Michael", None),
    ("s50_karte_2", "gute_nacht", "szene", "Gute Nacht", None, None),
    ("s50_karte_3", "kinoabend", "szene", "Kinoabend", None, None),
    ("s50_karte_4", "admin", "admin", "Admin", None, None),
    ("ntag215_karte_1", "radio_swr3", "medien", "SWR3", "SWR3", None),
    ("ntag215_karte_2", "radio_dasding", "medien", "DASDING", "DASDING", None),
    ("ntag216_armband", "gast_lea", "gast", "Lea", "Lea", ["flur", "kueche"]),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Laborkarten anlernen")
    ap.add_argument("--sim", action="store_true", help="virtuelle Karten verwenden")
    ap.add_argument("--config")
    args = ap.parse_args()
    cfg = config(args)
    kr = keyring(cfg)
    reg = load_registry(cfg)
    for sim_name, name, role, label, value, readers in KARTEN:
        if reg.by_name(name):
            print(f"{name:<14} schon im Register – übersprungen")
            continue
        if args.sim:
            reset_card(sim_name)
        else:
            input(f"Karte für „{label}“ ({role}) auflegen und Enter drücken … ")
        c = open_single(sim_name if args.sim else None)
        try:
            card = personalize(c.acr, c.atr, kr, reg, name, role, label, value, readers=readers)
        except PersonalizeError as exc:
            print(f"{name:<14} NICHT angelernt: {exc}")
            continue
        c.save()
        print(f"{name:<14} Nr. {card.id}  {role:<9} {card.type}")
    if args.sim:
        reset_card("ntag213_sticker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
