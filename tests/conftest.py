import asyncio
import importlib.util
import pathlib
import socket
import sys
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "00-virtuelle-geraete"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def load_script(rel: str, name: str):
    """Ein Kapitelskript als Modul laden (Ordnernamen beginnen mit Ziffern)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mini_oh():
    """Mini-openHAB in einem Thread; liefert (url, server)."""
    from werkzeug.serving import make_server
    from mini_openhab import create_server
    srv = create_server()
    port = free_port()
    http = make_server("127.0.0.1", port, srv.app(), threaded=True)
    t = threading.Thread(target=http.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", srv
    http.shutdown()


@pytest.fixture
def broker():
    """Kleiner MQTT-Broker (amqtt) in einem eigenen Thread; liefert den Port."""
    amqtt_broker = pytest.importorskip("amqtt.broker")
    port = free_port()
    config = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
              "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
              "topic-check": {"enabled": False}}
    loop = asyncio.new_event_loop()
    holder = {}

    def run():
        asyncio.set_event_loop(loop)
        b = amqtt_broker.Broker(config, loop=loop)
        holder["b"] = b
        loop.run_until_complete(b.start())
        loop.run_forever()

    threading.Thread(target=run, daemon=True).start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    yield port
    fut = asyncio.run_coroutine_threadsafe(holder["b"].shutdown(), loop)
    try:
        fut.result(5)
    except Exception:
        pass
    loop.call_soon_threadsafe(loop.stop)


@pytest.fixture
def keyring():
    from nfcsmarthome.keys import KeyRing
    return KeyRing(bytes(range(32)))


@pytest.fixture
def simdir(tmp_path, monkeypatch):
    """Virtuelle Karten in ein temporäres Verzeichnis umleiten."""
    from nfcsmarthome.readers import sim
    monkeypatch.setattr(sim, "SIM_DIR", tmp_path / "sim")
    return tmp_path / "sim"


def acr_for(card):
    from nfcsmarthome.apdu import Acr122u
    from nfcsmarthome.readers.sim import SimulatedAcr122u
    s = SimulatedAcr122u()
    s.place(card)
    return Acr122u(s), s
