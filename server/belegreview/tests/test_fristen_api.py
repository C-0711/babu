"""Fristen-API und Freigabe des Monatsabschlusses.

Geprüft wird, was am Server dranhängt: dass die Termine aus den echten
Stammdaten kommen, dass ein Team die Lohntermine freischaltet, und dass
die Freigabe den Entwurf nachweisbar in der Belegbox ablegt.
"""
import json
import subprocess
import sys
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
    import boxschreiber

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare, babu_web


def arten(daten):
    return {t["art"] for t in daten["termine"]}


# ————— Fristen —————

def test_ohne_anmeldung_kein_kalender():
    sys.path.insert(0, str(HIER.parent))
    import babu_web
    from fastapi.testclient import TestClient
    r = TestClient(babu_web.app, base_url="https://testserver").get("/api/fristen/2026")
    assert r.status_code == 401


def test_jahr_muss_vierstellig_sein(welt):
    client, _, _ = welt
    assert client.get("/api/fristen/26").status_code == 400
    assert client.get("/api/fristen/zweitausend").status_code == 400


def test_normaler_salon_bekommt_die_voranmeldungen(welt):
    client, _, _ = welt
    daten = client.get("/api/fristen/2026").json()
    assert daten["jahr"] == 2026
    assert "ustva" in arten(daten)
    assert len([t for t in daten["termine"] if t["art"] == "ustva"]) == 12
    # Ohne Team keine Lohntermine.
    assert "sozialversicherung" not in arten(daten)


def test_kleinunternehmerin_bekommt_keine_voranmeldung(welt):
    client, _, _ = welt
    client.post("/api/einstellungen", json={"kleinunternehmer": "Ja"})
    daten = client.get("/api/fristen/2026").json()
    assert daten["profil"]["ustva_rhythmus"] == "keine"
    assert "ustva" not in arten(daten)
    assert "jahreserklaerung" in arten(daten)


def test_team_schaltet_lohn_und_sozialversicherung_frei(welt):
    client, _, _ = welt
    client.post("/api/team", json={"name": "Lena", "brutto_monat": 2400})
    daten = client.get("/api/fristen/2026").json()
    assert daten["profil"]["lohn"] is True
    assert "sozialversicherung" in arten(daten)
    assert "lohnsteuer" in arten(daten)


def test_naechste_termine_kommen_mit(welt):
    client, _, _ = welt
    daten = client.get("/api/fristen/2026").json()
    assert len(daten["naechste"]) <= 3
    for t in daten["naechste"]:
        assert t["in_tagen"] >= 0


# ————— Freigabe des Monatsabschlusses —————

def test_freigabe_legt_den_entwurf_in_die_box(welt):
    client, bare, _ = welt
    r = client.post("/api/monatsabschluss/2026-07/freigeben")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    assert log == "monatsabschluss 2026-07 freigegeben"

    roh = subprocess.run(["git", "-C", str(bare), "show",
                          "HEAD:abschluss/2026-07/ustva.json"],
                         capture_output=True, text=True).stdout
    abgelegt = json.loads(roh)
    assert abgelegt["monat"] == "2026-07"
    assert abgelegt["ustva"]["stand"] == "entwurf"
    # Der Nachweis muss sagen, dass babu nicht übermittelt.
    assert "Übermittlung" in abgelegt["hinweis"]


def test_freigabe_braucht_einen_gueltigen_monat(welt):
    client, _, _ = welt
    assert client.post("/api/monatsabschluss/2026-7/freigeben").status_code == 400
    assert client.post("/api/monatsabschluss/juli/freigeben").status_code == 400


# ————— Die öffentliche Einkaufsseite —————

def test_einkaufsseite_ist_ohne_anmeldung_erreichbar(welt, tmp_path, monkeypatch):
    client, _, bw = welt
    monkeypatch.setattr(bw, "SEITE", tmp_path / "index.html")
    (tmp_path / "einkauf.html").write_text("<h1>Dein Beleg weiß, was du zahlst.</h1>")
    r = client.get("/einkauf")
    assert r.status_code == 200
    assert "Dein Beleg" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_einkaufsseite_ohne_datei_sagt_kommt_bald(welt, tmp_path, monkeypatch):
    client, _, bw = welt
    monkeypatch.setattr(bw, "SEITE", tmp_path / "index.html")
    assert client.get("/einkauf").status_code == 404
