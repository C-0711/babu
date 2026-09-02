"""Vorsteuer aus gedruckten Steuerzeilen, nicht aus dem Bruttobetrag.

Ninas Fund vom 02.09.2026 (P0-2): ein Getränkemarkt-Bon druckt Netto 57,06 €
und Steuer (19 %) 8,67 € bei Brutto 65,73 € — Pfand ist darin steuerfrei
enthalten. Bis dahin rechnete `_review_aus_einschaetzung` immer 19 % auf den
GANZEN Bruttobetrag, macht 1,82 € zu viel Vorsteuer in der DATEV-Zeile.
Liegt Gemmas Steuertabelle (`buchung["steuersaetze"]`) vor und deckt sie den
Betrag, gewinnt sie — die Rückrechnung bleibt nur der Fallback ohne Tabelle.

Reine Funktions-Tests, kein Git-Store nötig: `_review_aus_einschaetzung` ist
eine pure Funktion.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import babu_web as bw  # noqa: E402
import extf  # noqa: E402


def test_steuertabelle_gewinnt_vor_der_rueckrechnung():
    buchung = {
        "betrag_eur": 65.73,
        "ust_satz": 19,
        "lieferant": "Getränkemarkt",
        "datum": "2026-08-04",
        "steuersaetze": [
            {"satz": 19, "brutto": 59.06, "netto": 49.63, "ust": 9.43},
            {"satz": 0, "brutto": 6.67, "netto": 6.67, "ust": 0.0},
        ],
    }
    review, _ = bw._review_aus_einschaetzung("docs/x.pdf", buchung, [], "beleg")
    f = review["felder"]
    assert f["netto"] == 56.30
    assert f["ust"] == 9.43
    assert f["brutto"] == 65.73
    assert f["summenprobe_ok"] is True
    # Nicht die blinde 19-%-Rückrechnung auf den ganzen Betrag.
    assert (f["netto"], f["ust"]) != (55.24, 10.49)


def test_ohne_tabelle_bleibt_der_alte_pfad():
    buchung = {"betrag_eur": 65.73, "ust_satz": 19, "lieferant": "Getränkemarkt",
               "datum": "2026-08-04"}
    review, _ = bw._review_aus_einschaetzung("docs/x.pdf", buchung, [], "beleg")
    f = review["felder"]
    assert f["netto"] == 55.24
    assert f["ust"] == 10.49
    assert f["summenprobe_ok"] is None


def test_tabelle_die_den_betrag_nicht_deckt_faellt_zurueck():
    """Eine Steuertabelle aus alten/unvollständigen Positionen, die den
    Bruttobetrag nicht trifft, darf nicht stillschweigend übernommen werden
    — dann gilt weiter die Rückrechnung, ohne falsche Probe."""
    buchung = {"betrag_eur": 65.73, "ust_satz": 19, "lieferant": "Getränkemarkt",
               "datum": "2026-08-04",
               "steuersaetze": [{"satz": 19, "brutto": 40.00, "netto": 33.61, "ust": 6.39}]}
    review, _ = bw._review_aus_einschaetzung("docs/x.pdf", buchung, [], "beleg")
    f = review["felder"]
    assert f["netto"] == 55.24
    assert f["ust"] == 10.49
    assert f["summenprobe_ok"] is None


def test_gerissene_probe_setzt_summenprobe_ok_false():
    """Deckt die Tabelle den Brutto, aber Netto+USt der Tabelle selbst gehen
    nicht auf (Rundungs-/Lesefehler), wird das ehrlich als False markiert —
    das schickt den Beleg über `_status_ableiten` in die Nachfrage und
    schließt ihn in `vorsteuer_monat` aus Kz 66 aus."""
    buchung = {"betrag_eur": 65.73, "ust_satz": 19, "lieferant": "Getränkemarkt",
               "datum": "2026-08-04",
               "steuersaetze": [
                   {"satz": 19, "brutto": 59.06, "netto": 40.00, "ust": 9.43},
                   {"satz": 0, "brutto": 6.67, "netto": 6.67, "ust": 0.0},
               ]}
    review, _ = bw._review_aus_einschaetzung("docs/x.pdf", buchung, [], "beleg")
    f = review["felder"]
    assert f["summenprobe_ok"] is False
    assert bw._status_ableiten(review, bewirtung_da=False) == "nachfrage"


def test_mischsatz_traegt_steuertabelle_und_splittet_im_stapel():
    """Der eigentliche Mischsatz-Bug: `_review_aus_einschaetzung` schrieb
    `felder.steuertabelle` nie, obwohl `buchung.steuersaetze` genau die
    Form trägt, die `extf.buchungszeilen` für den Mehrsatz-Split braucht
    (der dm-Fall: 19 % + 7 % auf einem Bon). Ohne das Feld bucht der Stapel
    einen Satz auf den vollen Bruttobetrag statt zwei Zeilen."""
    buchung = {
        "betrag_eur": 100.00,
        "ust_satz": 19,
        "lieferant": "dm-drogerie markt",
        "datum": "2026-08-30",
        "konto": "4980",
        "steuersaetze": [
            {"satz": 19, "brutto": 60.00, "netto": 50.42, "ust": 9.58},
            {"satz": 7, "brutto": 40.00, "netto": 37.38, "ust": 2.62},
        ],
    }
    review, _ = bw._review_aus_einschaetzung("docs/dm.jpg", buchung, [], "beleg")
    f = review["felder"]
    assert f["steuertabelle"] == buchung["steuersaetze"]
    assert f["summenprobe_ok"] is True

    zeilen = extf.buchungszeilen(review)
    assert len(zeilen) == 2
    nach_satz = {z["satz"]: z for z in zeilen}
    assert nach_satz[19]["bu"] == "9" and nach_satz[19]["umsatz"] == "60,00"
    assert nach_satz[7]["bu"] == "8" and nach_satz[7]["umsatz"] == "40,00"


def test_ein_satz_traegt_keine_steuertabelle():
    """Golden-Diff-Sicherheit: ein einzelner Satz bleibt unverändert ohne
    das Feld — `extf.buchungszeilen` bucht wie bisher EINE Zeile."""
    buchung = {"betrag_eur": 65.73, "ust_satz": 19, "lieferant": "Getränkemarkt",
               "datum": "2026-08-04", "konto": "4980"}
    review, _ = bw._review_aus_einschaetzung("docs/x.pdf", buchung, [], "beleg")
    assert "steuertabelle" not in review["felder"]
    zeilen = extf.buchungszeilen(review)
    assert len(zeilen) == 1
