# ============================================================================
# Kapitel 23 – Ansatz A: Was eine Karte bewirkt, entscheiden openHAB-Regeln (Python Scripting)
# Datei: $OPENHAB_CONF/automation/python/nfc_mqtt.py
# Nur EINE Sprachvariante (DSL, JS oder Python) gleichzeitig aktivieren!
# ============================================================================

import json

from openhab import rule, Registry
from openhab.triggers import when

import scope

LESER = ["nachttisch", "kueche", "flur", "multimedia"]
RAUM = {"nachttisch": "iSmartHome", "kueche": "iKueche", "flur": "iIoT", "multimedia": "iMultimedia"}


def kanal(leser, k):
    return f"mqtt:topic:mosquitto:nfc_{leser}:{k}"


def _befehl(name, wert):
    Registry.getItem(name).sendCommand(wert)


def _setzen(name, wert):
    Registry.getItem(name).postUpdate(wert)


def _umschalten(name):
    _befehl(name, scope.OFF if Registry.getItemState(name) == scope.ON else scope.ON)


SZENEN = {
    "gute_nacht": [("gLichter", "OFF"), ("gRollladen", "DOWN"), ("iSzene_Gute_Nacht", "ON")],
    "kinoabend": [("iMultimedia_Hue_Lampen_Helligkeit", "20"),
                  ("iMultimedia_Somfy_Rollladen_Steuerung", "DOWN"),
                  ("iMultimedia_Beamer_Power", "ON"), ("iSzene_Kinoabend", "ON")],
}


def _flur(g):
    rolle, geste = g["role"], g["gesture"]
    if rolle in ("bewohner", "gast") and geste == "present":
        _befehl("iLabor_Tuer_Oeffner", "ON")                    # expire schaltet wieder aus
        _setzen("iLabor_Zutritt_Letzter", f"Gast: {g['label']}" if rolle == "gast" else g["label"])
        alt = Registry.getItemState("iLabor_Zutritte")
        n = int(str(alt)) if str(alt).isdigit() else 0
        _setzen("iLabor_Zutritte", n + 1)
        if rolle == "gast":
            _setzen("iAnwesend_Gast", "ON")
    if rolle == "bewohner" and geste == "tap":
        _setzen(f"iAnwesend_{g['value']}", "ON")
    if rolle == "bewohner" and geste == "hold":
        _setzen(f"iAnwesend_{g['value']}", "OFF")
        _befehl("NFC_Flur_Signal", "learn")
    if rolle == "admin" and geste == "hold":
        _umschalten("iSmartHome_Alarmanlage_Scharf")


@rule()
@when(f"Channel {kanal('nachttisch', 'gesture')} triggered")
@when(f"Channel {kanal('kueche', 'gesture')} triggered")
@when(f"Channel {kanal('flur', 'gesture')} triggered")
@when(f"Channel {kanal('multimedia', 'gesture')} triggered")
def nfc_gesten(module, input):
    g = json.loads(str(input["event"].getEvent()))
    raum = RAUM.get(g["reader"])
    if g["gesture"] == "present":
        for item, wert in SZENEN.get(g["card"], []):
            _befehl(item, wert)
    if g["role"] == "medien" and g["reader"] in ("kueche", "multimedia"):
        radio = f"{raum}_Webradio_{g['value']}"
        if g["gesture"] == "present":
            _befehl(radio, "ON")
        elif g["gesture"] == "removed":
            _befehl(radio, "OFF")
    if g["reader"] == "nachttisch" and g["role"] == "bewohner" and g["gesture"] == "tap":
        _umschalten(f"{raum}_Hue_Lampen_Schalter")
    if g["reader"] == "flur":
        _flur(g)


@rule()
@when("Item NFC_Nachttisch_Karte changed")
def nfc_nachttisch_praesenz(module, input):
    _setzen("iNachttisch_Karte_Liegt", "OFF" if str(input["event"].getItemState()) == "NONE" else "ON")


@rule()
@when(f"Channel {kanal('nachttisch', 'security')} triggered")
@when(f"Channel {kanal('kueche', 'security')} triggered")
@when(f"Channel {kanal('flur', 'security')} triggered")
@when(f"Channel {kanal('multimedia', 'security')} triggered")
def nfc_sicherheit(module, input):
    s = json.loads(str(input["event"].getEvent()))
    if s["status"] == "clone":                    # Kopie im Umlauf: Alarm
        _befehl("iSmartHome_Alarm", "ON")
    if s["status"] == "invalid":                  # manipuliert ODER abgerissen (Kapitel 13)
        _setzen("iLabor_Zutritt_Letzter", "ungültige Karte – prüfen/erneuern")
    if s["status"] == "unknown":
        _setzen("iLabor_Zutritt_Letzter", "unbekannte Karte")
