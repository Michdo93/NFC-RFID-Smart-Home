#!/usr/bin/env python3
"""
Kapitel 8 – Einen Datenblock beschreiben (16 Byte) und zurücklesen.

Sektor 0 Block 0 ist der Herstellerblock, jeder vierte Block ein Trailer – beides lehnt
das Skript ab. Für Trailer gibt es classic.write_trailer() mit Prüfung der Zugriffsbits.

Aufruf:  python3 08-mifare-classic/classic_schreiben.py --block 8 --text "Hallo Labor" [--sim s50_karte_2]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import apdu, classic, hexs, unhex            # noqa: E402
from nfcsmarthome.cli import add_card_args, open_card          # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Block schreiben")
    add_card_args(ap)
    ap.add_argument("--block", type=int, required=True)
    ap.add_argument("--text", help="Text (wird auf 16 Byte aufgefüllt)")
    ap.add_argument("--hex", help="16 Byte hex")
    ap.add_argument("--key", default="FFFFFFFFFFFF", help="Key A (hex), Standard: Werksschlüssel")
    args = ap.parse_args()
    if args.block == 0 or classic.is_trailer(args.block):
        sys.exit("Block 0 und Sektor-Trailer schreibt dieses Skript nicht")
    data = unhex(args.hex) if args.hex else (args.text or "").encode("utf-8")[:16].ljust(16, b"\x00")
    c = open_card(args)
    if not c.acr.login(args.block, unhex(args.key), apdu.KEY_A):
        sys.exit(f"Anmeldung an Sektor {classic.sector_of(args.block)} abgelehnt")
    try:
        c.acr.write_block(args.block, data)
    except apdu.ApduError as exc:
        sys.exit(f"Schreiben abgelehnt (Zugriffsbits?): {exc}")
    c.save()
    print(f"Block {args.block}: {hexs(c.acr.read_block(args.block), ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
