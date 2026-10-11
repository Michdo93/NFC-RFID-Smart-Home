#!/usr/bin/env python3
"""
Kapitel 10 – Warum eine UID-Liste kein Schutz ist (nur im Simulator).

1. Eine Karte wird mit ihrer UID ins Register eingetragen (Stufe 1).
2. Eine „Magic Card“ mit beliebig schreibbarer UID bekommt dieselbe UID – im Simulator
   ist das nur eine Kopie der JSON-Datei.
3. Die Prüfung nach Stufe 1 nimmt die Kopie an. Die Prüfung nach Stufe 3 nicht, weil der
   Kopie die signierten Nutzdaten fehlen – und mit ihnen würde der Zähler (Stufe 4) die
   Kopie spätestens beim nächsten Auflegen des Originals entlarven (Kapitel 13).

Dieses Skript arbeitet ausschließlich mit virtuellen Karten.

Aufruf:  python3 10-angriffsmodell/klon_im_simulator.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.apdu import Acr122u                          # noqa: E402
from nfcsmarthome.keys import KeyRing                          # noqa: E402
from nfcsmarthome.readers.common import read_tag               # noqa: E402
from nfcsmarthome.readers.sim import SimulatedAcr122u, VirtualClassic   # noqa: E402
from nfcsmarthome.registry import Registry                      # noqa: E402
from nfcsmarthome.verify import Verifier                        # noqa: E402


def lay(card, keyring=None):
    s = SimulatedAcr122u()
    s.place(card)
    return read_tag(Acr122u(s), "haustuer", card.atr, keyring)


def main() -> int:
    original = VirtualClassic.factory(bytes.fromhex("5A3F9C21"))
    reg = Registry(None)
    reg.add("michael", "bewohner", "5A3F9C21", "classic1k")
    print("Original im Register (Stufe 1: nur UID)")

    magic = VirtualClassic.from_dict(original.to_dict())       # „Magic Card“: UID kopiert
    print("Kopie auf eine Magic Card mit derselben UID\n")

    stufe1 = Verifier(None, reg, "uid")
    print(f"Stufe 1, Original: {stufe1.verify(lay(original)).status}")
    print(f"Stufe 1, Kopie:    {stufe1.verify(lay(magic)).status}   <- nicht zu unterscheiden\n")

    kr = KeyRing(b"Beispiel-Geheimnis-nur-fuer-Demo")
    stufe3 = Verifier(kr, reg, "signed")
    print(f"Stufe 3, Kopie ohne Nutzdaten: {stufe3.verify(lay(magic, kr)).status}"
          "   <- ohne signierte Daten keine Chance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
