#!/usr/bin/env python3
"""
Kapitel 12 – Eine Karte lesen und prüfen (ohne Zähler zu schreiben).

Aufruf:  python3 12-kartenformat/karte_pruefen.py [--sim s50_karte_1] [--stufe signed]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import cardformat, hexs                      # noqa: E402
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402
from nfcsmarthome.readers.common import read_tag               # noqa: E402
from nfcsmarthome.source import load_registry                   # noqa: E402
from nfcsmarthome.verify import Verifier, nfh_payload           # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Karte prüfen")
    add_card_args(ap)
    ap.add_argument("--stufe", choices=["uid", "signed", "rolling"], default="signed")
    args = ap.parse_args()
    cfg = config(args)
    kr = keyring(cfg)
    c = open_card(args)
    read = read_tag(c.acr, "pruefen", c.atr, kr)
    print(f"UID {read.uid_hex} ({read.tag_type})")
    raw = nfh_payload(read)
    if raw is not None:
        data = cardformat.parse(raw)
        print(f"NFH: Version {data.version}, Installation {hexs(data.installation, ' ')}, "
              f"Karte {data.card_id}, Rolle {data.role}, Zähler {data.counter}")
        print(f"     MAC {hexs(raw[18:32], ' ')}")
    d = Verifier(kr, load_registry(cfg), args.stufe).verify(read)
    print(f"Ergebnis: {d.status}" + (f" – {d.message}" if d.message else "")
          + (f" – {d.card.label} ({d.card.role})" if d.ok else ""))
    return 0 if d.ok else 2


if __name__ == "__main__":
    sys.exit(main())
