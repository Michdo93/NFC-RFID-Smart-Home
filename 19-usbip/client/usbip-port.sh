#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# Datei: /usr/local/sbin/usbip-port.sh
# Gibt die Nummer des virtuellen Ports aus, an dem die entfernte Bus-ID hängt
# (leer, wenn sie nicht verbunden ist). Ausgabe von "usbip port" z. B.:
#   Port 00: <Port in Use> at Full Speed(12Mbps)
#          Advanced Card Systems, Ltd : ACR122U PICC Interface (072f:2200)
#          3-1 -> usbip://192.168.0.231:3240/1-1.2
# Verglichen wird die Bus-ID am Ende der usbip://-Adresse exakt (1-1.2 ist nicht 1-1.21).
# Mit SERVER:BUS-ID (z. B. 192.168.0.232:1-1.2) zählt zusätzlich der Server – nötig,
# wenn mehrere Server Geräte mit derselben Bus-ID anbieten (NFC-Band, Kapitel 19).
# Ohne Server gilt USBIP_SERVER aus /etc/default/usbip-client (falls vorhanden).
ARG="${1:?Aufruf: usbip-port.sh [<server>:]<bus-id>}"
USBIP_SERVER=""
[[ -r /etc/default/usbip-client ]] && source /etc/default/usbip-client
HOST="$USBIP_SERVER"; BUS_ID="$ARG"
if [[ "$ARG" == *:* ]]; then HOST="${ARG%%:*}"; BUS_ID="${ARG#*:}"; fi
USBIP="$(command -v usbip || echo /usr/sbin/usbip)"
"$USBIP" port 2>/dev/null | awk -v id="$BUS_ID" -v host="$HOST" '
  /^Port [0-9]+:/ { p = $2; sub(":", "", p) }
  /usbip:\/\// {
      n = split($NF, a, "/"); split(a[3], h, ":")
      if (a[n] == id && (host == "" || h[1] == host)) print p + 0 }'
