#!/usr/bin/env python3
"""
Kapitel 7 – Eine NDEF-Nachricht auf ein NTAG schreiben (URL und/oder Text).

Aufruf:  python3 07-ntag/ndef_schreiben.py --url https://www.openhab.org [--text "Hallo"]
         python3 07-ntag/ndef_schreiben.py --sim ntag215_karte_2 --text "Küche"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import ndef, ntag                            # noqa: E402
from nfcsmarthome.apdu import ApduError                        # noqa: E402
from nfcsmarthome.cli import add_card_args, open_card          # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="NDEF schreiben")
    add_card_args(ap)
    ap.add_argument("--url")
    ap.add_argument("--text")
    args = ap.parse_args()
    records = ([ndef.Record.uri(args.url)] if args.url else []) + \
              ([ndef.Record.text(args.text)] if args.text else [])
    if not records:
        ap.error("--url und/oder --text angeben")
    c = open_card(args)
    t = ntag.identify(c.acr)
    try:
        pages = ntag.write_ndef(c.acr, t, records)
    except ApduError as exc:
        sys.exit(f"Schreiben abgelehnt – Tag geschützt? ({exc})")
    c.save()
    print(f"{pages} Seiten geschrieben ({pages * 4} von {t.user_bytes} Byte)")
    for r in ntag.read_ndef(c.acr, t):
        print("  " + r.describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
