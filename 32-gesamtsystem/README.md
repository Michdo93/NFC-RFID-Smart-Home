# Kapitel 32 – Das Gesamtsystem

Ein Haus, mehrere Leser, ein Kartenregister:

| Ort | Hardware | Anbindung | Stufe |
|---|---|---|---|
| Nachttisch | ACR122U am Gateway-Pi | pcscd/pyscard | rolling |
| Flur | ESP32 + PN532 | MQTT `nfc/raw/flur` | rolling (Gateway schickt Schreibbefehle) |
| Küche | ESP32 + RC522 | MQTT `nfc/raw/kueche` | rolling |
| Multimedia | ESP32 + PN532 | MQTT `nfc/raw/multimedia` | rolling |
| Haustür (optional) | ACR122U am Pi Zero 2 W | USB/IP zum Gateway-Pi (Kapitel 19) | rolling |
| Wand-Sticker | NTAG213/215 | Smartphone + Tag-Dienst (Kapitel 29) | Signatur + Anmeldung |

Genau EIN Programm prüft Karten und führt das Register – sonst laufen Zähler auseinander:

* **Ansatz A:** `21-nfc-gateway/nfc_gateway.py` (Dienst `nfc-gateway.service`), Regeln in openHAB
* **Ansatz B / Hybrid:** `26-kartenaktionen/nfc_fernbedienung.py --mqtt --esp32`
  (Dienst `nfc-fernbedienung.service`) – Profil für die Aktionen, Ereignisse trotzdem an MQTT

Dazu (unabhängig): `27-zustaende-sse/rueckkanal_sse.py` und `29-signierte-urls/tag_dienst.py`.

Sicherung: `config/secret.key` und `data/karten.json` gehören in die Datensicherung –
verschlüsselt, denn wer das Geheimnis hat, kann Karten fälschen:
`bash 32-gesamtsystem/sicherung.sh /opt/NFC-RFID-Smart-Home` (gpg, AES-256, Passphrase).
