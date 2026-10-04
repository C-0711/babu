"""Pfand und Versand bekommen ihr eigenes Konto (Entscheid 04.10.2026).

Ninas Meldungen #80/#81 (Pfand) und #82 (Versand als Software gebucht).
Der Auftraggeber hat entschieden:

- Pfand und Leergutrückgabe gehen auf ein eigenes Konto (SKR04 5820
  „Leergut“), getrennt vom Rest des Bons.
- Versandkosten gehen IMMER auf „Porto und Versand“ — auch, wenn sie auf
  einer Warenrechnung stehen.

Gemma liest die Positionen eines Bons mit Kategorie und Steuersatz; der
Stapel gliedert die Pfand- und Versandpositionen aus. Der Rest des Belegs
bleibt auf seinem Konto. Testfall ist Ninas Bon vom Getränkemarkt am
04.08.2026 mit seinen echten Beträgen.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import extf  # noqa: E402
import gemma_buchung  # noqa: E402
import kontierung as kt  # noqa: E402
import skr04_konten  # noqa: E402


def _review(kategorie, konto, positionen, **mehr):
    """Ein Review, wie es der Zielbild-Weg aus Gemmas Buchung baut."""
    import babu_web  # noqa: PLC0415
    brutto = round(sum(p["betrag"] for p in positionen), 2)
    buchung = {"dokumentklasse": "beleg", "lieferant": "Lieferant", "datum": "2026-08-04",
               "kategorie": kategorie, "kategorie_name": kt.KATEGORIEN[kategorie].name,
               "konto": konto, "betrag_eur": brutto, "zahlungsart": "karte",
               "ust_satz": 19, "positionen": positionen,
               "steuersaetze": gemma_buchung._steuertabelle(positionen),
               "buchungstext": "Einkauf", **mehr}
    review, _ = babu_web._review_aus_einschaetzung("docs/2026-08/x.jpg", buchung, [], "beleg")
    return review


GETRAENKE = [
    {"bezeichnung": "Coca-Cola Zero Dose 24", "betrag": 21.36, "ust_satz": 19,
     "kategorie": "aufmerksamkeit"},
    {"bezeichnung": "Pfand", "betrag": 6.00, "ust_satz": 0, "kategorie": "pfand"},
    {"bezeichnung": "Ensinger Gourmet Bio", "betrag": 32.97, "ust_satz": 19,
     "kategorie": "aufmerksamkeit"},
    {"bezeichnung": "Pfand", "betrag": 15.30, "ust_satz": 0, "kategorie": "pfand"},
    {"bezeichnung": "Leergut/Pfandrückgabe", "betrag": -9.90, "ust_satz": 0,
     "kategorie": "pfand"},
]

FARBE_MIT_VERSAND = [
    {"bezeichnung": "Haarfarbe 12 Tuben", "betrag": 100.00, "ust_satz": 19,
     "kategorie": "verbrauchsmaterial"},
    {"bezeichnung": "Versand", "betrag": 5.95, "ust_satz": 19, "kategorie": "porto"},
]


def _zeilen(review, **kw):
    return [(z["konto"], z["umsatz"], z["sh"], z["bu"]) for z in extf.buchungszeilen(review, **kw)]


# ————— Der Katalog —————

def test_pfand_hat_ein_eigenes_konto_im_katalog():
    k = kt.KATEGORIEN["pfand"]
    assert k.konto("SKR04") == "5820"
    assert skr04_konten.name("5820") == "Leergut"
    # Die Nummer stammt aus dem DATEV-Kontenrahmen, die Kanzlei hat sie noch
    # nicht bestätigt — der Prüfbefund sagt das, bis sie es tut.
    assert k.geprueft is False


def test_gemma_bekommt_pfand_und_versand_als_eigene_positionen_gesagt():
    assert "kategorie pfand" in gemma_buchung.REGELN
    assert "kategorie porto" in gemma_buchung.REGELN


# ————— Der Stapel —————

def test_pfand_geht_auf_das_leergutkonto():
    """Ninas Bon: 54,33 € Getränke zu 19 %, 11,40 € Pfand netto zu 0 %."""
    assert _zeilen(_review("aufmerksamkeit", "6643", GETRAENKE)) == [
        ("6643", "54,33", "S", "9"), ("5820", "11,40", "S", "")]


def test_versand_auf_einer_warenrechnung_geht_auf_porto():
    assert _zeilen(_review("verbrauchsmaterial", "5100", FARBE_MIT_VERSAND)) == [
        ("5100", "100,00", "S", "9"), ("6800", "5,95", "S", "9")]


def test_ein_reiner_versandbeleg_bleibt_eine_zeile():
    nur_versand = [{"bezeichnung": "DHL Paket", "betrag": 5.95, "ust_satz": 19,
                    "kategorie": "porto"}]
    assert _zeilen(_review("porto", "6800", nur_versand)) == [("6800", "5,95", "S", "9")]


def test_ohne_positionen_bleibt_alles_wie_es_war():
    r = _review("verbrauchsmaterial", "5100", FARBE_MIT_VERSAND)
    r["buchung"]["buchung"]["positionen"] = []
    assert _zeilen(r) == [("5100", "105,95", "S", "9")]


def test_kleinunternehmerin_bekommt_beide_konten_ohne_steuer():
    assert _zeilen(_review("verbrauchsmaterial", "5100", FARBE_MIT_VERSAND),
                   kleinunternehmerin=True) == [
        ("5100", "100,00", "S", ""), ("6800", "5,95", "S", "")]


def test_eine_gutschrift_dreht_beide_zeilen_ins_haben():
    gutschrift = [dict(p, betrag=-p["betrag"]) for p in FARBE_MIT_VERSAND]
    r = _review("verbrauchsmaterial", "5100", gutschrift, gutschrift=True)
    assert _zeilen(r) == [("5100", "100,00", "H", "9"), ("6800", "5,95", "H", "9")]


def test_im_skr03_ohne_pfandkonto_bleibt_der_bon_zusammen():
    r = _review("aufmerksamkeit", "4653", GETRAENKE)
    r["einschaetzung"]["kontenrahmen"] = "SKR03"
    assert [z[0] for z in _zeilen(r)] == ["4653", "4653"]


def test_eine_eigene_rechnung_wird_nicht_aufgeteilt():
    r = _review("umsatzerloese", "4400", FARBE_MIT_VERSAND)
    r["felder"]["dokumentklasse"] = "ausgangsrechnung"
    assert {z[0] for z in _zeilen(r)} == {"4400"}


def test_passt_die_rechnung_nicht_wird_nicht_aufgeteilt():
    """Mehr Versand als die Zeile hergibt — dann lieber ungeteilt als falsch."""
    r = _review("verbrauchsmaterial", "5100", FARBE_MIT_VERSAND)
    r["buchung"]["buchung"]["positionen"][1]["betrag"] = 500.0
    assert _zeilen(r) == [("5100", "105,95", "S", "9")]


# ————— Gemischt? —————

def test_pfand_macht_einen_bon_nicht_gemischt():
    """Viel Pfand (Wasserkästen) darf keine Rückfrage auslösen — es wird ohnehin
    ausgegliedert."""
    kaesten = [{"betrag": 10.0, "ust_satz": 19, "kategorie": "aufmerksamkeit"},
               {"betrag": 9.9, "ust_satz": 0, "kategorie": "pfand"},
               {"betrag": 2.0, "ust_satz": 19, "kategorie": "porto"}]
    assert gemma_buchung.gemischt({"positionen": kaesten}) is False
