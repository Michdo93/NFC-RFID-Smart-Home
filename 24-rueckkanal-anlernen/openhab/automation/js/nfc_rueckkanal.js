// ============================================================================
// Kapitel 24 – Rückkanal, Anlernen und Sperren (JavaScript Scripting)
// Datei: $OPENHAB_CONF/automation/js/nfc_rueckkanal.js
// Nur EINE Sprachvariante (DSL, JS oder Python) gleichzeitig aktivieren!
// ============================================================================

const ersterGross = (s) => s.charAt(0).toUpperCase() + s.slice(1);

rules.when().item("NFC_Anlernen_Start").receivedCommand().toOn().then(() => {
  const name = items.NFC_Anlernen_Name.state;
  const leser = items.NFC_Anlernen_Leser.isUninitialized ? "nachttisch" : items.NFC_Anlernen_Leser.state;
  if (!/^[a-z0-9_]{1,24}$/.test(name)) {
    console.warn("Anlernen: Name fehlt oder ungültig (a–z, 0–9, _)");
    return;
  }
  items.NFC_Gateway_Anlernen.sendCommand(JSON.stringify({ name, role: items.NFC_Anlernen_Rolle.state, leser }));
  items.getItem(`NFC_${ersterGross(leser)}_Signal`).sendCommand("learn");
}).build("NFC: Anlernen starten (JS)");

rules.when().item("NFC_Sperren_Start").receivedCommand().then((event) => {
  if (items.NFC_Sperren_Name.isUninitialized) return;
  const ziel = event.receivedCommand === "ON" ? items.NFC_Gateway_Sperren : items.NFC_Gateway_Entsperren;
  ziel.sendCommand(items.NFC_Sperren_Name.state);
}).build("NFC: Karte sperren oder entsperren (JS)");

rules.when().item("iSmartHome_Alarm").changed().to("ON").then(() => {
  items.gNFC.descendents.filter((i) => i.name.endsWith("_Signal")).forEach((i) => i.sendCommand("alarm"));
}).build("NFC: Alarm an allen Lesern zeigen (JS)");

rules.when().item("iSmartHome_Alarmanlage_Scharf").changed().then((event) => {
  items.NFC_Flur_Signal.sendCommand(event.newState === "ON" ? "deny" : "ok");
}).build("NFC: Alarmanlage am Flur bestätigen (JS)");
