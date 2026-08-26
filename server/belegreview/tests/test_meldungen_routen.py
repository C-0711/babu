"""„Meine Meldungen": sehen, freigeben, beanstanden — GitLab bleibt unsichtbar."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _issue(iid, state="opened", labels=(), titel="t"):
    return {"iid": iid, "state": state, "labels": list(labels), "title": titel,
            "web_url": f"https://gitlab.0711.io/0711/babu/-/issues/{iid}"}


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_PORTAL_DB", str(tmp_path / "portal.db"))
    import babu_web
    import gitlab_meldungen as gm
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    babu_web._MELDUNGEN_CACHE.update(stand=0.0, daten=None)  # Cache leeren
    monkeypatch.setattr(babu_web, "_box_wache", lambda request: ("nina@0711.io", None))
    monkeypatch.setattr(babu_web, "_rueckmeldung_nachtragen", lambda: 0)
    return TestClient(babu_web.app), babu_web, gm


def test_liste_sortiert_pruefen_zuoberst(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issues_holen", lambda labels="von-nina": [
        _issue(1, labels=["bug"]),
        _issue(2, state="closed"),
        _issue(3, labels=["zur-abnahme"]),
        _issue(4, labels=["in-arbeit"]),
    ])
    monkeypatch.setattr(bw, "_letzte_claude_notiz", lambda iid: "deployt, bitte prüfen")
    r = c.get("/api/rueckmeldungen")
    stati = [m["status"] for m in r.json()["meldungen"]]
    assert stati == ["bitte-pruefen", "in-arbeit", "gemeldet", "erledigt"]
    assert r.json()["meldungen"][0]["kommentar"] == "deployt, bitte prüfen"


def test_freigeben_nur_im_richtigen_zustand(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_holen", lambda iid: _issue(3, labels=["zur-abnahme"]))
    protokoll = []
    monkeypatch.setattr(gm, "notiz", lambda iid, text: protokoll.append(("notiz", text)) or True)
    monkeypatch.setattr(gm, "issue_aendern", lambda iid, **f: protokoll.append(("put", f)) or True)
    assert c.post("/api/rueckmeldungen/3/freigeben").status_code == 200
    assert protokoll[0] == ("notiz", "fachlich freigegeben von nina@0711.io")
    assert protokoll[1][1]["state_event"] == "close"

    monkeypatch.setattr(gm, "issue_holen", lambda iid: _issue(1, labels=["bug"]))
    assert c.post("/api/rueckmeldungen/1/freigeben").status_code == 409


def test_beanstanden_braucht_text_und_setzt_zurueck(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_holen", lambda iid: _issue(3, labels=["zur-abnahme"]))
    protokoll = []
    monkeypatch.setattr(gm, "notiz", lambda iid, text: protokoll.append(text) or True)
    monkeypatch.setattr(gm, "issue_aendern", lambda iid, **f: protokoll.append(f) or True)
    assert c.post("/api/rueckmeldungen/3/beanstanden", json={}).status_code == 400
    r = c.post("/api/rueckmeldungen/3/beanstanden", json={"text": "Farbe stimmt noch nicht"})
    assert r.status_code == 200
    assert "Farbe stimmt noch nicht" in protokoll[0]
    assert protokoll[1]["remove_labels"] == "zur-abnahme"
