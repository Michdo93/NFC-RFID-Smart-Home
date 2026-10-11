// Kapitel 15/16 – PN532 V3 über I2C (DIP-Schalter auf I2C: 1 = ON, 2 = OFF)
//   VCC -> 3V3 (nicht 5 V: die I2C-Pull-ups des Moduls hängen an VCC), GND,
//   SDA -> GPIO 21, SCL -> GPIO 22. Mehr nicht.
#ifdef LESER_PN532
#include <Wire.h>
#include <Adafruit_PN532.h>
#include "leser.h"

// Der I2C-Konstruktor verlangt Pin-Nummern für IRQ und RSTPD_N. Über I2C fragt die
// Bibliothek die Bereitschaft per Statusbyte ab; IRQ wird nicht gebraucht, und RSTPD_N
// führt das Modul nicht heraus. GPIO 4 und 16 bleiben deshalb UNBESCHALTET.
// (Den Pin „RSTO“ des Moduls nicht anschließen – er ist ein Ausgang des PN532.)
static Adafruit_PN532 nfc(4, 16, &Wire);

class LeserPN532 : public Leser {
 public:
  bool begin() override {
    Wire.begin(21, 22);
    if (!nfc.begin()) return false;
    uint32_t v = nfc.getFirmwareVersion();
    if (!v) return false;
    Serial.printf("PN5%02X, Firmware %d.%d\n", (v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF);
    nfc.setPassiveActivationRetries(0x02);   // nicht ewig auf eine Karte warten
    nfc.SAMConfig();
    return true;
  }

  bool suchen(Karte &k) override {
    uint8_t len = 0;
    if (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, k.uid, &len, 50)) return false;
    k.uidLen = len;
    // S50-Karten haben eine 4-Byte-UID, NTAG eine 7-Byte-UID
    k.typ = (len == 4) ? CLASSIC1K : ntagTyp(*this);
    return true;
  }

  bool waehlen(const Karte &k) override {
    uint8_t uid[10], len = 0;
    if (!nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &len, 50)) return false;
    return len == k.uidLen && memcmp(uid, k.uid, len) == 0;
  }

  bool classicAnmelden(const Karte &k, uint8_t block, bool keyB, const uint8_t key[6]) override {
    uint8_t kk[6];
    memcpy(kk, key, 6);
    return nfc.mifareclassic_AuthenticateBlock((uint8_t *)k.uid, k.uidLen, block, keyB ? 1 : 0, kk);
  }
  bool classicLesen(uint8_t block, uint8_t daten[16]) override {
    return nfc.mifareclassic_ReadDataBlock(block, daten);
  }
  bool classicSchreiben(uint8_t block, const uint8_t daten[16]) override {
    uint8_t d[16];
    memcpy(d, daten, 16);
    return nfc.mifareclassic_WriteDataBlock(block, d);
  }

  bool ntagLesen(uint8_t seite, uint8_t daten[4]) override {
    return nfc.ntag2xx_ReadPage(seite, daten);
  }
  bool ntagSchreiben(uint8_t seite, const uint8_t daten[4]) override {
    uint8_t d[4];
    memcpy(d, daten, 4);
    return nfc.ntag2xx_WritePage(seite, d);
  }
  bool ntagPasswort(const uint8_t pwd[4], uint8_t pack[2]) override {
    // PWD_AUTH (1B) über InDataExchange – ungetestet, siehe Kapitel 16
    uint8_t cmd[5] = {0x1B, pwd[0], pwd[1], pwd[2], pwd[3]};
    uint8_t resp[8];
    uint8_t len = sizeof(resp);
    if (!nfc.inDataExchange(cmd, 5, resp, &len) || len < 2) return false;
    pack[0] = resp[0];
    pack[1] = resp[1];
    return true;
  }
};

Leser *erzeugeLeser() { return new LeserPN532(); }
#endif
