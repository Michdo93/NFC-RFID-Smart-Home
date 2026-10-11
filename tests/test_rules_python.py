"""Die Python-Regeln (Kapitel 23, 24) mit nachgebauten openHAB-Modulen ausführen."""
import json
import sys
import types

import pytest

from conftest import load_script


class Item:
    def __init__(self, reg, name):
        self.reg, self.name = reg, name

    def sendCommand(self, v):
        self.reg.log.append((self.name, str(v)))
        self.reg.states[self.name] = str(v)

    def postUpdate(self, v):
        self.reg.states[self.name] = str(v)


class Registry:
    states, log = {}, []

    @classmethod
    def getItem(cls, name):
        return Item(cls, name)

    @classmethod
    def getItemState(cls, name):
        return cls.states.get(name, "NULL")


class Ev:
    def __init__(self, event=None, state=None, command=None):
        self.e, self.s, self.c = event, state, command

    def getEvent(self):
        return self.e

    def getItemState(self):
        return self.s

    def getItemCommand(self):
        return self.c


@pytest.fixture
def oh(monkeypatch):
    openhab = types.ModuleType("openhab")
    openhab.Registry = Registry
    openhab.rule = lambda *a, **k: (lambda f: f)
    triggers = types.ModuleType("openhab.triggers")
    triggers.when = lambda *a, **k: (lambda f: f)
    scope = types.ModuleType("scope")
    scope.ON, scope.OFF = "ON", "OFF"
    monkeypatch.setitem(sys.modules, "openhab", openhab)
    monkeypatch.setitem(sys.modules, "openhab.triggers", triggers)
    monkeypatch.setitem(sys.modules, "scope", scope)
    Registry.states, Registry.log = {}, []
    return Registry


def gesture(card, role, kind, reader, value=None, label=None):
    return {"event": Ev(json.dumps({"card": card, "label": label or card, "role": role, "value": value,
                                    "gesture": kind, "reader": reader, "duration": 0.4}))}


def test_nfc_rules(oh):
    m = load_script("23-mqtt-rules/openhab/automation/python/nfc_mqtt.py", "nfc_mqtt_rules")
    m.nfc_gesten(None, gesture("gute_nacht", "szene", "present", "nachttisch"))
    assert ("gLichter", "OFF") in oh.log and oh.states["iSzene_Gute_Nacht"] == "ON"
    m.nfc_gesten(None, gesture("radio_swr3", "medien", "present", "kueche", "SWR3"))
    assert oh.states["iKueche_Webradio_SWR3"] == "ON"
    m.nfc_gesten(None, gesture("radio_swr3", "medien", "removed", "kueche", "SWR3"))
    assert oh.states["iKueche_Webradio_SWR3"] == "OFF"
    m.nfc_gesten(None, gesture("radio_swr3", "medien", "present", "nachttisch", "SWR3"))
    assert "iSmartHome_Webradio_SWR3" not in oh.states             # am Nachttisch kein Radio
    m.nfc_gesten(None, gesture("michael", "bewohner", "tap", "nachttisch", "Michael"))
    assert oh.states["iSmartHome_Hue_Lampen_Schalter"] == "ON"
    m.nfc_gesten(None, gesture("michael", "bewohner", "present", "flur", "Michael", "Michael"))
    m.nfc_gesten(None, gesture("michael", "bewohner", "tap", "flur", "Michael"))
    assert oh.states["iLabor_Tuer_Oeffner"] == "ON" and oh.states["iAnwesend_Michael"] == "ON"
    assert oh.states["iLabor_Zutritte"] == "1" and oh.states["iLabor_Zutritt_Letzter"] == "Michael"
    m.nfc_gesten(None, gesture("michael", "bewohner", "hold", "flur", "Michael"))
    assert oh.states["iAnwesend_Michael"] == "OFF" and oh.log[-1] == ("NFC_Flur_Signal", "learn")
    m.nfc_gesten(None, gesture("admin", "admin", "hold", "flur"))
    assert oh.states["iSmartHome_Alarmanlage_Scharf"] == "ON"
    m.nfc_nachttisch_praesenz(None, {"event": Ev(state="gute_nacht")})
    assert oh.states["iNachttisch_Karte_Liegt"] == "ON"
    m.nfc_sicherheit(None, {"event": Ev(json.dumps({"status": "clone"}))})
    assert oh.states["iSmartHome_Alarm"] == "ON"


def test_rueckkanal_rules(oh):
    m = load_script("24-rueckkanal-anlernen/openhab/automation/python/nfc_rueckkanal.py", "nfc_rk")
    oh.states.update({"NFC_Anlernen_Name": "gast_tom", "NFC_Anlernen_Rolle": "gast"})
    m.nfc_anlernen(None, {})
    assert json.loads(oh.states["NFC_Gateway_Anlernen"]) == {"name": "gast_tom", "role": "gast", "leser": "nachttisch"}
    assert oh.log[-1] == ("NFC_Nachttisch_Signal", "learn")
    oh.states["NFC_Anlernen_Name"] = "Böse Karte!"
    n = len(oh.log)
    m.nfc_anlernen(None, {})
    assert len(oh.log) == n                                          # ungültiger Name: nichts
    oh.states["NFC_Sperren_Name"] = "gast_tom"
    m.nfc_sperren(None, {"event": Ev(command="ON")})
    assert oh.log[-1] == ("NFC_Gateway_Sperren", "gast_tom")
    m.nfc_alarm_zeigen(None, {})
    assert ("NFC_Multimedia_Signal", "alarm") in oh.log
    m.nfc_alarmanlage(None, {"event": Ev(state="ON")})
    assert oh.log[-1] == ("NFC_Flur_Signal", "deny")


def test_security_rule_alarm_only_for_clone(oh):
    """invalid kann ein abgerissener Schreibvorgang sein (Kapitel 13) – kein Alarm."""
    m = load_script("23-mqtt-rules/openhab/automation/python/nfc_mqtt.py", "nfc_mqtt_rules_sec")

    def sec(status):
        return {"event": Ev(json.dumps({"status": status, "message": "", "card": None, "time": ""}))}

    m.nfc_sicherheit(None, sec("invalid"))
    assert "iSmartHome_Alarm" not in oh.states
    assert oh.states["iLabor_Zutritt_Letzter"].startswith("ungültige Karte")
    m.nfc_sicherheit(None, sec("clone"))
    assert oh.states["iSmartHome_Alarm"] == "ON"
