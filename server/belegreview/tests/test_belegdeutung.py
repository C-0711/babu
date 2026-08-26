"""Die Deutung an echten Belegen prüfen — besonders an denen, die schiefgingen.

Die drei Belege am Anfang dieser Datei sind keine erfundenen Beispiele: es
sind die, an denen babu im August 2026 sichtbar falsch gelesen hat. Sie
stehen hier nachgebaut, wie die Texterkennung sie geliefert hat — mit
Position und Schriftgröße, denn genau die entscheiden.
"""
from datetime import date

import pytest

from belegdeutung import (Kasten, betraege_in_zeile, betragsspalte, deuten,
                          zeilen_bilden)


def k(text, x0, y0, breite=None, hoehe=20, konf=0.97):
    """Ein Kasten, kurz geschrieben — Breite schätzt sich aus der Textlänge."""
    breite = breite if breite is not None else len(text) * hoehe * 0.55
    return Kasten(text, konf, x0, y0, x0 + breite, y0 + hoehe)


def rechts(text, rechte_kante, y, hoehe=20, konf=0.97):
    """Ein rechtsbündiger Kasten — so stehen Beträge auf einer Rechnung."""
    breite = len(text) * hoehe * 0.55
    return Kasten(text, konf, rechte_kante - breite, y, rechte_kante, y + hoehe)


# ── Die drei Belege, an denen es schiefging ──────────────────────────────────

@pytest.fixture
def parkquittung():
    """Der Beleg, auf dem „19,00 %“ als Betrag gewann statt 3,50 €."""
    return [
        k("Parkhaus am Markt", 60, 20, hoehe=26),
        k("Betreiber: PBW GmbH", 60, 56, hoehe=16),
        k("Einfahrt  22.08.2026 09:14", 60, 96, hoehe=16),
        k("Ausfahrt  22.08.2026 11:02", 60, 118, hoehe=16),
        k("Parkdauer 1:48 h", 60, 140, hoehe=16),
        k("Beleg-Nr. 20260822-0417", 60, 176, hoehe=16),
        k("Zu zahlen", 60, 214, hoehe=20),
        rechts("3,50 EUR", 340, 214, hoehe=20),
        k("darin MwSt 19,00 %", 60, 248, hoehe=16),
        rechts("0,56", 340, 248, hoehe=16),
        k("Netto", 60, 270, hoehe=16),
        rechts("2,94", 340, 270, hoehe=16),
    ]


@pytest.fixture
def rechnung_mit_fusszeile():
    """Die Rechnung, auf der das Stammkapital 43.783,86 € gewann statt 40,00 €
    — und als Lieferant „Rechnungsadresse“ stand."""
    return [
        k("FRISEURBEDARF SÜDWEST GMBH", 60, 30, hoehe=30),
        k("Industriestraße 14", 60, 74, hoehe=15),
        k("70565 Stuttgart", 60, 94, hoehe=15),

        k("Rechnungsadresse", 60, 150, hoehe=15),
        k("Salon SupremeBeauty", 60, 172, hoehe=15),
        k("Nina Weingärtle", 60, 192, hoehe=15),
        k("Hauptstraße 3", 60, 212, hoehe=15),
        k("70173 Stuttgart", 60, 232, hoehe=15),

        k("Rechnungsnummer 2026-4711", 60, 290, hoehe=16),
        k("Rechnungsdatum 14.08.2026", 60, 312, hoehe=16),

        k("Pos  Artikel", 60, 360, hoehe=15),
        rechts("Betrag", 520, 360, hoehe=15),
        k("1  Coloration 60 ml", 60, 386, hoehe=15),
        rechts("21,85", 520, 386, hoehe=15),
        k("2  Entwickler 1 L", 60, 408, hoehe=15),
        rechts("11,76", 520, 408, hoehe=15),
        k("Nettosumme", 60, 448, hoehe=15),
        rechts("33,61", 520, 448, hoehe=15),
        k("zzgl. USt 19 %", 60, 470, hoehe=15),
        rechts("6,39", 520, 470, hoehe=15),
        k("Rechnungsbetrag", 60, 496, hoehe=18),
        rechts("40,00", 520, 496, hoehe=18),

        k("Friseurbedarf Südwest GmbH · Amtsgericht Stuttgart HRB 12345", 60, 700, hoehe=12),
        k("Stammkapital 43.783,86 EUR · Geschäftsführer: T. Vogt", 60, 716, hoehe=12),
        k("IBAN DE02 1203 0000 0000 2020 51 · USt-IdNr. DE123456789", 60, 732, hoehe=12),
    ]


