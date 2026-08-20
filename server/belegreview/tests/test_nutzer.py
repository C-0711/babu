"""Userverwaltung: eigene Konten (E-Mail + Passwort), Rollen, Verwaltung.

Kein Store nötig — Login/Verwaltung laufen komplett über SQLite + Session.
PAT-Weg (wer_token gemockt) bleibt der Root-Zugang mit Rolle kanzlei.
"""
import os
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def bw(tmp_path_factory):
    os.environ.setdefault("BABU_SEITE", str(HIER / "golden" / "review_weingaertle.json"))
    os.environ.setdefault("BABU_SESSION_GEHEIMNIS",
                          str(tmp_path_factory.mktemp("s") / ".geheimnis"))
    sys.path.insert(0, str(HIER.parent))
    import babu_web  # noqa: PLC0415
    babu_web.PORTAL_DB = tmp_path_factory.mktemp("db") / "portal.db"
    babu_web.wer_token = lambda token: {"test-pat": "christoph0711.io"}.get(token)
    return babu_web


@pytest.fixture()
def client(bw):
    bw._LOGIN_VERSUCHE.clear()
    bw._REG_ZULETZT.clear()
    from fastapi.testclient import TestClient  # noqa: PLC0415
    return TestClient(bw.app, base_url="https://testserver")


def _als_kanzlei(client):
    r = client.post("/api/anmelden", json={"pat": "test-pat"})
    assert r.status_code == 200


def test_pw_roundtrip(bw):
    h = bw.pw_hash("geheim-123")
    assert h.startswith("scrypt$")
    assert bw.pw_pruefen("geheim-123", h)
    assert not bw.pw_pruefen("falsch", h)
    assert not bw.pw_pruefen("geheim-123", "kaputt")


def test_login_unbekannt_ist_generisch(client):
    r = client.post("/api/login", json={"email": "gibtsnicht@x.de", "passwort": "x"})
    assert r.status_code == 401
    assert r.json()["fehler"] == "E-Mail oder Passwort stimmt nicht."


def test_login_rate_limit(bw, client):
    for _ in range(5):
        client.post("/api/login", json={"email": "a@b.de", "passwort": "x"})
    r = client.post("/api/login", json={"email": "a@b.de", "passwort": "x"})
    assert r.status_code == 429


def test_verwaltung_braucht_rolle(client):
    assert client.get("/api/nutzer").status_code == 401
    _als_kanzlei(client)
    assert client.get("/api/nutzer").status_code == 200


