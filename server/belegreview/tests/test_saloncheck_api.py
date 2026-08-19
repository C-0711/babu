"""Salon-Check-API: Upload, Hintergrund-Job, Status-Poll, Report.

Die Pipeline ist gemockt (kein LLM) — geprüft wird der Job-Lebenszyklus:
wartet → liest → fertig, 409 bei Doppelstart, Snapshot nach Neustart,
Konfliktregel der Konto-Einrichtung und der Karten-Report aus der Box.
"""
import json
import subprocess
import sys
import threading
import time
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
    monkeypatch.setattr(babu_web, "ABSCHLUSS_TMP", tmp_path / "abschluss-tmp")
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web._ABSCHLUSS_JOBS.clear()
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare, babu_web


def _warte_auf(client, stand, sekunden=5.0):
    frist = time.time() + sekunden
    while time.time() < frist:
        d = client.get("/api/abschluss/status").json()
        if d.get("stand") == stand:
            return d
        time.sleep(0.05)
    raise AssertionError(f"Status '{stand}' kam nicht: {d}")


def test_abschluss_rundreise(welt, monkeypatch):
    client, bare, bw = welt
    import abschluss_lesen

    # Vorher: Finanzamt schon gepflegt (Konfliktfall), Steuernummer leer.
    client.post("/api/einstellungen", json={"finanzamt": "Stuttgart"})

    r = client.post("/api/abschluss", params={"jahr": 2024, "name": "euer 2024.pdf"},
                    content=b"%PDF-1.4 euer")
    assert r.status_code == 200 and r.json()["jahr"] == 2024
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("abschluss: ")

    tor = threading.Event()

    def fake_lesen(pfad, jahr=None, melden=None, fortschritt=None, **k):
        tor.wait(5)
        fortschritt("Ich lese Gewinnrechnung — 6 Seiten")
        for feld in (
            {"schluessel": "umsatz", "wert": 100000.0,
             "quelle": "Gewinnrechnung (euer.pdf)", "sicher": True},
            {"schluessel": "steuernummer", "wert": "71/123/45678",
             "quelle": "Gewinnrechnung (euer.pdf)", "sicher": True},
            {"schluessel": "finanzamt", "wert": "Ludwigsburg",
             "quelle": "Gewinnrechnung (euer.pdf)", "sicher": True},
        ):
            melden(feld)
        return {"datei": Path(pfad).name, "art": "euer", "seiten": 6,
                "lane": "text",
                "werte": {"umsatz": 100000.0, "wareneinsatz": 11000.0,
                          "personal": 48000.0, "raumkosten": 12000.0,
                          "afa": 3000.0, "sonstige_kosten": 6000.0,
                          "gewinn": 20000.0, "steuernummer": "71/123/45678",
                          "finanzamt": "Ludwigsburg"},
                "afa_liste": []}

    monkeypatch.setattr(abschluss_lesen, "dokument_lesen", fake_lesen)

    assert client.post("/api/abschluss/start",
                       params={"jahr": 2024}).status_code == 200
    # Solange der Job liest: Doppelstart abgewiesen.
    assert client.post("/api/abschluss/start",
                       params={"jahr": 2024}).status_code == 409
    tor.set()

    d = _warte_auf(client, "fertig")
    assert [f["schluessel"] for f in d["felder"]] == ["umsatz", "steuernummer",
                                                      "finanzamt"]
    assert d["dokumente"][0]["stand"] == "gelesen"
    # Konfliktregel: leere Steuernummer übernommen, belegtes Finanzamt nur Vorschlag.
    e = client.get("/api/einstellungen").json()
    assert e["steuernummer"] == "71/123/45678"
    assert e["finanzamt"] == "Stuttgart"
    assert d["vorschlaege"] == [{"schluessel": "finanzamt", "alt": "Stuttgart",
                                 "neu": "Ludwigsburg"}]

    # kennzahlen.json liegt in der Box, der Report baut Karten daraus.
    kennzahlen = json.loads(subprocess.run(
        ["git", "-C", str(bare), "show", "HEAD:abschluss/2024/kennzahlen.json"],
        capture_output=True, check=True).stdout)
    assert kennzahlen["zahlen"]["gewinn"] == 20000.0
    assert kennzahlen["pruefungen"]["summenprobe_ok"] is True

    r = client.get("/api/salon-check", params={"jahr": 2024}).json()
    assert r["stand"] == "fertig"
    assert [k["id"] for k in r["karten"]] == ["gewinn", "material", "personal",
                                              "raum", "ruecklage", "ust"]
    # Arbeitskopien sind nach dem Lesen weggeräumt.
    ablage = bw.ABSCHLUSS_TMP / "christoph0711.io" / "2024"
    assert not any(ablage.glob("*.pdf"))


def test_start_ohne_unterlagen(welt):
    client, _, _ = welt
    r = client.post("/api/abschluss/start", params={"jahr": 2024})
    assert r.status_code == 400
    assert "hochladen" in r.json()["fehler"]


