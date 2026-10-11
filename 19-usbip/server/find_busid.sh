#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# Bus-IDs der angeschlossenen USB-Geräte anzeigen; bekannte Geräte der Reihe werden markiert.
#   bash find_busid.sh            alle Geräte
#   bash find_busid.sh 072f:2200  nur diese USB-Kennung
set -euo pipefail
sudo modprobe usbip_host
usbip list -l | awk -v filter="${1:-}" '
  /busid/ { id = $3; line = $0; next }
  /\(/ && id != "" {
      match($0, /\([0-9a-f]{4}:[0-9a-f]{4}\)/); usb = substr($0, RSTART + 1, 9)
      tag = ""
      if (usb == "045e:0719" || usb == "045e:0291") tag = "  <- Xbox-360-Funkempfänger"
      else if (usb == "045e:028e")                 tag = "  <- Xbox-360-Controller (Kabel)"
      else if (usb == "054c:0ba0")                 tag = "  <- DualShock-4-USB-Funkadapter"
      else if (usb ~ /^054c:/)                     tag = "  <- Sony-Controller"
      else if (usb ~ /^f182:/)                     tag = "  <- Leap Motion"
      else if (usb ~ /^045e:02(ae|c4|d8)/)         tag = "  <- Kinect"
      else if (usb == "072f:2200")                 tag = "  <- ACR122U (NFC-Leser)"
      if (filter == "" || usb == filter) printf "%-8s %s%s\n", id, $0, tag
      id = ""
  }'
