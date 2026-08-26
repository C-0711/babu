"""Das Protokoll abholen und einen Beleg neu lesen lassen.

Zwei Wege, die zusammengehören: hinter dem ⓘ liegt das Leseprotokoll, und
wenn es alt ist — gelesen vor einer Verbesserung —, stößt ein Knopf die
Lesung neu an, ohne dass jemand den Beleg noch einmal fotografieren muss.

Die Regel, die dabei nicht brechen darf: **neu lesen löscht nur das
Ergebnis, nie den Beleg.** Ein Beleg ist ein Original mit
Aufbewahrungspflicht; ein Ergebnis ist eine Meinung darüber.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 300


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
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
    monkeypatch.setattr(babu_web, "_vertrag_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "_brief_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "ERLAUBT", set())
    babu_web._REG_ZULETZT.clear()
    return babu_web, bare


def konto(bw, email="nina@0711.io"):
    c = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    c.post("/api/signup", json={"salon": "Salon Nina", "email": email,
                                "passwort": "passwort-lang"})
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=1 WHERE email=?", (email,))
    return c


def beleg_mit_review(bw, bare, stamm="20260822-120000-abc-bon"):
    """Einen Beleg samt Lesung in die Box legen — wie nach einem Watcher-Lauf."""
    import boxschreiber
    boxschreiber.schreiben({
        f"docs/{stamm}.jpg": JPEG,
        f"review/{stamm}.json": json.dumps(
            {"datei": f"docs/{stamm}.jpg", "felder": {"brutto": 1.30}}).encode(),
        f"review/{stamm}.md": "# Leseprotokoll\n\nZeile 1 · SUMME 1,30\n".encode(),
        f"review/{stamm}.embedding.json": b'{"dim": 2, "vektor": [0, 1]}',
    }, None, "aufnahme: Bon", "nina@0711.io")
    return stamm


def in_der_box(bare) -> set[str]:
    r = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                       capture_output=True, text=True, check=True)
    return set(r.stdout.split())


# ————— Das Protokoll —————

def test_das_protokoll_kommt_als_markdown(welt):
    bw, bare = welt
    c = konto(bw)
    stamm = beleg_mit_review(bw, bare)
    r = c.get(f"/review/{stamm}/protokoll")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/markdown")
    assert "Leseprotokoll" in r.text


def test_ohne_anmeldung_kein_protokoll(welt):
    bw, bare = welt
    stamm = beleg_mit_review(bw, bare)
    c = TestClient(bw.app, base_url="https://testserver")
    assert c.get(f"/review/{stamm}/protokoll").status_code == 401


def test_ohne_freischaltung_kein_protokoll(welt):
    bw, bare = welt
    stamm = beleg_mit_review(bw, bare)
    c = konto(bw, "fremd@x.de")
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=0 WHERE email=?", ("fremd@x.de",))
    assert c.get(f"/review/{stamm}/protokoll").status_code == 403


def test_ein_altes_review_ohne_protokoll_sagt_was_zu_tun_ist(welt):
    """Belege von vor der Einführung haben keine .md — das darf kein
    nacktes 404 sein."""
    import boxschreiber
    bw, bare = welt
    c = konto(bw)
    boxschreiber.schreiben({
        "docs/alt.jpg": JPEG,
        "review/alt.json": b'{"felder": {}}',
    }, None, "aufnahme: alt", "nina@0711.io")
    r = c.get("/review/alt/protokoll")
    assert r.status_code == 404
    assert "Leseprotokoll" in r.json()["fehler"]


def test_unbekannter_beleg_ergibt_404(welt):
    bw, _ = welt
    c = konto(bw)
    assert c.get("/review/gibtsnicht/protokoll").status_code == 404


@pytest.mark.parametrize("boeser", ["../../etc/passwd", "a/b", "..", "a b"])
def test_kein_ausbruch_aus_dem_review_ordner(welt, boeser):
    bw, _ = welt
    c = konto(bw)
    assert c.get(f"/review/{boeser}/protokoll").status_code in (400, 404)
