# server/belegreview/tests/test_rueckmeldung_route.py
"""Der Rückmeldeknopf: eine Meldung geht nie verloren.

GitLab da → Issue. GitLab weg → Puffer in portal.db, Antwort trotzdem „ok".
"""
import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_PORTAL_DB", str(tmp_path / "portal.db"))
    import babu_web
    import gitlab_meldungen as gm
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    # Wache: jede Anfrage ist nina.
    monkeypatch.setattr(babu_web, "_api_wache", lambda request: ("nina@0711.io", None))
    return TestClient(babu_web.app), babu_web, gm


def test_gitlab_da_wird_issue(klient, monkeypatch):
    c, bw, gm = klient
    gesehen = {}
    def _anlegen(issue, bild_jpeg=None):
        gesehen.update(issue=issue, bild=bild_jpeg)
        return True, "91"
    monkeypatch.setattr(gm, "issue_anlegen", _anlegen)
    r = c.post("/api/rueckmeldung", json={
        "text": "Die Kacheln springen beim Blättern.",
        "art": "fehler", "ansicht": "Dokumente",
        "bild": base64.b64encode(b"jpegbytes").decode()})
    assert r.status_code == 200
    assert r.json()["issue"] == "91"
    assert gesehen["issue"]["labels"] == "bug,von-nina"
    assert gesehen["bild"] == b"jpegbytes"


def test_gitlab_weg_wird_gepuffert(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_anlegen", lambda *a, **k: (False, "weg"))
    r = c.post("/api/rueckmeldung", json={"text": "Etwas stimmt nicht."})
    assert r.status_code == 200 and r.json()["ok"] is True
    with bw._db() as conn:
        n = conn.execute("select count(*) from meldung_puffer").fetchone()[0]
    assert n == 1


def test_zu_grosses_bild_wird_abgelehnt(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_anlegen", lambda *a, **k: (True, "1"))
    riesig = base64.b64encode(b"x" * (3 * 1024 * 1024 + 1)).decode()
    r = c.post("/api/rueckmeldung", json={"text": "Bild zu groß.", "bild": riesig})
    assert r.status_code == 400
