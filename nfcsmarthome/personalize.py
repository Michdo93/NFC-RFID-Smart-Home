"""
personalize.py – Karten anlernen und zurücksetzen (Kapitel 12).

Anlernen (am ACR122U oder Simulator):

  MIFARE Classic 1K
    1. Am Datensektor 1 mit dem Werksschlüssel anmelden
    2. NFH-Nutzdaten in Block 4 und 5 schreiben
    3. Trailer schreiben: Key A = Lese-Schlüssel der Installation,
       Key B = Schreib-Schlüssel DIESER Karte, Zugriffsbits 78 77 88
    4. Mit dem neuen Key A zurücklesen und prüfen

  NTAG213/215/216
    1. NDEF schreiben: optional ein URI-Record (für Smartphones), dazu der NFH-Record
    2. Passwort und PACK DIESER Karte setzen, AUTH0 = 4 (Schreiben ab Seite 4 geschützt)
    3. Zurücklesen und prüfen

Erst wenn alles geklappt hat, bleibt die Karte im Register.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from . import apdu as ap
from . import cardformat, classic, ndef, ntag
from .events import TagRead
from .keys import KeyRing
from .readers.common import DATA_BLOCKS, DATA_SECTOR, card_type, read_tag
from .registry import Card, Registry

log = logging.getLogger("nfcpersonalize")


class PersonalizeError(Exception):
    pass


def personalize(acr: ap.Acr122u, atr: bytes, keyring: KeyRing, registry: Registry, name: str,
                role: str, label: str = "", value: Optional[str] = None,
                uri: Optional[str] = None, rolling: bool = True,
                readers: Optional[List[str]] = None) -> Card:
    kind = card_type(atr, acr)
    uid = acr.uid()
    if kind not in ("classic1k", "ntag213", "ntag215", "ntag216"):
        raise PersonalizeError(f"Kartentyp {kind} wird nicht unterstützt")
    if role not in cardformat.ROLE_CODES:
        raise PersonalizeError(f"Rolle {role!r} unbekannt ({', '.join(cardformat.ROLE_CODES)})")
    if registry.by_uid(uid.hex()):
        raise PersonalizeError(f"Diese Karte ist schon als {registry.by_uid(uid.hex()).name!r} angelernt")
    card = registry.add(name, role, uid.hex(), kind, label, value, readers)
    try:
        data = cardformat.CardData(keyring.installation_id(), card.id, role, 0, rolling)
        payload = cardformat.encode(data, uid, keyring.mac_key())
        if kind == "classic1k":
            _classic(acr, keyring, uid, payload)
        else:
            _ntag(acr, keyring, uid, payload, uri)
        check = read_tag(acr, "anlernen", atr, keyring)
        from .verify import nfh_payload
        if nfh_payload(check) != payload:
            raise PersonalizeError("Zurücklesen ergab andere Daten")
    except Exception:
        registry.cards.pop(card.id, None)       # nichts Halbfertiges im Register lassen
        registry.save()
        raise
    log.info("Karte %s (%s, %s) angelernt als Nr. %d", name, role, kind, card.id)
    return card


def _classic(acr: ap.Acr122u, keyring: KeyRing, uid: bytes, payload: bytes) -> None:
    first = DATA_SECTOR * 4
    if not acr.login(first, classic.FACTORY_KEY, ap.KEY_A):
        raise PersonalizeError("Sektor 1 nicht im Werkszustand (Werksschlüssel abgelehnt)")
    for i, block in enumerate(DATA_BLOCKS):
        acr.write_block(block, payload[16 * i:16 * (i + 1)])
    trailer = classic.make_trailer(keyring.classic_key_a(), keyring.classic_key_b(uid))
    classic.write_trailer(acr, DATA_SECTOR, classic.FACTORY_KEY, ap.KEY_A, trailer)


def _ntag(acr: ap.Acr122u, keyring: KeyRing, uid: bytes, payload: bytes, uri: Optional[str]) -> None:
    t = ntag.identify(acr)
    cfg = ntag.read_config(acr, t)
    if cfg["auth0"] != 0xFF:
        raise PersonalizeError("Tag ist schon passwortgeschützt – erst zurücksetzen")
    records = [ndef.Record.uri(uri)] if uri else []
    records.append(ndef.Record.external(cardformat.NDEF_TYPE, payload))
    ntag.format_cc(acr, t)
    ntag.write_ndef(acr, t, records)
    ntag.set_password(acr, t, keyring.ntag_pwd(uid), keyring.ntag_pack(uid), auth0=4, prot=False)


def reset(acr: ap.Acr122u, atr: bytes, keyring: KeyRing, registry: Optional[Registry] = None) -> str:
    """Karte in den Werkszustand zurücksetzen (nur Karten DIESER Installation)."""
    kind = card_type(atr, acr)
    uid = acr.uid()
    if kind == "classic1k":
        key_b = keyring.classic_key_b(uid)
        if not acr.login(DATA_SECTOR * 4, key_b, ap.KEY_B):
            raise PersonalizeError("Key B abgelehnt – Karte gehört nicht zu dieser Installation")
        for block in (4, 5, 6):
            acr.write_block(block, bytes(16))
        factory = classic.FACTORY_KEY + classic.FACTORY_ACCESS + b"\x69" + classic.FACTORY_KEY
        acr.write_block(classic.trailer_of(DATA_SECTOR), factory)
    elif kind.startswith("ntag"):
        t = ntag.identify(acr)
        if ntag.read_config(acr, t)["auth0"] != 0xFF:
            ntag.remove_password(acr, t, keyring.ntag_pwd(uid))
        acr.write_page(4, bytes([0x03, 0x00, 0xFE, 0x00]))
    else:
        raise PersonalizeError(f"Kartentyp {kind} wird nicht unterstützt")
    if registry is not None:
        card = registry.by_uid(uid.hex())
        if card:
            registry.cards.pop(card.id)
            registry.save()
    return kind


def roll(acr: ap.Acr122u, read: TagRead, keyring: KeyRing, payload: bytes) -> bool:
    """Neuen Zähler schreiben (Wrapper für readers.common.write_payload)."""
    from .readers.common import write_payload
    return write_payload(acr, read, keyring, payload)


def renew(acr: ap.Acr122u, atr: bytes, keyring: KeyRing, registry: Registry) -> Card:
    """
    NFH-Nutzdaten einer Karte DIESER Installation neu schreiben (Kapitel 13).

    Für Karten, die nach einem abgerissenen Schreibvorgang „invalid“ sind oder deren
    Zähler aus dem Tritt geraten ist. Die Daten kommen aus dem Register, nicht von der
    Karte; der neue Zähler liegt eins über dem Register. Geschrieben wird mit Key B bzw.
    dem Passwort dieser Karte – eine fremde Karte lässt sich so nicht „erneuern“.
    """
    read = read_tag(acr, "erneuern", atr, keyring)
    card = registry.by_uid(read.uid_hex)
    if card is None:
        raise PersonalizeError("UID nicht im Register – Karte erst anlernen")
    if card.blocked:
        raise PersonalizeError(f"Karte '{card.name}' ist gesperrt – erst entsperren")
    data = cardformat.CardData(keyring.installation_id(), card.id, card.role, card.counter + 1)
    payload = cardformat.encode(data, read.uid, keyring.mac_key())
    from .readers.common import write_payload
    if not write_payload(acr, read, keyring, payload):
        raise PersonalizeError("Schreiben fehlgeschlagen – Karte liegen lassen und wiederholen")
    registry.commit_counter(card.id, data.counter)
    return card
