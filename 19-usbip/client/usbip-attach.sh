#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# Datei: /usr/local/sbin/usbip-attach.sh
# Verbindet [<server>:]<bus-id>. Ohne Server gilt USBIP_SERVER aus /etc/default/usbip-client.
#   usbip-attach.sh 1-1.2                 -> Standard-Server
#   usbip-attach.sh 192.168.0.232:1-1.2   -> ausdrücklich dieser Server
set -euo pipefail
ARG="${1:?Aufruf: usbip-attach.sh [<server>:]<bus-id>}"
[[ -r /etc/default/usbip-client ]] && source /etc/default/usbip-client
HOST="${USBIP_SERVER:-}"; BUS_ID="$ARG"
if [[ "$ARG" == *:* ]]; then HOST="${ARG%%:*}"; BUS_ID="${ARG#*:}"; fi
[[ -n "$HOST" ]] || { echo "Kein Server angegeben (USBIP_SERVER fehlt)"; exit 1; }
USBIP="$(command -v usbip || echo /usr/sbin/usbip)"
exec "$USBIP" attach -r "$HOST" -b "$BUS_ID"