@pytest.fixture
def baeckerbon():
    """Der Bon, auf dem „7,00 %“ als 19 % gelesen wurde."""
    return [
        k("Bäckerei Probe GmbH", 40, 20, hoehe=22),
        k("Königstr. 1, 70173 Stuttgart", 40, 50, hoehe=13),
        k("Bon-Nr. 4711", 40, 84, hoehe=14),
        k("22.08.2026 07:41", 40, 104, hoehe=14),
        k("1 x Brötchen", 40, 140, hoehe=14),
        rechts("1,30", 300, 140, hoehe=14),
        k("SUMME", 40, 176, hoehe=18),
        rechts("1,30", 300, 176, hoehe=18),
        k("Netto", 40, 206, hoehe=13),
        rechts("1,21", 300, 206, hoehe=13),
        k("MwSt 7,00 %", 40, 224, hoehe=13),
        rechts("0,09", 300, 224, hoehe=13),
    ]


# ── Genau die Fehler von damals ──────────────────────────────────────────────

def test_prozentsatz_ist_kein_betrag(parkquittung):
    """19,00 % darf nie der Rechnungsbetrag sein."""
    l = deuten(parkquittung, heute=date(2026, 8, 22))
    assert l.wert("brutto") == 3.50


def test_parkquittung_vollstaendig(parkquittung):
    l = deuten(parkquittung, heute=date(2026, 8, 22))
    assert l.wert("brutto") == 3.50
    assert l.wert("ust") == 0.56
    assert l.wert("netto") == 2.94
    assert l.wert("ust_satz") == 19
    assert l.wert("summenprobe_ok") is True
    assert l.wert("datum") == "2026-08-22"
    assert l.wert("beleg_nr") == "20260822-0417"


def test_stammkapital_gewinnt_nicht(rechnung_mit_fusszeile):
    """Was in der Fußzeile steht, ist kein Rechnungsbetrag."""
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    assert l.wert("brutto") == 40.00


def test_lieferant_ist_nicht_rechnungsadresse(rechnung_mit_fusszeile):
    """Der Aussteller steht im Kopf, nicht in der Anschrift der Kundin."""
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    assert l.wert("lieferant") == "FRISEURBEDARF SÜDWEST GMBH"


def test_kundin_wird_nicht_zum_lieferanten(rechnung_mit_fusszeile):
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    name = (l.wert("lieferant") or "").lower()
    assert "nina" not in name and "supremebeauty" not in name


def test_rechnung_vollstaendig(rechnung_mit_fusszeile):
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    assert l.wert("beleg_nr") == "2026-4711"
    assert l.wert("datum") == "2026-08-14"
    assert l.wert("netto") == 33.61
    assert l.wert("ust") == 6.39
    assert l.wert("ust_satz") == 19
    assert l.wert("summenprobe_ok") is True


def test_sieben_prozent_mit_nachkommastelle(baeckerbon):
    """„7,00 %“ ist 7 %, nicht 19 % — der Satz wird gerechnet, nicht gesucht."""
    l = deuten(baeckerbon, heute=date(2026, 8, 22))
    assert l.wert("brutto") == 1.30
    assert l.wert("ust_satz") == 7
    assert l.wert("ust") == 0.09
    assert l.wert("netto") == 1.21


def test_bon_nummer_und_datum(baeckerbon):
    l = deuten(baeckerbon, heute=date(2026, 8, 22))
    assert l.wert("beleg_nr") == "4711"
    assert l.wert("datum") == "2026-08-22"


# ── Zeilenbildung ────────────────────────────────────────────────────────────

def test_zeilen_aus_kaesten():
    """Was auf gleicher Höhe steht, wird eine Zeile — links nach rechts."""
    z = zeilen_bilden([k("Betrag", 400, 100), k("MwSt", 60, 100),
                       k("Summe", 60, 140)])
    assert len(z) == 2
    assert z[0].text == "MwSt Betrag"
    assert z[1].text == "Summe"


def test_leicht_versetzte_kaesten_bleiben_eine_zeile():
    z = zeilen_bilden([k("Summe", 60, 100, hoehe=20), k("12,00", 400, 104, hoehe=20)])
    assert len(z) == 1


def test_getrennte_zeilen_bleiben_getrennt():
    z = zeilen_bilden([k("oben", 60, 100, hoehe=20), k("unten", 60, 130, hoehe=20)])
    assert len(z) == 2


