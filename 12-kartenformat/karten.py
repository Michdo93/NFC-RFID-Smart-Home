#!/usr/bin/env python3
"""
Kapitel 12 – Das Kartenregister anzeigen, Karten sperren und entsperren.

Aufruf:  python3 12-kartenformat/karten.py
         python3 12-kartenformat/karten.py --sperren gast_lea
         python3 12-kartenformat/karten.py --entsperren gast_lea
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.config import try_load_config                 # noqa: E402
from nfcsmarthome.source import load_registry                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Kartenregister")
    ap.add_argument("--sperren")
    ap.add_argument("--entsperren")
    ap.add_argument("--config")
    args = ap.parse_args()
    reg = load_registry(try_load_config(args.config))
    try:
        if args.sperren:
            print(f"gesperrt: {reg.block(args.sperren).name}")
        if args.entsperren:
            print(f"entsperrt: {reg.block(args.entsperren, False).name}")
    except KeyError as exc:
        sys.exit(f"Karte {exc} unbekannt")
    print(f"{'Nr':>3}  {'Name':<14} {'Rolle':<9} {'Typ':<10} {'Zähler':>6}  {'Status':<9} {'zuletzt'}")
    for c in sorted(reg.cards.values(), key=lambda c: c.id):
        status = "GESPERRT" if c.blocked else ("ALARM" if c.alarms else "ok")
        last = f"{c.last_seen or '-'} {c.last_reader or ''}".strip()
        print(f"{c.id:>3}  {c.name:<14} {c.role:<9} {c.type:<10} {c.counter:>6}  {status:<9} {last}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
