"""Ansatz B: Kartenprofile, Executor gegen das Mini-openHAB, Profilprüfung."""
import asyncio

from nfcsmarthome.actions import CardProfile
from nfcsmarthome.check import check_profile
from nfcsmarthome.logic import Gesture
from nfcsmarthome.registry import Card
from nfcsmarthome.rest import OpenHABSender
from nfcsmarthome.runtime import Executor
from nfcsmarthome.verify import Decision

LABOR = "31-labor-szenarien/profile/labor.yaml"
CARDS = [Card(1, "michael", "bewohner", "5A3F9C21", "classic1k", "Michael", value="Michael"),
         Card(2, "gast_lea", "gast", "04A7", "ntag216", "Lea"),
         Card(3, "radio_swr3", "medien", "045B", "ntag215", "SWR3", value="SWR3"),
         Card(4, "gute_nacht", "szene", "8E11", "classic1k", "Gute Nacht"),
         Card(5, "kinoabend", "szene", "C2D4", "classic1k", "Kinoabend"),
         Card(6, "admin", "admin", "0491", "ntag215", "Admin")]


def g(reader, card, kind, status="accepted"):
    return Gesture(reader, card.name if status == "accepted" else status, kind,
                   Decision(status, reader, card.uid, "rolling", card))


def test_lookup_all_matches():
    p = CardProfile.load(LABOR)
    ops = p.handle(g("nachttisch", CARDS[3], "present"))
    assert [str(o) for o in ops] == ["update iNachttisch_Karte_Liegt ON", "command gLichter OFF",
                                     "command gRollladen DOWN", "command iSzene_Gute_Nacht ON"]
    ops = p.handle(g("kueche", CARDS[2], "removed"))
    assert [str(o) for o in ops] == ["command iKueche_Webradio_SWR3 OFF"]
    ops = p.handle(g("flur", CARDS[0], "hold"))
    assert [o.kind for o in ops] == ["update", "feedback"] and ops[0].item == "iAnwesend_Michael"
    ops = p.handle(g("flur", CARDS[0], "present", status="clone"))
    assert [str(o) for o in ops] == ["command iSmartHome_Alarm ON"]


def test_profiles_check():
    import sys
    sys.path.insert(0, "00-virtuelle-geraete")
    from mini_openhab import create_server
    items = create_server().items
    for path in (LABOR, "26-kartenaktionen/profile/erste_karten.yaml"):
        errors, n = check_profile(CardProfile.load(path), items, CARDS)
        assert errors == [], errors
        assert n >= 8


def test_executor_against_mini_openhab(mini_oh):
    url, srv = mini_oh
    p = CardProfile.load(LABOR)

    async def main():
        async with OpenHABSender(url) as sender:
            ex = Executor(sender).start()
            ex.submit(p.handle(g("nachttisch", CARDS[0], "tap")))
            ex.submit(p.handle(g("kueche", CARDS[2], "present")))
            ex.submit(p.handle(g("flur", CARDS[0], "tap")))
            await ex.drain()
            await ex.stop()

    asyncio.run(main())
    st = {k: v["state"] for k, v in srv.items.items()}
    assert st["iSmartHome_Hue_Lampen_Schalter"] == "ON"
    assert st["iKueche_Webradio_SWR3"] == "ON"
    assert st["iAnwesend_Michael"] == "ON"


def test_increment_counts_entries(mini_oh):
    """{increment: iLabor_Zutritte} zählt jeden Zutritt am Flur (Kapitel 31)."""
    url, srv = mini_oh
    p = CardProfile.load(LABOR)

    async def main():
        async with OpenHABSender(url) as sender:
            ex = Executor(sender).start()
            ex.submit(p.handle(g("flur", CARDS[0], "present")))
            ex.submit(p.handle(g("flur", CARDS[0], "present")))
            await ex.drain()
            await ex.stop()

    asyncio.run(main())
    assert srv.items["iLabor_Zutritte"]["state"] == "2"
