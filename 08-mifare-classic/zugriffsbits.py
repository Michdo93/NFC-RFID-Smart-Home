#!/usr/bin/env python3
"""
Kapitel 8 – Zugriffsbits kodieren und erklären (ohne Karte).

Aufruf:  python3 08-mifare-classic/zugriffsbits.py                 Werkszustand und unsere Belegung
         python3 08-mifare-classic/zugriffsbits.py --bits 787788
         python3 08-mifare-classic/zugriffsbits.py --bedingungen 100,100,100,011
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import classic, hexs, unhex                  # noqa: E402


def show(title: str, access: bytes) -> None:
    print(f"{title}: {hexs(access, ' ')}")
    try:
        for line in classic.describe_access(access):
            print("   " + line)
    except classic.ClassicError as exc:
        print(f"   UNGÜLTIG: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Zugriffsbits")
    ap.add_argument("--bits", help="3 Byte hex, z. B. FF0780")
    ap.add_argument("--bedingungen", help="C1C2C3 für Block 0,1,2,Trailer, z. B. 100,100,100,011")
    args = ap.parse_args()
    if args.bits:
        show("Bits", unhex(args.bits))
    elif args.bedingungen:
        cond = [tuple(int(ch) for ch in part) for part in args.bedingungen.split(",")]
        show("Ergebnis", classic.encode_access_bits(cond))
    else:
        show("Werkszustand (Transport)", classic.FACTORY_ACCESS)
        print()
        show("Unsere Belegung (Kapitel 12)", classic.encode_access_bits(classic.HOUSE_CONDITIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
