"""Kapitelskripte mit dem Simulator einmal ausführen (ohne Leser, ohne openHAB)."""
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT


@pytest.fixture
def repo(tmp_path):
    """Eigene Kopie von config/secret.key und data/ – das echte Repo bleibt unberührt."""
    cfg = tmp_path / "config.yaml"
    (tmp_path / "secret.key").write_text("00" * 32 + "\n")
    (tmp_path / "secret.key").chmod(0o600)
    cfg.write_text(f"""
security: {{level: rolling, secret_file: {tmp_path / 'secret.key'}, registry: {tmp_path / 'karten.json'}}}
readers:
  nachttisch: {{type: acr122u}}
  kueche: {{type: esp32}}
  flur: {{type: esp32, roles: [bewohner, gast, admin]}}
  multimedia: {{type: esp32}}
logic: {{hold_time: 1.5, absent_time: 0.3}}
""")
    sim = ROOT / "data" / "sim"
    backup = tmp_path / "sim-backup"
    if sim.exists():
        shutil.copytree(sim, backup)
        shutil.rmtree(sim)
    yield cfg
    if sim.exists():
        shutil.rmtree(sim)
    if backup.exists():
        shutil.copytree(backup, sim)


def run(*args, cfg=None, ok=True, timeout=90):
    env = {"NFC_CONFIG": str(cfg)} if cfg else {}
    import os
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
                       timeout=timeout, env={**os.environ, **env})
    if ok:
        assert r.returncode == 0, r.stderr + r.stdout
    return r.stdout + r.stderr


def test_offline_scripts():
    assert "home.arpa:nfh" in run("03-tags-ndef/ndef_zerlegen.py")
    assert "78 77 88" in run("08-mifare-classic/zugriffsbits.py")
    assert "accepted   <- nicht zu unterscheiden" in run("10-angriffsmodell/klon_im_simulator.py")
    out = run("13-rollierender-zaehler/zaehler_demo.py")
    assert "=> clone" in out and "Alarme im Register: 1" in out


def test_card_scripts(repo):
    assert "UID:      5A 3F 9C 21" in run("06-pcsc-apdus/uid_lesen.py", "--sim", "s50_karte_1")
    assert "48 61 6C 6C 6F" in run("08-mifare-classic/classic_schreiben.py", "--sim", "s50_karte_2",
                                "--block", "8", "--text", "Hallo Labor")
    assert "4 Seiten" in run("07-ntag/ndef_schreiben.py", "--sim", "ntag213_sticker", "--text", "Hallo")
    assert "aufgelegt" in run("09-ereignisse/gesten.py", "--sim", "sim/szenarien/auflegen.yaml")
    out = run("31-labor-szenarien/labor_karten_anlernen.py", "--sim", cfg=repo)
    assert "gast_lea" in out
    assert "accepted" in run("12-kartenformat/karte_pruefen.py", "--sim", "s50_karte_1", cfg=repo)
    assert "gast_lea" in run("12-kartenformat/karten.py", cfg=repo)
    errors = run("30-kartenarten-items/profil_pruefen.py", "31-labor-szenarien/profile/labor.yaml",
                 "--items", "00-virtuelle-geraete/openhab/items", cfg=repo)
    assert "0 Fehler" in errors
    out = run("21-nfc-gateway/nfc_gateway.py", "--sim", "sim/szenarien/rundgang.yaml", "--dry-run",
              "--tempo", "4", cfg=repo)
    assert "nfc/nachttisch/event       michael:tap" in out
    assert '"status": "unknown"' in out
    assert "zurückgesetzt" in run("12-kartenformat/zuruecksetzen.py", "--sim", "s50_karte_3", cfg=repo)
