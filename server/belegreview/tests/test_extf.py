"""EXTF-v13-Writer: Golden-Format-Tests (CP1252, CRLF, Kopf, Mehrsatz-Split)."""
import json
import sys
import time
from pathlib import Path

import pytest

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


def _zeilen(review):
    return extf.buchungszeilen(review)


def _mit_satz(satz, brutto=119.0):
    return {"felder": {"brutto": brutto, "ust_satz": satz, "datum": "12.08.2026",
                       "beleg_nr": "R-1"},
            "einschaetzung": {"konto_skr04": "5900"},
            "semantik": {"belegart": "Wareneinkauf"},
            "vlm": {"lieferant": "Großhandel"}}


def test_steuerschluessel_je_satz():
    """Der Schlüssel sagt dem Import, wie viel Vorsteuer gezogen wird —
    ein falscher zieht stillschweigend den falschen Betrag."""
    assert _zeilen(_mit_satz(19))[0]["bu"] == "9"
    assert _zeilen(_mit_satz(7))[0]["bu"] == "8"
    assert _zeilen(_mit_satz(0))[0]["bu"] == ""


def test_corona_saetze_werden_nicht_als_neunzehn_gebucht():
    """5 % und 16 % gab es wirklich (2020) — der Watcher liest sie."""
    assert _zeilen(_mit_satz(5))[0]["bu"] == "7"
    assert _zeilen(_mit_satz(16))[0]["bu"] == "5"


def test_unbekannter_satz_kommt_nicht_in_den_stapel():
    """Lieber eine Zeile weniger als eine falsch besteuerte."""
    assert _zeilen(_mit_satz(12)) == []
    text = extf.stapel([_mit_satz(12)], "2026-08", erzeugt=ERZEUGT)
    assert len(text.rstrip("\r\n").split("\r\n")) == 2      # nur Kopf + Spalten


def _mit_text(buchungstext, beleg_nr="R-1"):
    return {"felder": {"brutto": 119.0, "ust_satz": 19, "datum": "12.08.2026",
                       "beleg_nr": beleg_nr},
            "einschaetzung": {"konto_skr04": "5900"},
            "semantik": {"belegart": "Wareneinkauf"},
            "vlm": {"buchungstext": buchungstext}}


def test_buchungstext_wird_in_excel_keine_formel():
    """Die EXTF-Datei landet beim Steuerbüro und wird dort in Excel geöffnet.

    Ein Buchungstext, der mit `=`, `+`, `-` oder `@` beginnt, ist für Excel
    eine Formel — ein Lieferantenname wie `=cmd|…` wird damit zum Angriff
    auf den Rechner der Steuerkanzlei. Das führende Apostroph macht daraus
    wieder Text; DATEV liest das Feld unverändert als Buchungstext.
    """
    for gefaehrlich in ("=cmd|'/c calc'!A1", "+1+1", "-2+3", "@SUM(A1)"):
        zeile = extf._zeile(_zeilen(_mit_text(gefaehrlich))[0])
        feld = zeile.split(";")[13]
        assert feld.startswith('"\''), feld
        assert gefaehrlich in feld            # der Inhalt bleibt vollständig


def test_harmloser_buchungstext_bleibt_unangetastet():
    """Kein Apostroph, wo keines hingehört — sonst stünde es in jeder Buchung."""
    zeile = extf._zeile(_zeilen(_mit_text("Wareneinkauf Großhandel"))[0])
    assert zeile.split(";")[13] == '"Wareneinkauf Großhandel"'


def test_buchungstext_bleibt_auch_entschaerft_hoechstens_sechzig_zeichen():
    """DATEV nimmt 60 Zeichen — das Schutzzeichen darf sie nicht sprengen."""
    zeile = _zeilen(_mit_text("=" + "A" * 80))[0]
    assert len(zeile["text"]) == 60


def test_belegfeld_faengt_nie_mit_einem_rechenzeichen_an():
    """Belegfeld 1 lässt DATEV nur wenige Zeichen zu — ein Apostroph gehört
    nicht dazu. Also fällt das Rechenzeichen vorn weg."""
    assert _zeilen(_mit_text("Einkauf", beleg_nr="-2+3"))[0]["belegfeld1"] == "2+3"


# ————— Der Mischungs-Melder: was den Stapel verlässt, wird geprüft —————
#
# BABU-57. Der Buchungsstapel ist die Stelle, an der babus Konten das Haus
# verlassen. Fällt eine Vermischung hier nicht auf, fällt sie beim
# Steuerberater auf — und dann ist der Import schon gelaufen.

