"""`/api/wissen`: hochladen, im Hintergrund einlesen, in der Ablage finden.

Wie beim Salon-Check ist die Pipeline gemockt (kein Embedding-Dienst) —
geprüft wird der Weg: Erst-Commit sofort, Klartext und Atome nach dem
Hintergrund-Job, Dublettenschutz, Themen-Autoerkennung, Ablage- und
Suche-Integration.
"""
import json
import subprocess
import sys
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
    monkeypatch.setattr(babu_web, "WISSEN_TMP", tmp_path / "wissen-tmp")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web._WISSEN_JOBS.clear()
    babu_web._WISSEN_VEKTOREN = (None, [], None)
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    # Kein echter Embedding-Dienst im Test — ein deterministischer Vektor
    # genügt, der Job soll nur den Weg durchlaufen, nicht wirklich suchen.
    monkeypatch.setattr(babu_web, "embedding_rechnen",
                        lambda text, als_dokument=True: {
                            "modell": "test", "dim": 3, "vektor": [1.0, 0.0, 0.0]})

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare, babu_web


def _warte_bis_fertig(client, pfad, sekunden=5.0):
    frist = time.time() + sekunden
    d = {}
    while time.time() < frist:
        d = client.get("/api/wissen/status", params={"pfad": pfad}).json()
        if d.get("stand") in ("fertig", "fehler"):
            return d
        time.sleep(0.02)
    raise AssertionError(f"Job für {pfad} wurde nicht fertig: {d}")


def test_wissen_hochladen_legt_datei_und_meta_in_einem_commit_ab(welt):
    client, bare, bw = welt
    r = client.post("/api/wissen",
                    params={"name": "steuerschluessel.txt", "thema": "steuerschluessel",
                            "titel": "Steuerschlüssel-Übersicht"},
                    content=b"Automatikkonten und ihr Steuerschluessel.")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["thema"] == "steuerschluessel"
    pfad = d["pfad"]
    assert pfad.startswith("wissen/steuerschluessel/")

    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("wissen: ")

    meta = json.loads(bw.git_show(pfad + ".meta.json"))
    assert meta["titel"] == "Steuerschlüssel-Übersicht"
    assert meta["thema"] == "steuerschluessel"
    assert meta["status"] == "wird eingelesen"


def test_wissen_thema_autoerkennung_ohne_parameter(welt):
    client, bare, bw = welt
    text = ("Der SKR04-Kontenrahmen gliedert sich in zehn Kontenklassen. "
           "Jedes Sachkonto hat eine vierstellige Kontonummer.")
    r = client.post("/api/wissen", params={"name": "kontenrahmen.txt"},
                    content=text.encode())
    assert r.status_code == 200, r.text
    assert r.json()["thema"] == "kontenrahmen"
    assert r.json()["pfad"].startswith("wissen/kontenrahmen/")


def test_wissen_job_schreibt_text_und_atome(welt):
    client, bare, bw = welt
    text = "Erster Absatz zum Kontenrahmen.\n\nZweiter Absatz mit mehr Inhalt " * 3
    r = client.post("/api/wissen",
                    params={"name": "handbuch.txt", "thema": "kontenrahmen"},
                    content=text.encode())
    pfad = r.json()["pfad"]
    status = _warte_bis_fertig(client, pfad)
    assert status["stand"] == "fertig"

    meta = json.loads(bw.git_show(pfad + ".meta.json"))
    assert meta["status"] == "eingelesen"
    assert meta["absaetze"] >= 1
    assert meta["titel"]  # vom ersten Commit übernommen, nicht verloren

    textjson = json.loads(bw.git_show(pfad + ".text.json"))
    assert "Kontenrahmen" in textjson["text"]

    atome = json.loads(bw.git_show(pfad + ".atome.json"))
    assert len(atome) == meta["absaetze"]
    assert all("vektor" in a and "loc" in a for a in atome)
    assert atome[0]["loc"].startswith("S1#")


def test_wissen_dublette_wird_nicht_doppelt_abgelegt(welt):
    client, bare, bw = welt
    daten = b"Ein und dasselbe Dokument, byte-identisch."
    r1 = client.post("/api/wissen", params={"name": "a.txt", "thema": "afa"},
                     content=daten)
    pfad = r1.json()["pfad"]
    _warte_bis_fertig(client, pfad)

    r2 = client.post("/api/wissen", params={"name": "b.txt", "thema": "afa"},
                     content=daten)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("dublette") is True
    assert d2["pfad"] == pfad


def test_wissen_erscheint_im_fach_wissen(welt):
    client, bare, bw = welt
    r = client.post("/api/wissen",
                    params={"name": "afa-tabelle.txt", "thema": "afa",
                            "titel": "AfA-Tabelle"},
                    content=b"Nutzungsdauer und Abschreibung im Anlagevermoegen.")
    pfad = r.json()["pfad"]
    _warte_bis_fertig(client, pfad)

    ablage = client.get("/api/ablage").json()
    stuecke = [s for j in ablage["jahre"] for a in j["arten"] if a["art"] == "wissen"
              for s in a["stuecke"]]
    assert any(s["pfad"] == pfad and s["titel"] == "AfA-Tabelle" for s in stuecke)
    treffer = next(s for s in stuecke if s["pfad"] == pfad)
    assert treffer["thema"] == "afa"
    assert treffer["status"] == "eingelesen"


def test_wissen_suche_findet_ueber_den_klartext(welt):
    """Beweis, dass `.text.json` ohne Codeänderung von der bestehenden
    Ablage-Stichwortsuche mitgefunden wird (`_abschluss_klartexte()` filtert
    nur auf die Endung, nicht auf einen Pfad-Präfix)."""
    client, bare, bw = welt
    r = client.post("/api/wissen",
                    params={"name": "lohnkonto.txt", "thema": "lohn"},
                    content=b"Das Sonderwort Zwiebelfischangel steht nur hier.")
    pfad = r.json()["pfad"]
    _warte_bis_fertig(client, pfad)

    treffer = client.get("/api/ablage/suche",
                         params={"q": "zwiebelfischangel"}).json()
    assert treffer["gesamt"] >= 1
    assert any(t["pfad"] == pfad for t in treffer["treffer"])


def test_wissen_falsches_format_wird_abgelehnt(welt):
    client, bare, bw = welt
    r = client.post("/api/wissen", params={"name": "boese.exe"}, content=b"x")
    assert r.status_code == 400


def test_wissen_status_fuer_unbekannten_pfad(welt):
    client, bare, bw = welt
    d = client.get("/api/wissen/status", params={"pfad": "wissen/afa/nichts.txt"}).json()
    assert d["stand"] == "unbekannt"


def test_wissen_atome_json_ist_kein_eigener_ablage_eintrag(welt):
    """`.atome.json` ist Beiwerk — es darf nicht als eigenes Stück auftauchen."""
    client, bare, bw = welt
    r = client.post("/api/wissen", params={"name": "x.txt", "thema": "afa"},
                    content=b"Etwas Text fuer die Atome.")
    pfad = r.json()["pfad"]
    _warte_bis_fertig(client, pfad)
    ablage = client.get("/api/ablage").json()
    alle_pfade = [s["pfad"] for j in ablage["jahre"] for a in j["arten"]
                 for s in a["stuecke"]]
    assert pfad + ".atome.json" not in alle_pfade
    assert pfad + ".text.json" not in alle_pfade
    assert pfad + ".meta.json" not in alle_pfade
