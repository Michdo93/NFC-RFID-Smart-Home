#!/usr/bin/env python3
"""
Kapitel 11 – Das Installationsgeheimnis erzeugen (einmal je Installation).

32 zufällige Byte aus secrets.token_hex, gespeichert in config/secret.key mit Rechten 600.
Ein zweites Mal verweigert das Skript: Ein neues Geheimnis macht alle Karten ungültig.

Sichern Sie die Datei (z. B. ausgedruckt im Tresor) – wer sie hat, kann Karten fälschen;
wer sie verliert, muss alle Karten neu anlernen.

Aufruf:  python3 11-stufen/geheimnis_erzeugen.py [--datei config/secret.key]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs, rel                             # noqa: E402
from nfcsmarthome.config import try_load_config                 # noqa: E402
from nfcsmarthome.keys import KeyRing                           # noqa: E402
from nfcsmarthome.source import secret_path                     # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Installationsgeheimnis erzeugen")
    ap.add_argument("--datei", help="Zieldatei (Standard: security.secret_file aus config.yaml)")
    args = ap.parse_args()
    target = Path(args.datei) if args.datei else secret_path(try_load_config())
    try:
        p = KeyRing.create(target)
    except FileExistsError as exc:
        print(exc)
        return 1
    kr = KeyRing.load(p)
    print(f"Geheimnis gespeichert: {rel(p)} (Rechte 600)")
    print(f"Installations-ID:      {hexs(kr.installation_id(), ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
