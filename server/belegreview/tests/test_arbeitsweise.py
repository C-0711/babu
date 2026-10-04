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


# ————— Task 2: am Betrieb —————

from test_acting_as import _login, welt2  # noqa: E402,F401


def test_ein_kanzleibetrieb_ohne_einstellungen_bleibt_beim_steuerbuero(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/ich").json()["arbeitsweise"] == "steuerbuero"
    assert nina.get("/api/einstellungen").json()["arbeitsweise"] == "steuerbuero"


def test_die_inhaberin_stellt_auf_selbst_um(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.post("/api/einstellungen",
                  json={"steuerberater_modus": "Ich selbst (Independence Day)",
                        "ustva_rhythmus": "Vierteljährlich",
                        "dauerfristverlaengerung": "Ja",
                        "bundesland": "Baden-Württemberg", "hat_personal": "Nein"})
    assert r.status_code == 200, r.text
    e = nina.get("/api/einstellungen").json()
    assert e["arbeitsweise"] == "selbst"
    assert (e["ustva_rhythmus"], e["bundesland"]) == ("Vierteljährlich", "Baden-Württemberg")
    assert nina.get("/api/ich").json()["arbeitsweise"] == "selbst"


# ————— Task 5: ehrliche Texte —————

def test_kein_steuer_backend_mehr_in_den_texten():
    import monatsabschluss as ma  # noqa: PLC0415
    selbst = ma.uebermittlung_text("selbst")
    buero = ma.uebermittlung_text("steuerbuero")
    assert "Mein ELSTER" in selbst and "Steuer-Backend" not in selbst
    assert "Steuerbüro" in buero and "Steuer-Backend" not in buero


def test_der_entwurf_und_das_pdf_sagen_wer_uebermittelt(welt2, monkeypatch):
    nina = _login(welt2["bw"], welt2["nina"])
    nina.post("/api/einstellungen", json={"steuerberater_modus": "Ich selbst (Independence Day)",
                                          "kleinunternehmer": "Nein"})
    d = nina.get("/api/monatsabschluss/2026-05").json()
    assert "Mein ELSTER" in d["ustva"]["hinweis"]
