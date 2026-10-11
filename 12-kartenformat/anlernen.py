#!/usr/bin/env python3
"""
Kapitel 12 – Eine Karte anlernen: NFH-Nutzdaten schreiben, schützen, ins Register.

Aufruf:  python3 12-kartenformat/anlernen.py --name michael --rolle bewohner --wert Michael
         python3 12-kartenformat/anlernen.py --sim s50_karte_1 --name michael --rolle bewohner
         python3 12-kartenformat/anlernen.py --sim ntag215_karte_1 --name radio_swr3 \
                 --rolle medien --wert SWR3 --label "SWR3"

Rollen: bewohner, gast, szene, medien, admin.
--uri schreibt bei NTAG zusätzlich einen URI-Record (für Smartphones, Kapitel 28/29).
--nur-leser flur,kueche  beschränkt die Karte auf diese Leser.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs                                  # noqa: E402
from nfcsmarthome.cardformat import ROLE_CODES                 # noqa: E402
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402
from nfcsmarthome.personalize import PersonalizeError, personalize      # noqa: E402
from nfcsmarthome.source import load_registry                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Karte anlernen")
    add_card_args(ap)
    ap.add_argument("--name", required=True, help="eindeutiger Name, z. B. michael, gute_nacht")
    ap.add_argument("--rolle", required=True, choices=sorted(ROLE_CODES))
    ap.add_argument("--label", default="", help="Anzeigename")
    ap.add_argument("--wert", help="freier Wert, z. B. Sender einer Medienkarte")
    ap.add_argument("--uri", help="NTAG: zusätzlicher URI-Record")
    ap.add_argument("--nur-leser", help="kommagetrennte Liste erlaubter Leser")
    ap.add_argument("--ohne-zaehler", action="store_true", help="rollierenden Zähler nicht verwenden")
    args = ap.parse_args()
    cfg = config(args)
    kr = keyring(cfg)
    reg = load_registry(cfg)
    c = open_card(args)
    readers = args.nur_leser.split(",") if args.nur_leser else None
    try:
        card = personalize(c.acr, c.atr, kr, reg, args.name, args.rolle, args.label, args.wert,
                           args.uri, rolling=not args.ohne_zaehler, readers=readers)
    except PersonalizeError as exc:
        sys.exit(f"Nicht angelernt: {exc}")
    c.save()
    print(f"Karte Nr. {card.id} angelernt: {card.name} ({card.role}, {card.type})")
    print(f"  UID {card.uid} – Installations-ID {hexs(kr.installation_id(), ' ')}")
    if card.type == "classic1k":
        print("  Sektor 1: Key A = Lese-Schlüssel der Installation, Key B = Schlüssel dieser Karte")
    else:
        print("  NTAG: Schreiben ab Seite 4 mit dem Passwort dieser Karte geschützt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
