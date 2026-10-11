#!/usr/bin/env python3
"""
Kapitel 6 – LED und Summer des ACR122U.

  --signal ok|deny|unknown|alarm|learn|idle   benanntes Signal (feedback.py)
  --summer-aus / --summer-an                  Piepton beim Erkennen einer Karte

Mit aufgelegter Karte geht alles über SCardTransmit. Ohne Karte versucht das Skript den
Escape-Weg (SCardControl 3500) – der muss im CCID-Treiber freigeschaltet sein (Kapitel 6).

Aufruf:  python3 06-pcsc-apdus/led_summer.py --signal alarm
         python3 06-pcsc-apdus/led_summer.py --sim s50_karte_1 --signal ok
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome import hexs                                  # noqa: E402
from nfcsmarthome.apdu import apdu_buzzer_on_detect            # noqa: E402
from nfcsmarthome.feedback import SIGNALS, signal_apdu         # noqa: E402
from nfcsmarthome.readers.simreader import open_single         # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="LED und Summer")
    ap.add_argument("--signal", choices=sorted(SIGNALS))
    ap.add_argument("--summer-aus", action="store_true")
    ap.add_argument("--summer-an", action="store_true")
    ap.add_argument("--sim", metavar="KARTE")
    args = ap.parse_args()
    apdus = []
    if args.summer_aus or args.summer_an:
        apdus.append(apdu_buzzer_on_detect(args.summer_an))
    if args.signal:
        apdus.append(signal_apdu(args.signal))
    if not apdus:
        ap.error("--signal oder --summer-aus/--summer-an angeben")
    for apdu in apdus:
        print(f"> {hexs(bytes(apdu), ' ')}")
        try:
            c = open_single(args.sim)
            data, sw1, sw2 = c.acr.conn.transmit(apdu)
            print(f"< {sw1:02X} {sw2:02X}" + ("   (Simulator: Signal abgespielt)" if c.sim else ""))
        except Exception:
            from nfcsmarthome.readers.pcsc import control_without_card
            print(f"< {hexs(control_without_card(apdu), ' ')}   (ohne Karte, Escape)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
