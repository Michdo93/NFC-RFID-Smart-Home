"""
common.py – eine aufgelegte Karte erkennen und auslesen (für ACR122U und Simulator).

  card_type(atr, acr)  ATR auswerten (PC/SC Teil 3), bei Ultralight-Familie GET_VERSION
  read_tag(...)        UID, Typ und – falls möglich – die NFH-Nutzdaten lesen
  write_payload(...)   neue NFH-Nutzdaten schreiben (rollierender Zähler, Kapitel 13)
"""

from __future__ import annotations

import logging
from typing import Optional

from .. import apdu as ap
from .. import cardformat, classic, ntag
from ..events import TagRead
from ..keys import KeyRing
from ..verify import replace_nfh

log = logging.getLogger("nfcreader")

DATA_SECTOR = 1                     # Sektor 1 = Blöcke 4, 5, 6 (Trailer 7)
DATA_BLOCKS = (4, 5)

ATR_NAMES = {(0x00, 0x01): "classic1k", (0x00, 0x02): "classic4k", (0x00, 0x03): "ultralight",
             (0x00, 0x26): "mifare_mini", (0xF0, 0x04): "topaz", (0xF0, 0x11): "felica"}


def card_type(atr: bytes, acr: Optional[ap.Acr122u] = None) -> str:
    """Kartentyp aus dem ATR; NTAG meldet sich als „Ultralight“ – GET_VERSION unterscheidet."""
    name = "unbekannt"
    if len(atr) >= 15 and atr[4:7] == b"\x80\x4F\x0C" and atr[7:12] == b"\xA0\x00\x00\x03\x06":
        name = ATR_NAMES.get((atr[13], atr[14]), "unbekannt")
    if name == "ultralight" and acr is not None:
        try:
            name = ntag.identify(acr).name.lower()
        except (ntag.NtagError, ap.CardError, ap.ApduError):
            pass
    return name


def read_tag(acr: ap.Acr122u, reader: str, atr: bytes, keyring: Optional[KeyRing] = None) -> TagRead:
    uid = acr.uid()
    kind = card_type(atr, acr)
    read = TagRead(reader, uid, kind)
    try:
        if kind == "classic1k" and keyring is not None:
            if acr.login(DATA_BLOCKS[0], keyring.classic_key_a(), ap.KEY_A):
                read.payload = b"".join(acr.read_block(b) for b in DATA_BLOCKS)
                if read.payload[:3] != cardformat.MAGIC:
                    read.payload = None
        elif kind.startswith("ntag"):
            t = ntag.TYPES[{"ntag213": 0x0F, "ntag215": 0x11, "ntag216": 0x13}[kind]]
            read.records = ntag.read_ndef(acr, t)
    except (ap.ApduError, ap.CardError, ntag.NtagError, ValueError) as exc:
        log.debug("Nutzdaten nicht lesbar: %s", exc)
    return read


def changed_blocks(old: Optional[bytes], new: bytes) -> dict:
    """
    Nur die Blöcke, die sich ändern. Beim Hochzählen ist das bis Zähler 65535 nur
    Block 5 – ein einziger Schreibbefehl, der abreißen kann (Kapitel 13).
    """
    out = {}
    for i, block in enumerate(DATA_BLOCKS):
        chunk = new[16 * i:16 * (i + 1)]
        if old is None or old[16 * i:16 * (i + 1)] != chunk:
            out[block] = chunk
    return out


def write_payload(acr: ap.Acr122u, read: TagRead, keyring: KeyRing, payload: bytes) -> bool:
    """
    NFH-Nutzdaten auf die aufgelegte Karte schreiben und zurücklesen.
    Classic: mit dem Key B DIESER Karte. NTAG: nach PWD_AUTH mit dem Passwort DIESER Karte.
    """
    if len(payload) != cardformat.SIZE:
        raise ValueError("NFH-Nutzdaten haben 32 Byte")
    if acr.uid() != read.uid:
        log.warning("Andere Karte aufgelegt – Schreiben abgebrochen")
        return False
    try:
        if read.tag_type == "classic1k":
            if not acr.login(DATA_BLOCKS[0], keyring.classic_key_b(read.uid), ap.KEY_B):
                log.warning("Key B abgelehnt – Karte nicht von dieser Installation personalisiert?")
                return False
            for block, data in changed_blocks(read.payload, payload).items():
                acr.write_block(block, data)                    # meist nur Block 5
            back = b"".join(acr.read_block(b) for b in DATA_BLOCKS)
            return back == payload
        if read.tag_type.startswith("ntag"):
            t = ntag.identify(acr)
            ntag.authenticate(acr, keyring.ntag_pwd(read.uid), keyring.ntag_pack(read.uid))
            records = replace_nfh(read.records, payload)
            ntag.write_ndef(acr, t, records)
            back = ntag.read_ndef(acr, t)
            return back == records
    except (ap.ApduError, ap.CardError, ntag.NtagError, classic.ClassicError) as exc:
        log.warning("Schreiben fehlgeschlagen: %s", exc)
    return False
