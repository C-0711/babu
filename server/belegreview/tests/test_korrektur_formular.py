"""Das Korrekturformular im Beleg (Independence Day A, Review 04.10.2026).

Es zeigt das Konto, das der Stapel wirklich bucht (`konto`, bei SKR03 ohne
`konto_skr04`), bietet nur an, was der Stapel auch auswertet (Konto und
Buchungstext — den Steuersatz nimmt er aus den Positionen), und schickt nur,
was sich geändert hat: sonst schriebe eine reine Textkorrektur ein altes
Konto fest.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()


def _funktion(name: str) -> str:
    start = PORTAL.index(f"function {name}(")
    tiefe, i = 0, PORTAL.index("{", start)
    for j in range(i, len(PORTAL)):
        tiefe += {"{": 1, "}": -1}.get(PORTAL[j], 0)
        if tiefe == 0:
            return PORTAL[start:j + 1]
    raise AssertionError(name)


def _formular(d: dict) -> str:
    if not shutil.which("node"):
        pytest.skip("node fehlt")
    js = ("const esc = s => String(s ?? '');\n" + _funktion("korrekturFormular")
          + f"\nprocess.stdout.write(korrekturFormular({json.dumps(d)}));")
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


def test_das_formular_zeigt_das_konto_des_stapels():
    html = _formular({"stamm": "s1", "einschaetzung": {"konto": "4930", "konto_skr04": "6815"},
                      "vlm": {"buchungstext": "Büro"}})
    assert 'value="4930"' in html


def test_ohne_konto_im_rahmen_gilt_skr04():
    html = _formular({"stamm": "s1", "einschaetzung": {"konto_skr04": "6815"}, "vlm": {}})
    assert 'value="6815"' in html


def test_kein_steuerfeld_das_der_stapel_nicht_auswertet():
    html = _formular({"stamm": "s1", "einschaetzung": {"steuerschluessel": "94"}, "vlm": {}})
    assert "korr-bu" not in html


def test_es_geht_nur_raus_was_sich_geaendert_hat():
    knopf = PORTAL[PORTAL.index('ev.target.closest("#korr-feld [data-korr]")'):][:1500]
    assert "dataset.vorher" in knopf
    assert "steuerschluessel" not in knopf