def test_zeilenkonfidenz_ist_die_schlechteste():
    z = zeilen_bilden([k("gut", 60, 100, konf=0.99), k("schlecht", 300, 100, konf=0.42)])
    assert z[0].konf == pytest.approx(0.42)


# ── Beträge ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,erwartet", [
    ("12,50", [12.50]),
    ("1.234,56", [1234.56]),
    ("1234.56", [1234.56]),
    ("Summe 40,00 EUR", [40.00]),
    ("19,00 %", []),
    ("19,00%", []),
    ("MwSt 7,00 % 0,09", [0.09]),
    ("22.08.2026", []),
    ("22.08.2026 07:41", []),
    ("12.30 Uhr", []),
    ("Menge 2 x 3,25", [3.25]),
    ("kein Geld hier", []),
    ("33,61 6,39 40,00", [33.61, 6.39, 40.00]),
])
def test_betraege_erkennen(text, erwartet):
    z = zeilen_bilden([k(text, 0, 0)])
    assert [b.wert for b in betraege_in_zeile(z[0])] == erwartet


def test_betragsspalte_wird_erkannt():
    kaesten = [rechts(t, 520, y) for t, y in
               [("21,85", 100), ("11,76", 130), ("33,61", 160), ("40,00", 190)]]
    kaesten.append(k("Fließtext mit 5,00 mittendrin", 60, 220))
    z = zeilen_bilden(kaesten)
    alle = [b for zl in z for b in betraege_in_zeile(zl)]
    spalte = betragsspalte(alle, blattbreite=600)
    assert spalte is not None and spalte > 400


def test_zu_wenige_betraege_ergeben_keine_spalte():
    """Ein Kassenbon hat keine Spalte — dann wird auch keine behauptet."""
    z = zeilen_bilden([rechts("1,30", 300, 100), rechts("0,09", 300, 130)])
    alle = [b for zl in z for b in betraege_in_zeile(zl)]
    assert betragsspalte(alle, blattbreite=340) is None


# ── Die Summe ────────────────────────────────────────────────────────────────

def test_zwischensumme_gewinnt_nicht():
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Zwischensumme", 40, 100), rechts("18,00", 300, 100),
        k("Rabatt", 40, 130), rechts("3,00", 300, 130),
        k("Gesamtbetrag", 40, 160), rechts("15,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") == 15.00


