// Kapitel 16/17 – NFC-Leser am ESP32: Karte lesen, Rohdaten per MQTT melden,
// Schreibbefehle des Gateways ausführen, Signale anzeigen.
//
// Topics (MQTT_BASE = "nfc", LESER_NAME = "flur"):
//   nfc/raw/flur              -> {"uid":"5A3F9C21","type":"classic1k","data":"<32 Byte>"}
//                                {"uid":"04…","type":"ntag215","mem":"<NDEF-Bereich>"}
//                                {"removed":true}
//   nfc/flur/status           -> online / offline (Last Will)
//   nfc/flur/cmd              <- {"id":7,"op":"write",...}   (Kapitel 17)
//   nfc/flur/cmd/result       -> {"id":7,"ok":true}
//   nfc/flur/set/signal       <- ok | deny | unknown | alarm | learn | idle
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "leser.h"
#include "secrets.h"

static const int LED_GRUEN = 25, LED_ROT = 26, SUMMER = 27;
static const uint8_t KEY_A_INSTALLATION[6] = KEY_A;

#ifdef MQTT_CA_PEM                           // TLS (Kapitel 20): CA-Zertifikat in secrets.h
#include <WiFiClientSecure.h>
WiFiClientSecure netz;
#else
WiFiClient netz;
#endif
PubSubClient mqtt(netz);
Leser *leser = nullptr;
Karte aktuell;
bool liegt = false;
uint8_t fehlt = 0;
unsigned long letztePruefung = 0;
String tRaw, tStatus, tCmd, tResult, tSignal;

// ---------------------------------------------------------------- Hilfen
const char *typName(KartenTyp t) {
  switch (t) {
    case CLASSIC1K: return "classic1k";
    case NTAG213: return "ntag213";
    case NTAG215: return "ntag215";
    case NTAG216: return "ntag216";
    case ULTRALIGHT: return "ultralight";
    default: return "unbekannt";
  }
}

KartenTyp ntagTyp(Leser &l) {
  uint8_t cc[4];
  if (!l.ntagLesen(3, cc) || cc[0] != 0xE1) return ULTRALIGHT;
  if (cc[2] == 0x12) return NTAG213;
  if (cc[2] == 0x3E) return NTAG215;
  if (cc[2] == 0x6D) return NTAG216;
  return ULTRALIGHT;
}

static String hex(const uint8_t *b, size_t n) {
  static const char *H = "0123456789ABCDEF";
  String s;
  s.reserve(n * 2);
  for (size_t i = 0; i < n; i++) { s += H[b[i] >> 4]; s += H[b[i] & 15]; }
  return s;
}

static size_t unhex(const char *s, uint8_t *out, size_t max) {
  size_t n = 0;
  while (s && s[0] && s[1] && n < max) {
    char t[3] = {s[0], s[1], 0};
    out[n++] = (uint8_t)strtoul(t, nullptr, 16);
    s += 2;
  }
  return n;
}

// ---------------------------------------------------------------- Signale
static void piep(int ms) { digitalWrite(SUMMER, HIGH); delay(ms); digitalWrite(SUMMER, LOW); }

static void signal(const String &s) {
  if (s == "ok") { digitalWrite(LED_GRUEN, HIGH); piep(80); delay(220); digitalWrite(LED_GRUEN, LOW); }
  else if (s == "unknown") { digitalWrite(LED_ROT, HIGH); piep(150); delay(150); digitalWrite(LED_ROT, LOW); }
  else if (s == "deny") {
    for (int i = 0; i < 2; i++) { digitalWrite(LED_ROT, HIGH); piep(80); delay(80); digitalWrite(LED_ROT, LOW); delay(80); }
  } else if (s == "alarm") {
    for (int i = 0; i < 10; i++) { digitalWrite(LED_ROT, HIGH); piep(100); delay(100); digitalWrite(LED_ROT, LOW); delay(100); }
  } else if (s == "learn") {
    for (int i = 0; i < 6; i++) { digitalWrite(LED_GRUEN, i % 2); digitalWrite(LED_ROT, !(i % 2)); delay(250); }
    digitalWrite(LED_GRUEN, LOW); digitalWrite(LED_ROT, LOW);
  } else { digitalWrite(LED_GRUEN, LOW); digitalWrite(LED_ROT, LOW); }
}

// ---------------------------------------------------------------- Karte lesen
static void meldeAufgelegt(const Karte &k) {
  JsonDocument doc;
  doc["uid"] = hex(k.uid, k.uidLen);
  doc["type"] = typName(k.typ);
  if (k.typ == CLASSIC1K) {
    uint8_t d[32];
    if (leser->classicAnmelden(k, 4, false, KEY_A_INSTALLATION) &&
        leser->classicLesen(4, d) && leser->classicLesen(5, d + 16)) {
      doc["data"] = hex(d, 32);            // nur mit dem Key A UNSERER Installation lesbar
    }
  } else if (k.typ == NTAG213 || k.typ == NTAG215 || k.typ == NTAG216) {
    uint8_t mem[512];
    if (leser->ntagLesen(4, mem)) {
      size_t n = 16;
      if (mem[0] == 0x03 && mem[1] != 0xFF) n = mem[1] + 3;                  // 03 <Länge> … FE
      else if (mem[0] == 0x03 && leser->ntagLesen(5, mem + 4)) n = ((mem[2] << 8) | mem[3]) + 5;
      if (n > sizeof(mem)) n = sizeof(mem);
      bool ok = true;
      for (size_t p = 0; p * 4 < n && ok; p++) ok = leser->ntagLesen(4 + p, mem + 4 * p);
      if (ok) doc["mem"] = hex(mem, (n + 3) / 4 * 4);
    }
  }
  String out;
  serializeJson(doc, out);
  mqtt.publish(tRaw.c_str(), out.c_str());
  Serial.println(out);
}

