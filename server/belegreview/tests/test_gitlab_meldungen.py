"""Die Abbildung Meldung → GitLab-Issue und Labels → Status."""
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
