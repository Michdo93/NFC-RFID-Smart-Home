#!/usr/bin/env python3
"""
Kapitel 5 – Ist alles bereit? Prüft Python, Bibliotheken, pcscd, Kernel-Module und Leser.

Aufruf:  python3 05-installation/pruefen.py
"""

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ok(text, good, hint=""):
    print(f"[{'OK' if good else '--'}] {text}" + (f"   -> {hint}" if not good and hint else ""))
    return good


def main() -> int:
    good = ok(f"Python {sys.version.split()[0]}", sys.version_info >= (3, 9), "Python 3.9 oder neuer")
    for mod, hint in (("yaml", "pip install pyyaml"), ("paho.mqtt", "pip install paho-mqtt"),
                      ("openhab", "pip install -r requirements.txt"), ("flask", "pip install flask"),
                      ("smartcard", "sudo apt install swig libpcsclite-dev && pip install pyscard")):
        try:
            importlib.import_module(mod)
            ok(f"Modul {mod}", True)
        except ImportError:
            good &= ok(f"Modul {mod}", False, hint)
    if shutil.which("systemctl"):
        # pcscd startet über pcscd.socket bei Bedarf und beendet sich ohne Clients (--auto-exit)
        def active(unit):
            return subprocess.run(["systemctl", "is-active", unit], capture_output=True,
                                  text=True).stdout.strip() == "active"
        running = active("pcscd.socket") or active("pcscd.service")
        good &= ok(f"pcscd: {'bereit' if running else 'nicht aktiv'}", running,
                   "sudo apt install pcscd libccid && sudo systemctl enable --now pcscd.socket")
    import grp
    import os
    try:
        member = grp.getgrnam("nfc").gr_gid in os.getgroups()
    except KeyError:
        member = False
    ok("Gruppe nfc (pcscd über SSH, polkit)", member,
       "sudo groupadd --system nfc && sudo usermod -aG nfc $USER, neu anmelden (Kapitel 5)")
    try:
        mods = Path("/proc/modules").read_text()
        good &= ok("Kernel-Modul pn533 nicht geladen", "pn533" not in mods,
                   "05-installation/blacklist-pn533.conf nach /etc/modprobe.d/ kopieren")
    except OSError:
        pass
    try:
        from smartcard.System import readers
        names = [str(r) for r in readers()]
        good &= ok(f"Leser: {', '.join(names) or 'keiner'}", any("ACR122" in n for n in names),
                   "ACR122U eingesteckt? pcsc_scan zeigt mehr")
    except Exception as exc:
        ok(f"Leser nicht abfragbar ({exc})", False)
    cfg = ROOT / "config" / "config.yaml"
    ok("config/config.yaml vorhanden", cfg.exists(), "cp config/config.example.yaml config/config.yaml")
    ok("config/secret.key vorhanden", (ROOT / "config" / "secret.key").exists(),
       "python3 11-stufen/geheimnis_erzeugen.py (Kapitel 11)")
    print("\nOhne Leser funktionieren alle Skripte mit --sim (Simulator).")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
