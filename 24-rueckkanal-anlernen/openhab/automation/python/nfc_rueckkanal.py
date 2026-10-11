# ============================================================================
# Kapitel 24 – Rückkanal, Anlernen und Sperren (Python Scripting)
# Datei: $OPENHAB_CONF/automation/python/nfc_rueckkanal.py
# Nur EINE Sprachvariante (DSL, JS oder Python) gleichzeitig aktivieren!
# ============================================================================

import json
import re

from openhab import rule, Registry
from openhab.triggers import when

LESER = ["nachttisch", "kueche", "flur", "multimedia"]


def _text(name):
    s = str(Registry.getItemState(name))
    return None if s in ("NULL", "UNDEF") else s


@rule()
@when("Item NFC_Anlernen_Start received command ON")
def nfc_anlernen(module, input):
    name = _text("NFC_Anlernen_Name") or ""
    leser = _text("NFC_Anlernen_Leser") or "nachttisch"
    if not re.fullmatch(r"[a-z0-9_]{1,24}", name):
        return
    befehl = json.dumps({"name": name, "role": _text("NFC_Anlernen_Rolle") or "bewohner", "leser": leser})
    Registry.getItem("NFC_Gateway_Anlernen").sendCommand(befehl)
    Registry.getItem(f"NFC_{leser.capitalize()}_Signal").sendCommand("learn")


@rule()
@when("Item NFC_Sperren_Start received command")
def nfc_sperren(module, input):
    name = _text("NFC_Sperren_Name")
    if not name:
        return
    ziel = "NFC_Gateway_Sperren" if str(input["event"].getItemCommand()) == "ON" else "NFC_Gateway_Entsperren"
    Registry.getItem(ziel).sendCommand(name)


@rule()
@when("Item iSmartHome_Alarm changed to ON")
def nfc_alarm_zeigen(module, input):
    for leser in LESER:
        Registry.getItem(f"NFC_{leser.capitalize()}_Signal").sendCommand("alarm")


@rule()
@when("Item iSmartHome_Alarmanlage_Scharf changed")
def nfc_alarmanlage(module, input):
    neu = str(input["event"].getItemState())
    Registry.getItem("NFC_Flur_Signal").sendCommand("deny" if neu == "ON" else "ok")
