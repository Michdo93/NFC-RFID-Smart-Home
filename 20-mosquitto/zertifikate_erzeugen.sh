#!/usr/bin/env bash
# Kapitel 20 – Eine eigene kleine CA und ein Server-Zertifikat für Mosquitto (TLS, Port 8883)
#
#   sudo bash 20-mosquitto/zertifikate_erzeugen.sh nfc.home.arpa 192.168.0.10
#
# Legt unter /etc/mosquitto/certs an:
#   ca.crt      CA-Zertifikat – kommt auf Gateway, openHAB und ESP32 (öffentlich)
#   ca.key      privater CA-Schlüssel – bleibt hier, Rechte 600, NIE kopieren
#   server.crt  Zertifikat des Brokers (Name und IP als SubjectAltName)
#   server.key  privater Schlüssel des Brokers, Rechte 600, gehört mosquitto
set -euo pipefail
NAME="${1:?Aufruf: $0 <hostname> [<ip>]}"
IP="${2:-}"
DIR=/etc/mosquitto/certs
SAN="DNS:${NAME}"
[[ -n "$IP" ]] && SAN="${SAN},IP:${IP}"
mkdir -p "$DIR"
cd "$DIR"
umask 077
if [[ ! -e ca.key ]]; then
    openssl req -x509 -new -newkey rsa:3072 -nodes -days 3650 -sha256 \
        -subj "/CN=NFC Smart Home CA" -keyout ca.key -out ca.crt
fi
openssl req -new -newkey rsa:2048 -nodes -subj "/CN=${NAME}" -keyout server.key -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 825 -sha256 \
    -extfile <(printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth\n' "$SAN") -out server.crt
rm -f server.csr
chmod 644 ca.crt server.crt
chown mosquitto:mosquitto server.key
echo "Fertig: $DIR/ca.crt (verteilen), $DIR/server.crt, $DIR/server.key"
openssl x509 -in server.crt -noout -subject -ext subjectAltName
