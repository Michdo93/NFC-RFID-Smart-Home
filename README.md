# NFC-RFID-Smart-Home

Begleit-Repository zum Buch **„Smart Home & NFC/RFID“** – Karten, Tags und Armbänder
mit ACR122U (Raspberry Pi, Python), PN532 und RC522 (ESP32), openHAB 5, MQTT und REST.

## Schnellstart ohne Hardware (Simulator)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # ohne Leser: pyscard darf fehlschlagen
pip install -e .
cp config/config.example.yaml config/config.yaml
python3 11-stufen/geheimnis_erzeugen.py                       # Installationsgeheimnis
python3 31-labor-szenarien/labor_karten_anlernen.py --sim     # virtuelle Karten anlernen
python3 21-nfc-gateway/nfc_gateway.py --sim sim/szenarien/rundgang.yaml --dry-run
pytest
```

Virtuelle Karten liegen als Vorlage in `sim/vorlagen/` und werden beim ersten Zugriff nach
`data/sim/` kopiert – was ein Skript auf sie schreibt, liest das nächste wieder.

## Aufbau

| Ordner | Kapitel |
|---|---|
| `nfcsmarthome/` | Begleitbibliothek: APDUs, NDEF, NTAG, MIFARE Classic, Schlüssel, Kartenformat, Register, Prüfung, Gesten, Leser, Gateway, Profile |
| `00-virtuelle-geraete/` | virtuelle openHAB-Items, Hilfsregel, Sitemap, Mini-openHAB |
| `03` – `09` | Grundlagen: NDEF, Installation, APDUs, NTAG, MIFARE Classic, Gesten |
| `10` – `13` | Sicherheit: Angriffsmodell, Stufen, Kartenformat, rollierender Zähler |
| `15` – `17`, `firmware/` | ESP32 mit PN532 und RC522 (PlatformIO), ESPHome |
| `19-usbip/` | gemeinsame USB/IP-Konfiguration der Reihe (mit mehreren Servern) |
| `20` – `24` | Ansatz A: Mosquitto, NFC-Gateway, Things/Items, Regeln (DSL/JS/Python), Rückkanal |
| `25` – `27` | Ansatz B: REST, Kartenprofile, Rückkanal über SSE |
| `28` – `29` | Smartphone: openHAB-App-Tags, signierte URLs mit Tag-Dienst |
| `30` – `32` | Szenarien, Profilprüfung, Gesamtsystem |

## Geheimnisse

Nie eingecheckt (`.gitignore`): `config/config.yaml`, `config/secret.key`,
`config/tagdienst_benutzer.json`, `data/` (Kartenregister), `firmware/*/include/secrets.h`,
`17-esp32-schreiben/esphome/secrets.yaml`, Zertifikate und Schlüssel (`*.crt`, `*.key`).
Vorlagen: `*.example.*`.

Wichtige Werkzeuge für den Betrieb:

* `05-installation/50-pcscd-nfc.rules` – pcscd für die Gruppe `nfc` (SSH, Dienste)
* `13-rollierender-zaehler/karte_erneuern.py` – Karte nach abgerissenem Schreiben erneuern
* `20-mosquitto/zertifikate_erzeugen.sh` + `nfc-tls.conf.example` – TLS mit eigener CA
* `21-nfc-gateway/dienst_einrichten.sh [gateway|fernbedienung]` – als Dienst unter `nfc`
* `30-kartenarten-items/profil_pruefen.py` – Profil gegen openHAB prüfen
* `32-gesamtsystem/sicherung.sh` – Geheimnis und Register verschlüsselt sichern

## Getestet – und was nicht

Die Bibliothek, das Gateway, die Profile, der Tag-Dienst und die Python-Regeln laufen in
`pytest` gegen Simulator, Mini-openHAB und einen MQTT-Broker in Python. Gateway, ESP32-Simulator,
Zugriffsliste und TLS wurden zusätzlich mit einem echten Mosquitto 2.0 ausprobiert. **Nicht** mit
echter Hardware geprüft sind: ACR122U-Antworten (pyscard), PN532/RC522-Firmware (nur gegen die
Bibliotheks-Header syntaxgeprüft, nicht auf einem ESP32 gebaut; `PWD_AUTH` über den PN532),
ESPHome-Konfiguration, openHAB-Regeln in DSL und JavaScript, Lock-Bits auf echten NTAGs,
polkit auf Raspberry Pi OS, iOS.
