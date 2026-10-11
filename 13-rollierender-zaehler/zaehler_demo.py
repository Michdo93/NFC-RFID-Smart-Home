#!/usr/bin/env python3
"""
Kapitel 13 – Der rollierende Zähler entlarvt eine Kopie (Simulator).

  1. Karte anlernen (Zähler 0)
  2. Jemand kopiert die Karte vollständig – UID UND Nutzdaten (Magic Card)
  3. Das Original wird zweimal benutzt: Zähler 0 -> 1 -> 2
  4. Die Kopie (Zähler 0) wird aufgelegt: Klonverdacht

Und umgekehrt: Wird die Kopie ZUERST benutzt, gilt sie als echt – dann fällt das
Original auf. Auch das ist ein Alarm, nur zeigt er auf die falsche Karte.

Mit --abriss: Die Karte wird mitten im Schreiben von Block 5 weggezogen; der Block ist
danach halb neu, halb alt (so kann ein abgerissener EEPROM-Schreibvorgang enden).
Sie meldet danach „invalid“, bis sie mit personalize.renew() erneuert wird.

Aufruf:  python3 13-rollierender-zaehler/zaehler_demo.py [--kopie-zuerst | --abriss]
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.apdu import Acr122u                           # noqa: E402
from nfcsmarthome.keys import KeyRing                           # noqa: E402
from nfcsmarthome import apdu as ap                              # noqa: E402
from nfcsmarthome.personalize import personalize, renew         # noqa: E402
from nfcsmarthome.readers.common import read_tag, write_payload # noqa: E402
from nfcsmarthome.readers.sim import SimulatedAcr122u, VirtualClassic   # noqa: E402
from nfcsmarthome.registry import Registry                      # noqa: E402
from nfcsmarthome.verify import Verifier                        # noqa: E402

kr = KeyRing(b"Beispiel-Geheimnis-nur-fuer-Demo")
reg = Registry(None)
verifier = Verifier(kr, reg, "rolling")


def use(card, label: str, abriss: bool = False) -> None:
    sim = SimulatedAcr122u()
    sim.place(card)
    acr = Acr122u(sim)
    read = read_tag(acr, "flur", card.atr, kr)
    expected = reg.by_name("michael").counter
    d = verifier.verify(read)
    note = ""
    if d.next_payload and abriss:                    # Block 5 nur zur Hälfte geschrieben
        acr.login(4, kr.classic_key_b(read.uid), ap.KEY_B)
        acr.write_block(5, d.next_payload[16:24] + read.payload[24:32])
        note = "  -> Karte beim Schreiben weggezogen"
    elif d.next_payload and write_payload(acr, read, kr, d.next_payload):
        verifier.commit(d)
        note = f"  -> neuer Zähler {d.data.counter + 1}"
    counter = d.data.counter if d.data else "?"
    print(f"{label:<9} Karte {counter}, Register {expected}  => {d.status:<8}{note}".rstrip())


def main() -> int:
    ap = argparse.ArgumentParser(description="Zähler-Demo")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--kopie-zuerst", action="store_true")
    grp.add_argument("--abriss", action="store_true", help="Schreibvorgang abreißen lassen")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)
    original = VirtualClassic.factory(bytes.fromhex("5A3F9C21"))
    sim = SimulatedAcr122u()
    sim.place(original)
    personalize(Acr122u(sim), original.atr, kr, reg, "michael", "bewohner")
    if args.abriss:
        print("Karte angelernt\n")
        use(original, "Original")
        use(original, "Original", abriss=True)
        use(original, "Original")
        sim = SimulatedAcr122u()
        sim.place(original)
        card = renew(Acr122u(sim), original.atr, kr, reg)
        print(f"Erneuert  aus dem Register, Zähler jetzt {card.counter}")
        use(original, "Original")
        return 0
    kopie = VirtualClassic.from_dict(original.to_dict())        # vollständige Kopie
    print("Karte angelernt und vollständig kopiert (UID + Sektor 1)\n")
    order = [(kopie, "Kopie"), (original, "Original"), (original, "Original")] if args.kopie_zuerst \
        else [(original, "Original"), (original, "Original"), (kopie, "Kopie")]
    for card, label in order:
        use(card, label)
    print(f"\nAlarme im Register: {reg.by_name('michael').alarms}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
