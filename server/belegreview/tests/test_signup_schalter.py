"""Im Pilot gibt es kein Selbstbedienungs-Konto: `BABU_SIGNUP=0`.

Konten legt die Kanzlei im Portal an, Betriebe kommen auf Einladung. Die
Tür ist dann nicht „zu" (403), es gibt sie nicht (404) — und die
Anmeldeseite fragt vorher nach, ob sie „Konto anlegen" zeigen soll.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def klient(tmp_path):
    import babu_web
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    babu_web._REG_ZULETZT.clear()
    return TestClient(babu_web.app, base_url="https://testserver"), babu_web


SIGNUP = {"salon": "Salon Test", "email": "neu@example.org",
          "passwort": "ein-langes-passwort"}


def test_ohne_schalter_bleibt_die_tuer_offen(klient, monkeypatch):
    client, bw = klient
    monkeypatch.delenv("BABU_SIGNUP", raising=False)
    assert client.get("/api/signup-offen").json() == {"offen": True}
    assert client.post("/api/signup", json=SIGNUP).status_code == 200


def test_im_pilot_gibt_es_die_tuer_nicht(klient, monkeypatch):
    client, bw = klient
    monkeypatch.setenv("BABU_SIGNUP", "0")
    assert client.get("/api/signup-offen").json() == {"offen": False}
    r = client.post("/api/signup", json=SIGNUP)
    assert r.status_code == 404
    # Es ist kein Konto entstanden.
    assert bw.nutzer_holen("neu@example.org") is None


def test_die_anmeldeseite_fragt_nach():
    portal = (Path(__file__).resolve().parents[1] / "portal.html").read_text()
    assert "/api/signup-offen" in portal
    assert '$("#reg-einstieg").hidden = true' in portal
