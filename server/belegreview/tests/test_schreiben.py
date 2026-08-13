"""Stufe-2-Tests: boxschreiber + POST /api/bewirtung + POST /api/hochladen.

Eigenes Modul mit frischem Store (Schreibtests mutieren den Zustand).
Remote = lokales Bare-Repo ohne Auth; der PAT-Header bleibt aus, weil die
PAT-Datei im Test nicht existiert.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    golden = json.loads(GOLDEN.read_text())
    gespeichert = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}
    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "docs" / "2026-08" / f"{STAMM}.jpg").write_bytes(b"\xff\xd8x")
    (arbeit / "review").mkdir()
    (arbeit / "review" / f"{STAMM}.json").write_text(json.dumps(gespeichert, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", f"aufnahme+review: {STAMM}")
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare


def test_bewirtung_antwort_macht_geprueft(welt):
    client, bare = welt
    vorher = client.get(f"/api/beleg/{STAMM}").json()
    assert vorher["status"] == "nachfrage"

    r = client.post(f"/api/bewirtung/{STAMM}",
                    json={"anlass": "Team-Essen nach der Schulung",
                          "teilnehmer": ["Nicole Baic", "Jana Allgaier"]})
    assert r.status_code == 200 and r.json()["ok"] is True

    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log == f"bewirtung: {STAMM}|christoph0711.io"

    nachher = client.get(f"/api/beleg/{STAMM}").json()
    assert nachher["status"] == "geprüft"          # Trinkgeld-Offen ist nur Info
    assert nachher["bewirtung_beantwortet"] is True
    assert nachher["bewirtung"]["anlass"] == "Team-Essen nach der Schulung"
    assert nachher["bewirtung"]["teilnehmer"] == ["Nicole Baic", "Jana Allgaier"]


def test_bewirtung_validierung(welt):
    client, _ = welt
    r = client.post(f"/api/bewirtung/{STAMM}", json={"anlass": "", "teilnehmer": []})
    assert r.status_code == 400


def test_hochladen(welt):
    client, bare = welt
    r = client.post("/api/hochladen", params={"name": "kassenbon.jpg"},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200
    datei = r.json()["datei"]
    assert datei.startswith("docs/") and datei.endswith("-kassenbon.jpg")
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("aufnahme: ") and log.endswith("|christoph0711.io")
    d = client.get("/api/belege").json()
    assert any(z["datei"] == datei and z["status"] == "erfasst" for z in d["belege"])


def test_hochladen_grenzen(welt):
    client, _ = welt
    assert client.post("/api/hochladen", params={"name": "boese.exe"},
                       content=b"x").status_code == 400
    assert client.post("/api/hochladen", params={"name": "leer.jpg"},
                       content=b"").status_code == 400