def test_anfrage_einrichten_und_login(bw, client):
    # 1. Interessentin registriert sich (öffentlich).
    r = client.post("/api/registrierung", json={
        "salon": "Testsalon Locke", "name": "Nina Test", "email": "nina@locke.de",
        "rechtsform": "Einzelunternehmen", "kleinunternehmer": "Nein",
        "steuerberater": "Ja"})
    assert r.status_code == 200

    # 2. Verwaltung sieht die Anfrage und richtet den Zugang ein.
    _als_kanzlei(client)
    regs = client.get("/api/registrierungen").json()["registrierungen"]
    anfrage = next(x for x in regs if x.get("email") == "nina@locke.de")
    r = client.post("/api/registrierung-einrichten", json={"id": anfrage["id"]})
    assert r.status_code == 200
    start = r.json()["startpasswort"]
    assert len(start) >= 8

    # Doppelt einrichten → 409, Status ist umgestellt.
    assert client.post("/api/registrierung-einrichten",
                       json={"id": anfrage["id"]}).status_code == 409
    regs = client.get("/api/registrierungen").json()["registrierungen"]
    assert next(x for x in regs if x["id"] == anfrage["id"])["status"] == "eingerichtet"

    # 3. Nina meldet sich mit dem Startpasswort an (frischer Client = eigene Session).
    from fastapi.testclient import TestClient  # noqa: PLC0415
    nina = TestClient(bw.app, base_url="https://testserver")
    bw._LOGIN_VERSUCHE.clear()
    r = nina.post("/api/login", json={"email": "nina@locke.de", "passwort": start})
    assert r.status_code == 200
    assert r.json() == {"un": "nina@locke.de", "rolle": "salon"}

    # Ihre Steuerdaten aus der Anfrage sind vorbefüllt; Verwaltung bleibt zu.
    e = nina.get("/api/einstellungen").json()
    assert e["rechtsform"] == "Einzelunternehmen"
    assert e["betrieb_name"] == "Testsalon Locke"
    assert e["steuerberater_status"] == "Ja"
    assert nina.get("/api/nutzer").status_code == 403
    assert nina.get("/api/ich").json()["rolle"] == "salon"

    # 4. Passwort ändern: falsches Alt → 401, zu kurz → 400, dann klappt es.
    assert nina.post("/api/passwort", json={"alt": "falsch", "neu": "neu-passwort"}).status_code == 401
    assert nina.post("/api/passwort", json={"alt": start, "neu": "kurz"}).status_code == 400
    assert nina.post("/api/passwort", json={"alt": start, "neu": "locke-4-ever"}).status_code == 200
    bw._LOGIN_VERSUCHE.clear()
    assert nina.post("/api/login", json={"email": "nina@locke.de",
                                         "passwort": "locke-4-ever"}).status_code == 200

    # 5. Verwaltung schaltet ab → Login und API sind zu.
    r = client.post("/api/nutzer-aktion", json={"email": "nina@locke.de",
                                                "aktion": "deaktivieren"})
    assert r.status_code == 200
    bw._LOGIN_VERSUCHE.clear()
    assert nina.post("/api/login", json={"email": "nina@locke.de",
                                         "passwort": "locke-4-ever"}).status_code == 401
    assert nina.get("/api/ich").status_code == 403   # alte Session greift nicht mehr


def test_signup_direkt(bw, client):
    # Zu kurzes Passwort → 400 (und kein Rate-Limit-Verbrauch).
    r = client.post("/api/signup", json={"salon": "Signup Salon", "email": "selbst@salon.de",
                                         "passwort": "kurz"})
    assert r.status_code == 400
    # Echtes Signup: Konto + sofort angemeldet + Steuerdaten vorbefüllt.
    r = client.post("/api/signup", json={"salon": "Signup Salon", "name": "Selbst Macher",
                                         "email": "selbst@salon.de",
                                         "passwort": "selbst-gewaehlt", "rechtsform": "GbR"})
    assert r.status_code == 200
    assert r.json() == {"un": "selbst@salon.de", "rolle": "salon"}
    assert client.get("/api/ich").json()["un"] == "selbst@salon.de"
    e = client.get("/api/einstellungen").json()
    assert e["rechtsform"] == "GbR" and e["betrieb_name"] == "Signup Salon"
    # Gleiche E-Mail nochmal → 409 mit freundlichem Hinweis.
    bw._REG_ZULETZT.clear()
    r = client.post("/api/signup", json={"salon": "x", "email": "selbst@salon.de",
                                         "passwort": "selbst-gewaehlt"})
    assert r.status_code == 409


