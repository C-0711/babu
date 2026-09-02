"""Der Zielbild-Weg (seit 27.08.2026, `_review_aus_einschaetzung`) schreibt
`felder.datum` als ISO (JJJJ-MM-TT), Gemma liefert es so. extf.py liest seit
2b281ed beide Formen (`_datum_teile`/`_ttmm`) — dieser Test deckt die drei
weiteren Fundstellen ab, die noch blind `split(".")` machten und für
Zielbild-Belege leer/falsch liefen: `_anlage_vorschlaege` und
`datev_buchungssatz` in babu_web.py.

Reine Funktions-Tests, kein Git-Store nötig.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import babu_web as bw  # noqa: E402


def test_anlage_vorschlag_mit_iso_datum(monkeypatch):
    """Ein als Anlagevermögen eingestuftes ISO-datiertes Review (Zielbild-
    Weg) muss im Anlagenverzeichnis-Vorschlag auftauchen — vorher lieferte
    `datum.split(".")` bei "2026-03-15" nur EIN Teil, `len(teile) == 3`
    schlug fehl, `iso` blieb leer, der Beleg fiel lautlos aus der Liste."""
    idx = {"reviews": {
        "z1": {
            "einschaetzung": {"kategorie": "anlagevermoegen"},
            "felder": {"netto": 899.0, "datum": "2026-03-15",
                       "lieferant": "Föhn-Fachhandel", "beleg_nr": "R-1"},
            "vlm": {},
        },
        # Altweg-Format muss weiter funktionieren.
        "z2": {
            "einschaetzung": {"kategorie": "anlagevermoegen"},
            "felder": {"netto": 1200.0, "datum": "02.01.2026",
                       "lieferant": "Stuhl GmbH", "beleg_nr": "R-2"},
            "vlm": {},
        },
    }}
    monkeypatch.setattr(bw, "index_aktuell", lambda: idx)
    vorschlaege = bw._anlage_vorschlaege("nina@example.com", 2026, set())
    staemme = {v["stamm"]: v for v in vorschlaege}
    assert staemme["z1"]["angeschafft"] == "2026-03-15"
    assert staemme["z2"]["angeschafft"] == "2026-01-02"


def test_anlage_vorschlag_ausserhalb_des_jahres_faellt_raus(monkeypatch):
    """Die Jahresfilterung muss auf dem ISO-Datum genauso greifen wie auf
    dem Altweg-Datum — sonst reißt ein falsches Jahr in beide Richtungen."""
    idx = {"reviews": {
        "z1": {
            "einschaetzung": {"kategorie": "anlagevermoegen"},
            "felder": {"netto": 899.0, "datum": "2027-01-05",
                       "lieferant": "X", "beleg_nr": None},
            "vlm": {},
        },
    }}
    monkeypatch.setattr(bw, "index_aktuell", lambda: idx)
    vorschlaege = bw._anlage_vorschlaege("nina@example.com", 2026, set())
    assert vorschlaege == []


def test_datev_buchungssatz_mit_iso_datum():
    """`datev_buchungssatz` (Portal-Buchungstext-Vorschau, Belegdatum-
    Anzeige) muss ein ISO-Belegdatum genauso lesen wie TT.MM.JJJJ — vorher
    blieb `belegdatum` None und der Kurzdatum-Teil des Buchungstexts leer."""
    review = {
        "felder": {"brutto": 42.0, "datum": "2026-08-27", "beleg_nr": "B-9"},
        "einschaetzung": {"konto_skr04": "4980", "steuerschluessel": "9"},
        "vlm": None,
        "semantik": {"belegart": "Material"},
    }
    satz = bw.datev_buchungssatz(review)
    assert satz["belegdatum"] == "2708"
    assert satz["buchungstext"].startswith("Material 27.08.")

    alt = {
        "felder": {"brutto": 42.0, "datum": "27.08.2026", "beleg_nr": "B-9"},
        "einschaetzung": {"konto_skr04": "4980", "steuerschluessel": "9"},
        "vlm": None,
        "semantik": {"belegart": "Material"},
    }
    assert bw.datev_buchungssatz(alt)["belegdatum"] == "2708"
