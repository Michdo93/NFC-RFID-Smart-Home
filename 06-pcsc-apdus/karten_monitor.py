#!/usr/bin/env python3
"""
Kapitel 6 – Auflegen und Abnehmen beobachten (pyscard CardMonitor bzw. Simulator).

Aufruf:  python3 06-pcsc-apdus/karten_monitor.py                   (ACR122U)
         python3 06-pcsc-apdus/karten_monitor.py --sim sim/szenarien/auflegen.yaml
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.readers.pcsc import PcscReader               # noqa: E402
from nfcsmarthome.readers.simreader import SimReader           # noqa: E402


async def main_async(args) -> None:
    reader = SimReader.from_file(args.sim) if args.sim else PcscReader("acr122u")
    t0 = time.monotonic()
    async for ev in reader.events():
        print(f"{ev.t - t0:6.2f} s  {ev}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Karten beobachten")
    ap.add_argument("--sim", metavar="SZENARIO", help="Szenario-Datei statt ACR122U")
    try:
        asyncio.run(main_async(ap.parse_args()))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
