"""Smartphone-Tags: openHAB-URI, signierte URL, Tag-Dienst."""
import json
import re

from werkzeug.security import generate_password_hash

from conftest import load_script
from nfcsmarthome.keys import KeyRing
from nfcsmarthome.phone import check_signature, openhab_uri, parse_signed_url, signed_url


def test_uris(keyring):
    assert openhab_uri("iKueche_Hue_Lampen_Schalter", "TOGGLE") == "openhab://?i=iKueche_Hue_Lampen_Schalter&s=TOGGLE"
    url = signed_url("https://home.local:8443", keyring.url_key(), "kueche_wand", "licht_kueche")
    tag, aktion, sig = parse_signed_url(url)
    assert (tag, aktion) == ("kueche_wand", "licht_kueche") and len(sig) == 22
    assert check_signature(keyring.url_key(), tag, aktion, sig)
    assert not check_signature(keyring.url_key(), tag, "tuer_labor", sig)
    assert not check_signature(KeyRing(b"x" * 32).url_key(), tag, aktion, sig)


class FakeOH:
    def __init__(self):
        self.ops = []

    def run(self, op):
        self.ops.append(op)
        return str(op)


def test_tag_service(tmp_path, keyring):
    m = load_script("29-signierte-urls/tag_dienst.py", "tag_dienst")
    users = tmp_path / "u.json"
    users.write_text(json.dumps({"michael": generate_password_hash("geheim-geheim")}))
    oh = FakeOH()
    app = m.create_app(keyring, "29-signierte-urls/aktionen.yaml", users, oh, secure_cookie=False)
    c = app.test_client()
    path = signed_url("", keyring.url_key(), "kueche_wand", "licht_kueche")
    assert c.get(path.replace("?s=", "?s=x")).status_code == 403               # falsche Signatur
    r = c.get(path)
    assert r.status_code == 302 and "/anmelden" in r.headers["Location"]       # erst anmelden
    r = c.post(r.headers["Location"], data={"benutzer": "michael", "passwort": "geheim-geheim"})
    assert r.status_code == 302 and r.headers["Location"].startswith("/t/kueche_wand/licht_kueche")
    assert c.get(path).status_code == 200 and oh.ops == [{"toggle": "iKueche_Hue_Lampen_Schalter"}]
    # folgenreich: Bestätigung per POST mit CSRF
    tuer = signed_url("", keyring.url_key(), "flur_tuer", "tuer_labor")
    html = c.get(tuer).get_data(as_text=True)
    assert "Wirklich" in html and len(oh.ops) == 1
    csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    sig = tuer.split("?s=")[1]
    assert c.post(tuer.split("?")[0], data={"s": sig, "csrf": "falsch"}).status_code == 400
    assert c.post(tuer.split("?")[0], data={"s": sig, "csrf": csrf}).status_code == 200
    assert oh.ops[-1] == {"command": "iLabor_Tuer_Oeffner", "value": "ON"}