def test_status_nach_neustart_ist_unterbrochen(welt):
    client, _, bw = welt
    bw.db_abschluss_snapshot("christoph0711.io", 2024,
                             {"stand": "liest", "jahr": 2024, "dokumente": [],
                              "felder": [], "vorschlaege": [], "hinweis": "…"})
    bw._ABSCHLUSS_JOBS.clear()   # „Neustart": In-Memory-Zustand ist weg
    d = client.get("/api/abschluss/status").json()
    assert d["stand"] == "unterbrochen"
    assert "nochmal" in d["hinweis"]


def test_salon_check_ohne_kennzahlen_ist_leer(welt):
    client, _, _ = welt
    r = client.get("/api/salon-check", params={"jahr": 2024}).json()
    assert r == {"jahr": 2024, "stand": "leer", "karten": []}


def test_paket_felder_und_empfehlung(welt):
    client, _, _ = welt
    d = client.post("/api/einstellungen",
                    json={"kleinunternehmer": "Ja", "filialen": "Nein",
                          "steuerberater_modus": "Mein Steuerbüro bleibt"}).json()
    assert d["paket_empfehlung"]["paket"] == "solo"
    assert any("günstiger" in h for h in d["paket_empfehlung"]["hinweise"])
    d = client.post("/api/einstellungen", json={"filialen": "Ja"}).json()
    assert d["paket_empfehlung"]["paket"] == "plus"
    assert client.get("/api/einstellungen").json() == d


def test_kassenbuch_empfang(welt):
    client, bare, _ = welt
    r = client.post("/api/kassenbuch", json={
        "datum": "2026-08-18", "bestandVortag": 150, "einnahmenBar": 420.5,
        "gezaehltSchluss": 540, "differenzGrund": "10 € Wechselgeld verzählt"})
    assert r.status_code == 200
    blatt = json.loads(subprocess.run(
        ["git", "-C", str(bare), "show", "HEAD:kassenbuch/2026-08/2026-08-18.json"],
        capture_output=True, check=True).stdout)
    assert blatt["einnahmenBar"] == 420.5
    assert blatt["differenzGrund"] == "10 € Wechselgeld verzählt"
    assert blatt["von"] == "christoph0711.io"
    # Ohne Datum → 400, kaputte Zahl wird 0.
    assert client.post("/api/kassenbuch", json={}).status_code == 400
    r = client.post("/api/kassenbuch", json={"datum": "2026-08-19",
                                             "einnahmenBar": "quatsch"})
    assert r.status_code == 200


def test_brief_wird_erklaert(welt, monkeypatch):
    client, _, bw = welt
    monkeypatch.setattr(bw, "brief_erklaerung_bauen", lambda daten, name: {
        "einfach": "Das Finanzamt will deine Umsatzsteuer-Voranmeldung.",
        "was_tun": "Schick sie bis zur Frist ab.", "bis_wann": "2026-09-10"})
    r = client.post("/api/dokumente",
                    params={"name": "brief.pdf", "titel": "Brief vom Amt",
                            "art": "behoerde"},
                    content=b"%PDF-1.4 brief")
    assert r.status_code == 200
    frist = time.time() + 5
    erklaerung = None
    while time.time() < frist:
        docs = client.get("/api/dokumente").json()["dokumente"]
        erklaerung = next((d["erklaerung"] for d in docs
                           if d["art"] == "behoerde"), None)
        if erklaerung:
            break
        time.sleep(0.1)
    assert erklaerung and erklaerung["bis_wann"] == "2026-09-10"
    # Das Sidecar taucht nicht als eigenes Dokument auf.
    assert all(not d["pfad"].endswith(".erklaerung.json")
               for d in client.get("/api/dokumente").json()["dokumente"])


def test_upload_grenzen(welt):
    client, _, _ = welt
    assert client.post("/api/abschluss", params={"name": "boese.exe"},
                       content=b"x").status_code == 400
    assert client.post("/api/abschluss", params={"jahr": 1990, "name": "a.pdf"},
                       content=b"x").status_code == 400
    assert client.post("/api/abschluss", params={"jahr": 2024, "name": "a.pdf"},
                       content=b"").status_code == 400


def test_ablage_ordnet_nach_jahr_und_art(welt):
    client, _, _ = welt
    client.post("/api/dokumente", params={"name": "bescheid.pdf", "titel": "ESt-Bescheid",
                                          "art": "behoerde"}, content=b"%PDF-1.4 x")
    client.post("/api/kassenbuch", json={"datum": "2026-08-18", "einnahmenBar": 10})
    d = client.get("/api/ablage").json()
    assert d["gesamt"] >= 2
    jahre = {j["jahr"]: j for j in d["jahre"]}
    assert "2026" in jahre
    arten = {a["art"]: a for a in jahre["2026"]["arten"]}
    assert "kassenbuch" in arten and arten["kassenbuch"]["name"] == "Kassenbuch"
    assert "behoerde" in arten
    # Sidecars tauchen nie als eigene Unterlage auf.
    alle = [s["pfad"] for j in d["jahre"] for a in j["arten"] for s in a["stuecke"]]
    assert not any(p.endswith((".meta.json", ".erklaerung.json", ".umsaetze.json"))
                   for p in alle)
