#!/usr/bin/env python3
"""
Kapitel 29 – Einen Benutzer für den Tag-Dienst anlegen (Passwort als Hash, Datei 600).

Aufruf:  python3 29-signierte-urls/benutzer_anlegen.py michael
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.config import try_load_config                 # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Benutzer anlegen")
    ap.add_argument("name")
    ap.add_argument("--config")
    args = ap.parse_args()
    cfg = try_load_config(args.config)
    p = cfg.resolve(cfg.section("phone").get("users_file", "config/tagdienst_benutzer.json"))
    users = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    pw = getpass.getpass(f"Passwort für {args.name}: ")
    if len(pw) < 10 or pw != getpass.getpass("Noch einmal: "):
        sys.exit("Passwörter verschieden oder kürzer als 10 Zeichen")
    users[args.name] = generate_password_hash(pw)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(users, fh, indent=2)
    print(f"{args.name} gespeichert in {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
