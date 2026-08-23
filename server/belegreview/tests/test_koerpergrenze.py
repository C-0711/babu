"""Wie viel darf eine Anfrage schicken — und wann merkt der Server es.

Der Befund vom 23.08.2026: die Upload-Routen lasen den ganzen Anfragekörper
in den Speicher und prüften ERST DANACH die Größe. Wer ein Gigabyte schickte,
kippte den Prozess, bevor die Prüfung an die Reihe kam. Der Fehler 413 war
also nicht falsch, er kam nur zu spät.

Besonders offen lag `POST /api/whatsapp/webhook`: die Route verlangt keine
Anmeldung. Eine Signatur wird zwar geprüft — aber erst, wenn der Körper
schon vollständig gelesen ist.

Gemessen wird deshalb nicht die Antwort, sondern was der Server VOM KÖRPER
ABGEHOLT hat. Nur daran ist zu sehen, ob die Grenze vorher greift. Der
Testclient puffert den Körper selbst, bevor er die App ruft — die zählenden
Tests sprechen die ASGI-Schnittstelle deshalb direkt an.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._REG_ZULETZT.clear()
    return babu_web


def _konto(bw, email="nina@0711.io"):
    c = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    c.post("/api/signup", json={"salon": "Salon Nina", "email": email,
                                "passwort": "passwort-lang"})
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=1 WHERE email=?", (email,))
    return c


HAEPPCHEN = 64 * 1024


def rufe(app, pfad: str, haeppchen: int, laenge_behauptet: int | None = None):
    """Die Route über ASGI rufen und mitzählen, wie viel sie abholt.

    Gibt (Status, gelieferte Bytes) zurück. Die Häppchen werden erst
    erzeugt, wenn die Route sie anfordert — deshalb ist die Zahl am Ende
    genau das, was der Server gelesen hat.
    """
    geliefert = {"bytes": 0}
    offen = {"n": haeppchen}
    antwort = {"status": None}
    kopf = [(b"host", b"testserver"), (b"content-type", b"application/octet-stream")]
    if laenge_behauptet is not None:
        kopf.append((b"content-length", str(laenge_behauptet).encode()))

    async def empfangen():
        if offen["n"] <= 0:
            return {"type": "http.disconnect"}
        offen["n"] -= 1
        geliefert["bytes"] += HAEPPCHEN
        return {"type": "http.request", "body": b"\xff\xd8\xff\xe0" + b"x" * (HAEPPCHEN - 4),
                "more_body": offen["n"] > 0}

    async def senden(nachricht):
        if nachricht["type"] == "http.response.start":
            antwort["status"] = nachricht["status"]

    pfad, _, frage = pfad.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
             "http_version": "1.1", "method": "POST", "scheme": "https",
             "path": pfad, "raw_path": pfad.encode(), "query_string": frage.encode(),
             "root_path": "", "headers": kopf,
             "client": ("127.0.0.1", 1234), "server": ("testserver", 443)}
    asyncio.run(app(scope, empfangen, senden))
    return antwort["status"], geliefert["bytes"]


def test_der_whatsapp_webhook_liest_ohne_anmeldung_nicht_unbegrenzt(welt):
    """4 MB angeboten, eine halbe erlaubt — mehr darf nicht ankommen.

    Diese Route ist die offene Flanke: keine Anmeldung, und die Signatur
    wird erst nach dem Lesen geprüft.
    """
    bw = welt
    status, gelesen = rufe(bw.app, "/api/whatsapp/webhook", haeppchen=64)
    # Meta bekommt weiterhin 200 — sonst wiederholt es stundenlang.
    assert status == 200
    # Ein Häppchen Vorlauf ist normal: das, mit dem die Grenze reißt, ist
    # schon abgeholt. Alles danach nicht mehr.
    assert gelesen <= bw.WA_KOERPER_MAX + HAEPPCHEN, gelesen


def test_der_upload_hoert_auf_zu_lesen_statt_alles_zu_schlucken(welt, monkeypatch):
    """8 MB angeboten, 1 MB erlaubt — höchstens gut 1 MB darf ankommen."""
    bw = welt
    monkeypatch.setattr(bw, "HOCHLADEN_MAX", 1024 * 1024)
    monkeypatch.setattr(bw, "_box_wache", lambda request: ("nina@0711.io", None))
    status, gelesen = rufe(bw.app, "/api/hochladen?name=beleg.jpg", haeppchen=128)
    assert status == 413
    assert gelesen <= bw.HOCHLADEN_MAX + HAEPPCHEN, gelesen


def test_content_length_ueber_der_grenze_kostet_kein_einziges_byte(welt, monkeypatch):
    """Sagt der Kopf schon, dass es zu viel wird, wird gar nicht erst gelesen."""
    bw = welt
    monkeypatch.setattr(bw, "HOCHLADEN_MAX", 1024)
    monkeypatch.setattr(bw, "_box_wache", lambda request: ("nina@0711.io", None))
    status, gelesen = rufe(bw.app, "/api/hochladen?name=beleg.jpg", haeppchen=16,
                           laenge_behauptet=16 * HAEPPCHEN)
    assert status == 413
    assert gelesen == 0


def test_ein_normaler_beleg_geht_weiterhin_durch(welt):
    """Die Grenze darf den Normalfall nicht anfassen."""
    bw = welt
    c = _konto(bw)
    r = c.post("/api/hochladen?name=beleg.jpg",
               content=b"\xff\xd8\xff\xe0" + b"x" * 300)
    assert r.status_code == 200, r.text


def test_ein_leerer_koerper_bleibt_ein_leerer_koerper(welt):
    bw = welt
    c = _konto(bw)
    r = c.post("/api/hochladen?name=beleg.jpg", content=b"")
    assert r.status_code == 400
    assert r.json()["fehler"] == "leer"
