"""Bausteine ohne Leser: APDUs, NDEF, Zugriffsbits, Schlüssel, Kartenformat."""
import pytest

from nfcsmarthome import apdu, cardformat, classic, ndef, ntag
from nfcsmarthome.keys import KeyRing, hkdf


def test_apdus():
    assert apdu.apdu_get_uid() == [0xFF, 0xCA, 0x00, 0x00, 0x00]
    assert apdu.apdu_load_key(b"\xFF" * 6) == [0xFF, 0x82, 0x00, 0x00, 0x06] + [0xFF] * 6
    assert apdu.apdu_authenticate(4, apdu.KEY_B) == [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, 4, 0x61, 0]
    assert apdu.apdu_update(5, b"abcd")[:5] == [0xFF, 0xD6, 0x00, 5, 4]
    with pytest.raises(ValueError):
        apdu.apdu_update(5, b"abc")


def test_ndef_roundtrip():
    recs = [ndef.Record.uri("https://home.local/t/flur/licht?s=x"), ndef.Record.text("Hallo"),
            ndef.Record.external("home.arpa:nfh", bytes(32))]
    data = ndef.encode_message(recs)
    back = ndef.decode_message(data)
    assert back == recs
    assert back[0].as_uri() == "https://home.local/t/flur/licht?s=x"
    assert back[0].payload[0] == 0x04                      # Präfix "https://"
    assert back[1].as_text() == "Hallo"
    tlv = ndef.wrap_tlv(data)
    assert ndef.find_ndef_tlv(b"\x00" + tlv + b"\x00" * 8) == data


def test_ndef_long_record():
    rec = ndef.Record.text("x" * 300)
    assert ndef.decode_message(ndef.encode_message([rec])) == [rec]


def test_access_bits():
    assert classic.encode_access_bits([(0, 0, 0)] * 3 + [(0, 0, 1)]) == classic.FACTORY_ACCESS
    assert classic.encode_access_bits(classic.HOUSE_CONDITIONS) == bytes([0x78, 0x77, 0x88])
    assert classic.decode_access_bits(bytes([0x78, 0x77, 0x88])) == classic.HOUSE_CONDITIONS
    with pytest.raises(classic.ClassicError):
        classic.decode_access_bits(bytes([0xFF, 0xFF, 0xFF]))
    assert classic.check_data_access(bytes([0x78, 0x77, 0x88]), 0, "A", write=False)
    assert not classic.check_data_access(bytes([0x78, 0x77, 0x88]), 0, "A", write=True)


def test_value_block():
    vb = classic.value_block(100, 4)
    assert vb[0:4] == (100).to_bytes(4, "little") and vb[12:16] == bytes([4, 0xFB, 4, 0xFB])


def test_keys_are_separated():
    a, b = KeyRing(b"A" * 32), KeyRing(b"B" * 32)
    uid1, uid2 = bytes.fromhex("5A3F9C21"), bytes.fromhex("8E117B04")
    assert a.installation_id() != b.installation_id()
    assert a.classic_key_b(uid1) != a.classic_key_b(uid2)
    assert len(a.classic_key_a()) == 6 and len(a.ntag_pwd(uid1)) == 4 and len(a.ntag_pack(uid1)) == 2
    # RFC 5869, Testfall 1 (SHA-256)
    okm = hkdf(bytes.fromhex("0b" * 22), bytes.fromhex("f0f1f2f3f4f5f6f7f8f9"), 42,
               salt=bytes.fromhex("000102030405060708090a0b0c"))
    assert okm.hex().startswith("3cb25f25faacd57a90434f64d0362f2a")


def test_keyring_file_permissions(tmp_path):
    p = KeyRing.create(tmp_path / "secret.key")
    assert len(KeyRing.load(p).installation_id()) == 4
    p.chmod(0o644)
    with pytest.raises(PermissionError):
        KeyRing.load(p)
    with pytest.raises(FileExistsError):
        KeyRing.create(p)


def test_cardformat(keyring):
    uid = bytes.fromhex("5A3F9C21")
    data = cardformat.CardData(keyring.installation_id(), 7, "gast", 3)
    raw = cardformat.encode(data, uid, keyring.mac_key())
    assert len(raw) == 32 and raw[:3] == b"NFH"
    assert cardformat.parse(raw) == data
    assert cardformat.verify_mac(raw, uid, keyring.mac_key())
    assert not cardformat.verify_mac(raw, bytes.fromhex("5A3F9C22"), keyring.mac_key())
    tampered = raw[:12] + bytes([5]) + raw[13:]                 # Rolle Gast -> Admin
    assert not cardformat.verify_mac(tampered, uid, keyring.mac_key())


def test_ntag_types():
    assert ntag.NTAG215.cc == bytes([0xE1, 0x10, 0x3E, 0x00])          # Datenblatt, Werkszustand
    assert ntag.NTAG216.pwd == 0xE5 and ntag.NTAG213.pack == 0x2C
