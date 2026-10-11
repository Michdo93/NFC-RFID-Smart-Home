"""
keys.py – alle Schlüssel aus einem einzigen Installationsgeheimnis ableiten (Kapitel 11).

Jede Installation hat ein zufälliges Geheimnis (32 Byte, Datei config/secret.key, Rechte
600). Daraus entstehen mit HKDF-SHA256 (RFC 5869) alle weiteren Schlüssel – für jeden
Zweck und, wo sinnvoll, für jede Karte einen eigenen:

  installation_id()        4 Byte   öffentlich: erkennt Karten der EIGENEN Installation
  mac_key()               32 Byte   HMAC-Schlüssel für das Kartenformat – bleibt im Gateway
  classic_key_a()          6 Byte   Lese-Schlüssel des Datensektors (darf auf den ESP32)
  classic_key_b(uid)       6 Byte   Schreib-Schlüssel, je Karte verschieden
  ntag_pwd(uid), ntag_pack(uid)     Passwort und PACK, je Karte verschieden

Wer einen Kartenschlüssel ausliest, kennt damit weder das Geheimnis noch die Schlüssel
anderer Karten. Fremde Installationen leiten aus IHREM Geheimnis völlig andere Werte ab.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from pathlib import Path

SALT = b"NFC-RFID-Smart-Home v1"


def hkdf(secret: bytes, info: bytes, length: int, salt: bytes = SALT) -> bytes:
    """HKDF-SHA256: Extract (PRK = HMAC(salt, secret)), dann Expand mit info."""
    prk = hmac.new(salt, secret, hashlib.sha256).digest()
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


class KeyRing:
    def __init__(self, secret: bytes):
        if len(secret) < 16:
            raise ValueError("Das Installationsgeheimnis muss mindestens 16 Byte haben")
        self._secret = bytes(secret)

    # -- laden und erzeugen ---------------------------------------------------------------
    @classmethod
    def load(cls, path) -> "KeyRing":
        p = Path(path)
        data = p.read_text(encoding="ascii").strip()
        mode = stat.S_IMODE(p.stat().st_mode)
        if os.name == "posix" and mode & 0o077:
            raise PermissionError(f"{p} ist für andere lesbar (Rechte {mode:o}) – bitte chmod 600")
        return cls(bytes.fromhex(data))

    @staticmethod
    def create(path) -> Path:
        p = Path(path)
        if p.exists():
            raise FileExistsError(f"{p} gibt es schon – ein neues Geheimnis macht alle Karten ungültig")
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(secrets.token_hex(32) + "\n")
        return p

    # -- abgeleitete Schlüssel --------------------------------------------------------------
    def derive(self, purpose: str, uid: bytes = b"", length: int = 32) -> bytes:
        return hkdf(self._secret, purpose.encode("ascii") + b"|" + uid, length)

    def installation_id(self) -> bytes:
        return self.derive("installation-id", length=4)

    def mac_key(self) -> bytes:
        return self.derive("card-mac")

    def classic_key_a(self) -> bytes:
        return self.derive("classic-key-a", length=6)

    def classic_key_b(self, uid: bytes) -> bytes:
        return self.derive("classic-key-b", uid, 6)

    def ntag_pwd(self, uid: bytes) -> bytes:
        return self.derive("ntag-pwd", uid, 4)

    def ntag_pack(self, uid: bytes) -> bytes:
        return self.derive("ntag-pack", uid, 2)

    def url_key(self) -> bytes:
        """Schlüssel für signierte Smartphone-URLs (Kapitel 29)."""
        return self.derive("phone-url")
