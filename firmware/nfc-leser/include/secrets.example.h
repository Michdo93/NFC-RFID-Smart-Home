// Kapitel 15 – Vorlage. Kopieren nach secrets.h (gitignored) und ausfüllen.
//   cp include/secrets.example.h include/secrets.h
// KEY_A erzeugt:  python3 15-esp32-hardware/secrets_erzeugen.py
#pragma once

#define WIFI_SSID      "MEIN_WLAN"
#define WIFI_PASS      "CHANGE_ME"

#define MQTT_HOST      "192.168.0.10"
#define MQTT_PORT      1883
#define MQTT_USER      "flur"          // = LESER_NAME (Zugriffsliste mit %u, Kapitel 20)
#define MQTT_PASS      "CHANGE_ME"
#define MQTT_BASE      "nfc"

// TLS (Kapitel 20): Port 8883 und das CA-Zertifikat des Brokers (ca.crt, öffentlich).
// MQTT_HOST muss dann zum Namen bzw. zur IP im Server-Zertifikat passen.
// #define MQTT_PORT   8883
// #define MQTT_CA_PEM "-----BEGIN CERTIFICATE-----\n" \
//                     "MIID...\n" \
//                     "-----END CERTIFICATE-----\n"

#define LESER_NAME     "flur"          // erscheint in nfc/raw/<name>

// Lese-Schlüssel (Key A) des Datensektors – für alle Karten der Installation gleich.
// Er erlaubt nur das LESEN von Sektor 1. Schreiben geht nur mit Key B, den das Gateway
// je Karte mitschickt.
#define KEY_A          { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 }
