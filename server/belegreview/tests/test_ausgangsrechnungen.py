"""Ausgangsrechnungen (seit 17.09.2026, Fall nullsiebenelf): Ein Betrieb,
der selbst fakturiert, legt seine Rechnungen als Beleg ab — babu bucht sie
als ERTRAG (8400, Haben, gegen Debitor), nie als Aufwand."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extf  # noqa: E402
import gemma_buchung as gb  # noqa: E402
import kontierung as kt  # noqa: E402
import monatsabschluss as ma  # noqa: E402


def test_kategorie_umsatzerloese_steht_im_katalog():
    kat = kt.KATEGORIEN["umsatzerloese"]
    assert kat.konto("SKR04") == "4400"   # Erlöse 19 % USt (SKR04)
    assert kat.konto("SKR03") == "8400"   # Erlöse (SKR03)


def test_dokumentklasse_ausgangsrechnung_ist_erlaubt():
    assert "ausgangsrechnung" in gb.DOKUMENTKLASSEN
    # Eine ungueltige Klasse wird zur Rueckfrage — die neuen Optionen dort
    # pruefen wir nicht Wort fuer Wort, nur dass gebucht weitergeht.
    r = gb.buchung_pruefen({"status": "gebucht", "kategorie": "umsatzerloese",
                            "dokumentklasse": "ausgangsrechnung",
                            "betrag": 535.50, "ust_satz": 19})
    assert r["status"] == "gebucht"
    assert r["buchung"]["dokumentklasse"] == "ausgangsrechnung"


def test_buchung_traegt_kunde_nicht_lieferant():
    """Eine Ausgangsrechnung nennt den EMPFAENGER als kunde."""
    r = gb.buchung_pruefen({"status": "gebucht", "kategorie": "umsatzerloese",
                            "dokumentklasse": "ausgangsrechnung",
                            "kunde": "Jana Allgaier", "betrag": 535.50,
                            "ust_satz": 19, "datum": "2026-09-03",
                            "buchungstext": "Stuhlmiete September"})
    assert r["status"] == "gebucht"
    b = r["buchung"]
    assert b["kategorie"] == "umsatzerloese"
    assert b["konto"] == "4400"
    assert b["kunde"] == "Jana Allgaier"
    # Eingangsbelege tragen kein kunde-Feld
    r2 = gb.buchung_pruefen({"status": "gebucht", "kategorie": "verbrauchsmaterial",
                             "dokumentklasse": "beleg", "kunde": "x",
                             "betrag": 10, "ust_satz": 7})
    assert r2["buchung"].get("kunde") is None


def _review(brutto, satz=19, klasse="ausgangsrechnung", zahlungsart=None):
    v = {"dokumentklasse": klasse, "kategorie": "umsatzerloese",
         "betrag": brutto, "ust_satz": satz, "datum": "2026-09-03",
         "buchungstext": "Stuhlmiete", "betrag_eur": brutto}
    f = {"brutto": brutto, "datum": "2026-09-03", "lieferant": None}
    e = {"konto": "4400", "kontenrahmen": "SKR04"}
    review = {"vlm": v, "felder": f, "einschaetzung": e}
    if zahlungsart:
        v["zahlungsart"] = zahlungsart
    return review


def test_datev_zeile_erloes_im_haben_gegen_debitor():
    zeilen = extf.buchungszeilen(_review(535.50))
    assert len(zeilen) == 1
    z = zeilen[0]
    assert z["konto"] == "4400"
    assert z["gegenkonto"] == extf.DEBITOR["SKR04"]      # 12000 Debitoren
    assert z["sh"] == "H"                                 # Ertrag im Haben
    assert z["umsatz"] == "535,50"


def test_bar_gezahlter_erloes_geht_gegen_die_kasse():
    zeilen = extf.buchungszeilen(_review(535.50, zahlungsart="bar"))
    assert zeilen[0]["gegenkonto"] == extf.KASSE
    assert zeilen[0]["sh"] == "H"


def test_gutschrift_an_kunden_dreht_zurueck():
    review = _review(-535.50)
    zeilen = extf.buchungszeilen(review)
    assert zeilen[0]["sh"] == "S"      # Storno unseres Erlöses: zurück im Soll
    assert zeilen[0]["umsatz"] == "535,50"


def test_eingangsbeleg_bleibt_unberuehrt():
    v = {"dokumentklasse": "beleg", "kategorie": "verbrauchsmaterial",
         "betrag": 10, "betrag_eur": 10, "ust_satz": 7,
         "datum": "2026-09-03", "buchungstext": "Farbe", "lieferant": "delilà"}
    zeilen = extf.buchungszeilen({"vlm": v, "felder": {"brutto": 10,
                                  "datum": "2026-09-03", "lieferant": "delilà"},
                                  "einschaetzung": {"konto": "6850"}})
    assert zeilen[0]["sh"] == "S"
    assert zeilen[0]["gegenkonto"] == extf.GEGENKONTO


def test_erloese_monat_zaehlt_beleg_erloese_und_weist_sie_aus():
    e = ma.erloese_monat([], monat="2026-09", beleg_erloese=[
        {"brutto": 535.50, "ust_satz": 19, "datum": "2026-09-03"},
        {"brutto": 100.00, "ust_satz": 7, "datum": "2026-09-05"},
        {"brutto": 50.00, "ust_satz": 19, "datum": "2026-08-31"}])  # anderer Monat
    assert e["aus_belegen"] == 635.50
    assert e["brutto_19"] == 535.50
    assert e["brutto_7"] == 100.00
    assert e["brutto_gesamt"] == 635.50


def test_ohne_beleg_erloese_zaehlt_nichts_doppelt():
    e = ma.erloese_monat([], monat="2026-09")
    assert e["aus_belegen"] == 0
