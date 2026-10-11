#!/usr/bin/env python3
"""
Kapitel 9 – Vom Ereignis zur Geste: present, tap, hold, removed – mit Entprellung.

Noch ohne Prüfung: Jede Karte heißt hier nach ihrer UID. (Ab Kapitel 12 kommt der Name
aus dem Kartenregister.)

Aufruf:  python3 09-ereignisse/gesten.py --sim sim/szenarien/auflegen.yaml
         python3 09-ereignisse/gesten.py                     (ACR122U)
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.logic import TagLogic                        # noqa: E402
from nfcsmarthome.registry import Card                          # noqa: E402
from nfcsmarthome.verify import Decision                        # noqa: E402


async def main_async(args) -> None:
    if args.sim:
        from nfcsmarthome.readers.simreader import SimReader
        reader = SimReader.from_file(args.sim)
    else:
        from nfcsmarthome.readers.pcsc import PcscReader
        reader = PcscReader("acr122u")
    logic = TagLogic(args.halten, args.weg)
    t0 = time.monotonic()

    def show(gestures):
        for g in gestures:
            extra = f"  ({g.duration:.1f} s)" if g.kind in ("tap", "removed", "hold") else ""
            print(f"{time.monotonic() - t0:6.2f} s    Geste    {g.reader:<10} {g}{extra}")

    async def ticker():
        while True:
            await asyncio.sleep(0.05)
            show(logic.tick(time.monotonic()))

    tick = asyncio.create_task(ticker())
    async for ev in reader.events():
        print(f"{ev.t - t0:6.2f} s  Ereignis   {ev}")
        d = None
        if ev.read:   # ohne Register: Name = UID
            d = Decision("accepted", ev.reader, ev.read.uid_hex, "uid",
                         Card(0, ev.read.uid_hex[:8], "-", ev.read.uid_hex, ev.read.tag_type))
        show(logic.feed(ev, d))
    await asyncio.sleep(args.weg + 0.1)
    tick.cancel()


def main() -> int:
    ap = argparse.ArgumentParser(description="Gesten")
    ap.add_argument("--sim", metavar="SZENARIO")
    ap.add_argument("--halten", type=float, default=1.5, help="Sekunden bis hold")
    ap.add_argument("--weg", type=float, default=0.6, help="Entprellzeit beim Abnehmen")
    try:
        asyncio.run(main_async(ap.parse_args()))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
