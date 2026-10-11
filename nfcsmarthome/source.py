"""
source.py – Schlüssel, Register, Prüfung und Leser aus config.yaml und Kommandozeile.

Gemeinsame Optionen aller Programme ab Kapitel 21:

  --sim SZENARIO.yaml   Simulator statt Hardware (Kapitel 9)
  --tempo 2             Szenario schneller abspielen
  --kein-acr122u        lokalen ACR122U nicht verwenden
  --stufe uid|signed|rolling   Sicherheitsstufe für alle Leser überschreiben

Ohne --sim werden die Leser aus dem Abschnitt „readers“ der config.yaml geöffnet:
type acr122u -> PcscReader (pyscard), type esp32 -> MqttReaders (über den Broker).
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .config import Config, REPO_ROOT
from .keys import KeyRing
from .logic import TagLogic
from .readers.base import Reader
from .readers.readerset import ReaderSet
from .registry import Registry
from .verify import Verifier

log = logging.getLogger("nfcsource")

DEFAULT_SECRET = "config/secret.key"
DEFAULT_REGISTRY = "data/karten.json"


def add_source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--sim", metavar="SZENARIO", help="Simulator: Szenario-Datei (YAML)")
    p.add_argument("--tempo", type=float, default=1.0, help="Szenario schneller abspielen (Faktor)")
    p.add_argument("--kein-acr122u", action="store_true", help="lokalen ACR122U nicht öffnen")
    p.add_argument("--stufe", choices=["uid", "signed", "rolling"], help="Sicherheitsstufe überschreiben")


def secret_path(cfg: Config) -> Path:
    return cfg.resolve(cfg.section("security").get("secret_file", DEFAULT_SECRET))


def load_keyring(cfg: Config, required: bool = True) -> Optional[KeyRing]:
    p = secret_path(cfg)
    if not p.exists():
        if required:
            raise FileNotFoundError(f"{p} fehlt – zuerst: python3 11-stufen/geheimnis_erzeugen.py")
        return None
    return KeyRing.load(p)


def load_registry(cfg: Config) -> Registry:
    return Registry(cfg.resolve(cfg.section("security").get("registry", DEFAULT_REGISTRY)))


@dataclass
class Setup:
    keyring: Optional[KeyRing]
    registry: Registry
    verifier: Verifier
    logic: TagLogic
    readers: ReaderSet


def build(args, cfg: Config, mqtt=None) -> Setup:
    sec = cfg.section("security")
    level = args.stufe or sec.get("level", "signed")
    readers_cfg = dict(cfg.get("readers") or {})
    if args.stufe:                                    # Kommandozeile gilt für alle Leser
        readers_cfg = {k: {**v, "level": args.stufe} for k, v in readers_cfg.items()}
    keyring = load_keyring(cfg, required=level != "uid")
    registry = load_registry(cfg)
    verifier = Verifier(keyring, registry, level, readers_cfg)
    logic = TagLogic.from_config(cfg.section("logic"))
    sources: List[Reader] = []
    if args.sim:
        from .readers.simreader import SimReader
        sim_file = Path(args.sim)
        if not sim_file.exists():
            sim_file = REPO_ROOT / args.sim
        sources.append(SimReader.from_file(sim_file, keyring, args.tempo))
    else:
        for name, rc in readers_cfg.items():
            if rc.get("type") == "acr122u" and not args.kein_acr122u:
                from .readers.pcsc import PcscReader
                sources.append(PcscReader(name, rc.get("match", "ACR122"), keyring))
        if mqtt is not None and any(rc.get("type") == "esp32" for rc in readers_cfg.values()):
            from .readers.mqttreader import MqttReaders
            sources.append(MqttReaders(mqtt, keyring))
    if not sources:
        raise SystemExit("Kein Leser: --sim SZENARIO angeben oder Leser in config.yaml eintragen")
    return Setup(keyring, registry, verifier, logic, ReaderSet(sources))
