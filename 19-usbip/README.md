# USB/IP – gemeinsame Konfiguration der Reihe

Diese Dateien sind in allen Bänden der Reihe „Smart Home & …“ gleich (Leap Motion,
Gamepads, Kinect, NFC/RFID). Sie gehen auf das Repo
[USBIP-Configuration](https://github.com/Michdo93/USBIP-Configuration) zurück und
beheben dessen Schwächen:

| Vorlage | hier |
|---|---|
| README startet `usbip.service`, die Unit heißt `usbipd.service` | einheitlich `usbipd.service` |
| `ExecStop` trennt **alle** verbundenen Ports | `usbip-detach.sh %i` trennt nur die eigene Bus-ID |
| Watchdog prüft eine fest eingetragene Bus-ID per `grep` (1-1.2 passt auch auf 1-1.21) | alle Bus-IDs aus `/etc/default/usbip-client`, exakter Vergleich in `usbip-port.sh` |
| Server-IP fest in der Unit | `/etc/default/usbip-client` |
| Ubuntu: `/usr/bin/usbip` statt `/usr/sbin/usbip` | die Skripte suchen `usbip` selbst |
| nur ein Server je Client | Instanz `SERVER:BUS-ID` (z. B. `192.168.0.232:1-1.2`) – mehrere Server, auch mit gleicher Bus-ID |

```bash
# Server (Gerät steckt hier)
bash server/find_busid.sh
sudo bash server/setup_server.sh 1-1.2

# Client (Programm läuft hier)
sudo bash client/setup_client.sh 192.168.0.231 1-1.2
# zweiter Server mit eigener Bus-ID-Liste
sudo bash client/setup_client.sh 192.168.0.231 1-1.2 192.168.0.232:1-1.2
```
