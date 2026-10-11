#!/usr/bin/env python3
"""
Kapitel 29 – Der Tag-Dienst: signierte Smartphone-Tags sicher auswerten.

Ein Tag trägt eine URL  https://home.local:8443/t/<tag>/<aktion>?s=<signatur>.
Tippt ein Smartphone darauf, öffnet sich diese Seite. Der Dienst prüft

  1. WAS:  Ist die Signatur gültig? (Tag-ID + Aktion, HMAC mit dem Installationsgeheimnis)
           -> Ein umgeschriebener Tag mit anderer Aktion fällt durch.
  2. WER:  Ist das Gerät angemeldet? (Sitzungs-Cookie, einmal anmelden, 90 Tage gültig)
           -> Ein Besucher, der den Tag kopiert, kann damit nichts auslösen.
  3. WIE:  Folgenreiche Aktionen (bestaetigen: true) erst nach einem zweiten Tippen –
           per POST mit CSRF-Token, damit kein fremder Link sie auslösen kann.

Aufruf:  python3 29-signierte-urls/tag_dienst.py [--url http://127.0.0.1:8080] [--port 8088] --proxy
         Für den Betrieb hinter einem Reverse Proxy mit HTTPS (Caddyfile.example, Kapitel 29):
         https://home.local:8443  ->  http://127.0.0.1:8088
         --unsicher-http nur zum Ausprobieren im eigenen Netz (Cookie ohne Secure-Flag).
"""

import argparse
import json
import logging
import secrets
import sys
import time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfcsmarthome.config import load_yaml, try_load_config      # noqa: E402
from nfcsmarthome.phone import check_signature                  # noqa: E402
from nfcsmarthome.source import load_keyring                    # noqa: E402

HERE = Path(__file__).resolve().parent
log = logging.getLogger("tagdienst")


class OpenHAB:
    """Synchroner Zugriff mit python-openhab-rest-client."""

    def __init__(self, url, token=None):
        from openhab import Items, OpenHABClient
        self.items = Items(OpenHABClient(url=url, token=token))

    def run(self, op: dict) -> str:
        if "toggle" in op:
            state = str(self.items.getItemState(op["toggle"])).strip()
            new = "OFF" if state == "ON" else "ON"
            self.items.sendCommand(op["toggle"], new)
            return f"{op['toggle']} -> {new}"
        self.items.sendCommand(op["command"], str(op["value"]))
        return f"{op['command']} -> {op['value']}"


def create_app(keyring, actions_file, users_file, openhab, secure_cookie=True):
    app = Flask("tagdienst", template_folder=str(HERE / "templates"))
    app.secret_key = keyring.derive("tagdienst-session")
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=secure_cookie,
                      PERMANENT_SESSION_LIFETIME=timedelta(days=90))
    url_key = keyring.url_key()
    fails = defaultdict(list)                      # IP -> Zeitpunkte ungültiger Signaturen

    def config():
        return load_yaml(actions_file)

    def users():
        p = Path(users_file)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def page(titel, text="", klasse="", status=200, **kw):
        return render_template("seite.html", titel=titel, text=text, klasse=klasse, **kw), status

    def check(tag, aktion, sig):
        ip = request.remote_addr or "-"
        now = time.monotonic()
        fails[ip] = [t for t in fails[ip] if now - t < 600]
        if len(fails[ip]) >= 20:
            abort(429)
        if not check_signature(url_key, tag, aktion, sig):
            fails[ip].append(now)
            log.warning("Ungültige Signatur von %s: %s/%s", ip, tag, aktion)
            return page("Ungültiger Tag", "Dieser Tag gehört nicht zu diesem Zuhause.", "fehler", 403)
        cfg = config()
        if tag in (cfg.get("gesperrte_tags") or []):
            return page("Tag gesperrt", "Dieser Tag wurde gesperrt.", "fehler", 403)
        if aktion not in (cfg.get("aktionen") or {}):
            return page("Unbekannte Aktion", "", "fehler", 404)
        if "benutzer" not in session:
            return redirect(url_for("anmelden", weiter=request.full_path))
        return None

    def execute(tag, aktion):
        a = config()["aktionen"][aktion]
        done = [openhab.run(op) for op in a["ops"]]
        log.info("%s: %s über Tag %s (%s)", session["benutzer"], aktion, tag, "; ".join(done))
        return page(a.get("label", aktion), "erledigt", "ok")

    @app.get("/t/<tag>/<aktion>")
    def tag_get(tag, aktion):
        sig = request.args.get("s", "")
        bad = check(tag, aktion, sig)
        if bad is not None:
            return bad
        a = config()["aktionen"][aktion]
        if a.get("bestaetigen"):
            session.setdefault("csrf", secrets.token_urlsafe(16))
            return page(a.get("label", aktion), "Wirklich ausführen?", formular="bestaetigen",
                        csrf=session["csrf"], sig=sig, knopf=a.get("label", aktion))
        return execute(tag, aktion)

    @app.post("/t/<tag>/<aktion>")
    def tag_post(tag, aktion):
        bad = check(tag, aktion, request.form.get("s", ""))
        if bad is not None:
            return bad
        if not session.get("csrf") or request.form.get("csrf") != session["csrf"]:
            return page("Abgelehnt", "Bitte den Tag erneut antippen.", "fehler", 400)
        return execute(tag, aktion)

    @app.route("/anmelden", methods=["GET", "POST"])
    def anmelden():
        weiter = request.args.get("weiter", "/")
        if not weiter.startswith("/t/"):
            weiter = "/"
        if request.method == "POST":
            name = request.form.get("benutzer", "")
            pw_hash = users().get(name)
            if pw_hash and check_password_hash(pw_hash, request.form.get("passwort", "")):
                session.clear()
                session.permanent = True
                session["benutzer"] = name
                log.info("Gerät angemeldet: %s (%s)", name, request.remote_addr)
                return redirect(weiter)
            time.sleep(1)
            return page("Anmelden", "Benutzer oder Passwort falsch.", "fehler", 401,
                        formular="anmelden", weiter=weiter)
        return page("Anmelden", "Dieses Gerät ist noch nicht angemeldet.", formular="anmelden",
                    weiter=weiter)

    @app.get("/abmelden")
    def abmelden():
        session.clear()
        return page("Abgemeldet")

    return app


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag-Dienst für Smartphones")
    ap.add_argument("--url", help="openHAB-URL (überschreibt config.yaml, ohne Token)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--proxy", action="store_true",
                    help="hinter einem Reverse Proxy: X-Forwarded-For/-Proto auswerten")
    ap.add_argument("--aktionen", default=str(HERE / "aktionen.yaml"))
    ap.add_argument("--unsicher-http", action="store_true", help="Cookie auch ohne HTTPS (nur Tests)")
    ap.add_argument("--config")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    cfg = try_load_config(args.config)
    oh = cfg.section("openhab")
    url, token = (args.url, None) if args.url else (oh.get("url", "http://127.0.0.1:8080"), oh.get("token"))
    users_file = cfg.resolve(cfg.section("phone").get("users_file", "config/tagdienst_benutzer.json"))
    app = create_app(load_keyring(cfg), args.aktionen, users_file, OpenHAB(url, token),
                     secure_cookie=not args.unsicher_http)
    if args.proxy:                  # echte Client-IP für die Sperre nach Fehlversuchen
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.run(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
