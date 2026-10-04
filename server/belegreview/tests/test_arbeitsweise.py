"""Wer reicht beim Finanzamt ein? — die Deutung der Einstellung (Stufe A)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import arbeitsweise as aw  # noqa: E402


@pytest.mark.parametrize("wert, erwartet", [
    ("Mein Steuerbüro", aw.STEUERBUERO),
    ("Mein Steuerbüro bleibt", aw.STEUERBUERO),
    ("vorbereitend", aw.STEUERBUERO),
    ("Ich selbst (Independence Day)", aw.SELBST),
    ("Alles über babu", aw.SELBST),
])
def test_alle_werte_der_einstellung(wert, erwartet):
    assert aw.modus({"steuerberater_modus": wert}) == erwartet


def test_ohne_modus_entscheidet_die_frage_nach_dem_steuerberater():
    assert aw.modus({"steuerberater_status": "Ja"}) == aw.STEUERBUERO
    assert aw.modus({"steuerberater_status": "Nein"}, betreut=True) == aw.SELBST


def test_ohne_jede_angabe_entscheidet_die_betreuung():
    """Ein von einer Kanzlei angelegter Betrieb ohne Einstellungen bleibt beim
    Steuerbüro; ein Direktkunde ohne Angaben macht es selbst."""
    assert aw.modus({}, betreut=True) == aw.STEUERBUERO
    assert aw.modus(None, betreut=False) == aw.SELBST
    assert aw.modus({"steuerberater_modus": "  "}, betreut=True) == aw.STEUERBUERO
