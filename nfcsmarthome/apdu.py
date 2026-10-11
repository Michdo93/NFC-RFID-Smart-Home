"""
apdu.py – der ACR122U über PC/SC (Kapitel 6–8).

Der ACR122U spricht CCID: Das Betriebssystem (pcscd) sieht ihn als Chipkartenleser.
Befehle gehen als APDU (Application Protocol Data Unit) an den Leser. Für kontaktlose
Speicherkarten wie MIFARE Classic und NTAG gibt es keine Standard-APDUs; der ACR122U
kennt dafür eigene „Pseudo-APDUs“ mit der Klasse FF:

  FF CA 00 00 00            UID der aufgelegten Karte
  FF CA 01 00 00            ATS (nur ISO 14443-4, z. B. DESFire)
  FF 82 00 <slot> 06 <key>  Schlüssel (6 Byte) in einen flüchtigen Speicherplatz laden
  FF 86 00 00 05 01 00 <block> <60|61> <slot>   bei MIFARE Classic anmelden (Key A/B)
  FF B0 00 <block> <len>    Block (Classic) bzw. vier Seiten (NTAG) lesen
  FF D6 00 <block> <len> <daten>   Block (16 Byte) bzw. Seite (4 Byte) schreiben
  FF 00 00 00 <len> <PN532-Befehl>  Direkt an den eingebauten PN532 (z. B. D4 42 = InCommunicateThru)
  FF 00 40 <P2> 04 <T1> <T2> <n> <link>  LED und Summer
  FF 00 52 <00|FF> 00       Summer beim Erkennen einer Karte aus/an
  FF 00 48 00 00            Firmware-Version (ASCII)

Acr122u braucht nur ein Objekt mit transmit(apdu: list[int]) -> (data, sw1, sw2) –
genau die Schnittstelle einer pyscard-Verbindung. Der Simulator (readers.sim) bietet
dieselbe Methode; so laufen alle Funktionen dieses Moduls auch ohne Hardware.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from . import hexs

KEY_A, KEY_B = 0x60, 0x61

# Statuswörter (SW1 SW2), die der ACR122U liefert
SW_TEXT = {
    (0x90, 0x00): "OK",
    (0x63, 0x00): "Operation fehlgeschlagen",
    (0x6A, 0x81): "Funktion nicht unterstützt",
    (0x69, 0x82): "Sicherheitsbedingung nicht erfüllt",
}

# Statusbyte des PN532 nach InCommunicateThru (Auszug aus dem PN532-Handbuch)
PN532_STATUS = {
    0x00: "OK",
    0x01: "Zeitüberschreitung – keine Antwort der Karte",
    0x02: "CRC-Fehler",
    0x13: "Datenformat-Fehler",
    0x14: "Authentifizierung fehlgeschlagen",
    0x27: "Befehl im aktuellen Zustand nicht erlaubt",
}


class ApduError(Exception):
    def __init__(self, apdu: Sequence[int], sw1: int, sw2: int, detail: str = ""):
        self.sw = (sw1, sw2)
        text = SW_TEXT.get((sw1, sw2), "unbekannter Status")
        super().__init__(f"APDU {hexs(bytes(apdu[:5]), ' ')} … -> {sw1:02X} {sw2:02X} ({text}){detail}")


class CardError(Exception):
    """Die Karte hat einen durchgereichten Befehl abgelehnt (NAK, Zeitüberschreitung ...)."""


# -- APDU-Bausteine (reine Funktionen, leicht zu testen) -----------------------------------
def apdu_get_uid() -> List[int]:
    return [0xFF, 0xCA, 0x00, 0x00, 0x00]


def apdu_get_ats() -> List[int]:
    return [0xFF, 0xCA, 0x01, 0x00, 0x00]


def apdu_load_key(key: bytes, slot: int = 0) -> List[int]:
    if len(key) != 6:
        raise ValueError("MIFARE-Classic-Schlüssel haben genau 6 Byte")
    return [0xFF, 0x82, 0x00, slot, 0x06] + list(key)


def apdu_authenticate(block: int, key_type: int = KEY_A, slot: int = 0) -> List[int]:
    return [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block, key_type, slot]


def apdu_read(block: int, length: int = 16) -> List[int]:
    return [0xFF, 0xB0, 0x00, block, length]


def apdu_update(block: int, data: bytes) -> List[int]:
    if len(data) not in (4, 16):
        raise ValueError("Schreiben: 16 Byte (Classic-Block) oder 4 Byte (NTAG-Seite)")
    return [0xFF, 0xD6, 0x00, block, len(data)] + list(data)


def apdu_direct(pn532: bytes) -> List[int]:
    return [0xFF, 0x00, 0x00, 0x00, len(pn532)] + list(pn532)


def apdu_firmware() -> List[int]:
    return [0xFF, 0x00, 0x48, 0x00, 0x00]


def apdu_buzzer_on_detect(on: bool) -> List[int]:
    return [0xFF, 0x00, 0x52, 0xFF if on else 0x00, 0x00]


def led_p2(final_red: bool, final_green: bool, blink_red: bool = False,
           blink_green: bool = False, initial_red: bool = False, initial_green: bool = False) -> int:
    """
    P2 der LED-APDU. Bit 0/1: Endzustand rot/grün, Bit 2/3: Endzustand übernehmen,
    Bit 4/5: Anfangszustand beim Blinken, Bit 6/7: rot/grün blinken.
    """
    p2 = 0b0000_1100                      # Endzustand für beide LEDs übernehmen
    p2 |= (1 if final_red else 0) | (2 if final_green else 0)
    p2 |= (0x10 if initial_red else 0) | (0x20 if initial_green else 0)
    p2 |= (0x40 if blink_red else 0) | (0x80 if blink_green else 0)
    return p2


def apdu_led_buzzer(p2: int, t1: int = 1, t2: int = 1, repeat: int = 1, buzzer: int = 0) -> List[int]:
    """
    t1/t2: An- und Auszeit beim Blinken in 100 ms, repeat: Anzahl Wiederholungen,
    buzzer: 0 = aus, 1 = während T1, 2 = während T2, 3 = beides.
    """
    return [0xFF, 0x00, 0x40, p2, 0x04, t1, t2, repeat, buzzer]


# -- der Leser ----------------------------------------------------------------------------
class Acr122u:
    """Hochsprachliche Befehle für einen ACR122U (oder den Simulator)."""

    def __init__(self, connection):
        self.conn = connection
        self.log: Optional[List[Tuple[List[int], bytes, int, int]]] = None   # optional: Mitschnitt

    # Grundfunktion ---------------------------------------------------------------------
    def transmit(self, apdu: List[int], check: bool = True) -> bytes:
        data, sw1, sw2 = self.conn.transmit(list(apdu))
        data = bytes(data)
        if self.log is not None:
            self.log.append((list(apdu), data, sw1, sw2))
        if check and (sw1, sw2) != (0x90, 0x00):
            raise ApduError(apdu, sw1, sw2)
        return data

    # Karte -------------------------------------------------------------------------------
    def uid(self) -> bytes:
        return self.transmit(apdu_get_uid())

    def firmware(self) -> str:
        data, sw1, sw2 = self.conn.transmit(apdu_firmware())
        # Der ACR122U antwortet ohne 90 00: Die Antwort IST der Text (z. B. "ACR122U215").
        return bytes(data + [sw1, sw2]).decode("ascii", "replace").strip("\x00")

    # MIFARE Classic ------------------------------------------------------------------------
    def load_key(self, key: bytes, slot: int = 0) -> None:
        self.transmit(apdu_load_key(key, slot))

    def authenticate(self, block: int, key_type: int = KEY_A, slot: int = 0) -> bool:
        data, sw1, sw2 = self.conn.transmit(apdu_authenticate(block, key_type, slot))
        return (sw1, sw2) == (0x90, 0x00)

    def login(self, block: int, key: bytes, key_type: int = KEY_A) -> bool:
        """Schlüssel laden und am Sektor des Blocks anmelden."""
        self.load_key(key)
        return self.authenticate(block, key_type)

    def read_block(self, block: int, length: int = 16) -> bytes:
        return self.transmit(apdu_read(block, length))

    def write_block(self, block: int, data: bytes) -> None:
        self.transmit(apdu_update(block, data))

    # NTAG / Ultralight ----------------------------------------------------------------------
    def read_pages(self, page: int) -> bytes:
        """Vier Seiten ab page (16 Byte) – der READ-Befehl von NTAG liefert immer vier."""
        return self.transmit(apdu_read(page, 16))

    def write_page(self, page: int, data: bytes) -> None:
        if len(data) != 4:
            raise ValueError("Eine NTAG-Seite hat 4 Byte")
        self.transmit(apdu_update(page, data))

    # Durchreichen an den PN532 -------------------------------------------------------------
    def direct(self, pn532: bytes) -> bytes:
        return self.transmit(apdu_direct(pn532))

    def transceive(self, raw: bytes) -> bytes:
        """Rohbefehl an die Karte (InCommunicateThru, D4 42). Liefert die Antwort der Karte."""
        resp = self.direct(bytes([0xD4, 0x42]) + raw)
        if len(resp) < 3 or resp[0] != 0xD5 or resp[1] != 0x43:
            raise CardError(f"unerwartete PN532-Antwort {hexs(resp, ' ')}")
        status = resp[2] & 0x3F
        if status != 0:
            raise CardError(PN532_STATUS.get(status, f"PN532-Status {status:02X}"))
        return resp[3:]

    # NTAG-Befehle über transceive ----------------------------------------------------------
    def ntag_get_version(self) -> bytes:
        return self.transceive(bytes([0x60]))

    def ntag_pwd_auth(self, pwd: bytes) -> bytes:
        """PWD_AUTH (1B). Liefert PACK (2 Byte). Falsches Passwort -> CardError."""
        if len(pwd) != 4:
            raise ValueError("Das NTAG-Passwort hat 4 Byte")
        pack = self.transceive(bytes([0x1B]) + pwd)
        if len(pack) != 2:
            raise CardError("Passwort abgelehnt")
        return pack

    def ntag_read_sig(self) -> bytes:
        """READ_SIG (3C 00): ECC-Originalitätssignatur von NXP (32 Byte)."""
        return self.transceive(bytes([0x3C, 0x00]))

    def ntag_read_cnt(self) -> int:
        """READ_CNT (39 02): 24-Bit-NFC-Zähler (wenn NFC_CNT_EN gesetzt ist)."""
        data = self.transceive(bytes([0x39, 0x02]))
        return int.from_bytes(data[:3], "little")

    # LED und Summer ------------------------------------------------------------------------
    def buzzer_on_detect(self, on: bool) -> None:
        data, sw1, sw2 = self.conn.transmit(apdu_buzzer_on_detect(on))
        if sw1 != 0x90:
            raise ApduError(apdu_buzzer_on_detect(on), sw1, sw2)

    def led_buzzer(self, p2: int, t1: int = 1, t2: int = 1, repeat: int = 1, buzzer: int = 0) -> None:
        apdu = apdu_led_buzzer(p2, t1, t2, repeat, buzzer)
        data, sw1, sw2 = self.conn.transmit(apdu)
        if sw1 != 0x90:                     # Antwort: 90 <LED-Zustand>
            raise ApduError(apdu, sw1, sw2)
