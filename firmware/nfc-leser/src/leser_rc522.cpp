// Kapitel 15/16 – RC522 über SPI (3,3 V! Der RC522 verträgt keine 5 V)
//   SDA(SS) -> GPIO 5, SCK -> 18, MOSI -> 23, MISO -> 19, RST -> 22, 3.3V, GND
#ifdef LESER_RC522
#include <SPI.h>
#include <MFRC522.h>
#include "leser.h"

static MFRC522 rc(5, 22);

class LeserRC522 : public Leser {
 public:
  bool begin() override {
    SPI.begin();
    rc.PCD_Init();
    byte v = rc.PCD_ReadRegister(MFRC522::VersionReg);
    Serial.printf("RC522, Version 0x%02X\n", v);
    return v != 0x00 && v != 0xFF;
  }

  bool suchen(Karte &k) override {
    if (!rc.PICC_IsNewCardPresent() || !rc.PICC_ReadCardSerial()) return false;
    k.uidLen = rc.uid.size;
    memcpy(k.uid, rc.uid.uidByte, k.uidLen);
    MFRC522::PICC_Type t = rc.PICC_GetType(rc.uid.sak);
    if (t == MFRC522::PICC_TYPE_MIFARE_1K) k.typ = CLASSIC1K;
    else if (t == MFRC522::PICC_TYPE_MIFARE_UL) k.typ = ntagTyp(*this);
    else k.typ = UNBEKANNT;
    return true;
  }

  // Karte nach HALT mit WUPA wecken und auswählen: dieselbe UID = noch da
  bool waehlen(const Karte &k) override {
    rc.PCD_StopCrypto1();
    byte atqa[2];
    byte size = sizeof(atqa);
    if (rc.PICC_WakeupA(atqa, &size) != MFRC522::STATUS_OK) return false;
    if (!rc.PICC_ReadCardSerial()) return false;
    return rc.uid.size == k.uidLen && memcmp(rc.uid.uidByte, k.uid, k.uidLen) == 0;
  }

  bool classicAnmelden(const Karte &k, uint8_t block, bool keyB, const uint8_t key[6]) override {
    MFRC522::MIFARE_Key mk;
    memcpy(mk.keyByte, key, 6);
    auto cmd = keyB ? MFRC522::PICC_CMD_MF_AUTH_KEY_B : MFRC522::PICC_CMD_MF_AUTH_KEY_A;
    return rc.PCD_Authenticate(cmd, block, &mk, &rc.uid) == MFRC522::STATUS_OK;
  }
  bool classicLesen(uint8_t block, uint8_t daten[16]) override {
    byte buf[18];
    byte size = sizeof(buf);
    if (rc.MIFARE_Read(block, buf, &size) != MFRC522::STATUS_OK) return false;
    memcpy(daten, buf, 16);
    return true;
  }
  bool classicSchreiben(uint8_t block, const uint8_t daten[16]) override {
    byte d[16];
    memcpy(d, daten, 16);
    return rc.MIFARE_Write(block, d, 16) == MFRC522::STATUS_OK;
  }

  bool ntagLesen(uint8_t seite, uint8_t daten[4]) override {
    byte buf[18];
    byte size = sizeof(buf);
    if (rc.MIFARE_Read(seite, buf, &size) != MFRC522::STATUS_OK) return false;   // liefert 4 Seiten
    memcpy(daten, buf, 4);
    return true;
  }
  bool ntagSchreiben(uint8_t seite, const uint8_t daten[4]) override {
    byte d[4];
    memcpy(d, daten, 4);
    return rc.MIFARE_Ultralight_Write(seite, d, 4) == MFRC522::STATUS_OK;
  }
  bool ntagPasswort(const uint8_t pwd[4], uint8_t pack[2]) override {
    byte cmd[7] = {0x1B, pwd[0], pwd[1], pwd[2], pwd[3], 0, 0};
    if (rc.PCD_CalculateCRC(cmd, 5, &cmd[5]) != MFRC522::STATUS_OK) return false;
    byte back[4];
    byte backLen = sizeof(back);
    if (rc.PCD_TransceiveData(cmd, 7, back, &backLen, nullptr, 0, true) != MFRC522::STATUS_OK) return false;
    pack[0] = back[0];
    pack[1] = back[1];
    return true;
  }

  void fertig() override {
    rc.PICC_HaltA();
    rc.PCD_StopCrypto1();
  }
};

Leser *erzeugeLeser() { return new LeserRC522(); }
#endif