def test_rueckgeld_gewinnt_nicht():
    """Kassenbons drucken „Gegeben“ und „Rückgeld“ unter die Summe."""
    l = deuten([
        k("Kiosk Meier", 40, 20, hoehe=22),
        k("SUMME", 40, 100), rechts("7,40", 300, 100),
        k("Gegeben", 40, 130), rechts("10,00", 300, 130),
        k("Rückgeld", 40, 160), rechts("2,60", 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") == 7.40


def test_unterste_summenzeile_gewinnt():
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Summe Posten", 40, 100), rechts("50,00", 300, 100),
        k("Summe", 40, 200), rechts("59,50", 300, 200),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") == 59.50


def test_gesamtbetrag_brutto_ist_eine_summe():
    """„brutto“ steht auf der Verbotsliste — in „Gesamtbetrag brutto“ nicht."""
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Gesamtbetrag brutto", 40, 160), rechts("15,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") == 15.00


def test_offener_betrag_null_gewinnt_nicht():
    """Der Delila-Fall vom 26.08.2026: die Rechnung war bezahlt, unten stand
    „Offener Betrag 0,00 €" — und die Null gewann als unterste Betragszeile
    gegen den Gesamtbetrag darüber."""
    l = deuten([
        k("delilà Hair Extensions", 40, 20, hoehe=22),
        k("Gesamtbetrag netto", 40, 160), rechts("687,71", 300, 160),
        k("zzgl. MwSt (19,00 %)", 40, 190), rechts("130,67", 300, 190),
        k("Gesamtbetrag", 40, 220), rechts("818,38", 300, 220),
        k("Bereits gezahlt", 40, 250), rechts("818,38", 300, 250),
        k("Offener Betrag", 40, 280), rechts("0,00 €", 300, 280),
    ], heute=date(2026, 8, 26))
    assert l.wert("brutto") == 818.38


def test_offener_restbetrag_gewinnt_nicht():
    """Auch ein Teilrest ist der Rest, nicht die Summe."""
    l = deuten([
        k("delilà Hair Extensions", 40, 20, hoehe=22),
        k("Gesamtbetrag", 40, 160), rechts("818,38", 300, 160),
        k("Offener Betrag", 40, 220), rechts("50,00", 300, 220),
    ], heute=date(2026, 8, 26))
    assert l.wert("brutto") == 818.38


def test_lauter_nullen_ergeben_keinen_betrag():
    """Steht nirgends mehr als 0,00, ist nichts gelesen — None statt 0,
    damit die Gegenprobe die Lücke füllen darf."""
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Noch zu zahlen", 40, 160), rechts("0,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") is None


def test_ohne_summenwort_gewinnt_der_groesste_ueber_der_fusszeile():
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        rechts("12,00", 300, 100), rechts("18,00", 300, 130),
        rechts("30,00", 300, 160),
        k("Stammkapital 500.000,00 EUR", 40, 400, hoehe=11),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") == 30.00


# ── Die Steuer ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("satz,netto,ust,brutto", [
    (19, 33.61, 6.39, 40.00),
    (7, 1.21, 0.09, 1.30),
    (19, 100.00, 19.00, 119.00),
    (7, 100.00, 7.00, 107.00),
])
def test_satz_wird_aus_netto_und_steuer_gerechnet(satz, netto, ust, brutto):
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Netto", 40, 100), rechts(f"{netto:.2f}".replace(".", ","), 300, 100),
        k("MwSt", 40, 130), rechts(f"{ust:.2f}".replace(".", ","), 300, 130),
        k("Gesamtbetrag", 40, 160), rechts(f"{brutto:.2f}".replace(".", ","), 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == satz
    assert l.wert("summenprobe_ok") is True


def test_steuertabelle_mit_drei_spalten():
    """„A 19% 33,61 6,39 40,00“ — Netto, Steuer, Brutto in einer Zeile."""
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Gesamtbetrag", 40, 100), rechts("40,00", 500, 100),
        k("A 19%", 40, 160), k("33,61", 200, 160), k("6,39", 300, 160),
        k("40,00", 400, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == 19
    assert l.wert("ust") == 6.39
    assert l.wert("netto") == 33.61


def test_nur_brutto_und_satz_wird_herausgerechnet():
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Gesamtbetrag", 40, 100), rechts("119,00", 300, 100),
        k("inkl. 19 % MwSt", 40, 130),
    ], heute=date(2026, 8, 22))
    assert l.wert("netto") == 100.00
    assert l.wert("ust") == 19.00
    assert l.wert("summenprobe_ok") is True


def test_unstimmige_aufteilung_wird_verworfen_statt_gebucht():
    """Lieber kein Netto als ein falsches — Vorsteuer muss stimmen."""
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Netto", 40, 100), rechts("50,00", 300, 100),
        k("MwSt", 40, 130), rechts("9,50", 300, 130),
        k("Gesamtbetrag", 40, 160), rechts("40,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("brutto") == 40.00
    assert l.wert("summenprobe_ok") is False
    assert any("prüfen" in o for o in l.offen)


def test_unsinniger_satz_wird_nicht_uebernommen():
    """13 % gibt es nicht — dann bleibt der Satz aus der Prozentangabe."""
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("MwSt 19 %", 40, 130), rechts("13,00", 300, 130),
        k("Gesamtbetrag", 40, 160), rechts("113,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == 19


# ── Lieferant ────────────────────────────────────────────────────────────────

def test_rechtsform_schlaegt_schriftgroesse():
    l = deuten([
        k("QUITTUNG", 40, 10, hoehe=40),
        k("Mustermann Handels GmbH", 40, 60, hoehe=16),
        k("Summe", 40, 200), rechts("10,00", 300, 200),
    ], heute=date(2026, 8, 22))
    assert l.wert("lieferant") == "Mustermann Handels GmbH"


def test_ohne_rechtsform_gewinnt_die_groesste_schrift():
    l = deuten([
        k("Kassenbon", 40, 6, hoehe=12),
        k("Blumen Hofmann", 40, 26, hoehe=28),
        k("Marktplatz 2", 40, 64, hoehe=12),
        k("Summe", 40, 200), rechts("10,00", 300, 200),
    ], heute=date(2026, 8, 22))
    assert l.wert("lieferant") == "Blumen Hofmann"


def test_anschrift_wird_nicht_zum_lieferanten():
    l = deuten([
        k("Hauptstraße 12", 40, 20, hoehe=24),
        k("70173 Stuttgart", 40, 50, hoehe=24),
        k("Kiosk Sonnenschein", 40, 80, hoehe=20),
        k("Summe", 40, 200), rechts("10,00", 300, 200),
    ], heute=date(2026, 8, 22))
    assert l.wert("lieferant") == "Kiosk Sonnenschein"


def test_kein_lieferant_ist_besser_als_ein_falscher():
    l = deuten([
        k("Rechnung", 40, 20, hoehe=24),
        k("12345678", 40, 50, hoehe=20),
        k("Summe", 40, 200), rechts("10,00", 300, 200),
    ], heute=date(2026, 8, 22))
    assert l.wert("lieferant") is None
    assert any("ausgestellt" in o for o in l.offen)


# ── Datum ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,erwartet", [
    ("Rechnungsdatum 14.08.2026", "2026-08-14"),
    ("Datum: 1.9.2026", "2026-09-01"),
    ("Belegdatum 2026-08-14", "2026-08-14"),
    ("Datum 14. August 2026", "2026-08-14"),
    ("vom 14.08.26", "2026-08-14"),
])
def test_datumsformate(text, erwartet):
    l = deuten([k("Laden GmbH", 40, 20, hoehe=22), k(text, 40, 100)],
               heute=date(2026, 9, 30))
    assert l.wert("datum") == erwartet


def test_datum_in_der_zukunft_wird_verworfen():
    l = deuten([k("Laden GmbH", 40, 20, hoehe=22),
                k("Datum 14.08.2027", 40, 100)], heute=date(2026, 8, 22))
    assert l.wert("datum") is None


def test_benanntes_datum_schlaegt_beliebiges():
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Leistungszeitraum 01.07.2026", 40, 80),
        k("Rechnungsdatum 14.08.2026", 40, 110),
    ], heute=date(2026, 8, 22))
    assert l.wert("datum") == "2026-08-14"


