"""
config.py – lädt config/config.yaml (wird NICHT eingecheckt, siehe .gitignore).

Suchreihenfolge:
  1. ausdrücklich übergebener Pfad (--config)
  2. Pfad aus der Umgebungsvariable NFC_CONFIG
  3. ./config.yaml im aktuellen Verzeichnis
  4. <Repo>/config/config.yaml

Vorlage: config/config.example.yaml  ->  cp config/config.example.yaml config/config.yaml

Das Installationsgeheimnis (security.secret) steht NICHT in der config.yaml, sondern
in einer eigenen Datei (Standard: config/secret.key, Rechte 600) – erzeugt mit
  python3 11-stufen/geheimnis_erzeugen.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class Config(dict):
    path: Optional[Path] = None

    def section(self, name: str) -> Dict[str, Any]:
        return dict(self.get(name) or {})

    def resolve(self, value: Optional[str]) -> Optional[Path]:
        """Relative Pfade aus der Konfiguration beziehen sich auf das Repo."""
        if not value:
            return None
        p = Path(value)
        return p if p.is_absolute() else REPO_ROOT / p


def find_config_path(explicit: Optional[str] = None) -> Path:
    candidates = [explicit, os.environ.get("NFC_CONFIG"), "config.yaml",
                  str(REPO_ROOT / "config" / "config.yaml")]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    raise FileNotFoundError(
        "Keine config.yaml gefunden. Bitte zuerst anlegen:\n"
        f"  cp {REPO_ROOT / 'config' / 'config.example.yaml'} {REPO_ROOT / 'config' / 'config.yaml'}")


def load_config(path: Optional[str] = None) -> Config:
    p = find_config_path(path)
    with open(p, encoding="utf-8") as fh:
        cfg = Config(yaml.safe_load(fh) or {})
    cfg.path = p
    return cfg


def try_load_config(path: Optional[str] = None) -> Config:
    """Wie load_config, aber ohne Fehler: ohne config.yaml gibt es eine leere Konfiguration."""
    try:
        return load_config(path)
    except FileNotFoundError:
        return Config()


def load_yaml(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
