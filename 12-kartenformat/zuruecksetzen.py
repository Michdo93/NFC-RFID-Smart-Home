#!/usr/bin/env python3
"""
Kapitel 12 – Eine Karte DIESER Installation in den Werkszustand zurücksetzen
und aus dem Register entfernen.

Aufruf:  python3 12-kartenformat/zuruecksetzen.py [--sim s50_karte_1]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402
from nfcsmarthome.personalize import PersonalizeError, reset    # noqa: E402
from nfcsmarthome.source import load_registry                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Karte zurücksetzen")
    add_card_args(ap)
    args = ap.parse_args()
    cfg = config(args)
    c = open_card(args)
    try:
        kind = reset(c.acr, c.atr, keyring(cfg), load_registry(cfg))
    except PersonalizeError as exc:
        sys.exit(str(exc))
    c.save()
    print(f"{kind} zurückgesetzt – Werksschlüssel bzw. kein Passwort, Register bereinigt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
