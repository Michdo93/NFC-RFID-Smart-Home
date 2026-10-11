#!/usr/bin/env bash
# Gemeinsame USB/IP-Konfiguration der Reihe „Smart Home & …“ (Leap Motion, Gamepads, Kinect, NFC/RFID)
# Datei: /usr/local/sbin/usbip-watchdog.sh
# Hängt eine Bus-ID nicht mehr an einem virtuellen Port, wird ihr Client neu gestartet
# (etwa nach einem Neustart des Servers). Bus-IDs in /etc/default/usbip-client.
source /etc/default/usbip-client
rc=0
for BUS_ID in ${USBIP_BUSIDS}; do
    if [[ -z "$(/usr/local/sbin/usbip-port.sh "$BUS_ID")" ]]; then
        echo "WATCHDOG: USB/IP-Gerät ${BUS_ID} nicht verbunden – Neustart des Clients"
        systemctl restart "usbip-client@${BUS_ID}.service"
        rc=1
    fi
done
exit $rc
