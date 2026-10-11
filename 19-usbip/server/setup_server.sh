#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# USB/IP-Server einrichten:   sudo bash setup_server.sh 1-1.2 [1-1.3 ...]
set -euo pipefail
[[ $# -ge 1 ]] || { echo "Aufruf: $0 <bus-id> [<bus-id> ...]  (Bus-ID: bash find_busid.sh)"; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"

apt-get install -y usbip
# NFC-Band: pcscd würde einen ACR122U festhalten – auf dem Server abschalten
if systemctl list-unit-files pcscd.socket >/dev/null 2>&1; then
    echo "pcscd gefunden – wird abgeschaltet (der Leser gehört dem USB/IP-Client)"
    systemctl disable --now pcscd.socket pcscd.service || true
fi
grep -qx usbip_host /etc/modules || echo usbip_host >> /etc/modules
cp "$DIR/usbipd.service" "$DIR/usbip-server-bind@.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now usbipd.service       # Achtung: Der Dienst heißt usbipd, nicht usbip
for id in "$@"; do
    systemctl enable --now "usbip-server-bind@${id}.service"
done
usbip list -r localhost || true
