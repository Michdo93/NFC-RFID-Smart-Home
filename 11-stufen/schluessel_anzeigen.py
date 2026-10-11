#!/usr/bin/env python3
"""
Kapitel 11 – Welche Schlüssel entstehen aus dem Geheimnis? (nur zur Anschauung)

Ohne --zeigen werden Schlüssel gekürzt ausgegeben. Mit --uid für eine bestimmte Karte.

Aufruf:  python3 11-stufen/schluessel_anzeigen.py --uid 5A3F9C21 --uid 8E117B04
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs, unhex                           # noqa: E402
from nfcsmarthome.cli import config, keyring                    # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="abgeleitete Schlüssel")
    ap.add_argument("--uid", action="append", default=[])
    ap.add_argument("--zeigen", action="store_true", help="Schlüssel vollständig anzeigen")
    ap.add_argument("--config")
    args = ap.parse_args()
    kr = keyring(config(args))

    def k(b: bytes) -> str:
        h = hexs(b, " ")
        return h if args.zeigen else h[:5] + " …"

    print(f"Installations-ID (öffentlich):  {hexs(kr.installation_id(), ' ')}")
    print(f"MAC-Schlüssel (32 Byte):        {k(kr.mac_key())}")
    print(f"Classic Key A (alle Karten):    {k(kr.classic_key_a())}")
    for u in args.uid:
        uid = unhex(u)
        print(f"\nKarte {hexs(uid, ' ')}:")
        print(f"  Classic Key B:                {k(kr.classic_key_b(uid))}")
        print(f"  NTAG-Passwort / PACK:         {k(kr.ntag_pwd(uid))} / {k(kr.ntag_pack(uid))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
