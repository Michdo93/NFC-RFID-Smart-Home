#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# USB/IP-Client einrichten:   sudo bash setup_client.sh <server-ip> <bus-id> [<bus-id> | <server>:<bus-id> ...]
set -euo pipefail
[[ $# -ge 2 ]] || { echo "Aufruf: $0 <server-ip> <bus-id> [<bus-id> ...]"; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER="$1"; shift

# Ubuntu: usbip steckt in linux-tools; Raspberry Pi OS/Debian: Paket usbip
if ! command -v usbip >/dev/null; then
    apt-get install -y usbip 2>/dev/null || apt-get install -y "linux-tools-$(uname -r)" || apt-get install -y linux-tools-generic
fi
grep -qx vhci-hcd /etc/modules || echo vhci-hcd >> /etc/modules

# Die Skripte suchen usbip selbst (Ubuntu: /usr/bin, Debian/Raspberry Pi OS: /usr/sbin)
USBIP="$(command -v usbip)"
cp "$DIR/usbip-client@.service" "$DIR/usbip-watchdog.service" "$DIR/usbip-watchdog.timer" /etc/systemd/system/
install -m 755 "$DIR/usbip-port.sh" "$DIR/usbip-attach.sh" "$DIR/usbip-detach.sh" "$DIR/usbip-watchdog.sh" /usr/local/sbin/
printf 'USBIP_SERVER=%s\nUSBIP_BUSIDS="%s"\n' "$SERVER" "$*" > /etc/default/usbip-client

systemctl daemon-reload
for id in "$@"; do
    systemctl enable --now "usbip-client@${id}.service"
done
systemctl enable --now usbip-watchdog.timer
"${USBIP}" port
