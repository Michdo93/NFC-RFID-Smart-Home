#!/usr/bin/env bash
# Kapitel 21 – Gateway (oder Fernbedienung) als Dienst unter dem Benutzer „nfc“ einrichten
#
#   sudo bash 21-nfc-gateway/dienst_einrichten.sh                 nfc-gateway.service
#   sudo bash 21-nfc-gateway/dienst_einrichten.sh fernbedienung   nfc-fernbedienung.service
#
# Kopiert das Repository nach /opt/NFC-RFID-Smart-Home, legt dort eine venv an und
# übernimmt config/config.yaml und config/secret.key (Rechte 600, Eigentümer nfc).
# Das Kartenregister (data/) wird mitgenommen, falls vorhanden.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST=/opt/NFC-RFID-Smart-Home
case "${1:-gateway}" in
    gateway)       UNIT="$SRC/21-nfc-gateway/nfc-gateway.service" ;;
    fernbedienung) UNIT="$SRC/32-gesamtsystem/nfc-fernbedienung.service" ;;
    *) echo "Aufruf: $0 [gateway|fernbedienung]"; exit 1 ;;
esac
for f in config/config.yaml config/secret.key; do
    [[ -e "$SRC/$f" ]] || { echo "$f fehlt – erst Kapitel 11 und config.example.yaml"; exit 1; }
done

getent group nfc >/dev/null || groupadd --system nfc          # gibt es schon aus Kapitel 5
id nfc >/dev/null 2>&1 || useradd --system -g nfc --home-dir "$DST" --shell /usr/sbin/nologin nfc

mkdir -p "$DST"
# Code kopieren – ohne venv, Caches und lokale Geheimnisse (die kommen gezielt danach)
tar -C "$SRC" --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=.pio \
    --exclude=config/config.yaml --exclude=config/secret.key --exclude=data -cf - . | tar -C "$DST" -xf -
install -d -o nfc -g nfc -m 700 "$DST/data"
[[ -d "$SRC/data" ]] && cp -a "$SRC/data/." "$DST/data/"
install -o nfc -g nfc -m 600 "$SRC/config/config.yaml" "$DST/config/config.yaml"
install -o nfc -g nfc -m 600 "$SRC/config/secret.key"  "$DST/config/secret.key"
chown -R nfc:nfc "$DST/data"
chown root:nfc "$DST/config" && chmod 750 "$DST/config"

python3 -m venv "$DST/.venv"
"$DST/.venv/bin/pip" install -q -r "$DST/requirements.txt"

install -m 644 "$SRC/05-installation/50-pcscd-nfc.rules" /etc/polkit-1/rules.d/50-pcscd-nfc.rules
install -m 644 "$UNIT" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "$(basename "$UNIT")"
systemctl --no-pager status "$(basename "$UNIT")" | head -5
echo
echo "Wichtig: Ab jetzt führt der Dienst das Register unter $DST/data."
echo "Skripte zum Anlernen also mit  sudo -u nfc NFC_CONFIG=$DST/config/config.yaml ...  starten"
echo "oder den Dienst vorher anhalten (systemctl stop) – nie zwei Register parallel."
