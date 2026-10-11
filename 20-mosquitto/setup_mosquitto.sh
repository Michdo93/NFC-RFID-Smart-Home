#!/usr/bin/env bash
# Kapitel 20 – Mosquitto installieren und für das NFC-System einrichten
#   sudo bash 20-mosquitto/setup_mosquitto.sh [leser ...]      z. B.  flur kueche
# Fragt die Passwörter interaktiv ab (nichts landet in der Shell-Historie).
# MQTT-Benutzer der ESP32-Leser heißen wie der Leser (Zugriffsliste mit %u).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

apt-get install -y mosquitto mosquitto-clients
install -m 644 "$DIR/mosquitto/conf.d/nfc.conf" /etc/mosquitto/conf.d/nfc.conf
# Mosquitto 2.0 warnt, wenn ACL und Passwortdatei nicht ihm gehören oder lesbar sind
install -m 600 -o mosquitto -g mosquitto "$DIR/mosquitto/acl" /etc/mosquitto/acl

[ -e /etc/mosquitto/passwd ] || install -m 600 /dev/null /etc/mosquitto/passwd
chmod 600 /etc/mosquitto/passwd
for user in nfc-gateway openhab "$@"; do
    echo "Passwort für MQTT-Benutzer '$user':"
    mosquitto_passwd /etc/mosquitto/passwd "$user"
done
chown mosquitto:mosquitto /etc/mosquitto/passwd

systemctl enable mosquitto
systemctl restart mosquitto
systemctl --no-pager status mosquitto | head -5

cat <<'TXT'

Test in zwei Terminals:
  mosquitto_sub -h localhost -u openhab -P <passwort> -t 'nfc/+/event' -v
  mosquitto_pub -h localhost -u nfc-gateway -P <passwort> -t nfc/flur/event -m michael:present
TXT
