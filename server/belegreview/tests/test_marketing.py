"""Marketing: babu gestaltet, aber erfindet nichts.

Was auf einem Aushang steht, muss jemand entschieden haben, der die Zahlen
kennt. babu setzt es nur — in den Farben des Salons.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import marketing as mk  # noqa: E402

STAMM = {"betrieb_name": "Salon Nina", "marke_farbe": "#4A2545"}


def test_es_gibt_vier_stuecke():
    liste = mk.stuecke_liste()
    assert len(liste) == 4
    for s in liste:
        assert s["name"] and s["dazu"] and s["format"]


def test_unbekanntes_stueck_wird_abgewiesen():
    with pytest.raises(mk.MarketingFehler):
        mk.stueck("plakatwand")


@pytest.mark.parametrize("text", ["", "  ", "ab", None])
def test_ohne_text_kein_stueck(text):
    """babu denkt sich keine Angebote aus."""
    with pytest.raises(mk.MarketingFehler):
        mk.text_pruefen(text)


def test_text_wird_geglaettet_und_begrenzt():
    assert mk.text_pruefen("  Neue   Öffnungszeiten \n ab Montag ") == \
        "Neue Öffnungszeiten ab Montag"
    assert len(mk.text_pruefen("x" * 500)) == mk.TEXT_MAX


def test_der_auftrag_traegt_text_farbe_und_namen():
    a = mk.auftrag("aushang", "Wir haben vom 1. bis 14. August Urlaub.", STAMM)
    assert "Salon Nina" in a
    assert "#4A2545" in a
    assert "Wir haben vom 1. bis 14. August Urlaub." in a


def test_der_auftrag_verbietet_erfundene_zeilen():
    a = mk.auftrag("post", "Neue Öffnungszeiten", STAMM)
    assert "ohne erfundene Zeilen" in a
    assert "GENAU" in a


def test_der_auftrag_verbietet_was_kein_aushang_ist():
    a = mk.auftrag("aushang", "Urlaub im August", STAMM)
    for verboten in ("keine Gesichter", "keine Fotografie", "keine Rabattschilder"):
        assert verboten in a


def test_jedes_stueck_hat_sein_format():
    assert mk.stueck("post")["format"] == "1:1"
    assert mk.stueck("gutschein")["format"] == "3:2"
    assert mk.stueck("aushang")["format"] == "3:4"


def test_die_farbe_laesst_sich_uebersteuern():
    a = mk.auftrag("post", "Hallo", STAMM, farbe="#1F3A5F")
    assert "#1F3A5F" in a and "#4A2545" not in a


def test_ohne_stammdaten_kein_absturz():
    a = mk.auftrag("post", "Hallo", {})
    assert "der Salon" in a


def test_logo_platz_nur_auf_wunsch():
    assert "Logo" in mk.auftrag("post", "Hallo", STAMM, mit_logo=True)
    assert "Logo" not in mk.auftrag("post", "Hallo", STAMM, mit_logo=False)
