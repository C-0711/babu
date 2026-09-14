"""„Meine Meldungen": sehen, freigeben, beanstanden — GitLab bleibt unsichtbar."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Der Ein-Betrieb ohne Mandantenzeile meldet unter `betrieb-default` — das
# ist der Fall der Fixture unten (die Wache setzt keinen Mandanten).
EIGEN = "betrieb-default"


def _issue(iid, state="opened", labels=(), titel="t", betrieb=EIGEN):
    return {"iid": iid, "state": state, "labels": [*labels, betrieb], "title": titel,
            "web_url": f"https://gitlab.0711.io/0711/babu/-/issues/{iid}"}


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_PORTAL_DB", str(tmp_path / "portal.db"))
    import babu_web
    import gitlab_meldungen as gm
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    babu_web._MELDUNGEN_CACHE.clear()
    monkeypatch.setattr(babu_web, "_box_wache", lambda request: ("nina@0711.io", None))
    monkeypatch.setattr(babu_web, "_rueckmeldung_nachtragen", lambda: 0)
    return TestClient(babu_web.app), babu_web, gm


def test_liste_sortiert_pruefen_zuoberst(klient, monkeypatch):
    c, bw, gm = klient
    gefragt = []
    monkeypatch.setattr(gm, "issues_holen", lambda labels="von-nina": gefragt.append(labels) or [
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
    # GitLab bekommt beide Labels — nur die Meldungen dieses Betriebs.
    assert gefragt == [f"von-nina,{EIGEN}"]


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


def test_fremde_meldung_gibt_es_nicht(klient, monkeypatch):
    """Die Grenze zwischen den Betrieben: eine Meldung mit fremdem Label ist
    404 — nicht 403, das verriete, dass die Nummer vergeben ist. Weder
    freigeben noch beanstanden, und GitLab wird dabei nicht beschrieben."""
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_holen",
                        lambda iid: _issue(7, labels=["zur-abnahme"], betrieb="betrieb-9"))
    beschrieben = []
    monkeypatch.setattr(gm, "notiz", lambda iid, text: beschrieben.append(text) or True)
    monkeypatch.setattr(gm, "issue_aendern", lambda iid, **f: beschrieben.append(f) or True)
    assert c.post("/api/rueckmeldungen/7/freigeben").status_code == 404
    assert c.post("/api/rueckmeldungen/7/beanstanden",
                  json={"text": "das ist nicht meine"}).status_code == 404
    assert beschrieben == []


def test_zwei_betriebe_sehen_verschiedene_listen(klient, monkeypatch):
    """Zwei Mandanten im selben Prozess: jeder fragt GitLab mit seinem Label
    und bekommt seinen eigenen Cache — der zweite darf nicht die Liste des
    ersten aus dem Cache bekommen."""
    c, bw, gm = klient
    aktiv = {"mandant": 2}

    def wache(request):
        bw._AKTIVER_MANDANT.set(aktiv["mandant"])
        return ("salon@example.org", None)
    monkeypatch.setattr(bw, "_box_wache", wache)
    gefragt = []

    def holen(labels="von-nina"):
        gefragt.append(labels)
        n = int(labels.rsplit("-", 1)[1])
        return [_issue(n * 10, titel=f"von betrieb {n}", betrieb=f"betrieb-{n}")]
    monkeypatch.setattr(gm, "issues_holen", holen)

    assert [m["titel"] for m in c.get("/api/rueckmeldungen").json()["meldungen"]] == ["von betrieb 2"]
    aktiv["mandant"] = 5
    assert [m["titel"] for m in c.get("/api/rueckmeldungen").json()["meldungen"]] == ["von betrieb 5"]
    aktiv["mandant"] = 2
    # Der dritte Aufruf kommt aus dem Cache von Betrieb 2 — kein neuer GitLab-Aufruf.
    assert [m["titel"] for m in c.get("/api/rueckmeldungen").json()["meldungen"]] == ["von betrieb 2"]
    assert gefragt == ["von-nina,betrieb-2", "von-nina,betrieb-5"]


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
