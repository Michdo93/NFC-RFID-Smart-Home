"""Gesten, Gateway und Szenarien mit dem Simulator."""
import asyncio
import json

from conftest import acr_for

from nfcsmarthome.apdu import Acr122u
from nfcsmarthome.events import ReaderEvent, TagRead
from nfcsmarthome.gateway import LearnRequest, NfcGateway, PrintSink
from nfcsmarthome.logic import TagLogic
from nfcsmarthome.personalize import personalize
from nfcsmarthome.readers.readerset import ReaderSet
from nfcsmarthome.readers.sim import SimulatedAcr122u, load_card, save_card
from nfcsmarthome.readers.simreader import SimReader
from nfcsmarthome.registry import Registry
from nfcsmarthome.verify import Decision, Verifier


def ev(kind, t, uid=b"\x01\x02\x03\x04", reader="r"):
    return ReaderEvent(kind, reader, TagRead(reader, uid, t=t) if kind == "present" else None, t)


def acc(name="karte"):
    from nfcsmarthome.registry import Card
    return Decision("accepted", "r", "01020304", "signed", Card(1, name, "bewohner", "01020304", "x"))


def test_tap_hold_removed():
    lg = TagLogic(hold_time=1.0, absent_time=0.5)
    assert [str(g) for g in lg.feed(ev("present", 0.0), acc())] == ["karte:present"]
    lg.feed(ev("removed", 0.3))
    assert lg.tick(0.6) == []                                  # noch in der Entprellzeit
    assert [str(g) for g in lg.tick(0.9)] == ["karte:tap", "karte:removed"]
    lg.feed(ev("present", 2.0), acc())
    assert [str(g) for g in lg.tick(3.1)] == ["karte:hold"]
    lg.feed(ev("removed", 4.0))
    assert [str(g) for g in lg.tick(4.6)] == ["karte:removed"]


def test_debounce_same_card():
    lg = TagLogic(hold_time=5, absent_time=0.5)
    lg.feed(ev("present", 0.0), acc())
    lg.feed(ev("removed", 1.0))
    assert lg.feed(ev("present", 1.2), acc()) == []            # kurz verloren – nichts passiert
    assert lg.tick(2.0) == []
    assert lg.present("r") is not None


def test_unknown_card_gesture_name():
    lg = TagLogic()
    g = lg.feed(ev("present", 0), Decision("unknown", "r", "01", "signed"))[0]
    assert str(g) == "unknown:present"


def personalize_sim(name, keyring, reg, card_name, role):
    card = load_card(name)
    s = SimulatedAcr122u()
    s.place(card)
    personalize(Acr122u(s), card.atr, keyring, reg, card_name, role)
    save_card(name, card)


def run(coro):
    return asyncio.run(coro)


def test_gateway_scenario(simdir, keyring, tmp_path):
    reg = Registry(tmp_path / "karten.json")
    personalize_sim("s50_karte_1", keyring, reg, "michael", "bewohner")
    steps = [{"nach": 0, "karte": "s50_karte_1", "leser": "nachttisch"},
             {"nach": 0.05, "entfernen": True, "leser": "nachttisch"},
             {"nach": 0.05, "karte": "s50_karte_2", "leser": "nachttisch"},
             {"nach": 0.05, "entfernen": True, "leser": "nachttisch"},
             {"nach": 0.05, "karte": "s50_karte_1", "leser": "nachttisch"}]
    sim = SimReader(steps, keyring=keyring)
    sink = PrintSink(out=lambda s: None)
    gw = NfcGateway(Verifier(keyring, reg, "rolling"), TagLogic(1.0, 0.02), ReaderSet([sim]), sink,
                    keyring=keyring)
    run(gw.run(tick=0.01))
    assert [d.status for d in gw.decisions] == ["accepted", "unknown", "accepted"]
    assert [d.data.counter for d in gw.decisions if d.data] == [0, 1]
    assert Registry(tmp_path / "karten.json").by_name("michael").counter == 2
    topics = [(t, p) for t, p, r in sink.sent]
    assert ("nfc/nachttisch/event", "michael:present") in topics
    assert ("nfc/nachttisch/event", "michael:tap") in topics
    assert ("nfc/nachttisch/card", "NONE") in topics
    sec = [json.loads(p) for t, p in topics if t.endswith("/security")]
    assert sec[0]["status"] == "unknown"
    assert [s for _, s in sim.signals] == ["ok", "unknown", "ok"]


