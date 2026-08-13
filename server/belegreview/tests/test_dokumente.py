"""Stufe-3-Tests: Dokumentenkanal + Lesestatus + Einstellungen."""
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
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare


def test_dokument_rundreise(welt):
    client, bare = welt
    r = client.post("/api/dokumente",
                    params={"name": "Lohnauswertung Juli.pdf",
                            "titel": "Lohnauswertung Juli 2026", "art": "auswertung"},
                    content=b"%PDF-1.4 lohn")
    assert r.status_code == 200
    pfad = r.json()["pfad"]

    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("dokument: ")

    liste = client.get("/api/dokumente").json()
    assert liste["ungelesen"] == 1
    d = liste["dokumente"][0]
    assert d["titel"] == "Lohnauswertung Juli 2026"
    assert d["art"] == "auswertung"
    assert d["gelesen"] is False

    inhalt = client.get("/api/dokument/" + pfad)
    assert inhalt.status_code == 200
    assert inhalt.content == b"%PDF-1.4 lohn"
    assert inhalt.headers["content-type"].startswith("application/pdf")

    assert client.post("/api/dokument-gelesen", json={"pfad": pfad}).status_code == 200
    liste2 = client.get("/api/dokumente").json()
    assert liste2["ungelesen"] == 0
    assert liste2["dokumente"][0]["gelesen"] is True


def test_dokument_pfad_grenzen(welt):
    client, _ = welt
    assert client.get("/api/dokument/docs/2026-08/x.jpg").status_code == 400
    assert client.post("/api/dokumente", params={"name": "boese.exe"},
                       content=b"x").status_code == 400


def test_einstellungen_rundreise(welt):
    client, _ = welt
    r = client.post("/api/einstellungen",
                    json={"benachrichtigung_frage": "1", "quatsch": "x",
                          "kanzlei_name": "Nestle & Kollegen"})
    d = r.json()
    assert d["benachrichtigung_frage"] == "1"
    assert d["kanzlei_name"] == "Nestle & Kollegen"
    assert "quatsch" not in d
    assert client.get("/api/einstellungen").json() == d
