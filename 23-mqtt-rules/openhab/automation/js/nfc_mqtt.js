// ============================================================================
// Kapitel 23 – Ansatz A: Was eine Karte bewirkt, entscheiden openHAB-Regeln (JavaScript)
// Datei: $OPENHAB_CONF/automation/js/nfc_mqtt.js
// Nur EINE Sprachvariante (DSL, JS oder Python) gleichzeitig aktivieren!
// ============================================================================

const LESER = ["nachttisch", "kueche", "flur", "multimedia"];
const RAUM = { nachttisch: "iSmartHome", kueche: "iKueche", flur: "iIoT", multimedia: "iMultimedia" };
const kanal = (leser, k) => `mqtt:topic:mosquitto:nfc_${leser}:${k}`;

const umschalten = (name) => {
  const item = items.getItem(name);
  item.sendCommand(item.state === "ON" ? "OFF" : "ON");
};

// Karte -> Aktion bei „present“ (Dispatch-Tabelle)
const SZENEN = {
  gute_nacht: () => {
    items.gLichter.sendCommand("OFF");
    items.gRollladen.sendCommand("DOWN");
    items.iSzene_Gute_Nacht.sendCommand("ON");
  },
  kinoabend: () => {
    items.iMultimedia_Hue_Lampen_Helligkeit.sendCommand("20");
    items.iMultimedia_Somfy_Rollladen_Steuerung.sendCommand("DOWN");
    items.iMultimedia_Beamer_Power.sendCommand("ON");
    items.iSzene_Kinoabend.sendCommand("ON");
  },
};

function flur(g) {
  if ((g.role === "bewohner" || g.role === "gast") && g.gesture === "present") {
    items.iLabor_Tuer_Oeffner.sendCommand("ON");                 // expire schaltet wieder aus
    items.iLabor_Zutritt_Letzter.postUpdate(g.role === "gast" ? `Gast: ${g.label}` : g.label);
    items.iLabor_Zutritte.postUpdate((items.iLabor_Zutritte.numericState || 0) + 1);
    if (g.role === "gast") items.iAnwesend_Gast.postUpdate("ON");
  }
  if (g.role === "bewohner" && g.gesture === "tap") items.getItem(`iAnwesend_${g.value}`).postUpdate("ON");
  if (g.role === "bewohner" && g.gesture === "hold") {
    items.getItem(`iAnwesend_${g.value}`).postUpdate("OFF");
    items.NFC_Flur_Signal.sendCommand("learn");
  }
  if (g.role === "admin" && g.gesture === "hold") umschalten("iSmartHome_Alarmanlage_Scharf");
}

rules.JSRule({
  name: "NFC: Gesten aller Leser (JS)",
  triggers: LESER.map((l) => triggers.ChannelEventTrigger(kanal(l, "gesture"))),
  execute: (event) => {
    const g = JSON.parse(event.receivedEvent);
    const raum = RAUM[g.reader];
    if (g.gesture === "present" && SZENEN[g.card]) SZENEN[g.card]();
    if (g.role === "medien" && (g.reader === "kueche" || g.reader === "multimedia")) {
      const radio = items.getItem(`${raum}_Webradio_${g.value}`);
      if (g.gesture === "present") radio.sendCommand("ON");
      if (g.gesture === "removed") radio.sendCommand("OFF");
    }
    if (g.reader === "nachttisch" && g.role === "bewohner" && g.gesture === "tap") {
      umschalten(`${raum}_Hue_Lampen_Schalter`);
    }
    if (g.reader === "flur") flur(g);
  },
});

rules.when().item("NFC_Nachttisch_Karte").changed().then((event) => {
  items.iNachttisch_Karte_Liegt.postUpdate(event.newState === "NONE" ? "OFF" : "ON");
}).build("NFC: Karte auf dem Nachttisch (JS)");

rules.JSRule({
  name: "NFC: Sicherheitsereignisse (JS)",
  triggers: LESER.map((l) => triggers.ChannelEventTrigger(kanal(l, "security"))),
  execute: (event) => {
    const s = JSON.parse(event.receivedEvent);
    console.warn(`Sicherheitsereignis: ${event.receivedEvent}`);
    if (s.status === "clone") items.iSmartHome_Alarm.sendCommand("ON");            // Kopie im Umlauf
    if (s.status === "invalid") items.iLabor_Zutritt_Letzter.postUpdate("ungültige Karte – prüfen/erneuern");
    if (s.status === "unknown") items.iLabor_Zutritt_Letzter.postUpdate("unbekannte Karte");
  },
});
