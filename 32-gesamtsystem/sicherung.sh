#!/usr/bin/env bash
# Kapitel 32 – Geheimnis, Kartenregister und Zugänge VERSCHLÜSSELT sichern
#
#   bash 32-gesamtsystem/sicherung.sh [/opt/NFC-RFID-Smart-Home] [ziel.tar.gpg]
#
# Gesichert werden config/secret.key, config/config.yaml, config/tagdienst_benutzer.json
# und data/karten.json. Wer diese Dateien hat, kann Karten fälschen und openHAB steuern –
# deshalb verschlüsselt gpg sie symmetrisch mit einer Passphrase (AES-256).
# Wiederherstellen:  gpg -d nfc-sicherung-....tar.gpg | tar -C /opt/NFC-RFID-Smart-Home -xf -
set -euo pipefail
BASE="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
ZIEL="${2:-nfc-sicherung-$(date +%Y-%m-%d).tar.gpg}"
DATEIEN=()
for f in config/secret.key config/config.yaml config/tagdienst_benutzer.json data/karten.json; do
    [[ -e "$BASE/$f" ]] && DATEIEN+=("$f")
done
[[ ${#DATEIEN[@]} -gt 0 ]] || { echo "Nichts zu sichern unter $BASE"; exit 1; }
[[ -e "$ZIEL" ]] && { echo "$ZIEL gibt es schon"; exit 1; }
umask 077
tar -C "$BASE" -cf - "${DATEIEN[@]}" | gpg --symmetric --cipher-algo AES256 --output "$ZIEL"
echo "gesichert: ${DATEIEN[*]}"
echo "-> $ZIEL (Passphrase getrennt aufbewahren!)"