# ── Belegnummer ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,erwartet", [
    ("Rechnungsnummer 2026-4711", "2026-4711"),
    ("Beleg-Nr. 20260822-0417", "20260822-0417"),
    ("Bon-Nr. 4711", "4711"),
    ("Rechnung Nr. RE-2026/0815", "RE-2026/0815"),
])
def test_nummernformate(text, erwartet):
    l = deuten([k("Laden GmbH", 40, 20, hoehe=22), k(text, 40, 100)],
               heute=date(2026, 8, 22))
    assert l.wert("beleg_nr") == erwartet


def test_kundennummer_ist_keine_belegnummer():
    l = deuten([k("Laden GmbH", 40, 20, hoehe=22),
                k("Kundennummer 88231", 40, 100)], heute=date(2026, 8, 22))
    assert l.wert("beleg_nr") is None


def test_steuernummer_ist_keine_belegnummer():
    l = deuten([k("Laden GmbH", 40, 20, hoehe=22),
                k("Steuernummer 93815/12345", 40, 100)], heute=date(2026, 8, 22))
    assert l.wert("beleg_nr") is None


# ── Herkunft: jede Angabe muss nachweisbar sein ──────────────────────────────

def test_jede_deutung_nennt_ihre_zeile(rechnung_mit_fusszeile):
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    for name in ("lieferant", "beleg_nr", "datum", "brutto"):
        d = l.felder[name]
        assert d.wert is not None
        assert d.zeile_nr is not None, f"{name} nennt keine Zeile"
        assert d.regel, f"{name} nennt keine Regel"
        assert d.zeilentext, f"{name} nennt keinen Zeilentext"


def test_zeilentext_stammt_wirklich_aus_der_zeile(rechnung_mit_fusszeile):
    """Die Herkunftsangabe muss stimmen, sonst ist das Protokoll wertlos."""
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    for d in l.felder.values():
        if d.zeile_nr is not None:
            assert l.zeilen[d.zeile_nr].text == d.zeilentext


# ── Randfälle ────────────────────────────────────────────────────────────────

def test_leeres_bild():
    l = deuten([])
    assert l.wert("brutto") is None
    assert l.offen


def test_unsichere_erkennung_wird_gemeldet():
    l = deuten([k("Laden GmbH", 40, 20, hoehe=22, konf=0.3),
                k("Summe", 40, 100, konf=0.3), rechts("10,00", 300, 100, konf=0.3)],
               heute=date(2026, 8, 22))
    assert any("Foto" in o for o in l.offen)


def test_deuten_veraendert_die_eingabe_nicht(baeckerbon):
    vorher = list(baeckerbon)
    deuten(baeckerbon, heute=date(2026, 8, 22))
    assert baeckerbon == vorher


