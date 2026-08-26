# server/belegreview/tests/test_rueckmeldung_route.py
"""Der Rückmeldeknopf: eine Meldung geht nie verloren.

GitLab da → Issue. GitLab weg → Puffer in portal.db, Antwort trotzdem „ok".
"""
import base64
import sys
import threading
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
    monkeypatch.setattr(babu_web, "_box_wache", lambda request: ("nina@0711.io", None))
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


def test_nachtragen_laeuft_nie_doppelt(klient, monkeypatch):
    """Zwei gleichzeitige Nachtrag-Läufe dürfen nicht denselben Puffer-Eintrag
    beide an GitLab melden. Deterministisch mit zwei Events: der erste Lauf
    blockiert mitten in issue_anlegen, bis wir ihn freigeben — währenddessen
    muss ein zweiter Lauf sofort überspringen (kein zweiter issue_anlegen-Ruf)."""
    c, bw, gm = klient
    laeuft = threading.Event()
    weiter = threading.Event()
    aufrufe = []

    def _blockierend(issue, bild_jpeg=None):
        aufrufe.append(issue)
        laeuft.set()
        assert weiter.wait(2), "zweiter Lauf hat nicht rechtzeitig freigegeben"
        return True, "1"

    monkeypatch.setattr(gm, "issue_anlegen", _blockierend)
    with bw._db() as conn:
        gm.puffer_ablegen(conn, {"issue": {"title": "t", "description": "d",
                                           "labels": "bug"}, "bild_b64": None})

    t = threading.Thread(target=bw._rueckmeldung_nachtragen)
    t.start()
    assert laeuft.wait(2), "erster Lauf kam nicht in Gang"

    # Zweiter Lauf trifft das Mutex besetzt an — überspringt sofort, statt
    # den Eintrag ein zweites Mal an GitLab zu melden.
    bw._rueckmeldung_nachtragen()
    assert len(aufrufe) == 1

    weiter.set()
    t.join(2)
    assert not t.is_alive()
    assert len(aufrufe) == 1
    with bw._db() as conn:
        n = conn.execute("select count(*) from meldung_puffer").fetchone()[0]
    assert n == 0


def test_erfolgreiche_meldung_invalidiert_cache(klient, monkeypatch):
    """Neue Meldung soll sofort in der Liste erscheinen — dazu muss der Cache
    ungültig gemacht werden, sobald GitLab die Meldung angenommen hat."""
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_anlegen", lambda *a, **k: (True, "64"))
    # Cache vorher füllen — simuliert den Fall, dass Nina kurz vor dem Melden
    # die Liste aufgerufen hat (und dort ihre neue Meldung noch nicht sieht).
    bw._MELDUNGEN_CACHE.update(stand=999999.0, daten=[{"iid": 1, "titel": "alt"}])
    r = c.post("/api/rueckmeldung", json={"text": "Neue Meldung fehlt in der Liste."})
    assert r.status_code == 200
    # Cache muss ungültig sein (stand=0.0), damit der nächste GET frisch holt.
    assert bw._MELDUNGEN_CACHE["stand"] == 0.0


def test_gepufferte_meldung_invalidiert_cache_nicht(klient, monkeypatch):
    """Wenn GitLab weg ist und die Meldung nur gepuffert wird, darf der Cache
    NICHT ungültig gemacht werden — sonst würde die App beim nächsten Öffnen
    der Liste versuchen, GitLab zu erreichen (das gerade weg ist), statt den
    noch gültigen Cache zu verwenden."""
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_anlegen", lambda *a, **k: (False, "weg"))
    bw._MELDUNGEN_CACHE.update(stand=999999.0, daten=[{"iid": 1, "titel": "alt"}])
    r = c.post("/api/rueckmeldung", json={"text": "GitLab ist weg."})
    assert r.status_code == 200
    # Cache muss unverändert bleiben (stand immer noch 999999.0).
    assert bw._MELDUNGEN_CACHE["stand"] == 999999.0
