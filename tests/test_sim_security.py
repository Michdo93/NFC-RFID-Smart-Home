"""Simulator, Anlernen, Prüfen und rollierender Zähler – das Herz von Teil III."""
import pytest
from conftest import acr_for

from nfcsmarthome import apdu, classic, ntag, ndef
from nfcsmarthome.keys import KeyRing
from nfcsmarthome.personalize import PersonalizeError, personalize, reset
from nfcsmarthome.readers.common import read_tag, write_payload
from nfcsmarthome.readers.sim import VirtualClassic, VirtualNtag
from nfcsmarthome.registry import Registry
from nfcsmarthome.verify import Verifier

UID_C1, UID_C2 = bytes.fromhex("5A3F9C21"), bytes.fromhex("8E117B04")
UID_N1 = bytes.fromhex("045B2A1AF36C80")


def setup(keyring, kind="classic", level="rolling", **readers):
    card = VirtualClassic.factory(UID_C1) if kind == "classic" else VirtualNtag.factory("ntag215", UID_N1)
    acr, sim = acr_for(card)
    reg = Registry(None)
    personalize(acr, card.atr, keyring, reg, "michael", "bewohner",
                uri="https://home.local/x" if kind != "classic" else None)
    return card, acr, sim, reg, Verifier(keyring, reg, level, readers)


def test_firmware_and_uid(keyring):
    acr, _ = acr_for(VirtualClassic.factory(UID_C1))
    assert acr.firmware() == "ACR122U215"
    assert acr.uid() == UID_C1


@pytest.mark.parametrize("kind", ["classic", "ntag"])
def test_accept_and_roll(keyring, kind):
    card, acr, sim, reg, v = setup(keyring, kind)
    r = read_tag(acr, "flur", card.atr, keyring)
    d = v.verify(r)
    assert d.status == "accepted" and d.data.counter == 0 and d.next_payload
    assert write_payload(acr, r, keyring, d.next_payload)
    v.commit(d)
    assert reg.by_name("michael").counter == 1
    assert v.verify(r).status == "clone"                     # alter Stand = Kopie
    assert reg.by_name("michael").alarms == 1
    d2 = v.verify(read_tag(acr, "flur", card.atr, keyring))
    assert d2.status == "accepted" and d2.data.counter == 1


def test_classic_trailer_after_personalize(keyring):
    card, acr, *_ = setup(keyring)
    assert bytes(card.blocks[7][6:9]) == bytes([0x78, 0x77, 0x88])
    # Ein Smartphone mit Werksschlüssel kommt nicht mehr an Sektor 1
    assert not acr.login(4, classic.FACTORY_KEY, apdu.KEY_A)
    # mit Key A lesen geht, schreiben nicht
    assert acr.login(4, keyring.classic_key_a(), apdu.KEY_A)
    with pytest.raises(apdu.ApduError):
        acr.write_block(4, bytes(16))


def test_ntag_password(keyring):
    card, acr, sim, *_ = setup(keyring, "ntag")
    t = ntag.identify(acr)
    assert ntag.read_config(acr, t)["auth0"] == 4
    recs = ntag.read_ndef(acr, t)                            # Lesen ohne Passwort geht
    assert recs[0].as_uri() == "https://home.local/x"
    with pytest.raises(apdu.ApduError):                      # Schreiben nicht
        acr.write_page(4, bytes(4))
    with pytest.raises(apdu.CardError):
        acr.ntag_pwd_auth(b"\xFF\xFF\xFF\xFF")               # Werkspasswort abgelehnt
    sim.place(card)                                          # nach NAK: neu auflegen
    assert ntag.authenticate(acr, keyring.ntag_pwd(UID_N1), keyring.ntag_pack(UID_N1))