def test_die_spaltenangabe_bleibt_im_blatt():
    """„rechte Kante bei 109 % der Blattbreite“ liest sich wie ein Fehler —
    und war einer: die Spalte ist eine Position, die Breite eine Differenz."""
    kaesten = [k("Laden GmbH", 60, 20, hoehe=22)]
    kaesten += [rechts(t, 690, y) for t, y in
                [("21,85", 100), ("11,76", 130), ("33,61", 160)]]
    kaesten += [k("Rechnungsbetrag", 60, 190), rechts("40,00", 690, 190)]
    l = deuten(kaesten, heute=date(2026, 8, 22))
    spalten = [n for n in l.notizen if "Spalte" in n]
    assert spalten, "keine Spalte erkannt"
    prozent = int(spalten[0].split("bei ")[1].split("%")[0])
    assert 0 <= prozent <= 100, spalten[0]


@pytest.mark.parametrize("roh, soll", [
    ("Blumen Hofmann e.K.", "Blumen Hofmann e.K."),
    ("Friseur Weingärtle e.Kfr.", "Friseur Weingärtle e.Kfr."),
    ("Bürobedarf Müller GmbH.", "Bürobedarf Müller GmbH"),
    ("Kiosk Sonnenschein,", "Kiosk Sonnenschein"),
    ("— Laden GmbH —", "Laden GmbH"),
    ("Muster GmbH & Co. KG", "Muster GmbH & Co. KG"),
])
def test_der_punkt_einer_rechtsform_bleibt_stehen(roh, soll):
    """„e.K." ist eine Rechtsform, kein Satzende. Auf einer Rechnung ist der
    fehlende Punkt ein Zeichen zu wenig am Firmennamen."""
    from belegdeutung import _saubern
    assert _saubern(roh) == soll


# ── Die Rechenproben: der Beleg prüft sich selbst ────────────────────────────
#
# Nina, 22.08.2026: „Manchmal steht ein völlig falscher Endbetrag da." Das
# Tückische daran ist, dass niemand es merkt: die Zahl sieht aus wie ein
# Betrag, sie steht an der richtigen Stelle, sie ist plausibel. Auffliegen
# kann sie nur am Beleg selbst — die Posten müssen die Summe ergeben, Netto
# und Steuer den Bruttobetrag, die Steuer den Satz, Gegeben minus Rückgeld
# das, was zu zahlen war. Geht eine dieser Proben nicht auf, ist eine Zahl
# falsch gelesen, und dann wird gefragt statt gebucht.


def probe(lesung, name):
    for p in lesung.proben:
        if p.name == name:
            return p
    return None


@pytest.fixture
def rechnung_mit_verlesener_summe(rechnung_mit_fusszeile):
    """Dieselbe Rechnung — nur dass aus „40,00“ beim Lesen „90,00“ wurde.

    Das ist Ninas Fall in Reinform: der Betrag steht in der Summenzeile, er
    ist plausibel, und Netto und Steuer lassen sich aus ihm zurückrechnen.
    Nur die Positionen darüber wissen es besser.
    """
    return [x for x in rechnung_mit_fusszeile if x.text != "40,00"] + [
        rechts("90,00", 520, 496, hoehe=18)]


def test_verlesene_summe_faellt_durch_die_einzelposten(rechnung_mit_verlesener_summe):
    l = deuten(rechnung_mit_verlesener_summe, heute=date(2026, 8, 22))
    assert l.wert("brutto") == 90.00          # so steht es (verlesen) auf dem Blatt
    assert l.wert("summenprobe_ok") is False
    assert probe(l, "Einzelposten").bestanden is False
    assert any("Posten" in o for o in l.offen), l.offen


def test_einzelposten_die_aufgehen_bestehen_die_probe(rechnung_mit_fusszeile):
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    assert probe(l, "Einzelposten").bestanden is True
    assert l.wert("summenprobe_ok") is True


def test_ein_cent_zu_wenig_ist_ein_lesefehler():
    """Posten addieren sich ohne Rundung — ein Cent Differenz ist kein Rest."""
    l = deuten([
        k("Friseurbedarf Südwest GmbH", 60, 30, hoehe=30),
        k("1 Coloration 60 ml", 60, 386, hoehe=15), rechts("21,85", 520, 386, hoehe=15),
        k("2 Entwickler 1 L", 60, 408, hoehe=15), rechts("11,75", 520, 408, hoehe=15),
        k("Nettosumme", 60, 448, hoehe=15), rechts("33,61", 520, 448, hoehe=15),
        k("zzgl. USt 19 %", 60, 470, hoehe=15), rechts("6,39", 520, 470, hoehe=15),
        k("Rechnungsbetrag", 60, 496, hoehe=18), rechts("40,00", 520, 496, hoehe=18),
    ], heute=date(2026, 8, 22))
    assert probe(l, "Einzelposten").bestanden is False
    assert l.wert("summenprobe_ok") is False


