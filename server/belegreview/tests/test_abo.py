"""Abo und Zugang — die reine Regel (abo.py, seit 03.10.2026).

Ohne Datenbank, ohne Stripe: wer arbeitet heute voll, wer sieht nur an.
Die wichtigste Zusage steht in `test_ohne_abo_ist_es_der_testmonat`: solange
kein Betrieb ein Abo hat, ändert sich für niemanden etwas.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import abo  # noqa: E402
import testmonat  # noqa: E402

HEUTE = dt.date(2026, 10, 20)


def _z(**kw):
    werte = {"test_bis": None, "abo_status": None, "abo_ende": None,
             "zahlungsfehler_seit": None}
    werte.update(kw)
    return abo.zugang(heute=HEUTE, **werte)


def test_preise_netto_und_brutto():
    assert [(p["paket"], p["netto_cent"], p["brutto_cent"]) for p in abo.preise()] == [
        ("solo", 3900, 4641), ("salon", 7900, 9401), ("plus", 14900, 17731)]


def test_bestand_ohne_test_und_abo_arbeitet_voll():
    assert _z() == {"stufe": "voll", "grund": None, "bis": None}


@pytest.mark.parametrize("test_bis", ["2026-10-19", "2026-10-20", "2026-10-21", None])
def test_ohne_abo_ist_es_der_testmonat(test_bis):
    """Zeile für Zeile das Ergebnis des Testmonats vom 02.10.2026."""
    st = testmonat.stand(test_bis, HEUTE)
    z = _z(test_bis=test_bis)
    for methode, pfad in (("POST", "/api/aufnahme"), ("GET", "/api/belege"),
                          ("POST", "/api/rueckmeldung")):
        assert abo.sperrt(methode, pfad, z) == testmonat.sperrt(methode, pfad, st)


def test_test_bis_letzter_tag_voll_danach_nur_lesen():
    assert _z(test_bis="2026-10-20")["stufe"] == "voll"
    assert _z(test_bis="2026-10-20")["bis"] == "2026-10-20"
    z = _z(test_bis="2026-10-19")
    assert z == {"stufe": "nur_lesen", "grund": "test_vorbei", "bis": None}


@pytest.mark.parametrize("status", ["aktiv", "zahlung_laeuft"])
def test_bezahltes_abo_schlaegt_den_abgelaufenen_test(status):
    assert _z(test_bis="2026-09-01", abo_status=status)["stufe"] == "voll"


def test_zahlungsfrist_vierzehn_tage():
    # Fehler am 06.10. → bis einschließlich 20.10. voll, am 21.10. nur lesen.
    assert _z(abo_status="zahlung_offen", zahlungsfehler_seit="2026-10-06") == {
        "stufe": "voll", "grund": "frist", "bis": "2026-10-20"}
    z = _z(abo_status="zahlung_offen", zahlungsfehler_seit="2026-10-05")
    assert z["stufe"] == "nur_lesen" and z["grund"] == "zahlung_offen"


def test_zahlungsfrist_ohne_datum_beginnt_heute():
    assert _z(abo_status="zahlung_offen")["stufe"] == "voll"


def test_gekuendigt_bis_zum_ende_voll():
    assert _z(abo_status="gekuendigt", abo_ende="2026-10-31")["stufe"] == "voll"
    assert _z(abo_status="gekuendigt", abo_ende="2026-10-20")["stufe"] == "voll"
    assert _z(abo_status="gekuendigt", abo_ende="2026-10-19")["stufe"] == "nur_lesen"


def test_beendet_nur_lesen():
    assert _z(abo_status="beendet")["stufe"] == "nur_lesen"


def test_nur_lesen_laesst_lesen_rueckmeldung_und_abo_durch():
    z = _z(abo_status="beendet")
    assert abo.sperrt("POST", "/api/aufnahme", z) is True
    assert abo.sperrt("DELETE", "/api/beleg/x", z) is True
    for methode in ("GET", "HEAD", "OPTIONS"):
        assert abo.sperrt(methode, "/api/belege", z) is False
    assert abo.sperrt("POST", "/api/rueckmeldung", z) is False
    assert abo.sperrt("POST", "/api/abo/checkout", z) is False
    assert abo.sperrt("POST", "/api/aufnahme", _z()) is False
    assert abo.sperrt("POST", "/api/aufnahme", None) is False


def test_jeder_grund_hat_einen_text_ohne_technikwort():
    for grund in ("test_vorbei", "zahlung_offen", "gekuendigt", "beendet"):
        t = abo.text({"grund": grund})
        assert "Weitermachen" in t
        for wort in ("Stripe", "Server", "Token", "Abo-Status"):
            assert wort not in t


@pytest.mark.parametrize("stripe,ende,erwartet", [
    ("active", False, "aktiv"), ("trialing", False, "aktiv"),
    ("active", True, "gekuendigt"), ("incomplete", False, "zahlung_laeuft"),
    ("past_due", False, "zahlung_offen"), ("unpaid", False, "zahlung_offen"),
    ("canceled", False, "beendet"), ("incomplete_expired", False, "beendet"),
    (None, False, "beendet"),
])
def test_status_aus_stripe(stripe, ende, erwartet):
    assert abo.status_aus_stripe(stripe, ende) == erwartet


def test_schalter_standard_aus(monkeypatch):
    monkeypatch.delenv("BABU_ABO", raising=False)
    assert abo.an() is False
    monkeypatch.setenv("BABU_ABO", "1")
    assert abo.an() is True


def test_saloncheck_kennt_dieselben_preise():
    import saloncheck
    for schluessel, p in saloncheck.PAKETE.items():
        assert p["preis"] * 100 == abo.PAKETE[schluessel]["netto_cent"]


def test_app_texte_ohne_aufforderung_zum_abschliessen():
    for grund in ("test_vorbei", "zahlung_offen", "gekuendigt", "beendet"):
        t = abo.text({"grund": grund}, app=True)
        assert "ansehen" in t
        for wort in ("Weitermachen", "abschließen", "Portal", "mybabu", "Zahlungsdaten"):
            assert wort not in t, (grund, wort)
