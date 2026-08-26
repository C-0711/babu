"""Die Leitplanke und die Kandidatenwahl — deterministisch, ohne Netz."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "werkzeuge" / "fixlauf"))

import fixlauf  # noqa: E402
import leitplanke  # noqa: E402


def test_leitplanke_stoppt_die_vier_bereiche():
    assert leitplanke.riskant(["server/belegreview/boxschreiber.py"])
    assert leitplanke.riskant(["server/belegreview/kontierung.py"])
    assert leitplanke.riskant(["server/belegreview/extf.py"])
    assert leitplanke.riskant(["server/belegreview/migrationen/007_x.sql"])


def test_leitplanke_laesst_ui_durch():
    assert leitplanke.riskant(["ios/Beleg/Beleg/MeldenSheet.swift",
                               "server/belegreview/portal.html"]) is None


def _i(iid, labels, updated="2026-08-26T10:00:00Z"):
    return {"iid": iid, "labels": labels, "updated_at": updated}


def test_kandidaten_nur_bug_ohne_prozesslabel_max_drei():
    issues = [
        _i(1, ["bug"]), _i(2, ["wunsch"]), _i(3, ["bug", "zur-abnahme"]),
        _i(4, ["bug", "braucht-christoph"]), _i(5, ["bug"]), _i(6, ["bug"]),
        _i(7, ["bug"]),
    ]
    iids = [k["iid"] for k in fixlauf.kandidaten(issues, "2026-08-26T10:30:00Z")]
    assert iids == [1, 5, 6]  # 7 fällt der Drei-Grenze zum Opfer


def test_verwaiste_in_arbeit_wird_nach_zwei_stunden_wieder_kandidat():
    frisch = _i(8, ["bug", "in-arbeit"], updated="2026-08-26T09:30:00Z")
    verwaist = _i(9, ["bug", "in-arbeit"], updated="2026-08-26T07:00:00Z")
    iids = [k["iid"] for k in fixlauf.kandidaten([frisch, verwaist],
                                                 "2026-08-26T10:30:00Z")]
    assert iids == [9]
