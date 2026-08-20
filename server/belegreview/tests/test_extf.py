"""EXTF-v13-Writer: Golden-Format-Tests (CP1252, CRLF, Kopf, Mehrsatz-Split)."""
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import extf  # noqa: E402

GOLDEN = json.loads((HIER / "golden" / "review_weingaertle.json").read_text())
ERZEUGT = time.struct_time((2026, 8, 13, 12, 0, 0, 3, 225, 1))


def test_kopfzeile():
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT,
                       berater="12345", mandant="67890")
    kopf = text.split("\r\n")[0].split(";")
    assert kopf[0] == '"EXTF"'
    assert kopf[1] == "700"
    assert kopf[2] == "21"
    assert kopf[3] == '"Buchungsstapel"'
    assert kopf[4] == "13"
    assert kopf[5] == "20260813120000000"
    assert kopf[10] == "12345" and kopf[11] == "67890"
    assert kopf[12] == "20260101"          # WJ-Beginn
    assert kopf[14] == "20260701" and kopf[15] == "20260731"
    assert kopf[20] == "1"                 # Festschreibung


def test_spalten_und_weingaertle_zeile():
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT)
    zeilen = text.split("\r\n")
    spalten = zeilen[1].split(";")
    assert spalten[0] == "Umsatz (ohne Soll/Haben-Kz)"
    assert spalten[13] == "Buchungstext"
    # Der Weingärtle-Bon ist selbst ein Mehrsatz-Fall: 85,40 à 7 % (Speisen)
    # + 57,20 à 19 % (Getränke) = 142,60 → ZWEI Buchungszeilen. Genau die
    # Vereinfachung, die der einzeilige buchungssatz-Vorschau noch hatte.
    speisen = zeilen[2].split(";")
    getraenke = zeilen[3].split(";")
    assert len(speisen) == len(spalten), "Datenzeile muss die Spaltenzahl treffen"
    assert (speisen[0], speisen[8]) == ("85,40", "8")
    assert (getraenke[0], getraenke[8]) == ("57,20", "9")
    for daten in (speisen, getraenke):
        assert daten[1] == "S"
        assert daten[6] == "6640"
        assert daten[7] == "70099"
        assert daten[9] == "2107"
        assert daten[10] == '"R-A687-2026-00071"'
        assert daten[13] == '"Bewirtung 21.07. Rotenberger Weingärtle"'
    assert len(zeilen) == 5 and zeilen[4] == ""   # genau 2 Buchungen + CRLF-Abschluss


def test_mehrsatz_split():
    """Der dm-Fall aus dem Testkorpus: 19 % + 7 % auf einem Bon → zwei Sätze."""
    review = {
        "felder": {"brutto": 27.40, "datum": "02.04.2024", "beleg_nr": "9701",
                   "ust_satz": 19, "summenprobe_ok": True,
                   "steuertabelle": [
                       {"satz": 19, "netto": 18.87, "ust": 3.58, "brutto": 22.45},
                       {"satz": 7, "netto": 4.63, "ust": 0.32, "brutto": 4.95}]},
        "einschaetzung": {"konto_skr04": "5400", "steuerschluessel": "9"},
        "vlm": {"buchungstext": "Wareneinkauf dm 02.04."},
        "semantik": {"belegart": "Wareneinkauf"},
    }
    zeilen = extf.buchungszeilen(review)
    assert len(zeilen) == 2
    assert (zeilen[0]["umsatz"], zeilen[0]["bu"]) == ("22,45", "9")
    assert (zeilen[1]["umsatz"], zeilen[1]["bu"]) == ("4,95", "8")
    assert all(z["konto"] == "5400" for z in zeilen)


def test_cp1252_crlf():
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT)
    daten = extf.als_bytes(text)
    assert b"\r\n" in daten
    assert "ä".encode("cp1252") in daten            # Weingärtle
    assert daten.decode("cp1252")                    # rundreisefähig


def test_ohne_konto_keine_zeile():
    assert extf.buchungszeilen({"felder": {"brutto": 5.0},
                                "einschaetzung": {"konto_skr04": None}}) == []
