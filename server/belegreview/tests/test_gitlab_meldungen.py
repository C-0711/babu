"""Die Abbildung Meldung → GitLab-Issue und Labels → Status."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gitlab_meldungen as gm  # noqa: E402
import rueckmeldung as rm  # noqa: E402


def test_fehler_wird_bug_issue():
    m = rm.Meldung(text="Der Beleg vom Bäcker zeigt 19 % statt 7 %.",
                   art="fehler", quelle="app", von="nina@0711.io",
                   geraet="iPhone, iOS 26", fassung="42")
    issue = gm.als_issue(m)
    assert issue["title"] == "Der Beleg vom Bäcker zeigt 19 % statt 7 %"
    assert "19 % statt 7 %" in issue["description"]
    assert "iPhone, iOS 26" in issue["description"]
    assert issue["labels"] == "bug,von-nina"


def test_wunsch_bekommt_wunsch_label():
    m = rm.Meldung(text="Ich hätte gern eine Suche.", art="wunsch")
    assert gm.als_issue(m)["labels"] == "wunsch,von-nina"


def _issue(state="opened", labels=()):
    return {"state": state, "labels": list(labels)}


def test_status_abbildung():
    assert gm.status_von(_issue()) == "gemeldet"
    assert gm.status_von(_issue(labels=["bug", "in-arbeit"])) == "in-arbeit"
    assert gm.status_von(_issue(labels=["zur-abnahme"])) == "bitte-pruefen"
    # braucht-christoph ist für Nina schlicht „in Arbeit" — sie muss nichts tun.
    assert gm.status_von(_issue(labels=["braucht-christoph"])) == "in-arbeit"
    assert gm.status_von(_issue(state="closed", labels=["zur-abnahme"])) == "erledigt"


class _Antwort:
    def __init__(self, status, daten):
        self.status_code, self._daten = status, daten
        self.text = json.dumps(daten)
    def json(self):
        return self._daten


def _klient(monkeypatch, tmp_path, antworten):
    """gitlab_meldungen mit Token-Datei und aufgezeichneten HTTP-Antworten."""
    tok = tmp_path / "tok"
    tok.write_text("glpat-test")
    monkeypatch.setattr(gm, "TOKEN_PFAD", tok)
    rufe = []
    def _ruf(methode, url, **kw):
        rufe.append((methode, url, kw))
        return antworten.pop(0)
    monkeypatch.setattr(gm, "_http", _ruf)
    return rufe


def test_issue_anlegen_mit_bild(monkeypatch, tmp_path):
    rufe = _klient(monkeypatch, tmp_path, [
        _Antwort(201, {"markdown": "![f](/uploads/abc/f.jpg)"}),
        _Antwort(201, {"iid": 77}),
    ])
    ok, was = gm.issue_anlegen({"title": "t", "description": "d", "labels": "bug,von-nina"},
                               bild_jpeg=b"\xff\xd8kein-echtes-jpeg")
    assert (ok, was) == (True, "77")
    assert "/uploads" in rufe[0][1]
    # Das Bild steht als Markdown in der Beschreibung des zweiten Aufrufs.
    assert "/uploads/abc/f.jpg" in rufe[1][2]["json"]["description"]


def test_issue_anlegen_meldet_ausfall(monkeypatch, tmp_path):
    def _kaputt(methode, url, **kw):
        raise OSError("keine Verbindung")
    monkeypatch.setattr(gm, "_http", _kaputt)
    (tmp_path / "tok").write_text("glpat-test")
    monkeypatch.setattr(gm, "TOKEN_PFAD", tmp_path / "tok")
    ok, grund = gm.issue_anlegen({"title": "t", "description": "d", "labels": "bug"})
    assert ok is False and "Verbindung" in grund


def test_puffer_haelt_und_traegt_nach(monkeypatch, tmp_path):
    conn = sqlite3.connect(tmp_path / "portal.db")
    gm.puffer_ablegen(conn, {"issue": {"title": "t", "description": "d", "labels": "bug"},
                             "bild_b64": None})
    _klient(monkeypatch, tmp_path, [_Antwort(201, {"iid": 5})])
    assert gm.puffer_nachtragen(conn) == 1
    rest = conn.execute("select count(*) from meldung_puffer").fetchone()[0]
    assert rest == 0
