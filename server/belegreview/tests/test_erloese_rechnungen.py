"""Erlöse aus zwei Quellen: Ladenkasse und gestellte Rechnungen.

Die heikle Stelle: WANN eine Rechnung zählt. Bei Ist-Versteuerung (der
Normalfall, und was die EÜR verlangt) zählt sie, wenn das Geld ankommt —
eine gestellte, unbezahlte Rechnung gehört NICHT in die Voranmeldung.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monatsabschluss as ma  # noqa: E402
import rechnungen as re_  # noqa: E402


def blatt(**kw):
    grund = {"datum": "2026-08-17", "einnahmenBar": 0.0, "ecZahlungen": 0.0,
             "umsatzFrei": 0.0, "umsatz7": 0.0, "gutscheinVerkauf": 0.0,
             "gutscheineEingeloest": 0.0}
    grund.update(kw)
    return grund


STAMM = {"betrieb_name": "Salon Nina", "anschrift": "Hauptstraße 5",
         "steuernummer": "99012/34567", "kleinunternehmer": "Nein"}


def rechnung(nummer="2026-0001", datum="2026-08-21", betrag=450.0, satz=19,
             bezahlt=None):
    r = re_.aufbauen(nummer=nummer, datum=datum,
                     empfaenger={"name": "Jana", "anschrift": "Blumenweg 2"},
                     positionen=[{"text": "Stuhlmiete", "einzelpreis": betrag,
                                  "ust_satz": satz}],
                     stammdaten=STAMM)
    r["bezahlt_am"] = bezahlt
    return r


# ————— Ist-Versteuerung: das Geld zählt —————

def test_unbezahlte_rechnung_zaehlt_nicht():
    e = ma.erloese_monat([blatt(einnahmenBar=1000)], monat="2026-08",
                         rechnungen=[rechnung(bezahlt=None)], versteuerung="ist")
    assert e["brutto_19"] == 1000.0
    assert e["aus_rechnungen"] == 0.0
    assert e["offen"] == 535.5           # steht als Forderung, nicht als Umsatz


def test_bezahlte_rechnung_zaehlt_im_monat_der_zahlung():
    e = ma.erloese_monat([blatt(einnahmenBar=1000)], monat="2026-09",
                         rechnungen=[rechnung(datum="2026-08-21",
                                              bezahlt="2026-09-02")],
                         versteuerung="ist")
    assert e["aus_rechnungen"] == 535.5
    assert e["brutto_19"] == 1535.5


def test_im_rechnungsmonat_taucht_sie_bei_ist_noch_nicht_auf():
    e = ma.erloese_monat([], monat="2026-08",
                         rechnungen=[rechnung(datum="2026-08-21",
                                              bezahlt="2026-09-02")],
                         versteuerung="ist")
    assert e["aus_rechnungen"] == 0.0


# ————— Soll-Versteuerung: das Datum zählt —————

def test_soll_zaehlt_im_monat_der_rechnung():
    e = ma.erloese_monat([], monat="2026-08",
                         rechnungen=[rechnung(datum="2026-08-21",
                                              bezahlt="2026-09-02")],
                         versteuerung="soll")
    assert e["aus_rechnungen"] == 535.5


def test_soll_zaehlt_auch_unbezahlt():
    e = ma.erloese_monat([], monat="2026-08",
                         rechnungen=[rechnung(datum="2026-08-21", bezahlt=None)],
                         versteuerung="soll")
    assert e["aus_rechnungen"] == 535.5
    assert e["offen"] == 535.5


# ————— Getrennt ausgewiesen, gemeinsam summiert —————

def test_quellen_bleiben_unterscheidbar():
    e = ma.erloese_monat([blatt(einnahmenBar=300, ecZahlungen=700)],
                         monat="2026-08",
                         rechnungen=[rechnung(bezahlt="2026-08-25")],
                         versteuerung="ist")
    assert e["aus_kasse"] == 1000.0
    assert e["aus_rechnungen"] == 535.5
    assert e["brutto_gesamt"] == 1535.5


def test_sieben_prozent_landet_im_richtigen_topf():
    e = ma.erloese_monat([], monat="2026-08",
                         rechnungen=[rechnung(betrag=100.0, satz=7,
                                              bezahlt="2026-08-25")],
                         versteuerung="ist")
    assert e["brutto_7"] == 107.0
    assert e["brutto_19"] == 0.0


def test_storniertes_zaehlt_nirgends():
    r = rechnung(bezahlt="2026-08-25")
    r["storniert_durch"] = "2026-0002"
    e = ma.erloese_monat([], monat="2026-08", rechnungen=[r], versteuerung="ist")
    assert e["aus_rechnungen"] == 0.0


def test_ohne_rechnungen_bleibt_alles_wie_bisher():
    """Rückwärtskompatibel: der alte Aufruf muss weiter stimmen."""
    alt = ma.erloese_monat([blatt(einnahmenBar=1190)])
    assert alt["brutto_19"] == 1190.0
    assert alt["aus_rechnungen"] == 0.0


# ————— Bis in die Voranmeldung —————

def test_bezahlte_rechnung_erhoeht_die_zahllast():
    profil = ma.umsatz_profil({"kleinunternehmer": "Nein"})
    ohne = ma.ustva_entwurf("2026-08", ma.erloese_monat([], monat="2026-08"),
                            {"vorsteuer": 0.0, "pruefliste": []}, profil)
    mit = ma.ustva_entwurf(
        "2026-08",
        ma.erloese_monat([], monat="2026-08",
                         rechnungen=[rechnung(bezahlt="2026-08-25")],
                         versteuerung="ist"),
        {"vorsteuer": 0.0, "pruefliste": []}, profil)
    assert ohne["zahllast"] == 0.0
    assert mit["zahllast"] == 85.5        # 450 € netto × 19 %
