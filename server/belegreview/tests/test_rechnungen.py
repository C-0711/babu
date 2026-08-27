"""Rechnungen stellen: Nummernfolge, Pflichtangaben, Summen, Storno.

Reine Rechnung ohne I/O — was hier grün ist, gilt unabhängig davon, ob die
Rechnung aus der App oder aus dem Portal kommt.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rechnungen as re_  # noqa: E402


STAMM = {"betrieb_name": "Salon Nina", "anschrift": "Hauptstraße 5, 70173 Stuttgart",
         "steuernummer": "99012/34567", "kleinunternehmer": "Nein"}
EMPF = {"name": "Jana Allgaier", "anschrift": "Blumenweg 2, 70199 Stuttgart"}


def pos(text="Stuhlmiete August 2026", betrag=450.0, satz=19, menge=1,
        brutto=False):
    """Eine Rechnungsposition. `brutto=False`, weil die Tests unten die
    Netto-Arithmetik prüfen — seit dem 28.08.2026 ist die VORGABE der
    Rechnung dagegen brutto (die Zahl, die die Kundin zahlt); dafür gibt
    es einen eigenen Abschnitt am Ende."""
    return {"text": text, "einzelpreis": betrag, "menge": menge,
            "ust_satz": satz, "brutto": brutto}


# ————— Nummernfolge —————

def test_erste_nummer_eines_jahres():
    assert re_.naechste_nummer([], 2026) == "2026-0001"


def test_nummer_zaehlt_hoch():
    assert re_.naechste_nummer(["2026-0001", "2026-0002"], 2026) == "2026-0003"


def test_jedes_jahr_faengt_neu_an():
    assert re_.naechste_nummer(["2025-0001", "2025-0002"], 2026) == "2026-0001"


def test_nummer_richtet_sich_nach_der_hoechsten_nicht_nach_der_anzahl():
    """Eine Lücke darf sich nicht wiederholen — sonst gäbe es sie zweimal."""
    assert re_.naechste_nummer(["2026-0001", "2026-0004"], 2026) == "2026-0005"


def test_fremde_nummern_stoeren_nicht():
    assert re_.naechste_nummer(["kaputt", "", "2026-0007", None], 2026) == "2026-0008"


# ————— Summen —————

def test_summen_je_steuersatz():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21",
                     empfaenger=EMPF, positionen=[pos()], stammdaten=STAMM)
    assert r["netto"] == 450.0
    assert r["ust"] == 85.5
    assert r["brutto"] == 535.5
    assert r["saetze"] == [{"satz": 19, "netto": 450.0, "ust": 85.5}]


def test_mehrere_saetze_werden_getrennt_ausgewiesen():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos(betrag=100.0, satz=19),
                                 pos("Pflegeprodukt", betrag=50.0, satz=7)],
                     stammdaten=STAMM)
    assert r["saetze"] == [{"satz": 7, "netto": 50.0, "ust": 3.5},
                           {"satz": 19, "netto": 100.0, "ust": 19.0}]
    assert r["brutto"] == 172.5


def test_menge_multipliziert():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos(betrag=25.0, menge=4)], stammdaten=STAMM)
    assert r["netto"] == 100.0
    assert r["positionen"][0]["gesamt"] == 100.0


def test_rundung_bleibt_auf_dem_cent():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos(betrag=33.33, satz=19, menge=3)],
                     stammdaten=STAMM)
    assert r["netto"] == 99.99
    assert r["ust"] == 19.0
    assert r["brutto"] == 118.99


# ————— Kleinunternehmerin —————

def test_kleinunternehmerin_weist_keine_steuer_aus():
    stamm = dict(STAMM, kleinunternehmer="Ja")
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=stamm)
    assert r["ust"] == 0.0
    assert r["brutto"] == 450.0
    assert r["saetze"] == []
    assert "§ 19" in r["hinweis"]


def test_normalfall_hat_keinen_paragraph19_hinweis():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=STAMM)
    assert r["hinweis"] == ""


# ————— Pflichtangaben (§ 14 UStG) —————

def test_vollstaendige_rechnung_hat_keine_maengel():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=STAMM)
    assert re_.fehlende_pflichtangaben(r) == []


@pytest.mark.parametrize("weg, erwartet", [
    ("betrieb_name", "dein Betriebsname"),
    ("anschrift", "deine Anschrift"),
    ("steuernummer", "deine Steuernummer"),
])
def test_fehlende_stammdaten_werden_benannt(weg, erwartet):
    stamm = dict(STAMM); stamm[weg] = ""
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=stamm)
    assert any(erwartet in m for m in re_.fehlende_pflichtangaben(r))


def test_fehlender_empfaenger_wird_benannt():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21",
                     empfaenger={"name": "", "anschrift": ""},
                     positionen=[pos()], stammdaten=STAMM)
    maengel = re_.fehlende_pflichtangaben(r)
    assert any("Empfänger" in m for m in maengel)


def test_ohne_position_keine_rechnung():
    with pytest.raises(re_.RechnungFehler):
        re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[], stammdaten=STAMM)


def test_leistungszeitpunkt_faellt_auf_das_rechnungsdatum_zurueck():
    """§ 14 verlangt den Zeitpunkt der Leistung — fehlt er, gilt das Datum."""
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=STAMM)
    assert r["leistungszeitpunkt"] == "2026-08-21"
    r2 = re_.aufbauen(nummer="2026-0002", datum="2026-08-21", empfaenger=EMPF,
                      positionen=[pos()], stammdaten=STAMM,
                      leistungszeitpunkt="2026-07-31")
    assert r2["leistungszeitpunkt"] == "2026-07-31"


# ————— Kleinbetrag —————

def test_kleinbetragsrechnung_wird_erkannt():
    klein = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                         positionen=[pos(betrag=100.0)], stammdaten=STAMM)
    gross = re_.aufbauen(nummer="2026-0002", datum="2026-08-21", empfaenger=EMPF,
                         positionen=[pos(betrag=450.0)], stammdaten=STAMM)
    assert klein["kleinbetrag"] is True      # 119,00 € brutto
    assert gross["kleinbetrag"] is False     # 535,50 € brutto


# ————— Storno —————

def test_storno_dreht_die_betraege_um_und_verweist():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=STAMM)
    s = re_.storno(r, nummer="2026-0002", datum="2026-08-22")
    assert s["nummer"] == "2026-0002"
    assert s["storniert"] == "2026-0001"
    assert s["netto"] == -450.0
    assert s["brutto"] == -535.5
    assert "2026-0001" in s["positionen"][0]["text"]


def test_storno_eines_stornos_geht_nicht():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=STAMM)
    s = re_.storno(r, nummer="2026-0002", datum="2026-08-22")
    with pytest.raises(re_.RechnungFehler):
        re_.storno(s, nummer="2026-0003", datum="2026-08-23")


# ————— Stand —————

def test_offen_bis_bezahlt():
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos()], stammdaten=STAMM)
    assert re_.stand(r) == "offen"
    assert re_.stand(dict(r, bezahlt_am="2026-09-02")) == "bezahlt"
    assert re_.stand(dict(r, storniert_durch="2026-0002")) == "storniert"


# ————— Runden —————

def test_halber_cent_steuer_geht_auf_nicht_zur_geraden_zahl():
    """2,50 € netto zu 19 % sind 0,475 € Steuer — kaufmännisch also 0,48 €.

    Pythons `round()` rundete hier auf 0,47 ab, weil es zur geraden Ziffer
    rundet. Auf einer Rechnung ist das falsch ausgewiesene Steuer.
    """
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos(betrag=2.50, satz=19)], stammdaten=STAMM)
    assert r["ust"] == 0.48
    assert r["saetze"] == [{"satz": 19, "netto": 2.5, "ust": 0.48}]
    assert r["brutto"] == 2.98


def test_glatte_betraege_bleiben_wie_sie_waren():
    """Was schon richtig gerechnet war, darf sich nicht verschieben."""
    r = re_.aufbauen(nummer="2026-0001", datum="2026-08-21", empfaenger=EMPF,
                     positionen=[pos(betrag=450.0, satz=19),
                                 pos(text="Pflegeset", betrag=19.90, satz=7)],
                     stammdaten=STAMM)
    assert r["netto"] == 469.9
    assert r["ust"] == 86.89          # 85,50 + 1,39
    assert r["brutto"] == 556.79


# ————— Brutto ist die Vorgabe (Ninas Anmerkung, 27.08.2026) —————
#
# „Der Schnitt kostet 45 €" ist ein Bruttopreis. Bis zum 28.08. galt der
# eingegebene Betrag als netto, und aus 45 € wurden auf der Rechnung 53,55 €.

def test_eingegebener_preis_ist_der_preis_auf_der_rechnung():
    r = re_.aufbauen("2026-0001", "2026-08-28", EMPF,
                     [{"text": "Haarschnitt", "einzelpreis": 45.0, "ust_satz": 19},
                      {"text": "Shampoo", "einzelpreis": 12.90, "menge": 2,
                       "ust_satz": 19}],
                     STAMM)
    assert r["brutto"] == 70.80          # 45,00 + 2 x 12,90
    assert r["netto"] == 59.50
    assert r["ust"] == 11.30
    assert r["netto"] + r["ust"] == r["brutto"]


def test_die_zeilensummen_ergeben_die_endsumme_ohne_rundungsrest():
    """Aus dem Brutto abwärts zu rechnen ist kein Stil, sondern nötig:
    andersherum fehlt je Zeile ein Cent."""
    r = re_.aufbauen("2026-0001", "2026-08-28", EMPF,
                     [{"text": f"Position {i}", "einzelpreis": 33.33,
                       "ust_satz": 19} for i in range(7)], STAMM)
    assert r["brutto"] == 233.31
    assert sum(z["gesamt_brutto"] for z in r["positionen"]) == r["brutto"]
    assert r["netto"] + r["ust"] == r["brutto"]


def test_eine_einzelne_position_darf_netto_sein():
    r = re_.aufbauen("2026-0001", "2026-08-28", EMPF,
                     [{"text": "Miete netto vereinbart", "einzelpreis": 100.0,
                       "ust_satz": 19, "brutto": False}], STAMM)
    assert r["netto"] == 100.0 and r["brutto"] == 119.0


def test_wer_netto_rechnen_will_kann_das_weiter():
    r = re_.aufbauen("2026-0001", "2026-08-28", EMPF,
                     [{"text": "Stuhlmiete", "einzelpreis": 450.0, "ust_satz": 19}],
                     STAMM, preise_brutto=False)
    assert r["netto"] == 450.0 and r["brutto"] == 535.50


def test_kleinunternehmerin_bekommt_ihren_preis_unveraendert():
    """Ohne Umsatzsteuer gibt es nichts herauszurechnen — der eingegebene
    Betrag IST der Rechnungsbetrag."""
    r = re_.aufbauen("2026-0001", "2026-08-28", EMPF,
                     [{"text": "Schnitt", "einzelpreis": 45.0, "ust_satz": 19}],
                     dict(STAMM, kleinunternehmer="Ja"))
    assert r["netto"] == 45.0 and r["brutto"] == 45.0 and r["ust"] == 0.0


def test_ein_storno_hebt_die_rechnung_genau_auf():
    """Auch bei Bruttopreisen — sonst bleibt ein Rundungscent stehen."""
    r = re_.aufbauen("2026-0001", "2026-08-28", EMPF,
                     [{"text": "Haarschnitt", "einzelpreis": 45.0, "ust_satz": 19},
                      {"text": "Föhnen", "einzelpreis": 33.33, "ust_satz": 19}],
                     STAMM)
    s = re_.storno(r, nummer="2026-0002", datum="2026-08-29")
    assert s["brutto"] == -r["brutto"]
    assert s["netto"] == -r["netto"]
    assert s["ust"] == -r["ust"]
