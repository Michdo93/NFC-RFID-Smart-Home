#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# Datei: /usr/local/sbin/usbip-detach.sh
# Trennt NUR das Gerät mit der angegebenen Bus-ID – nicht alle verbundenen Geräte.
BUS_ID="${1:?Aufruf: usbip-detach.sh [<server>:]<bus-id>}"
USBIP="$(command -v usbip || echo /usr/sbin/usbip)"
PORT="$(/usr/local/sbin/usbip-port.sh "$BUS_ID")"
[[ -n "$PORT" ]] && "$USBIP" detach -p "$PORT"
exit 0
