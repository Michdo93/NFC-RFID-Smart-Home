#!/usr/bin/env python3
"""
Kapitel 13 – Nutzdaten einer Karte dieser Installation neu schreiben.

Hilft, wenn eine Karte nach einem abgerissenen Schreibvorgang „invalid“ meldet.
Die Daten stammen aus dem Kartenregister; der Zähler wird eins über das Register gesetzt.

Aufruf:  python3 13-rollierender-zaehler/karte_erneuern.py [--sim s50_karte_1]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402
from nfcsmarthome.personalize import PersonalizeError, renew    # noqa: E402
from nfcsmarthome.source import load_registry                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Karte erneuern")
    add_card_args(ap)
    args = ap.parse_args()
    cfg = config(args)
    c = open_card(args)
    try:
        card = renew(c.acr, c.atr, keyring(cfg), load_registry(cfg))
    except PersonalizeError as exc:
        sys.exit(str(exc))
    c.save()
    print(f"Karte Nr. {card.id} '{card.name}' erneuert – Zähler jetzt {card.counter}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
