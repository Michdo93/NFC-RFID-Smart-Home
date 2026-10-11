"""
cli.py – Hilfen für die Kapitelskripte.

  add_card_args(p)   --sim KARTE (virtuelle Karte statt ACR122U), --leser TEXT
  open_card(args)    -> readers.simreader.Single (acr, atr, save) – mit Fehlermeldung,
                        wenn kein Leser oder keine Karte da ist
  keyring(cfg)       Installationsgeheimnis laden oder mit Hinweis beenden
"""

from __future__ import annotations

import argparse
import sys

from .config import Config, try_load_config
from .keys import KeyRing
from .readers.simreader import Single, open_single


def add_card_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--sim", metavar="KARTE",
                   help="virtuelle Karte statt ACR122U, z. B. s50_karte_1 oder ntag215_karte_1")
    p.add_argument("--leser", default="ACR122", help="Teil des Lesernamens (Standard: ACR122)")
    p.add_argument("--config", help="Pfad zur config.yaml")


def open_card(args) -> Single:
    try:
        return open_single(args.sim, args.leser)
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    except ImportError:
        sys.exit("pyscard fehlt (Kapitel 5) – oder mit --sim KARTE den Simulator verwenden")
    except Exception as exc:                       # NoCardException, kein Leser ...
        sys.exit(f"Keine Karte am Leser? ({type(exc).__name__}: {exc})")


def config(args) -> Config:
    return try_load_config(getattr(args, "config", None))


def keyring(cfg: Config) -> KeyRing:
    from .source import load_keyring
    try:
        return load_keyring(cfg)
    except (FileNotFoundError, PermissionError) as exc:
        sys.exit(str(exc))
