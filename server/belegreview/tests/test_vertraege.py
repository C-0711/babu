"""Die Vertragskiste: was monatlich abgeht — und wann gekündigt sein muss.

Eine verpasste Kündigungsfrist kostet ein weiteres Jahr. Deshalb ist die
wichtigste Eigenschaft hier: was sich nicht sicher lesen lässt, wird NICHT
geraten. Lieber „steht im Vertrag" als ein erfundenes Datum.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vertraege as vt  # noqa: E402


def v(**kw) -> dict:
    grund = {"art": "miete", "art_name": "Mietvertrag", "partner": "Sonnenberg",
             "betrag_monat": 1250.0, "beginn": "2024-01-01", "laufzeit_bis": None,
             "kuendigungsfrist": None, "zahlweise": "monatlich"}
    grund.update(kw)
    return grund


# ————— Frist verstehen —————

@pytest.mark.parametrize("text, monate", [
    ("3 Monate zum Quartalsende", 3),
    ("drei Monate zum Monatsende", 3),
    ("1 Monat", 1),
    ("6 Monate zum Jahresende", 6),
    ("vier Wochen zum Monatsende", None),   # Wochen: nicht in Monaten rechenbar
    ("nach Absprache", None),
    ("", None),
    (None, None),
])
def test_frist_in_monaten(text, monate):
    assert vt.frist_monate(text) == monate


@pytest.mark.parametrize("text, erwartet", [
    ("3 Monate zum Quartalsende", "quartal"),
    ("3 Monate zum Monatsende", "monat"),
    ("6 Monate zum Jahresende", "jahr"),
    ("3 Monate", None),
])
def test_frist_zielpunkt(text, erwartet):
    assert vt.frist_ziel(text) == erwartet


# ————— Bis wann muss die Kündigung raus —————

def test_kuendigen_bis_zum_quartalsende():
    """Läuft bis 31.12., 3 Monate zum Quartalsende → raus bis 30.09."""
    ergebnis = vt.kuendigen_bis(
        v(laufzeit_bis="2026-12-31", kuendigungsfrist="3 Monate zum Quartalsende"),
        heute=dt.date(2026, 8, 21))
    assert ergebnis["datum"] == "2026-09-30"
    assert ergebnis["sicher"] is True


def test_kuendigen_bis_zum_monatsende():
    ergebnis = vt.kuendigen_bis(
        v(laufzeit_bis="2026-12-31", kuendigungsfrist="3 Monate zum Monatsende"),
        heute=dt.date(2026, 8, 21))
    assert ergebnis["datum"] == "2026-09-30"
    assert ergebnis["sicher"] is True


def test_kuendigen_bis_ohne_zielpunkt_ist_schlicht_die_frist():
    """„1 Monat" ohne Zielpunkt: einen Monat vor Laufzeitende."""
    ergebnis = vt.kuendigen_bis(
        v(laufzeit_bis="2026-12-31", kuendigungsfrist="1 Monat"),
        heute=dt.date(2026, 8, 21))
    assert ergebnis["datum"] == "2026-11-30"


def test_unlesbares_wird_nicht_geraten():
    """Der wichtigste Test: kein erfundenes Datum."""
    for vertrag in (v(laufzeit_bis="2026-12-31", kuendigungsfrist="nach Absprache"),
                    v(laufzeit_bis=None, kuendigungsfrist="3 Monate zum Quartalsende"),
                    v(laufzeit_bis="2026-12-31", kuendigungsfrist=None),
                    v(laufzeit_bis="kaputt", kuendigungsfrist="3 Monate")):
        ergebnis = vt.kuendigen_bis(vertrag, heute=dt.date(2026, 8, 21))
        assert ergebnis["datum"] is None
        assert ergebnis["sicher"] is False
        assert "Vertrag" in ergebnis["hinweis"]


def test_frist_schon_vorbei():
    ergebnis = vt.kuendigen_bis(
        v(laufzeit_bis="2026-09-30", kuendigungsfrist="3 Monate zum Monatsende"),
        heute=dt.date(2026, 8, 21))
    assert ergebnis["datum"] == "2026-06-30"
    assert ergebnis["vorbei"] is True


# ————— Die Kiste als Ganzes —————

def test_uebersicht_summiert_nur_laufende():
    heute = dt.date(2026, 8, 21)
    kiste = vt.uebersicht([
        v(partner="Sonnenberg", betrag_monat=1250.0),
        v(art="versicherung", partner="Allianz", betrag_monat=87.5),
        v(art="leasing", partner="Alt-Leasing", betrag_monat=200.0,
          laufzeit_bis="2026-03-31"),          # ausgelaufen
        v(art="telefon", partner="Ohne Betrag", betrag_monat=None),
    ], heute=heute)
    assert kiste["monatlich"] == 1337.5
    assert kiste["jaehrlich"] == 16050.0
    assert kiste["anzahl"] == 3               # ausgelaufener zählt nicht mit
    assert kiste["ohne_betrag"] == 1


def test_uebersicht_zeigt_anstehende_fristen():
    """Was in den nächsten 90 Tagen gekündigt sein muss, steht oben."""
    heute = dt.date(2026, 8, 21)
    kiste = vt.uebersicht([
        v(partner="Bald fällig", laufzeit_bis="2026-12-31",
          kuendigungsfrist="3 Monate zum Quartalsende"),      # bis 30.09. → 40 Tage
        v(partner="Später", laufzeit_bis="2027-12-31",
          kuendigungsfrist="3 Monate zum Quartalsende"),      # weit weg
    ], heute=heute)
    anstehend = kiste["anstehend"]
    assert len(anstehend) == 1
    assert anstehend[0]["partner"] == "Bald fällig"
    assert anstehend[0]["tage"] == 40


def test_uebersicht_sortiert_nach_geld():
    kiste = vt.uebersicht([v(partner="Klein", betrag_monat=20.0),
                           v(partner="Groß", betrag_monat=900.0)],
                          heute=dt.date(2026, 8, 21))
    assert [x["partner"] for x in kiste["vertraege"]] == ["Groß", "Klein"]


def test_leere_kiste_ist_kein_fehler():
    kiste = vt.uebersicht([], heute=dt.date(2026, 8, 21))
    assert kiste == {"monatlich": 0.0, "jaehrlich": 0.0, "anzahl": 0,
                     "ohne_betrag": 0, "vertraege": [], "anstehend": []}
