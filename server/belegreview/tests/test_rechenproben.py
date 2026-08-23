"""Was aus den Rechenproben und den Steuersätzen im Review landet.

`test_belegdeutung.py` prüft, ob der Beleg richtig gelesen wird. Hier geht
es um das, was danach passiert: ob die gescheiterte Probe beim Namen genannt
wird, statt als anonymes „Summenprobe nicht bestanden" durchzurutschen, und
ob zwei Steuersätze bis in den Buchungsstapel getrennt bleiben — sonst
stimmt die Voranmeldung nicht.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extf  # noqa: E402
from belegdeutung import Kasten, deuten  # noqa: E402


@pytest.fixture()
def rw():
    import review_watcher
    return review_watcher


def k(text, x0, y0, breite=None, hoehe=20, konf=0.97):
    breite = breite if breite is not None else len(text) * hoehe * 0.55
    return Kasten(text, konf, x0, y0, x0 + breite, y0 + hoehe)


def rechts(text, kante, y, hoehe=20, konf=0.97):
    breite = len(text) * hoehe * 0.55
    return Kasten(text, konf, kante - breite, y, kante, y + hoehe)


@pytest.fixture
def drogeriebon():
    """Der dm-Fall aus dem Testkorpus: 19 % und 7 % auf einem Bon."""
    return [
        k("dm-drogerie markt", 40, 20, hoehe=22),
        k("A 19%", 40, 160), k("15,97", 200, 160), k("3,03", 300, 160),
        k("19,00", 400, 160),
        k("B 7%", 40, 190), k("79,81", 200, 190), k("5,59", 300, 190),
        k("85,40", 400, 190),
        k("SUMME", 40, 230), k("104,40", 400, 230),
    ]


@pytest.fixture
def verlesene_rechnung():
    """Positionen über 33,61 netto, als Endbetrag steht 90,00 statt 40,00."""
    return [
        k("FRISEURBEDARF SÜDWEST GMBH", 60, 30, hoehe=30),
        k("1 Coloration 60 ml", 60, 386, hoehe=15), rechts("21,85", 520, 386, hoehe=15),
        k("2 Entwickler 1 L", 60, 408, hoehe=15), rechts("11,76", 520, 408, hoehe=15),
        k("Nettosumme", 60, 448, hoehe=15), rechts("33,61", 520, 448, hoehe=15),
        k("zzgl. USt 19 %", 60, 470, hoehe=15), rechts("6,39", 520, 470, hoehe=15),
        k("Rechnungsbetrag", 60, 496, hoehe=18), rechts("90,00", 520, 496, hoehe=18),
    ]


# ————— Was die Deutung in die Felder schreibt —————

def test_zwei_steuersaetze_kommen_als_tabelle_in_die_felder(rw, drogeriebon):
    f = rw.felder_aus_lesung(deuten(drogeriebon, heute=date(2026, 8, 22)))
    assert len(f["steuertabelle"]) == 2
    assert {z["satz"] for z in f["steuertabelle"]} == {7, 19}


def test_zwei_steuersaetze_werden_zwei_buchungszeilen(rw, drogeriebon):
    """Ohne die Tabelle bucht der Export alles auf einen Schlüssel — und die
    Umsatzsteuervoranmeldung weist zu viel Vorsteuer aus."""
    f = rw.felder_aus_lesung(deuten(drogeriebon, heute=date(2026, 8, 22)))
    f["datum"] = "02.04.2024"
    zeilen = extf.buchungszeilen({
        "felder": f, "einschaetzung": {"konto_skr04": "5400"},
        "vlm": {"buchungstext": "Wareneinkauf dm"}})
    assert len(zeilen) == 2
    assert {(z["umsatz"], z["bu"]) for z in zeilen} == {("19,00", "9"), ("85,40", "8")}


def test_ein_satz_bleibt_eine_buchungszeile(rw):
    f = rw.felder_aus_lesung(deuten([
        k("Bäckerei Probe GmbH", 40, 20, hoehe=22),
        k("SUMME", 40, 176, hoehe=18), rechts("1,30", 300, 176, hoehe=18),
        k("Netto", 40, 206, hoehe=13), rechts("1,21", 300, 206, hoehe=13),
        k("MwSt 7,00 %", 40, 224, hoehe=13), rechts("0,09", 300, 224, hoehe=13),
    ], heute=date(2026, 8, 22)))
    f["datum"] = "22.08.2026"
    zeilen = extf.buchungszeilen({
        "felder": f, "einschaetzung": {"konto_skr04": "5400"}, "vlm": {}})
    assert len(zeilen) == 1 and zeilen[0]["bu"] == "8"


def test_ohne_steuerausweis_wird_kein_steuerschluessel_erfunden(rw):
    """Porto trägt keine Umsatzsteuer. 19 % anzunehmen wäre Vorsteuer, die
    es nie gab — und die holt sich das Finanzamt zurück."""
    f = rw.felder_aus_lesung(deuten([
        k("Deutsche Post Filiale", 40, 20, hoehe=22),
        k("Porto Briefmarken", 40, 100, hoehe=14),
        k("Summe", 40, 140), rechts("8,50", 300, 140),
    ], heute=date(2026, 8, 22)))
    assert f["ust_satz"] == 0
    e = rw.einschaetzung(f, None, "Quittung")
    assert e["steuerschluessel"] == "0"


def test_die_proben_stehen_im_review(rw, verlesene_rechnung):
    f = rw.felder_aus_lesung(deuten(verlesene_rechnung, heute=date(2026, 8, 22)))
    assert f["summenprobe_ok"] is False
    namen = {p["name"] for p in f["proben"]}
    assert "Einzelposten" in namen
    assert any(not p["bestanden"] for p in f["proben"])


# ————— Der Hinweis muss die Probe benennen —————

def test_der_hinweis_nennt_die_gescheiterte_probe(rw, verlesene_rechnung):
    """„Summenprobe nicht bestanden" schickt Nina auf die Suche. Der Satz
    muss sagen, welche Zahl nicht passt."""
    f = rw.felder_aus_lesung(deuten(verlesene_rechnung, heute=date(2026, 8, 22)))
    e = rw.einschaetzung(f, None, "Rechnung")
    hinweis = " ".join(e["hinweise"])
    assert "Einzelposten" in hinweis
    assert "33,61" in hinweis


def test_ohne_proben_bleibt_der_alte_hinweis(rw):
    """Ein Stub-Review kennt keine Proben — dann darf der Hinweis nicht
    leer laufen."""
    f = {"ust_satz": 19, "summenprobe_ok": False, "bewirtungssignal": False,
         "offen": []}
    e = rw.einschaetzung(f, None, "unlesbar")
    assert any("prüfen" in h for h in e["hinweise"])
