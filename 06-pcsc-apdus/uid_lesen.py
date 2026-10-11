#!/usr/bin/env python3
"""
Kapitel 6 – Die erste APDU: Firmware, ATR und UID der aufgelegten Karte.

Aufruf:  python3 06-pcsc-apdus/uid_lesen.py            (ACR122U, Karte auflegen)
         python3 06-pcsc-apdus/uid_lesen.py --sim s50_karte_1
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs                                  # noqa: E402
from nfcsmarthome.cli import add_card_args, open_card          # noqa: E402
from nfcsmarthome.readers.common import card_type              # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="UID lesen")
    add_card_args(ap)
    args = ap.parse_args()
    c = open_card(args)
    c.acr.log = []                                   # APDUs mitschneiden
    print(f"Leser:    {c.acr.firmware()}")
    print(f"ATR:      {hexs(c.atr, ' ')}")
    print(f"Typ:      {card_type(c.atr, c.acr)}")
    uid = c.acr.uid()
    print(f"UID:      {hexs(uid, ' ')}  ({len(uid)} Byte)")
    print("\nAPDUs:")
    for apdu, data, sw1, sw2 in c.acr.log:
        print(f"  > {hexs(bytes(apdu), ' ')}")
        print(f"  < {(hexs(data, ' ') + ' ') if data else ''}{sw1:02X} {sw2:02X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