def test_app_anmelden_erzeugt_geraeteschluessel(bw, client):
    """Die App verbindet sich mit E-Mail + Passwort — der Schlüssel entsteht
    im Hintergrund und trägt danach als Bearer durch alle /api-Routen."""
    bw._REG_ZULETZT.clear()
    r = client.post("/api/signup", json={"salon": "App Salon", "email": "app@salon.de",
                                         "passwort": "app-passwort"})
    assert r.status_code == 200

    bw._LOGIN_VERSUCHE.clear()
    r = client.post("/api/app-anmelden", json={"email": "app@salon.de",
                                               "passwort": "app-passwort",
                                               "geraet": "Ninas iPhone"})
    assert r.status_code == 200
    schluessel = r.json()["schluessel"]
    assert len(schluessel) >= 40 and r.json()["un"] == "app@salon.de"

    # Frischer Client ohne Cookie: nur der Bearer-Geräteschlüssel zählt.
    from fastapi.testclient import TestClient  # noqa: PLC0415
    app_client = TestClient(bw.app, base_url="https://testserver")
    r = app_client.get("/api/ich", headers={"Authorization": f"Bearer {schluessel}"})
    assert r.status_code == 200 and r.json()["un"] == "app@salon.de"

    # Falsches Passwort bleibt generisch; Quatsch-Schlüssel kommt nicht rein.
    bw._LOGIN_VERSUCHE.clear()
    assert client.post("/api/app-anmelden", json={"email": "app@salon.de",
        "passwort": "falsch"}).status_code == 401
    assert app_client.get("/api/ich",
        headers={"Authorization": "Bearer quatsch"}).status_code == 401

    # Konto abgeschaltet → der Geräteschlüssel ist sofort tot.
    _als_kanzlei(client)
    assert client.post("/api/nutzer-aktion", json={"email": "app@salon.de",
        "aktion": "deaktivieren"}).status_code == 200
    assert app_client.get("/api/ich",
        headers={"Authorization": f"Bearer {schluessel}"}).status_code in (401, 403)


def test_selbstschutz_eigenes_konto(bw, client):
    _als_kanzlei(client)
    r = client.post("/api/nutzer", json={"email": "chefin@salon.de",
                                         "name": "Chefin", "rolle": "admin"})
    assert r.status_code == 200
    start = r.json()["startpasswort"]

    from fastapi.testclient import TestClient  # noqa: PLC0415
    chefin = TestClient(bw.app, base_url="https://testserver")
    bw._LOGIN_VERSUCHE.clear()
    assert chefin.post("/api/login", json={"email": "chefin@salon.de",
                                           "passwort": start}).status_code == 200
    # Admin darf verwalten, aber das eigene Konto nicht abschalten/zurückstufen.
    assert chefin.get("/api/nutzer").status_code == 200
    assert chefin.post("/api/nutzer-aktion", json={"email": "chefin@salon.de",
        "aktion": "deaktivieren"}).status_code == 400
    assert chefin.post("/api/nutzer-aktion", json={"email": "chefin@salon.de",
        "aktion": "rolle", "rolle": "salon"}).status_code == 400


def test_team_verwalten_und_personalkosten(bw, client):
    """Dein Team: vier Angaben je Person, die Summe trägt die Auswertung."""
    _als_kanzlei(client)

    # Festlohn und Stundenkraft
    r = client.post("/api/team", json={"name": "Jana Allgaier",
                                       "email": "jana@cap2.de",
                                       "lohn_art": "fest", "betrag": "2.400",
                                       "seit": "2024-05-01"})
    assert r.status_code == 200
    r = client.post("/api/team", json={"name": "Mira Aushilfe",
                                       "lohn_art": "stunden",
                                       "stundenlohn": "14,50", "stunden": "40"})
    assert r.status_code == 200
    d = r.json()
    assert d["kosten_monat"] == 2980.0          # 2400 + 14,50 × 40
    assert d["team"][0]["kosten_monat"] in (2400.0, 580.0)

    # Ohne Namen geht nichts, kaputte E-Mail auch nicht
    assert client.post("/api/team", json={"name": " "}).status_code == 400
    assert client.post("/api/team", json={"name": "X", "email": "keine"}).status_code == 400

    # Wer aufhört, zählt nicht mehr mit — bleibt aber in der Liste
    jana = next(p for p in d["team"] if p["name"] == "Jana Allgaier")
    r = client.post("/api/team-aktion", json={"id": jana["id"], "aktion": "beenden"})
    assert r.json()["kosten_monat"] == 580.0
    assert any(not p["aktiv"] for p in r.json()["team"])

    # Und kommt sie zurück, zählt sie wieder
    r = client.post("/api/team-aktion", json={"id": jana["id"], "aktion": "zurueck"})
    assert r.json()["kosten_monat"] == 2980.0

    # Die Auswertung rechnet damit
    assert bw.team_personalkosten("christoph0711.io") == 2980.0
