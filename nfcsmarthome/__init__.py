"""
nfcsmarthome – Begleitbibliothek zum Buch „Smart Home & NFC/RFID“.

Module:
  apdu       APDUs für den ACR122U (PC/SC): UID, Schlüssel, Blöcke, LED/Summer, Durchreichen
  ndef       NDEF-Nachrichten kodieren und dekodieren (URI, Text, External Type) und TLV
  ntag       NTAG213/215/216: Speicherseiten, NDEF, Passwortschutz, Konfiguration
  classic    MIFARE Classic 1K: Sektoren, Sektor-Trailer, Zugriffsbits
  keys       Schlüsselableitung aus dem Installationsgeheimnis (HKDF-SHA256)
  cardformat das hauseigene Kartenformat (Version, Karten-ID, Rolle, Zähler, HMAC)
  registry   Kartenregister (JSON): Namen, Rollen, Zähler, Sperrliste
  verify     Prüfung einer gelesenen Karte: angenommen, unbekannt, gefälscht, Klon ...
  personalize Karten anlernen und den Zähler fortschreiben
  events     TagRead und TagEvent: was ein Leser meldet
  logic      Auflegen, Halten, Antippen, Abnehmen – mit Entprellung
  readers    Leser: ACR122U (pyscard), Simulator, Aufzeichnung, ESP32 über MQTT
  feedback   LED und Summer des ACR122U
  mqtt       Ansatz A: Topics, Gateway-Nachrichten, Verbindung (paho-mqtt)
  gateway    das NFC-Gateway: prüfen, melden, Zähler schreiben lassen
  rest       Ansatz B: openHAB-REST (python-openhab-rest-client)
  actions    Kartenprofile (YAML): Karte/Rolle + Geste -> openHAB-Befehl
  runtime    Executor, Logging, Kommandozeile
  check      Profile gegen Items prüfen
  phone      Smartphone-Tags: openHAB-App-URIs und signierte URLs

Nur readers.pcsc braucht pyscard und einen PC/SC-Dienst; alles andere läuft auf
jedem System – auch ohne angeschlossenen Leser (Simulator).
"""

import os

__version__ = "1.0.0"


def rel(path) -> str:
    """Pfad relativ zum aktuellen Verzeichnis – für kurze Ausgaben im Terminal."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


def hexs(data: bytes, sep: str = "") -> str:
    """Bytes als Hex-Text, z. B. hexs(b'\\x04\\xa1', ' ') -> '04 A1'."""
    return sep.join(f"{b:02X}" for b in data)


def unhex(text: str) -> bytes:
    """Hex-Text (auch mit Leerzeichen, Doppelpunkten oder Bindestrichen) -> Bytes."""
    return bytes.fromhex(text.replace(" ", "").replace(":", "").replace("-", ""))
