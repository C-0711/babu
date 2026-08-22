"""Das Leseprotokoll — es muss alles zeigen, und es muss stimmen.

Das Protokoll ist der Grund, warum man der Lesung glauben darf: es nennt zu
jeder Zahl die Zeile. Ein Protokoll, das Zeilen unterschlägt oder eine
falsche Herkunft behauptet, wäre schlimmer als keines.
"""
import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from belegdeutung import Kasten, deuten  # noqa: E402
from leseprotokoll import protokoll  # noqa: E402


def k(text, x0, y0, breite=None, hoehe=20, konf=0.97):
    breite = breite if breite is not None else len(text) * hoehe * 0.55
    return Kasten(text, konf, x0, y0, x0 + breite, y0 + hoehe)


def rechts(text, kante, y, hoehe=20, konf=0.97):
    breite = len(text) * hoehe * 0.55
    return Kasten(text, konf, kante - breite, y, kante, y + hoehe)


@pytest.fixture
def bon():
    return [
        k("Bäckerei Probe GmbH", 40, 20, hoehe=22),
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


@pytest.fixture
def text(bon):
    lesung = deuten(bon, heute=date(2026, 8, 22))
    return protokoll(lesung, datei="bon.jpg", engine="PaddleOCR PP-OCRv6 (GPU-Dienst)",
                     dauer_s=0.03, zusammenfassung="Ein Brötchen beim Bäcker um die Ecke.",
                     belegart="Bewirtung", konto="6640", steuerschluessel="8",
                     gelesen_am="2026-08-22T07:42:00+00:00")


# ————— Vollständigkeit —————

def test_jede_erkannte_zeile_steht_drin(bon, text):
    lesung = deuten(bon, heute=date(2026, 8, 22))
    for z in lesung.zeilen:
        assert z.text in text, f"Zeile fehlt im Protokoll: {z.text!r}"


def test_die_zeilenzahl_wird_genannt(bon, text):
    lesung = deuten(bon, heute=date(2026, 8, 22))
    assert f"{len(lesung.zeilen)} Zeilen" in text


def test_alle_werte_stehen_drin(text):
    assert "Bäckerei Probe GmbH" in text
    assert "4711" in text
    assert "22. August 2026" in text
    assert "1,30 €" in text
    assert "1,21 €" in text
    assert "0,09 €" in text
    assert "7 %" in text


def test_die_zusammenfassung_steht_oben(text):
    kopf = text[:400]
    assert "Ein Brötchen beim Bäcker um die Ecke." in kopf


def test_belegart_und_konto_stehen_drin(text):
    assert "Bewirtung" in text and "6640" in text


def test_die_technik_steht_drin(text):
    assert "PP-OCRv6 (GPU-Dienst)" in text
    assert "0.03 s" in text
    assert "22. August 2026" in text


# ————— Die Herkunft muss stimmen —————

def test_jede_herkunft_nennt_eine_zeilennummer(text):
    for feld in ("Lieferant", "Beleg-Nr.", "Datum", "Rechnungsbetrag"):
        zeile = [z for z in text.splitlines() if z.startswith(f"| {feld} |")]
        assert zeile, f"{feld} fehlt in der Ergebnistabelle"
        assert "Zeile " in zeile[0], f"{feld} nennt keine Zeile: {zeile[0]}"


def test_die_genannte_zeilennummer_stimmt(bon):
    """Die Nummer im Protokoll muss auf die Zeile zeigen, aus der es kommt."""
    lesung = deuten(bon, heute=date(2026, 8, 22))
    d = lesung.felder["brutto"]
    assert "SUMME" in lesung.zeilen[d.zeile_nr].text
    text = protokoll(lesung, datei="bon.jpg", engine="x", dauer_s=0.1)
    zeile = [z for z in text.splitlines() if z.startswith("| Rechnungsbetrag |")][0]
    assert f"Zeile {d.zeile_nr + 1}" in zeile


def test_benutzte_zeilen_sind_markiert(bon):
    lesung = deuten(bon, heute=date(2026, 8, 22))
    text = protokoll(lesung, datei="bon.jpg", engine="x", dauer_s=0.1)
    nr = lesung.felder["brutto"].zeile_nr + 1
    zeile = [z for z in text.splitlines() if z.startswith(f"| {nr} |")][0]
    assert "›" in zeile


# ————— Die Steuerrechnung —————

def test_die_rechnung_geht_sichtbar_auf(text):
    assert "✓ geht auf" in text


def test_eine_nicht_aufgehende_rechnung_wird_deutlich():
    lesung = deuten([
        k("Laden GmbH", 40, 20, hoehe=22),
        k("Netto", 40, 100), rechts("50,00", 300, 100),
        k("MwSt", 40, 130), rechts("9,50", 300, 130),
        k("Gesamtbetrag", 40, 160), rechts("40,00", 300, 160),
    ], heute=date(2026, 8, 22))
    text = protokoll(lesung, datei="x.jpg", engine="x", dauer_s=0.1)
    assert "nicht verlässlich" in text or "geht NICHT auf" in text


# ————— Die Gegenprobe —————

def test_gegenprobe_ohne_abweichung(bon):
    lesung = deuten(bon, heute=date(2026, 8, 22))
    text = protokoll(lesung, datei="bon.jpg", engine="x", dauer_s=0.1,
                     gegenprobe={"lieferant": "Bäckerei Probe GmbH", "brutto": 1.30},
                     widerspruch=[])
    assert "Keine Abweichung" in text


def test_gegenprobe_mit_abweichung_sagt_was_gilt(bon):
    lesung = deuten(bon, heute=date(2026, 8, 22))
    text = protokoll(lesung, datei="bon.jpg", engine="x", dauer_s=0.1,
                     gegenprobe={"brutto": 7.00},
                     widerspruch=["Rechnungsbetrag: die Gegenprobe liest 7,00 €"])
    assert "Rechnungsbetrag: die Gegenprobe liest 7,00 €" in text
    assert "Gültig ist, was oben steht" in text


# ————— Zahlen deutsch —————

@pytest.mark.parametrize("wert, soll", [
    (1.3, "1,30 €"), (40.0, "40,00 €"), (1234.56, "1.234,56 €"),
    (43783.86, "43.783,86 €"), (0.0, "0,00 €"),
])
def test_betraege_stehen_deutsch_da(wert, soll):
    from leseprotokoll import _geld
    assert _geld(wert) == soll


def test_datum_steht_ausgeschrieben():
    from leseprotokoll import _datum_lang
    assert _datum_lang("2026-08-14") == "14. August 2026"
    assert _datum_lang(None) == "—"


# ————— Randfälle —————

def test_ein_leerer_beleg_ergibt_trotzdem_ein_protokoll():
    text = protokoll(deuten([]), datei="leer.jpg", engine="x", dauer_s=0.1)
    assert "leer.jpg" in text and "0 Zeilen" in text


def test_ein_senkrechter_strich_im_text_zerlegt_die_tabelle_nicht():
    lesung = deuten([k("Laden | GmbH", 40, 20, hoehe=22),
                     k("Summe", 40, 100), rechts("10,00", 300, 100)],
                    heute=date(2026, 8, 22))
    text = protokoll(lesung, datei="x.jpg", engine="x", dauer_s=0.1)
    tabellenzeile = [z for z in text.splitlines() if "Laden" in z and z.startswith("| 1 |")]
    assert tabellenzeile, "die Zeile fehlt"
    # Der Strich muss escaped sein, sonst zerfällt die Tabelle beim Anzeigen.
    assert r"Laden \| GmbH" in tabellenzeile[0]
    assert len(re.split(r"(?<!\\)\|", tabellenzeile[0])) == 6


def test_offene_punkte_stehen_drin():
    lesung = deuten([k("Rechnung", 40, 20, hoehe=22)], heute=date(2026, 8, 22))
    text = protokoll(lesung, datei="x.jpg", engine="x", dauer_s=0.1)
    assert "Was offen ist" in text
