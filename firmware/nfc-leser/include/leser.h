// Kapitel 16 – gemeinsame Schnittstelle für PN532 und RC522
#pragma once
#include <Arduino.h>

enum KartenTyp { UNBEKANNT, CLASSIC1K, NTAG213, NTAG215, NTAG216, ULTRALIGHT };

struct Karte {
  uint8_t uid[10];
  uint8_t uidLen = 0;
  KartenTyp typ = UNBEKANNT;
};

const char *typName(KartenTyp t);

class Leser {
 public:
  virtual ~Leser() {}
  virtual bool begin() = 0;
  // Neue Karte im Feld? Füllt uid/uidLen/typ.
  virtual bool suchen(Karte &k) = 0;
  // Karte (wieder) auswählen, damit Lesen/Schreiben möglich ist – z. B. vor einem
  // Schreibbefehl des Gateways. false, wenn sie nicht (mehr) da ist.
  virtual bool waehlen(const Karte &k) = 0;
  // Liegt die Karte mit dieser UID noch auf?
  bool nochDa(const Karte &k) {
    bool da = waehlen(k);
    fertig();
    return da;
  }

  // MIFARE Classic: Anmelden (keyB=false: Key A), Block lesen/schreiben (16 Byte)
  virtual bool classicAnmelden(const Karte &k, uint8_t block, bool keyB, const uint8_t key[6]) = 0;
  virtual bool classicLesen(uint8_t block, uint8_t daten[16]) = 0;
  virtual bool classicSchreiben(uint8_t block, const uint8_t daten[16]) = 0;

  // NTAG: eine Seite lesen (4 Byte) bzw. schreiben, Passwort prüfen (PACK zurück)
  virtual bool ntagLesen(uint8_t seite, uint8_t daten[4]) = 0;
  virtual bool ntagSchreiben(uint8_t seite, const uint8_t daten[4]) = 0;
  virtual bool ntagPasswort(const uint8_t pwd[4], uint8_t pack[2]) = 0;

  // nach jeder Kartenaktion: Karte in Ruhe versetzen (für nochDa)
  virtual void fertig() {}
};

Leser *erzeugeLeser();   // je nach Build-Flag PN532 oder RC522

// NTAG-Typ über den Capability Container (Seite 3, Byte 2) bestimmen
KartenTyp ntagTyp(Leser &l);
