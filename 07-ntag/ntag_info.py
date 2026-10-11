#!/usr/bin/env python3
"""
Kapitel 7 – Alles über ein NTAG: Typ, Speicher, CC, Schutz, NDEF, Zähler, Signatur.

Aufruf:  python3 07-ntag/ntag_info.py [--sim ntag215_karte_1] [--seiten]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs, ntag                            # noqa: E402
from nfcsmarthome.apdu import ApduError, CardError             # noqa: E402
from nfcsmarthome.cli import add_card_args, open_card          # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="NTAG-Informationen")
    add_card_args(ap)
    ap.add_argument("--seiten", action="store_true", help="Speicher seitenweise ausgeben")
    args = ap.parse_args()
    c = open_card(args)
    try:
        t = ntag.identify(c.acr)
    except (ntag.NtagError, CardError) as exc:
        sys.exit(f"Kein NTAG: {exc}")
    head = ntag.read_pages(c.acr, 0, 4)
    print(f"Typ:        {t.name} – {t.user_bytes} Byte Nutzspeicher, Seiten 4–{t.last_user_page}")
    print(f"UID:        {hexs(c.acr.uid(), ' ')}")
    print(f"Lock-Bytes: {hexs(head[10:12], ' ')}   CC: {hexs(head[12:16], ' ')}")
    cfg = ntag.read_config(c.acr, t)
    schutz = "keiner" if cfg["auth0"] == 0xFF else \
        f"ab Seite {cfg['auth0']} ({'Lesen und Schreiben' if cfg['prot'] else 'nur Schreiben'})"
    print(f"Passwort:   {schutz}")
    print(f"NFC-Zähler: {'an' if cfg['nfc_cnt_en'] else 'aus'}")
    try:
        print(f"Signatur:   {hexs(c.acr.ntag_read_sig()[:8], ' ')} … (32 Byte, NXP)")
        if cfg["nfc_cnt_en"]:
            print(f"Zählerstand: {c.acr.ntag_read_cnt()}")
    except (CardError, ApduError):
        pass
    records = ntag.read_ndef(c.acr, t)
    print(f"NDEF:       {len(records)} Record(s)")
    for r in records:
        print("            " + r.describe())
    if args.seiten:
        mem = ntag.read_pages(c.acr, 0, t.total_pages)
        for p in range(t.total_pages):
            print(f"  {p:3d} ({p:02X}h): {hexs(mem[4 * p:4 * p + 4], ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
