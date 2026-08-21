"""Der Chat merkt sich, worüber gesprochen wurde.

Bisher stand jede Frage für sich: „Wie viel war das nochmal?" lief ins Leere.
Jetzt gehen die letzten Züge mit ans Modell, und das Gespräch bleibt
gespeichert — in SQLite, nicht in der Belegbox: ein Chatverlauf ist kein
Auditmaterial und muss löschbar sein.
"""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    sys.path.insert(0, str(HIER.parent))
    import babu_web

    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()

    # Kein vLLM in Tests: die Antwort kommt aus einer Attrappe.
    gesagt: list[dict] = []

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Das kostet 141,00 €."}}]}

    def falsches_post(url, json=None, **kw):
        gesagt.append(json)
        return Antwort()

    monkeypatch.setattr(babu_web.requests, "post", falsches_post)
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"},
        "belege": [{"stamm": "s1", "lieferant": "Friseur Großhandel Wagner",
                    "brutto": 141.0, "monat": "2026-08", "datum": "03.08.2026",
                    "belegart": "Wareneinkauf", "offen": []}],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": [],
    })

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, babu_web, gesagt


# ————— Gedächtnis —————

def test_erste_frage_beginnt_ein_gespraech(welt):
    client, _, _ = welt
    r = client.post("/chat", json={"frage": "Was habe ich beim Großhandel gekauft?"})
    assert r.status_code == 200
    d = r.json()
    assert d["antwort"] == "Das kostet 141,00 €."
    assert isinstance(d["gespraech"], int)


def test_rueckfrage_kennt_das_vorherige(welt):
    """Der eigentliche Punkt: „und wie viel war das nochmal?" muss ankommen."""
    client, _, gesagt = welt
    erste = client.post("/chat", json={"frage": "Was habe ich beim Großhandel gekauft?"})
    g = erste.json()["gespraech"]

    client.post("/chat", json={"frage": "Und wie viel war das nochmal?",
                               "gespraech": g})
    nachrichten = gesagt[-1]["messages"]
    rollen = [m["role"] for m in nachrichten]
    texte = " ".join(m["content"] for m in nachrichten)
    assert rollen.count("user") >= 2, "die frühere Frage fehlt im Verlauf"
    assert "Großhandel" in texte
    assert "Das kostet 141,00 €." in texte, "die frühere Antwort fehlt im Verlauf"


def test_gespraech_wird_gespeichert(welt):
    client, _, _ = welt
    g = client.post("/chat", json={"frage": "Was habe ich gekauft?"}).json()["gespraech"]
    d = client.get(f"/api/gespraech/{g}").json()
    assert [n["rolle"] for n in d["nachrichten"]] == ["user", "assistant"]
    assert d["nachrichten"][0]["text"] == "Was habe ich gekauft?"


def test_liste_der_gespraeche(welt):
    client, _, _ = welt
    client.post("/chat", json={"frage": "Erste Frage"})
    client.post("/chat", json={"frage": "Ganz anderes Thema"})
    liste = client.get("/api/gespraeche").json()["gespraeche"]
    assert len(liste) == 2
    assert liste[0]["titel"] in ("Erste Frage", "Ganz anderes Thema")
    assert liste[0]["nachrichten"] == 2


def test_gespraech_loeschen(welt):
    client, _, _ = welt
    g = client.post("/chat", json={"frage": "Weg damit"}).json()["gespraech"]
    assert client.post(f"/api/gespraech/{g}/loeschen").status_code == 200
    assert client.get(f"/api/gespraech/{g}").status_code == 404
    assert client.get("/api/gespraeche").json()["gespraeche"] == []


def test_fremdes_gespraech_bleibt_fremd(welt):
    """Gespräche gehören dem Konto — nicht dem Server."""
    client, bw, _ = welt
    g = client.post("/chat", json={"frage": "Meins"}).json()["gespraech"]
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "fremd@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.get(f"/api/gespraech/{g}").status_code == 404
    assert fremd.post(f"/api/gespraech/{g}/loeschen").status_code == 404
    # 403 (kein Zugang zu dieser Box) ist die schärfere Antwort und genügt.
    assert fremd.post("/chat", json={"frage": "Rein da",
                                     "gespraech": g}).status_code in (403, 404)


# ————— Das Wissen, das ankommt —————

def test_der_chat_bekommt_mehr_als_belege(welt):
    client, _, gesagt = welt
    client.post("/chat", json={"frage": "Wie läuft mein Salon?"})
    inhalt = gesagt[-1]["messages"][-1]["content"]
    assert "DER BETRIEB" in inhalt
    assert "Salon Nina" in inhalt


def test_der_auftrag_geht_ueber_steuern_hinaus(welt):
    client, _, gesagt = welt
    client.post("/chat", json={"frage": "Wie sage ich einer Kundin ab?"})
    system = gesagt[-1]["messages"][0]["content"]
    assert "nicht nur für steuern" in system.lower()
    for thema in ("Preise", "Personal", "Kundinnen"):
        assert thema.lower() in system.lower(), f"{thema} fehlt im Auftrag"


def test_die_grenzen_stehen_drin(welt):
    """babu darf breit antworten — aber nicht so tun, als wäre es die Kanzlei."""
    client, _, gesagt = welt
    client.post("/chat", json={"frage": "Egal was"})
    system = gesagt[-1]["messages"][0]["content"]
    assert "keine Steuerberatung" in system
    assert "Erfinde nie" in system


def test_leere_frage_bleibt_abgewiesen(welt):
    client, _, _ = welt
    assert client.post("/chat", json={"frage": ""}).status_code == 400
    assert client.post("/chat", json={"frage": "x" * 2001}).status_code == 400
