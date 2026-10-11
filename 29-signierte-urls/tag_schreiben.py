#!/usr/bin/env python3
"""
Kapitel 29 – Eine signierte URL auf ein NTAG schreiben und den Tag schützen.

Aufruf:  python3 29-signierte-urls/tag_schreiben.py --tag kueche_wand --aktion licht_kueche \
                 [--sim ntag215_karte_2] [--nur-zeigen]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import ndef, ntag                             # noqa: E402
from nfcsmarthome.cli import add_card_args, config, keyring, open_card   # noqa: E402
from nfcsmarthome.phone import signed_url                       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="signierte URL schreiben")
    add_card_args(ap)
    ap.add_argument("--tag", required=True, help="Tag-ID, z. B. kueche_wand")
    ap.add_argument("--aktion", required=True, help="Aktion aus aktionen.yaml")
    ap.add_argument("--nur-zeigen", action="store_true", help="URL nur ausgeben")
    args = ap.parse_args()
    cfg = config(args)
    kr = keyring(cfg)
    base = cfg.section("phone").get("base_url", "https://home.local:8443")
    url = signed_url(base, kr.url_key(), args.tag, args.aktion)
    print(url)
    if args.nur_zeigen:
        return 0
    c = open_card(args)
    t = ntag.identify(c.acr)
    uid = c.acr.uid()
    if ntag.read_config(c.acr, t)["auth0"] != 0xFF:
        ntag.authenticate(c.acr, kr.ntag_pwd(uid))
    ntag.format_cc(c.acr, t)
    ntag.write_ndef(c.acr, t, [ndef.Record.uri(url)])
    if ntag.read_config(c.acr, t)["auth0"] == 0xFF:
        ntag.set_password(c.acr, t, kr.ntag_pwd(uid), kr.ntag_pack(uid), auth0=4)
    c.save()
    print(f"auf {t.name} geschrieben und gegen Überschreiben geschützt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
