"""
feedback.py – LED und Summer des ACR122U als Rückmeldung (Kapitel 6 und 23).

Der ACR122U hat eine zweifarbige LED (rot/grün) und einen Summer. Die APDU
FF 00 40 <P2> 04 <T1> <T2> <Wiederholungen> <Summer> lässt beide blinken
(T1/T2 in 100 ms). Wir verwenden benannte Signale – dieselben Namen versteht
auch die ESP32-Firmware:

  ok        grün, ein kurzer Ton                    Karte angenommen
  deny      rot, zwei kurze Töne                    nicht zugelassen, gesperrt
  unknown   rot, ein Ton                            unbekannte Karte
  alarm     rot blinkt 10×, Ton bei jedem Blinken    Klon- oder Fälschungsverdacht
  learn     grün/rot im Wechsel, kein Ton           Anlernmodus: Karte auflegen
  idle      LEDs aus, kein Ton                       Ruhezustand

Ohne aufgelegte Karte gehen diese APDUs nur über den „Escape“-Weg (SCardControl);
siehe readers.pcsc.
"""

from __future__ import annotations

from typing import Dict, Tuple

from .apdu import apdu_led_buzzer, led_p2

# Signal -> (P2, T1, T2, Wiederholungen, Summer)
SIGNALS: Dict[str, Tuple[int, int, int, int, int]] = {
    "ok":      (led_p2(False, False, blink_green=True, initial_green=True), 2, 1, 1, 1),
    "deny":    (led_p2(False, False, blink_red=True, initial_red=True), 1, 1, 2, 1),
    "unknown": (led_p2(False, False, blink_red=True, initial_red=True), 3, 1, 1, 1),
    "alarm":   (led_p2(False, False, blink_red=True, initial_red=True), 2, 2, 10, 1),
    "learn":   (led_p2(False, False, blink_red=True, blink_green=True, initial_green=True), 5, 5, 6, 0),
    "idle":    (led_p2(False, False), 1, 1, 1, 0),
}

# Prüfergebnis -> Signal
STATUS_SIGNAL = {
    "accepted": "ok", "unknown": "unknown", "foreign": "unknown", "not_allowed": "deny",
    "blocked": "deny", "invalid": "deny", "clone": "alarm",
}


def signal_apdu(name: str):
    if name not in SIGNALS:
        raise ValueError(f"Signal {name!r} unbekannt – {', '.join(SIGNALS)}")
    p2, t1, t2, rep, buz = SIGNALS[name]
    return apdu_led_buzzer(p2, t1, t2, rep, buz)


def signal(acr, name: str) -> None:
    """Signal über einen apdu.Acr122u ausgeben (braucht eine aufgelegte Karte)."""
    p2, t1, t2, rep, buz = SIGNALS[name]
    acr.led_buzzer(p2, t1, t2, rep, buz)
