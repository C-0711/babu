"""Die Terminplanung härten — was passiert, wenn es hart auf hart kommt.

Der Kalender prüft auf Überschneidung. Aber: er liest die bestehenden
Termine, entscheidet, und schreibt dann. Zwischen Lesen und Schreiben passt
eine zweite Anfrage. Genau das ist die Doppelbuchung, die man erst
bemerkt, wenn zwei Kundinnen im Laden stehen.
"""
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "start"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={},
                           kassenblaetter={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, babu_web


# ————— Die Doppelbuchung im selben Moment —————

def test_zwei_gleichzeitige_buchungen_bekommen_nicht_denselben_platz(welt):
    """Der Fehler, den man erst bemerkt, wenn zwei Kundinnen dastehen."""
    client, _ = welt
    ergebnisse = []
    sperre = threading.Lock()

    def buche(name):
        r = client.post("/api/termine", json={
            "start": "2099-09-03T10:00", "minuten": 60, "wer": "Jana",
            "kundin": name})
        with sperre:
            ergebnisse.append(r.status_code)

    faeden = [threading.Thread(target=buche, args=(f"Kundin {i}",))
              for i in range(5)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()

    assert ergebnisse.count(200) == 1, \
        f"nur eine darf durchkommen, war: {ergebnisse}"
    assert ergebnisse.count(409) == 4

    d = client.get("/api/termine", params={"von": "2099-09-03"}).json()
    assert d["tage"][0]["termine"] == 1


# ————— Außerhalb der Öffnungszeiten —————

def test_termin_nachts_um_drei_wird_abgewiesen(welt):
    client, _ = welt
    r = client.post("/api/termine", json={"start": "2099-09-03T03:00",
                                          "minuten": 60, "wer": "Jana"})
    assert r.status_code == 400
    assert "geöffnet" in r.json()["fehler"] or "Öffnung" in r.json()["fehler"]


def test_termin_der_ueber_ladenschluss_hinausgeht(welt):
    client, _ = welt
    r = client.post("/api/termine", json={"start": "2099-09-03T17:30",
                                          "minuten": 120, "wer": "Jana"})
    assert r.status_code == 400


def test_eigene_oeffnungszeiten_gelten(welt):
    client, bw = welt
    bw.db_einstellung_setzen("christoph0711.io", "oeffnet", "07:00")
    bw.db_einstellung_setzen("christoph0711.io", "schliesst", "21:00")
    assert client.post("/api/termine", json={"start": "2099-09-03T07:30",
                                             "minuten": 60,
                                             "wer": "Jana"}).status_code == 200
    # 19:30 + 60 min endet um 20:30 — passt. 20:30 + 60 wäre 21:30 und damit
    # nach Ladenschluss; das muss abgewiesen werden.
    assert client.post("/api/termine", json={"start": "2099-09-03T19:30",
                                             "minuten": 60,
                                             "wer": "Mira"}).status_code == 200
    assert client.post("/api/termine", json={"start": "2099-09-03T20:30",
                                             "minuten": 60,
                                             "wer": "Nora"}).status_code == 400


# ————— Vergangenheit —————

def test_termine_in_der_vergangenheit_brauchen_einen_grund(welt):
    """Nachtragen muss möglich sein — aber nicht versehentlich."""
    client, _ = welt
    r = client.post("/api/termine", json={"start": "2020-01-02T10:00",
                                          "minuten": 60, "wer": "Jana"})
    assert r.status_code == 400
    assert "Vergangenheit" in r.json()["fehler"]
    r2 = client.post("/api/termine", json={"start": "2020-01-02T10:00",
                                           "minuten": 60, "wer": "Jana",
                                           "nachtragen": True})
    assert r2.status_code == 200


# ————— Namen sauber vergleichen —————

def test_leerzeichen_im_namen_machen_keinen_zweiten_platz(welt):
    """„Jana" und „Jana " sind dieselbe Person."""
    client, _ = welt
    assert client.post("/api/termine", json={"start": "2099-09-03T10:00",
                                             "minuten": 60,
                                             "wer": "Jana"}).status_code == 200
    r = client.post("/api/termine", json={"start": "2099-09-03T10:30",
                                          "minuten": 30, "wer": " Jana "})
    assert r.status_code == 409


def test_gross_und_kleinschreibung_ebenso(welt):
    client, _ = welt
    client.post("/api/termine", json={"start": "2099-09-03T10:00",
                                      "minuten": 60, "wer": "Jana"})
    r = client.post("/api/termine", json={"start": "2099-09-03T10:30",
                                          "minuten": 30, "wer": "jana"})
    assert r.status_code == 409
