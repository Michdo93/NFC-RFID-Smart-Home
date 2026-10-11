#!/usr/bin/env python3
"""
Kapitel 27 – Server-Sent Events beobachten: Was würde der Rückkanal eines Profils tun?

Liest den Abschnitt „watch“ eines Kartenprofils, abonniert die Items über /rest/events
und gibt jede Zustandsänderung mit den Signalen aus, die die Fernbedienung (Kapitel 26)
daraufhin an den Lesern zeigen würde. Selbst schickt es keine Signale – das erledigt die
laufende Fernbedienung, die die Leser ohnehin in der Hand hat.

Aufruf:  python3 27-zustaende-sse/rueckkanal_sse.py --url http://127.0.0.1:8099 \
                 [--profil 31-labor-szenarien/profile/labor.yaml]
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.actions import CardProfile                    # noqa: E402
from nfcsmarthome.config import REPO_ROOT, try_load_config      # noqa: E402
from nfcsmarthome.rest import OpenHABSender                     # noqa: E402
from nfcsmarthome.runtime import base_parser, setup_logging     # noqa: E402

log = logging.getLogger("rueckkanal")


async def main_async(args) -> None:
    cfg = try_load_config(args.config)
    oh = cfg.section("openhab")
    if args.url:
        oh["url"], oh["token"] = args.url, None
    path = Path(args.profil)
    profile = CardProfile.load(path if path.exists() else REPO_ROOT / path)
    if not profile.watch:
        sys.exit(f"{path} hat keinen Abschnitt „watch“")
    async with OpenHABSender.from_config(oh) as sender:
        print(f"Beobachte {', '.join(profile.watch)}")
        async for item, state in sender.watch_states(profile.watch):
            signals = profile.signals_for(item, state)
            ziel = ", ".join(f"{r}: {s}" for r, s in signals) or "–"
            print(f"{item:<32} = {state:<5} -> {ziel}", flush=True)


def main() -> int:
    ap = base_parser("Rückkanal über SSE beobachten")
    ap.add_argument("--url", help="openHAB-URL (überschreibt config.yaml, ohne Token)")
    ap.add_argument("--profil", default="31-labor-szenarien/profile/labor.yaml")
    args = ap.parse_args()
    setup_logging(args.verbose)
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