def _im_rahmen(konto, rahmen, stamm="20260812-x-beleg"):
    return {"datei": f"docs/2026-08/{stamm}.jpg",
            "felder": {"brutto": 119.0, "ust_satz": 19, "datum": "12.08.2026",
                       "beleg_nr": "R-1"},
            "einschaetzung": {"konto": konto, "kontenrahmen": rahmen,
                              "konto_skr04": konto if rahmen == "SKR04" else None},
            "semantik": {"belegart": "Wareneinkauf"},
            "vlm": {"lieferant": "Großhandel"}}


def test_ein_skr03_beleg_kommt_ueberhaupt_in_den_stapel():
    """Vorher las der Writer nur `konto_skr04` — ein SKR03-Betrieb bekam
    einen leeren Stapel und keinen Hinweis, warum."""
    zeilen = extf.buchungszeilen(_im_rahmen("3400", "SKR03"))
    assert len(zeilen) == 1 and zeilen[0]["konto"] == "3400"


def test_ein_skr04_konto_im_skr03_stapel_faellt_auf():
    with pytest.raises(extf.RahmenVermischung) as exc:
        extf.stapel([_im_rahmen("3400", "SKR03"), _im_rahmen("5400", "SKR04")],
                    "2026-08", erzeugt=ERZEUGT, rahmen="SKR03")
    assert "5400" in str(exc.value)
    assert "SKR03" in str(exc.value)


def test_ein_sauberer_stapel_geht_durch():
    text = extf.stapel([_im_rahmen("3400", "SKR03")], "2026-08",
                       erzeugt=ERZEUGT, rahmen="SKR03")
    assert text.split("\r\n")[2].split(";")[6] == "3400"


def test_ohne_angegebenen_rahmen_wird_nicht_geprueft():
    """Alte Aufrufer bleiben, wie sie waren — der Melder ist eine Zutat."""
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT)
    assert text.split("\r\n")[2].split(";")[6] == "6640"


def test_ein_konto_das_babu_nicht_kennt_haelt_den_stapel_nicht_auf():
    """Handkorrigierte Konten (8400 Erlöse) kann babu nicht beurteilen.

    Sie zu verwerfen wäre schlimmer als sie durchzulassen: der Melder soll
    Vermischung finden, nicht fremde Kontierung überstimmen."""
    befund = extf.rahmen_pruefen([_im_rahmen("8400", "SKR03")], "SKR03")
    assert befund.vermischt == []
    assert befund.unbekannt == ["8400"]
    text = extf.stapel([_im_rahmen("8400", "SKR03")], "2026-08",
                       erzeugt=ERZEUGT, rahmen="SKR03")
    assert text.split("\r\n")[2].split(";")[6] == "8400"


def test_auch_der_vermerkte_rahmen_des_belegs_wird_geglaubt():
    """Ein Beleg, der selbst sagt „ich bin SKR04", gehört nicht in einen
    SKR03-Stapel — selbst wenn sein Konto in keinem der beiden vorkäme."""
    beleg = _im_rahmen("8400", "SKR04")
    with pytest.raises(extf.RahmenVermischung):
        extf.stapel([beleg], "2026-08", erzeugt=ERZEUGT, rahmen="SKR03")


def test_alte_reviews_ohne_rahmenvermerk_gelten_als_skr04():
    """Vor BABU-57 schrieb der Watcher nur `konto_skr04` — das war SKR04."""
    assert extf.rahmen_pruefen([GOLDEN], "SKR04").vermischt == []
    assert extf.rahmen_pruefen([GOLDEN], "SKR03").vermischt == ["6640"]


def test_die_meldung_nennt_den_beleg_nicht_nur_die_nummer():
    """Nina muss den Beleg finden können, nicht nur wissen, dass es ihn gibt."""
    beleg = _im_rahmen("5400", "SKR04", stamm="20260812-abc-schere")
    befund = extf.rahmen_pruefen([beleg], "SKR03")
    assert any("schere" in b for b in befund.belege)


def test_letzter_tag_im_februar():
    """Schaltjahr-Regel, nicht die Vierer-Faustregel: 2100 hat keinen 29.02."""
    assert extf.stapel([], "2024-02", erzeugt=ERZEUGT).split(";")[15] == "20240229"
    assert extf.stapel([], "2026-02", erzeugt=ERZEUGT).split(";")[15] == "20260228"
    assert extf.stapel([], "2100-02", erzeugt=ERZEUGT).split(";")[15] == "21000228"