def test_ohne_erkennbare_posten_wird_keine_probe_behauptet(baeckerbon):
    """Was sich nicht sauber addieren lässt, darf auch nicht durchfallen."""
    l = deuten([x for x in baeckerbon if x.text not in ("1 x Brötchen", "1,30")],
               heute=date(2026, 8, 22))
    assert probe(l, "Einzelposten") is None


def test_bargeld_geht_auf():
    l = deuten([
        k("Kiosk Meier", 40, 20, hoehe=22),
        k("SUMME", 40, 100), rechts("44,50", 300, 100),
        k("Gegeben", 40, 130), rechts("50,00", 300, 130),
        k("Rückgeld", 40, 160), rechts("5,50", 300, 160),
    ], heute=date(2026, 8, 22))
    assert probe(l, "Bargeld").bestanden is True
    assert l.wert("summenprobe_ok") is True


def test_bargeld_das_nicht_aufgeht_meldet_sich():
    """Wer 50 gibt und 5,50 zurückbekommt, hat nicht 54,50 bezahlt."""
    l = deuten([
        k("Kiosk Meier", 40, 20, hoehe=22),
        k("SUMME", 40, 100), rechts("54,50", 300, 100),
        k("Gegeben", 40, 130), rechts("50,00", 300, 130),
        k("Rückgeld", 40, 160), rechts("5,50", 300, 160),
    ], heute=date(2026, 8, 22))
    assert probe(l, "Bargeld").bestanden is False
    assert l.wert("summenprobe_ok") is False
    assert any("Rückgeld" in o for o in l.offen), l.offen


