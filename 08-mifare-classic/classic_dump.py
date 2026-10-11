#!/usr/bin/env python3
"""
Kapitel 8 – Alle Sektoren einer MIFARE Classic 1K lesen, die sich mit einem Schlüssel öffnen.

Standard ist der Werksschlüssel FF FF FF FF FF FF. Mit --installation werden der Lese-
schlüssel unserer Installation (Key A) und der Kartenschlüssel (Key B) zusätzlich probiert.

Aufruf:  python3 08-mifare-classic/classic_dump.py [--sim s50_karte_1] [--key A0A1A2A3A4A5]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import apdu, classic, hexs, unhex            # noqa: E402
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402


def printable(b: bytes) -> str:
    return "".join(chr(x) if 32 <= x < 127 else "." for x in b)


def main() -> int:
    ap = argparse.ArgumentParser(description="MIFARE Classic auslesen")
    add_card_args(ap)
    ap.add_argument("--key", action="append", default=[], help="weiterer Schlüssel (hex), mehrfach möglich")
    ap.add_argument("--installation", action="store_true", help="Schlüssel der Installation probieren")
    args = ap.parse_args()
    c = open_card(args)
    uid = c.acr.uid()
    keys = [("Werk A", classic.FACTORY_KEY, apdu.KEY_A)] + \
           [(f"--key {k}", unhex(k), apdu.KEY_A) for k in args.key]
    if args.installation:
        kr = keyring(config(args))
        keys += [("Install. A", kr.classic_key_a(), apdu.KEY_A), ("Karte B", kr.classic_key_b(uid), apdu.KEY_B)]
    m = classic.ManufacturerBlock
    for sector in range(16):
        opened = None
        for label, key, kt in keys:
            if c.acr.login(sector * 4, key, kt):
                opened = label
                break
        if not opened:
            print(f"Sektor {sector:2d}: gesperrt – keiner der Schlüssel passt")
            continue
        print(f"Sektor {sector:2d}: geöffnet mit {opened}")
        for i in range(4):
            block = sector * 4 + i
            try:
                data = c.acr.read_block(block)
            except apdu.ApduError:
                print(f"   {block:2d}  (Lesen nicht erlaubt)")
                continue
            note = ""
            if block == 0:
                mb = m.parse(data)
                note = f"  UID {hexs(mb.uid)}, BCC {'ok' if mb.bcc_ok else 'FALSCH'}, SAK {mb.sak:02X}"
            elif i == 3:
                note = f"  Bits {hexs(data[6:9], ' ')}"
            else:
                note = f"  {printable(data)}"
            print(f"   {block:2d}  {hexs(data, ' ')}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
