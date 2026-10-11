"""
phone.py – Tags für Smartphones (Kapitel 28 und 29).

1. openHAB-Android-App
   Die App schreibt und liest Tags mit einer URI der Form
       openhab://?i=<Item>&s=<Zustand>
   Beim Antippen sendet die App den Befehl – mit IHREN Zugangsdaten. Ein fremdes
   Handy ohne eingerichtete App kann nichts auslösen, aber den Tag überschreiben.

2. Signierte URL für den eigenen Tag-Dienst (Kapitel 29)
       https://home.local:8443/t/<tag-id>/<aktion>?s=<signatur>
   Die Signatur (HMAC-SHA256, 128 Bit, Base64url) bindet Tag-ID und Aktion an das
   Installationsgeheimnis. Wer den Tag umschreibt, um eine andere Aktion auszulösen,
   hat keine gültige Signatur. Wer den Tag kopiert, hat dieselbe URL – deshalb verlangt
   der Dienst zusätzlich ein angemeldetes Gerät.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import Optional, Tuple
from urllib.parse import quote, urlsplit, parse_qs

SIG_LEN = 16                     # Byte -> 22 Zeichen Base64url
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def openhab_uri(item: str, state: str) -> str:
    return f"openhab://?i={quote(item)}&s={quote(state)}"


def _sig(key: bytes, tag_id: str, action: str) -> str:
    mac = hmac.new(key, f"{tag_id}|{action}".encode("utf-8"), hashlib.sha256).digest()[:SIG_LEN]
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def signed_url(base: str, key: bytes, tag_id: str, action: str) -> str:
    if not ID_RE.match(tag_id) or not ID_RE.match(action):
        raise ValueError("Tag-ID und Aktion: Kleinbuchstaben, Ziffern, _ und -, max. 32 Zeichen")
    return f"{base.rstrip('/')}/t/{tag_id}/{action}?s={_sig(key, tag_id, action)}"


def check_signature(key: bytes, tag_id: str, action: str, sig: str) -> bool:
    return hmac.compare_digest(_sig(key, tag_id, action), sig or "")


def parse_signed_url(url: str) -> Optional[Tuple[str, str, str]]:
    parts = urlsplit(url)
    m = re.match(r"^.*/t/([^/]+)/([^/?]+)$", parts.path)
    if not m:
        return None
    sig = parse_qs(parts.query).get("s", [""])[0]
    return m.group(1), m.group(2), sig