def test_trinkgeld_ist_kein_lesefehler():
    """Mehr gegeben als zurückbekommen heißt Trinkgeld, nicht falsch gelesen."""
    l = deuten([
        k("Gasthaus Sonne", 40, 20, hoehe=22),
        k("SUMME", 40, 100), rechts("44,50", 300, 100),
        k("Gegeben", 40, 130), rechts("50,00", 300, 130),
        k("Rückgeld", 40, 160), rechts("3,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert probe(l, "Bargeld") is None
    assert any("Trinkgeld" in n for n in l.notizen), l.notizen
    assert l.wert("summenprobe_ok") is True


def test_der_steuersatz_muss_zu_netto_und_steuer_passen():
    """13 % von 100 gibt es nicht — dann ist eine der Zahlen falsch gelesen."""
    l = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Netto", 40, 100), rechts("100,00", 300, 100),
        k("MwSt 19 %", 40, 130), rechts("13,00", 300, 130),
        k("Gesamtbetrag", 40, 160), rechts("113,00", 300, 160),
    ], heute=date(2026, 8, 22))
    assert probe(l, "Steuersatz").bestanden is False
    assert l.wert("summenprobe_ok") is False
    assert any("Steuer" in o for o in l.offen), l.offen


def test_die_gescheiterte_probe_wird_benannt(rechnung_mit_verlesener_summe):
    """„Summenprobe nicht bestanden“ hilft niemandem — welche denn?"""
    l = deuten(rechnung_mit_verlesener_summe, heute=date(2026, 8, 22))
    d = l.felder["summenprobe_ok"]
    assert "Einzelposten" in d.regel, d.regel
    gescheitert = [p for p in l.proben if not p.bestanden]
    assert gescheitert and all("33,61" in p.erklaerung for p in gescheitert)


def test_bestandene_proben_stehen_im_protokoll(rechnung_mit_fusszeile):
    """Auch eine bestandene Probe gehört sichtbar gemacht — sonst glaubt man
    der Zahl nur, statt sie nachlesen zu können."""
    l = deuten(rechnung_mit_fusszeile, heute=date(2026, 8, 22))
    assert any("Probe" in n for n in l.notizen), l.notizen


# ── Steuersätze: 7 % und 0 % kommen im Salon wirklich vor ────────────────────
#
# Die Lesung nahm 19 % als Normalfall an. Im Salon stimmt das oft nicht:
# Zeitschriften fürs Wartezimmer sind 7 %, Porto und Versicherung 0 %, und
# was ein Kleinunternehmer schreibt, trägt gar keine Steuer. Wer 19 %
# annimmt, wo nichts steht, zieht Vorsteuer, die es nie gab.


def test_ohne_steuerausweis_werden_keine_neunzehn_prozent_erfunden():
    l = deuten([
        k("Kosmetikstudio Elke", 40, 20, hoehe=22),
        k("Gemäß §19 UStG keine Umsatzsteuer ausgewiesen", 40, 100, hoehe=13),
        k("Gesamt", 40, 140), rechts("25,00", 300, 140),
    ], heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == 0
    assert l.wert("ust") == 0.0
    assert l.wert("netto") == 25.00
    assert any("19" in n and "UStG" in n for n in l.notizen), l.notizen


def test_stiller_beleg_bekommt_null_prozent_statt_neunzehn():
    """Steht keine Umsatzsteuer drauf, ist das eine Aussage — keine Lücke."""
    l = deuten([
        k("Deutsche Post Filiale", 40, 20, hoehe=22),
        k("Porto Briefmarken", 40, 100, hoehe=14),
        k("Summe", 40, 140), rechts("8,50", 300, 140),
    ], heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == 0
    assert l.wert("ust") == 0.0
    assert l.wert("netto") == 8.50
    assert not any("Umsatzsteuer" in o for o in l.offen), l.offen


def test_hoher_betrag_ohne_steuerausweis_wird_zur_rueckfrage():
    """Über der Kleinbetragsgrenze muss eine Rechnung die Steuer ausweisen —
    fehlt sie dort, ist entweder die Lesung unvollständig oder der Beleg."""
    l = deuten([
        k("Möbelhaus Bahn", 40, 20, hoehe=22),
        k("Empfangstresen", 40, 100, hoehe=14),
        k("Summe", 40, 140), rechts("480,00", 300, 140),
    ], heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == 0
    assert any("Umsatzsteuer" in o for o in l.offen), l.offen


def test_zwei_steuersaetze_bleiben_getrennt():
    """Ein Drogeriebon trägt 19 % und 7 % nebeneinander. Wer daraus einen
    Satz macht, meldet eine falsche Voranmeldung."""
    l = deuten([
        k("REWE Markt", 40, 20, hoehe=22),
        k("A 19%", 40, 160), k("15,97", 200, 160), k("3,03", 300, 160),
        k("19,00", 400, 160),
        k("B 7%", 40, 190), k("79,81", 200, 190), k("5,59", 300, 190),
        k("85,40", 400, 190),
        k("SUMME", 40, 230), k("104,40", 400, 230),
    ], heute=date(2026, 8, 22))
    assert len(l.steuerpositionen) == 2
    assert {p.satz for p in l.steuerpositionen} == {7, 19}
    assert l.wert("brutto") == 104.40
    assert l.wert("netto") == 95.78
    assert l.wert("ust") == 8.62
    assert l.wert("summenprobe_ok") is True


def test_ein_satz_bleibt_ein_satz(baeckerbon):
    """Der Normalfall darf durch die Mehrsatz-Logik nicht schlechter werden."""
    l = deuten(baeckerbon, heute=date(2026, 8, 22))
    assert l.wert("ust_satz") == 7
    assert l.wert("summenprobe_ok") is True


def test_steuertabelle_in_der_reihenfolge_des_bons():
    """Der Weingärtle-Bon druckt USt, Brutto, Netto — in dieser Reihenfolge.

    Wer nur „Netto Steuer Brutto" erwartet, findet die Zeile nie. Welche
    Spalte welche ist, sagt am Ende nicht die Kopfzeile, sondern die
    Rechnung: der größte Wert ist der Brutto, und Netto plus Steuer muss ihn
    ergeben.
    """
    l = deuten([
        k("Rotenberger Weingärtle", 40, 20, hoehe=22),
        k("USt.", 40, 300, hoehe=12), k("Brutto", 140, 300, hoehe=12),
        k("Netto", 240, 300, hoehe=12), k("USt.%", 340, 300, hoehe=12),
        k("5,59", 40, 330), k("85,40", 140, 330), k("79,81", 240, 330),
        k("A 7%", 340, 330),
        k("9,13", 40, 360), k("57,20", 140, 360), k("48,07", 240, 360),
        k("19%", 340, 360),
        k("Summe", 40, 400), k("142,60", 240, 400),
    ], heute=date(2026, 8, 22))
    assert {p.satz for p in l.steuerpositionen} == {7, 19}
    assert l.wert("netto") == 127.88
    assert l.wert("ust") == 14.72
    assert l.wert("ust_satz") == 7          # der größere Anteil