// ---------------------------------------------------------------- Schreibbefehl (Kapitel 17)
static bool schreiben(JsonDocument &cmd) {
  if (!liegt || hex(aktuell.uid, aktuell.uidLen) != String((const char *)cmd["uid"])) return false;
  if (!leser->waehlen(aktuell)) return false;
  const char *typ = cmd["type"];
  if (!strcmp(typ, "classic1k")) {
    uint8_t keyB[6];
    if (unhex(cmd["key_b"], keyB, 6) != 6) return false;
    if (!leser->classicAnmelden(aktuell, 4, true, keyB)) return false;
    for (JsonPair kv : cmd["blocks"].as<JsonObject>()) {
      uint8_t blk = atoi(kv.key().c_str()), d[16], zurueck[16];
      if (unhex(kv.value().as<const char *>(), d, 16) != 16) return false;
      if (!leser->classicSchreiben(blk, d) || !leser->classicLesen(blk, zurueck)) return false;
      if (memcmp(d, zurueck, 16)) return false;
    }
    return true;
  }
  // NTAG: erst Passwort DIESER Karte, PACK vergleichen, dann Seiten schreiben
  uint8_t pwd[4], packSoll[2], packIst[2];
  if (unhex(cmd["pwd"], pwd, 4) != 4 || unhex(cmd["pack"], packSoll, 2) != 2) return false;
  if (!leser->ntagPasswort(pwd, packIst) || memcmp(packSoll, packIst, 2)) return false;
  uint8_t daten[512];
  size_t n = unhex(cmd["pages"], daten, sizeof(daten));
  uint8_t start = cmd["start"] | 4;
  for (size_t i = 0; i < n; i += 4) {
    uint8_t zurueck[4];
    if (!leser->ntagSchreiben(start + i / 4, daten + i)) return false;
    if (!leser->ntagLesen(start + i / 4, zurueck) || memcmp(zurueck, daten + i, 4)) return false;
  }
  return true;
}

static void empfangen(char *topic, byte *payload, unsigned int len) {
  String t(topic);
  if (t == tSignal) {
    signal(String((const char *)payload).substring(0, len));
    return;
  }
  JsonDocument cmd;
  JsonDocument res;
  bool ok = false;
  if (!deserializeJson(cmd, payload, len) && cmd["op"] == "write") ok = schreiben(cmd);
  leser->fertig();
  res["id"] = cmd["id"];
  res["ok"] = ok;
  String out;
  serializeJson(res, out);
  mqtt.publish(tResult.c_str(), out.c_str());
}

// ---------------------------------------------------------------- Verbindung
static void verbinden() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
    if (WiFi.status() != WL_CONNECTED) return;
    Serial.printf("WLAN: %s\n", WiFi.localIP().toString().c_str());
  }
  String id = String("esp32-") + LESER_NAME;
  if (mqtt.connect(id.c_str(), MQTT_USER, MQTT_PASS, tStatus.c_str(), 1, true, "offline")) {
    mqtt.publish(tStatus.c_str(), "online", true);
    mqtt.subscribe(tCmd.c_str(), 1);
    mqtt.subscribe(tSignal.c_str(), 1);
    Serial.println("MQTT verbunden");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_GRUEN, OUTPUT);
  pinMode(LED_ROT, OUTPUT);
  pinMode(SUMMER, OUTPUT);
  String base = String(MQTT_BASE) + "/";
  tRaw = base + "raw/" + LESER_NAME;
  tStatus = base + LESER_NAME + "/status";
  tCmd = base + LESER_NAME + "/cmd";
  tResult = tCmd + "/result";
  tSignal = base + LESER_NAME + "/set/signal";
  leser = erzeugeLeser();
  while (!leser->begin()) {
    Serial.println("Kein Leser gefunden – Verdrahtung prüfen");
    signal("alarm");
    delay(3000);
  }
  WiFi.mode(WIFI_STA);
#ifdef MQTT_CA_PEM
  netz.setCACert(MQTT_CA_PEM);               // prüft das Zertifikat des Brokers
#endif
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(2048);                  // NTAG216: bis zu 888 Byte = 1776 Hex-Zeichen
  mqtt.setCallback(empfangen);
}

void loop() {
  if (!mqtt.connected()) {
    verbinden();
    delay(500);
    return;
  }
  mqtt.loop();
  if (!liegt) {
    Karte k;
    if (leser->suchen(k)) {
      aktuell = k;
      liegt = true;
      fehlt = 0;
      meldeAufgelegt(k);
      leser->fertig();
    }
  } else if (millis() - letztePruefung > 200) {
    letztePruefung = millis();
    if (leser->nochDa(aktuell)) {
      fehlt = 0;
    } else if (++fehlt >= 2) {                // zweimal nicht gefunden: entfernt
      liegt = false;
      mqtt.publish(tRaw.c_str(), "{\"removed\":true}");
    }
  }
}
