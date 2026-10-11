#!/usr/bin/env python3
"""
Kapitel 28 – Einen Tag für die openHAB-Android-App schreiben und gegen Überschreiben schützen.

Die App versteht URIs der Form openhab://?i=<Item>&s=<Zustand>. Sie kann solche Tags
selbst schreiben – dieses Skript macht dasselbe am ACR122U und setzt anschließend das
Passwort DIESES Tags (aus dem Installationsgeheimnis abgeleitet). Lesen bleibt für jedes
Handy möglich, Überschreiben nicht mehr.

Aufruf:  python3 28-smartphone-tags/openhab_app_tag.py --item iKueche_Hue_Lampen_Schalter \
                 --zustand TOGGLE [--sim ntag215_karte_2] [--ohne-schutz]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import ndef, ntag                             # noqa: E402
from nfcsmarthome.apdu import ApduError                         # noqa: E402
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402
from nfcsmarthome.phone import openhab_uri                      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag für die openHAB-App")
    add_card_args(ap)
    ap.add_argument("--item", required=True)
    ap.add_argument("--zustand", required=True, help="ON, OFF, TOGGLE, 50, ...")
    ap.add_argument("--ohne-schutz", action="store_true", help="kein Passwort setzen")
    args = ap.parse_args()
    c = open_card(args)
    t = ntag.identify(c.acr)
    uri = openhab_uri(args.item, args.zustand)
    kr = None if args.ohne_schutz else keyring(config(args))
    uid = c.acr.uid()
    try:
        if ntag.read_config(c.acr, t)["auth0"] != 0xFF and kr:
            ntag.authenticate(c.acr, kr.ntag_pwd(uid))
        ntag.format_cc(c.acr, t)
        ntag.write_ndef(c.acr, t, [ndef.Record.uri(uri)])
        if kr and ntag.read_config(c.acr, t)["auth0"] == 0xFF:
            ntag.set_password(c.acr, t, kr.ntag_pwd(uid), kr.ntag_pack(uid), auth0=4)
    except (ApduError, ntag.NtagError) as exc:
        sys.exit(f"Schreiben fehlgeschlagen: {exc}")
    c.save()
    print(f"Geschrieben: {uri}")
    print("Schutz:      " + ("keiner – jedes Handy kann den Tag überschreiben" if args.ohne_schutz
                            else "Passwort dieses Tags, Schreiben ab Seite 4 gesperrt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
