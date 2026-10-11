#!/usr/bin/env python3
"""
Kapitel 7 – Passwortschutz eines NTAG setzen, prüfen und entfernen.

Ohne --pwd nimmt das Skript Passwort und PACK, die aus dem Installationsgeheimnis für
GENAU DIESES Tag abgeleitet werden (Kapitel 11). Mit --pwd/--pack von Hand (hex).

Aufruf:  python3 07-ntag/ntag_passwort.py --setzen  [--lesen-schuetzen] [--sim ntag215_karte_2]
         python3 07-ntag/ntag_passwort.py --pruefen
         python3 07-ntag/ntag_passwort.py --entfernen
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs, ntag, unhex                     # noqa: E402
from nfcsmarthome.apdu import CardError                        # noqa: E402
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="NTAG-Passwort")
    add_card_args(ap)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--setzen", action="store_true")
    g.add_argument("--pruefen", action="store_true")
    g.add_argument("--entfernen", action="store_true")
    ap.add_argument("--pwd", help="Passwort, 4 Byte hex (sonst abgeleitet)")
    ap.add_argument("--pack", help="PACK, 2 Byte hex (sonst abgeleitet)")
    ap.add_argument("--lesen-schuetzen", action="store_true", help="PROT=1: auch Lesen schützen")
    ap.add_argument("--ab-seite", type=lambda s: int(s, 0), default=4, help="AUTH0 (Standard 4)")
    args = ap.parse_args()
    c = open_card(args)
    t = ntag.identify(c.acr)
    uid = c.acr.uid()
    if args.pwd:
        pwd, pack = unhex(args.pwd), unhex(args.pack or "0000")
    else:
        kr = keyring(config(args))
        pwd, pack = kr.ntag_pwd(uid), kr.ntag_pack(uid)
    try:
        if args.setzen:
            if ntag.read_config(c.acr, t)["auth0"] != 0xFF:
                ntag.authenticate(c.acr, pwd)
            ntag.set_password(c.acr, t, pwd, pack, auth0=args.ab_seite, prot=args.lesen_schuetzen)
            print(f"Passwort gesetzt, Schutz ab Seite {args.ab_seite}"
                  f"{' (auch Lesen)' if args.lesen_schuetzen else ''}")
        elif args.pruefen:
            got = ntag.authenticate(c.acr, pwd)
            print(f"Passwort angenommen, PACK {hexs(got, ' ')} – {'passt' if got == pack else 'FALSCH'}")
        else:
            ntag.remove_password(c.acr, t, pwd)
            print("Passwortschutz entfernt (AUTH0 = FF)")
    except (CardError, ntag.NtagError) as exc:
        sys.exit(f"Abgelehnt: {exc} – Tag neu auflegen, bevor Sie es erneut versuchen")
    c.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