def test_clone_detected_in_scenario(simdir, keyring, tmp_path):
    reg = Registry(tmp_path / "karten.json")
    personalize_sim("ntag215_karte_1", keyring, reg, "gast1", "gast")
    clone = load_card("ntag215_karte_1").to_dict()          # Kopie VOR der ersten Benutzung
    steps = [{"nach": 0, "karte": "ntag215_karte_1"}, {"nach": 0.05, "entfernen": True}]
    gw = NfcGateway(Verifier(keyring, reg, "rolling"), TagLogic(1, 0.01),
                    ReaderSet([SimReader(steps, keyring=keyring)]), PrintSink(lambda s: None))
    run(gw.run(tick=0.01))
    (simdir / "klon.json").write_text(json.dumps(clone))
    gw2 = NfcGateway(Verifier(keyring, reg, "rolling"), TagLogic(1, 0.01),
                     ReaderSet([SimReader([{"nach": 0, "karte": str(simdir / "klon.json")}], keyring=keyring)]),
                     PrintSink(lambda s: None))
    run(gw2.run(tick=0.01))
    assert gw2.decisions[0].status == "clone"


def test_learn_mode(simdir, keyring, tmp_path):
    reg = Registry(tmp_path / "karten.json")
    sim = SimReader([{"nach": 0, "karte": "ntag216_armband", "leser": "nachttisch"},
                     {"nach": 0.05, "entfernen": True, "leser": "nachttisch"},
                     {"nach": 0.05, "karte": "ntag216_armband", "leser": "nachttisch"}], keyring=keyring)
    sink = PrintSink(lambda s: None)
    gw = NfcGateway(Verifier(keyring, reg, "rolling"), TagLogic(1, 0.01), ReaderSet([sim]), sink,
                    keyring=keyring)
    gw.command("nfc/gateway/learn", json.dumps({"name": "armband_lea", "role": "gast", "leser": "nachttisch"}))
    run(gw.run(tick=0.01))
    assert reg.by_name("armband_lea") is not None
    assert [d.status for d in gw.decisions] == ["accepted"]


def test_slow_writer_does_not_block_other_reader(keyring, tmp_path):
    """Ein Leser, der beim Schreiben hängt, hält die Ereignisse anderer Leser nicht auf."""
    import time
    from nfcsmarthome import cardformat
    from nfcsmarthome.readers.base import Reader

    reg = Registry(tmp_path / "karten.json")
    uid = bytes.fromhex("5A3F9C21")
    card = reg.add("michael", "bewohner", uid.hex(), "classic1k")
    payload = cardformat.encode(cardformat.CardData(keyring.installation_id(), card.id, "bewohner"),
                                uid, keyring.mac_key())
    seen = []

    class Slow(Reader):
        can_write = True

        async def events(self):
            for reader in ("flur", "kueche"):
                read = TagRead(reader, uid, "classic1k", t=time.monotonic())
                read.payload = payload
                yield ReaderEvent("present", reader, read, read.t)

        async def write(self, read, p):
            await asyncio.sleep(0.3 if read.reader == "flur" else 0)
            return False

    gw = NfcGateway(Verifier(keyring, reg, "rolling"), TagLogic(1, 0.01), ReaderSet([Slow()]),
                    PrintSink(lambda s: None), on_gesture=lambda g: seen.append((g.reader, time.monotonic())))
    t0 = time.monotonic()
    run(gw.run(tick=0.01))
    first_kueche = next(t for r, t in seen if r == "kueche")
    assert first_kueche - t0 < 0.2                    # nicht 0,3 s hinter dem Flur-Leser
