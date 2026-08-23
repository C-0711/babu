"""Der Rückmeldeknopf im Lauf.

Die eine Zusage, die nicht brechen darf: **eine Meldung geht nie verloren.**
Fixit kann weg sein, der Token kann fehlen — Ninas Text liegt trotzdem in
der Belegbox, versioniert, und wird nachgereicht. Wenn sie „ist angekommen"
liest, ist es angekommen.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent


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
    monkeypatch.setattr(babu_web, "FIXIT_PAT_PFAD", tmp_path / "kein-fixit-pat")
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "_vertrag_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "_brief_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "ERLAUBT", set())
    babu_web._REG_ZULETZT.clear()
    return babu_web, bare, tmp_path


def konto(bw, email="nina@0711.io"):
    c = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    c.post("/api/signup", json={"salon": "Salon Nina", "email": email,
                                "passwort": "passwort-lang"})
    return c


def in_der_box(bare):
    r = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                       capture_output=True, text=True, check=True)
    return [z for z in r.stdout.split() if z.startswith("rueckmeldungen/")]


MELDUNG = {"text": "Der Beleg vom Bäcker zeigt 19 % statt 7 %.",
           "art": "fehler", "quelle": "app", "ansicht": "Dokumente",
           "beleg": "RE-2026-4711", "geraet": "iPhone 15 Pro Max",
           "fassung": "34c4a20"}


# ————— Die Meldung geht nie verloren —————

def test_ohne_fixit_token_liegt_sie_trotzdem_in_der_box(welt):
    """Der wichtigste Fall — heute ist genau der der Normalfall."""
    bw, bare, _ = welt
    c = konto(bw)
    r = c.post("/api/rueckmeldung", json=MELDUNG)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["weitergereicht"] is False
    assert "wartet" in d["hinweis"]
    dateien = in_der_box(bare)
    assert len(dateien) == 1


def test_der_text_steht_unveraendert_in_der_abgelegten_datei(welt):
    bw, bare, _ = welt
    c = konto(bw)
    c.post("/api/rueckmeldung", json=MELDUNG)
    roh = bw.git_show(in_der_box(bare)[0])
    d = json.loads(roh)
    assert d["meldung"]["text"] == MELDUNG["text"]
    assert d["vorgang"]["title"] == "Der Beleg vom Bäcker zeigt 19 % statt 7 %"
    assert d["vorgang"]["type"] == "bug"
    assert d["vorgang"]["status"] == "todo"


def test_der_zusammenhang_kommt_mit(welt):
    bw, bare, _ = welt
    c = konto(bw)
    c.post("/api/rueckmeldung", json=MELDUNG)
    koerper = json.loads(bw.git_show(in_der_box(bare)[0]))["vorgang"]["body"]
    for erwartet in ("Dokumente", "RE-2026-4711", "nina@0711.io",
                     "iPhone 15 Pro Max", "34c4a20"):
        assert erwartet in koerper, erwartet


def test_ein_wunsch_wird_als_aufgabe_abgelegt(welt):
    bw, bare, _ = welt
    c = konto(bw)
    c.post("/api/rueckmeldung", json={"text": "Ich hätte gern eine Suche.",
                                      "art": "wunsch", "quelle": "portal"})
    v = json.loads(bw.git_show(in_der_box(bare)[0]))["vorgang"]
    assert v["type"] == "task" and v["component"] == "Web"


def test_mit_token_wird_weitergereicht(welt, monkeypatch):
    bw, bare, tmp = welt
    (tmp / "fixit-pat").write_text("gcpat-" + "x" * 40)
    monkeypatch.setattr(bw, "FIXIT_PAT_PFAD", tmp / "fixit-pat")
    gesendet = {}

    class Antwort:
        status_code = 201
        text = ""
        def json(self): return {"issue": {"key": "BABU-99", "number": 99}}

    def falsches_post(url, json=None, timeout=None, headers=None):
        gesendet.update(url=url, nutzlast=json, kopf=headers)
        return Antwort()

    monkeypatch.setattr(bw.requests, "post", falsches_post)
    r = c_post = konto(bw).post("/api/rueckmeldung", json=MELDUNG)
    assert r.status_code == 200
    assert r.json()["weitergereicht"] is True
    assert r.json()["hinweis"] == "BABU-99"
    # Der Kanal steht im Pfad, nicht im Körper — und der Dienst ist der lokale
    # GitChain-Container, nicht die Weboberfläche (die nimmt keinen Bearer).
    assert gesendet["url"] == "http://127.0.0.1:3361/git/workspace/0711/babu/issues"
    assert gesendet["kopf"]["Authorization"].startswith("Bearer gcpat-")
    assert gesendet["nutzlast"]["type"] == "bug"
    assert "channel" not in gesendet["nutzlast"]
    # Auch mit Fixit bleibt die Kopie in der Box.
    assert len(in_der_box(bare)) == 1


def test_ein_fehler_bei_fixit_verliert_die_meldung_nicht(welt, monkeypatch):
    bw, bare, tmp = welt
    (tmp / "fixit-pat").write_text("gcpat-" + "x" * 40)
    monkeypatch.setattr(bw, "FIXIT_PAT_PFAD", tmp / "fixit-pat")

    def kaputt(*a, **k):
        raise RuntimeError("Netz weg")

    monkeypatch.setattr(bw.requests, "post", kaputt)
    r = konto(bw).post("/api/rueckmeldung", json=MELDUNG)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["weitergereicht"] is False
    assert len(in_der_box(bare)) == 1


# ————— Was nicht durchgeht —————

@pytest.mark.parametrize("text", ["", "  ", "ab"])
def test_eine_leere_meldung_wird_freundlich_abgelehnt(welt, text):
    bw, _, _ = welt
    r = konto(bw).post("/api/rueckmeldung", json={"text": text})
    assert r.status_code == 400
    assert "ein Satz" in r.json()["fehler"]


def test_ohne_anmeldung_geht_nichts(welt):
    bw, _, _ = welt
    c = TestClient(bw.app, base_url="https://testserver")
    assert c.post("/api/rueckmeldung", json=MELDUNG).status_code == 401


def test_sehr_langer_text_wird_gekappt_statt_abgelehnt(welt):
    """Wer viel schreibt, hat viel zu sagen — nicht wegwerfen."""
    bw, bare, _ = welt
    c = konto(bw)
    r = c.post("/api/rueckmeldung", json={"text": "A" * 20000})
    assert r.status_code == 200
    d = json.loads(bw.git_show(in_der_box(bare)[0]))
    assert len(d["meldung"]["text"]) == bw.RUECKMELDUNG_MAX


def test_ein_unbrauchbarer_koerper_ergibt_400(welt):
    bw, _, _ = welt
    c = konto(bw)
    r = c.post("/api/rueckmeldung", content=b"kein json",
               headers={"Content-Type": "application/json"})
    assert r.status_code == 400