def test_uid_level(keyring):
    card, acr, sim, reg, _ = setup(keyring)
    v = Verifier(None, reg, "uid")
    assert v.verify(read_tag(acr, "x", card.atr)).status == "accepted"
    other = VirtualClassic.factory(UID_C2)
    sim.place(other)
    assert v.verify(read_tag(acr, "x", other.atr)).status == "unknown"


def test_copy_to_other_card_is_invalid(keyring):
    card, acr, sim, reg, v = setup(keyring)
    good = read_tag(acr, "flur", card.atr, keyring)
    other = VirtualClassic.factory(UID_C2)                   # Daten auf andere Karte kopiert
    good.uid = UID_C2
    assert v.verify(good).status == "invalid"


def test_foreign_installation(keyring):
    card, acr, sim, reg, v = setup(keyring)
    foreign = Verifier(KeyRing(b"N" * 32), Registry(None), "signed")
    r = read_tag(acr, "flur", card.atr, KeyRing(b"N" * 32))
    assert r.payload is None                                 # fremder Key A: Sektor nicht lesbar
    r = read_tag(acr, "flur", card.atr, keyring)
    assert foreign.verify(r).status == "foreign"


def test_blocked_and_roles(keyring):
    card, acr, sim, reg, v = setup(keyring, level="signed", flur={"roles": ["gast"]})
    r = read_tag(acr, "flur", card.atr, keyring)
    assert v.verify(r).status == "not_allowed"
    r.reader = "nachttisch"
    assert v.verify(r).status == "accepted"
    assert v.verify(r).next_payload is None                  # Stufe signed: kein Zähler
    reg.block("michael")
    assert v.verify(r).status == "blocked"


def test_reset_and_repersonalize(keyring):
    card, acr, sim, reg, v = setup(keyring)
    with pytest.raises(PersonalizeError):
        personalize(acr, card.atr, keyring, reg, "nochmal", "gast")
    assert reset(acr, card.atr, keyring, reg) == "classic1k"
    assert not reg.cards
    assert acr.login(4, classic.FACTORY_KEY, apdu.KEY_A)
    personalize(acr, card.atr, keyring, reg, "neu", "gast")


def test_invalid_trailer_bricks_sector_in_sim():
    card = VirtualClassic.factory(UID_C1)
    acr, _ = acr_for(card)
    assert acr.login(7, classic.FACTORY_KEY)
    acr.write_block(7, b"\xFF" * 6 + b"\xFF\xFF\xFF\x69" + b"\xFF" * 6)   # ungültige Bits
    assert not acr.login(4, classic.FACTORY_KEY)
    with pytest.raises(classic.ClassicError):                # unsere Funktion verweigert so etwas
        classic.write_trailer(acr, 2, classic.FACTORY_KEY, apdu.KEY_A, b"\xFF" * 16)


def test_ntag_static_lock_and_cc_otp():
    card = VirtualNtag.factory("ntag213", bytes.fromhex("0412C47AB25E80"))
    acr, _ = acr_for(card)
    t = ntag.identify(acr)
    assert t.name == "NTAG213"
    with pytest.raises(ntag.NtagError):
        ntag.lock_permanently(acr, t)
    ntag.lock_permanently(acr, t, confirm="UNWIDERRUFLICH")
    with pytest.raises(apdu.ApduError):
        acr.write_page(4, bytes(4))
    with pytest.raises(ntag.NtagError):
        ntag.write_ndef(acr, t, [ndef.Record.text("x")], check_cc=True)


def test_ntag_counter_and_signature():
    card = VirtualNtag.factory("ntag216", bytes.fromhex("04A731529D6181"))
    acr, sim = acr_for(card)
    t = ntag.identify(acr)
    ntag.set_password(acr, t, b"1234", b"ok", auth0=0xFF, nfc_counter=True)
    sim.place(card)
    ntag.read_pages(acr, 4, 1)
    sim.place(card)
    ntag.read_pages(acr, 4, 1)
    assert acr.ntag_read_cnt() == 2
    assert len(acr.ntag_read_sig()) == 32
