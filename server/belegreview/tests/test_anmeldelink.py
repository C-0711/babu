"""Anmelden per Link (08.10.2026): `/api/anmeldelink`, `/anmelden/{token}`,
`/api/anmeldelink/einloesen` — und dass „Passwort setzen“ gleich anmeldet.

Der Link ist eine Zeile in `passwort_reset`. Er schickt sich immer mit
derselben Antwort, ein GET löst ihn nicht ein (Mailvorschau, App erst holen),
und einlösen geht genau einmal — für die App mit Geräteschlüssel, im
Browser mit Cookie.
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASSWORT = "ein-langes-passwort-hier"


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import babu_web
    import postfach
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.test")
    post = []
    monkeypatch.setattr(postfach, "senden", lambda an, betreff, text, *, stempel: (
        post.append((an, betreff, text)) or (True, "ok")))
    babu_web._RESET_VERSUCHE.clear()  # noqa: SLF001
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    assert babu_web.nutzer_anlegen("kim@salon.de", "Kim", "Kims Salon", "salon",
                                   passwort=PASSWORT, box=False) is not None
    client = TestClient(babu_web.app, base_url="https://testserver")
    return client, babu_web, post


def _token(text: str) -> str:
    return re.search(r"/anmelden/(\S+)", text).group(1)


def test_link_kommt_per_mail_und_die_antwort_verraet_nichts(welt):
    client, bw, post = welt
    r = client.post("/api/anmeldelink", json={"email": "Kim@Salon.de", "app": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(post) == 1 and post[0][0] == "kim@salon.de"
    assert "https://babu.test/anmelden/" in post[0][2] and "anmelden" not in r.text
    # Unbekannte Adresse: dieselbe Antwort, keine Mail.
    r = client.post("/api/anmeldelink", json={"email": "niemand@salon.de"})
    assert r.status_code == 200 and r.json() == {"ok": True} and len(post) == 1


def test_die_app_bekommt_einen_geraeteschluessel_einmal(welt):
    client, bw, post = welt
    client.post("/api/anmeldelink", json={"email": "kim@salon.de", "app": True})
    token = _token(post[0][2])
    # Die Seite hinter dem Link löst NICHT ein (Mailvorschau, App erst holen).
    seite = client.get(f"/anmelden/{token}")
    assert seite.status_code == 200
    assert f"babu://anmelden/{token}" in seite.text and f"babupro://anmelden/{token}" in seite.text
    assert client.get(f"/anmelden/{token}").status_code == 200
    r = client.post("/api/anmeldelink/einloesen",
                    json={"token": token, "app": True, "geraet": "iPhone"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["un"] == "kim@salon.de" and d["rolle"] == "salon" and d["box"] is False
    assert bw.app_schluessel_pruefen(d["schluessel"]) == "kim@salon.de"
    # Zweimal geht nicht — und die Seite sagt es dann auch.
    r = client.post("/api/anmeldelink/einloesen", json={"token": token, "app": True})
    assert r.status_code == 400 and "schon benutzt" in r.json()["fehler"]
    seite = client.get(f"/anmelden/{token}")
    assert seite.status_code == 400 and "Neuen Link schicken" in seite.text


def test_im_browser_gibt_es_das_cookie(welt):
    client, bw, post = welt
    client.post("/api/anmeldelink", json={"email": "kim@salon.de"})
    r = client.post("/api/anmeldelink/einloesen", json={"token": _token(post[0][2])})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert bw.SESSION_COOKIE in r.cookies
    ich = client.get("/api/ich")
    assert ich.status_code == 200 and ich.json()["un"] == "kim@salon.de"


def test_fremder_oder_kaputter_token_meldet_nicht_an(welt):
    client, bw, post = welt
    r = client.post("/api/anmeldelink/einloesen", json={"token": "gibt-es-nicht", "app": True})
    assert r.status_code == 400 and "schluessel" not in r.text
    assert client.get("/anmelden/gibt-es-nicht").status_code == 400


def test_link_gilt_einen_tag(welt, monkeypatch):
    client, bw, post = welt
    client.post("/api/anmeldelink", json={"email": "kim@salon.de"})
    token = _token(post[0][2])
    import datetime as dt

    import passwort_reset as pr
    spaeter = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1, minutes=5)
    monkeypatch.setattr(pr, "_jetzt", lambda: spaeter)
    r = client.post("/api/anmeldelink/einloesen", json={"token": token})
    assert r.status_code == 400 and "abgelaufen" in r.json()["fehler"]


def test_passwort_setzen_meldet_gleich_an(welt):
    client, bw, post = welt
    client.post("/api/anmeldelink", json={"email": "kim@salon.de"})
    token = _token(post[0][2])
    r = client.post("/api/passwort-reset", json={"token": token, "passwort": "ganz-neu-und-lang",
                                                 "passwort2": "ganz-neu-und-lang"})
    assert r.status_code == 200, r.text
    assert r.json()["angemeldet"] is True and bw.SESSION_COOKIE in r.cookies
    assert client.get("/api/ich").json()["un"] == "kim@salon.de"
