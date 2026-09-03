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
    assert kopf[4] == "12"          # Formatversion, siehe unten
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
    # 5400 ist ein Automatikkonto (AV 19 %): kein Schlüssel. Der 7 %-Anteil
    # gehört auf 5300 (Wareneingang 7 % Vorsteuer, ebenfalls Automatik).
    assert (zeilen[0]["umsatz"], zeilen[0]["konto"], zeilen[0]["bu"]) == ("22,45", "5400", "")
    assert (zeilen[1]["umsatz"], zeilen[1]["konto"], zeilen[1]["bu"]) == ("4,95", "5300", "")


def _zielbild_review(datum, **felder_overrides):
    """Form eines Reviews aus dem Zielbild-Weg (babu_web._review_aus_
    einschaetzung, seit 27.08.2026): `vlm`/`semantik` sind None, `datum`
    kommt von Gemma als `JJJJ-MM-TT`, `konto`/`kontenrahmen` statt
    `konto_skr04` in der Einschätzung."""
    felder = {"brutto": 27.40, "datum": datum, "beleg_nr": None,
              "ust_satz": 19}
    felder.update(felder_overrides)
    return {"felder": felder,
            "einschaetzung": {"konto": "5900", "kontenrahmen": "SKR04"},
            "vlm": None, "semantik": None}


def test_iso_datum_aus_dem_zielbild_weg_traegt_ein_belegdatum():
    """Befund: Gemma schreibt seit 27.08.2026 `felder.datum` als
    `JJJJ-MM-TT` (siehe _review_aus_einschaetzung in babu_web.py), extf.py
    las bislang nur `TT.MM.JJJJ` — jeder Beleg aus dem Zielbild-Weg ging
    ohne Belegdatum in den DATEV-Stapel."""
    zeilen = extf.buchungszeilen(_zielbild_review("2026-04-02"))
    assert zeilen[0]["belegdatum"] == "0204"


def test_altformat_datum_bleibt_lesbar():
    zeilen = extf.buchungszeilen(_zielbild_review("02.04.2026"))
    assert zeilen[0]["belegdatum"] == "0204"


def test_datum_tolerant_gegen_leerraum():
    zeilen = extf.buchungszeilen(_zielbild_review(" 2026-04-02 "))
    assert zeilen[0]["belegdatum"] == "0204"
    zeilen = extf.buchungszeilen(_zielbild_review("2.4.2026"))
    assert zeilen[0]["belegdatum"] == "0204"


def test_unlesbares_datum_liefert_kein_belegdatum_statt_absturz():
    for kaputt in ("kaputt", "2026/04/02", "", None, "2026-04"):
        zeilen = extf.buchungszeilen(_zielbild_review(kaputt))
        assert zeilen[0]["belegdatum"] is None


def test_buchungstext_fallback_nutzt_iso_datum_ebenfalls():
    """Ohne Gemma-Buchungstext baut extf.py den Text aus Einordnung +
    Kurzdatum + Lieferant zusammen — das Kurzdatum (`TT.MM.`) muss auch
    aus einem ISO-Datum kommen, nicht nur leer bleiben."""
    review = _zielbild_review("2026-04-02", lieferant="Großhandel")
    review["semantik"] = {"belegart": "Wareneinkauf"}
    zeilen = extf.buchungszeilen(review)
    assert zeilen[0]["text"] == "Wareneinkauf 02.04. Großhandel"


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


# ————— Automatikkonten (seit 02.09.2026) —————

def _auf(konto, satz=19, brutto=119.0):
    r = _mit_satz(satz, brutto)
    r["einschaetzung"]["konto_skr04"] = konto
    return r


def test_automatikkonto_traegt_keinen_schluessel():
    """Im SKR04 rechnen AV/AM-Konten ihre Steuer selbst — ein Schlüssel
    obendrauf ist ein Widerspruch, den erst der Import meldet."""
    assert _zeilen(_auf("5400", 19))[0]["bu"] == ""          # AV 19 %
    assert _zeilen(_auf("5400"))[0]["konto"] == "5400"


def test_verbrauchsmaterial_ist_kein_automatikkonto():
    """5100 hat im SKR04 kein AV — dort entscheidet der Schlüssel."""
    assert _zeilen(_auf("5100", 19))[0]["bu"] == "9"
    assert _zeilen(_auf("5100", 7))[0]["bu"] == "8"


def test_fremder_satz_wandert_auf_das_geschwisterkonto():
    z = _zeilen(_auf("5400", 7))[0]
    assert (z["konto"], z["bu"]) == ("5300", "")


def test_skr03_bleibt_unangetastet():
    """Für SKR03 liegt babu kein Kontenrahmen als Quelle vor — dort
    bleibt der Schlüssel, wie er war."""
    r = _auf("3400", 19)
    r["einschaetzung"] = {"konto": "3400", "kontenrahmen": "SKR03"}
    z = _zeilen(r)
    assert z and z[0]["bu"] == "9"


# ————— Die Erlösseite —————

def _blatt(**w):
    b = {"datum": "2026-08-01", "einnahmenBar": 0.0, "ecZahlungen": 0.0}
    b.update(w)
    return b


def test_ein_kassentag_wird_kasse_an_erloese_je_satz():
    z = extf.erloeszeilen([_blatt(einnahmenBar=100, ecZahlungen=50, umsatz7=20)])
    assert [(x["konto"], x["gegenkonto"], x["umsatz"], x["bu"]) for x in z] == [
        ("1600", "4400", "130,00", ""),        # 150 − 20 → 19 %, Automatik
        ("1600", "4300", "20,00", ""),
        ("1460", "1600", "50,00", ""),         # Kartenumsatz raus aus der Kasse
    ]
    assert all(x["belegdatum"] == "0108" for x in z)
    assert all(x["belegfeld1"] == "KB20260801" for x in z)
    assert z[0]["text"] == "Tageseinnahmen 19 %"
    assert z[2]["text"] == "Kartenumsatz an Geldtransit"


def test_verkaufte_gutscheine_sind_umsatz_eingeloeste_nicht():
    """Einzweck-Gutschein: versteuert beim Verkauf — wie erloese_monat."""
    z = extf.erloeszeilen([_blatt(einnahmenBar=100, gutscheinVerkauf=30,
                                  gutscheineEingeloest=25)])
    assert z[0]["umsatz"] == "130,00"
    assert len(z) == 1


def test_steuerfreier_umsatz_geht_auf_4100():
    z = extf.erloeszeilen([_blatt(einnahmenBar=80, umsatzFrei=80)])
    assert [(x["gegenkonto"], x["umsatz"]) for x in z] == [("4100", "80,00")]


def test_die_kleinunternehmerin_bucht_alles_auf_4184():
    """§ 19 UStG: kein Steuerausweis. Auf 4400 rechnete DATEV
    Umsatzsteuer heraus, die es nicht gibt."""
    z = extf.erloeszeilen([_blatt(einnahmenBar=100, ecZahlungen=50, umsatz7=20)],
                          kleinunternehmerin=True)
    assert [(x["konto"], x["gegenkonto"], x["umsatz"]) for x in z] == [
        ("1600", "4184", "150,00"), ("1460", "1600", "50,00")]


def test_ein_leerer_tag_erzeugt_keine_zeile():
    assert extf.erloeszeilen([_blatt()]) == []
    assert extf.erloeszeilen([{"datum": "kaputt", "einnahmenBar": 5}]) == []


def test_der_stapel_traegt_belege_und_kassentage():
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT,
                       kassenblaetter=[_blatt(datum="2026-07-03", einnahmenBar=100)])
    zeilen = text.rstrip("\r\n").split("\r\n")
    belege = len(extf.buchungszeilen(GOLDEN))
    assert len(zeilen) == 2 + belege + 1
    assert zeilen[-1].startswith('100,00;S;EUR;;;;1600;4400;;0307;"KB20260703";;;"Tageseinnahmen 19 %"')


def test_ohne_kassenblaetter_bleibt_der_stapel_wie_er_war():
    assert extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT) == \
        extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT, kassenblaetter=[])


def test_skr03_stapel_bekommt_keine_erloesseite(capsys):
    """Geraten wird nicht: die SKR03-Erlöskonten liegen nicht als Quelle vor."""
    text = extf.stapel([], "2026-07", erzeugt=ERZEUGT, rahmen="SKR03",
                       kassenblaetter=[_blatt(einnahmenBar=100)])
    assert len(text.rstrip("\r\n").split("\r\n")) == 2
    assert "SKR03" in capsys.readouterr().out


# ————— Das Format gegen einen echten Kanzlei-Export (03.09.2026) —————
#
# Vergleichsstück ist `historie/2026/stapel.csv` aus Ninas Belegbox — ein
# Buchungsstapel, den die Kanzlei selbst aus DATEV exportiert hat. Er sagt
# zwei Dinge über babus Datei: Formatversion 12 statt 13, und 124 Spalten
# statt 120. Die Einzelheiten stehen in
# docs/uebergabe-datev-2026-09-02/23-referenzstapel-kanzlei.md.

SPALTENZEILE = (
    "Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ Umsatz;"
    "Kurs;Basis-Umsatz;WKZ Basis-Umsatz;Konto;"
    "Gegenkonto (ohne BU-Schlüssel);BU-Schlüssel;Belegdatum;"
    "Belegfeld 1;Belegfeld 2;Skonto;Buchungstext;Postensperre;"
    "Diverse Adressnummer;Geschäftspartnerbank;Sachverhalt;Zinssperre;"
    "Beleglink;Beleginfo - Art 1;Beleginfo - Inhalt 1;"
    "Beleginfo - Art 2;Beleginfo - Inhalt 2;Beleginfo - Art 3;"
    "Beleginfo - Inhalt 3;Beleginfo - Art 4;Beleginfo - Inhalt 4;"
    "Beleginfo - Art 5;Beleginfo - Inhalt 5;Beleginfo - Art 6;"
    "Beleginfo - Inhalt 6;Beleginfo - Art 7;Beleginfo - Inhalt 7;"
    "Beleginfo - Art 8;Beleginfo - Inhalt 8;KOST1 - Kostenstelle;"
    "KOST2 - Kostenstelle;Kost-Menge;EU-Land u. UStID;EU-Steuersatz;"
    "Abw. Versteuerungsart;Sachverhalt L+L;Funktionsergänzung L+L;"
    "BU 49 Hauptfunktionstyp;BU 49 Hauptfunktionsnummer;"
    "BU 49 Funktionsergänzung;Zusatzinformation - Art 1;"
    "Zusatzinformation - Inhalt 1;Zusatzinformation - Art 2;"
    "Zusatzinformation - Inhalt 2;Zusatzinformation - Art 3;"
    "Zusatzinformation - Inhalt 3;Zusatzinformation - Art 4;"
    "Zusatzinformation - Inhalt 4;Zusatzinformation - Art 5;"
    "Zusatzinformation - Inhalt 5;Zusatzinformation - Art 6;"
    "Zusatzinformation - Inhalt 6;Zusatzinformation - Art 7;"
    "Zusatzinformation - Inhalt 7;Zusatzinformation - Art 8;"
    "Zusatzinformation - Inhalt 8;Zusatzinformation - Art 9;"
    "Zusatzinformation - Inhalt 9;Zusatzinformation - Art 10;"
    "Zusatzinformation - Inhalt 10;Zusatzinformation - Art 11;"
    "Zusatzinformation - Inhalt 11;Zusatzinformation - Art 12;"
    "Zusatzinformation - Inhalt 12;Zusatzinformation - Art 13;"
    "Zusatzinformation - Inhalt 13;Zusatzinformation - Art 14;"
    "Zusatzinformation - Inhalt 14;Zusatzinformation - Art 15;"
    "Zusatzinformation - Inhalt 15;Zusatzinformation - Art 16;"
    "Zusatzinformation - Inhalt 16;Zusatzinformation - Art 17;"
    "Zusatzinformation - Inhalt 17;Zusatzinformation - Art 18;"
    "Zusatzinformation - Inhalt 18;Zusatzinformation - Art 19;"
    "Zusatzinformation - Inhalt 19;Zusatzinformation - Art 20;"
    "Zusatzinformation - Inhalt 20;Stück;Gewicht;Zahlweise;"
    "Forderungsart;Veranlagungsjahr;Zugeordnete Fälligkeit;Skontotyp;"
    "Auftragsnummer;Buchungstyp;USt-Schlüssel (Anzahlungen);"
    "EU-Land (Anzahlungen);Sachverhalt L+L (Anzahlungen);"
    "EU-Steuersatz (Anzahlungen);Erlöskonto (Anzahlungen);Herkunft-Kz;"
    "Leerfeld;KOST-Datum;SEPA-Mandatsreferenz;Skontosperre;"
    "Gesellschaftername;Beteiligtennummer;Identifikationsnummer;"
    "Zeichnernummer;Postensperre bis;Bezeichnung SoBil-Sachverhalt;"
    "Kennzeichen SoBil-Buchung;Festschreibung;Leistungsdatum;"
    "Datum Zuord. Steuerperiode;Fälligkeit;Generalumkehr (GU);"
    "Steuersatz;Land;Abrechnungsreferenz;BVV-Position;"
    "EU-Land u. UStID (Ursprung);EU-Steuersatz (Ursprung)"
)


def test_spalten_entsprechen_der_kanzlei_referenz():
    """Die Spaltenzeile ist eingefroren — Wort für Wort, Stelle für Stelle.

    Sie ist der Vertrag mit der Kanzlei-Software: jede Buchungszeile zählt
    ihre Felder daran ab (`_zeile` baut `[""] * len(SPALTEN)`), und wer
    hier eine Spalte einschiebt, verschiebt stillschweigend jede Zahl in
    jeder Datei. Bricht dieser Test, ist das keine Kleinigkeit — dann muss
    jemand nachsehen, ob die Verschiebung gewollt war.
    """
    assert len(extf.SPALTEN) == 124
    assert ";".join(extf.SPALTEN) == SPALTENZEILE
    # Die vier, die zur Referenz dazukamen, stehen hinten und bleiben leer.
    assert extf.SPALTEN[-4:] == ["Abrechnungsreferenz", "BVV-Position",
                                 "EU-Land u. UStID (Ursprung)",
                                 "EU-Steuersatz (Ursprung)"]
    # Die Stellen, an denen wirklich etwas steht, haben sich NICHT bewegt.
    for stelle, name in ((0, "Umsatz (ohne Soll/Haben-Kz)"),
                         (1, "Soll/Haben-Kennzeichen"), (6, "Konto"),
                         (7, "Gegenkonto (ohne BU-Schlüssel)"),
                         (8, "BU-Schlüssel"), (9, "Belegdatum"),
                         (10, "Belegfeld 1"), (13, "Buchungstext")):
        assert extf.SPALTEN[stelle] == name


def test_jede_buchungszeile_hat_die_volle_spaltenzahl():
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT)
    for zeile in text.rstrip("\r\n").split("\r\n")[1:]:
        assert len(zeile.split(";")) == 124, zeile[:60]


def test_kopf_formatversion_12():
    """Der Kanzlei-Export trägt 12 — babu schrieb 13 und lief damit der
    Software voraus. Gleichziehen, nicht vorauseilen."""
    kopf = extf.stapel([], "2026-07", erzeugt=ERZEUGT).split("\r\n")[0].split(";")
    assert kopf[4] == "12"
    # Feld 27 (die Kontenrahmen-Angabe) bleibt leer — auch in der Referenz
    # steht dort nichts. Wer ihn füllte, behauptete etwas über die
    # Einstellung der Kanzlei, das babu nicht weiß.
    assert kopf[26] == ""
    assert len(kopf) == 31


def test_als_bytes_utf8_bom():
    """Windows-1252 bleibt der Standard; UTF-8 gibt es auf Wunsch."""
    text = extf.stapel([GOLDEN], "2026-07", erzeugt=ERZEUGT)
    standard = extf.als_bytes(text)
    assert not standard.startswith(b"\xef\xbb\xbf")
    assert "ä".encode("cp1252") in standard

    utf8 = extf.als_bytes(text, utf8_bom=True)
    assert utf8.startswith(b"\xef\xbb\xbf")
    assert utf8[3:].decode("utf-8") == text
    assert "ä".encode("utf-8") in utf8


def test_utf8_rettet_zeichen_die_windows_1252_nicht_kennt():
    """`errors="replace"` macht aus einem türkischen ğ ein Fragezeichen —
    in UTF-8 bleibt der Lieferantenname stehen, wie er geschrieben wird."""
    review = _mit_text("Einkauf Doğan Friseurbedarf")
    text = extf.stapel([review], "2026-08", erzeugt=ERZEUGT)
    assert "?" in extf.als_bytes(text).decode("cp1252")
    assert "Doğan" in extf.als_bytes(text, utf8_bom=True).decode("utf-8-sig")


# ————— Gutschriften: positiver Betrag, Kennzeichen H (03.09.2026) —————
#
# Eine Gutschrift trägt ihr Minus seit Ninas Anmerkung P1-26 schon in den
# Beträgen (gemma_buchung setzt das Vorzeichen einmal). Im Stapel wurde
# daraus bis heute `-119,00;S` — ein negativer Betrag in der Umsatzspalte,
# den DATEV beim Import ablehnt. Richtig ist `119,00;H`.

def _gutschrift(brutto=-40.00, satz=19, **rest):
    r = {"felder": {"brutto": brutto, "ust_satz": satz, "datum": "12.08.2026",
                    "beleg_nr": "GS-7", "gutschrift": True},
         "einschaetzung": {"konto_skr04": "5100"},
         "semantik": {"belegart": "Erstattung"},
         "vlm": {"buchungstext": "Rücksendung Friseurbedarf"}}
    r["felder"].update(rest)
    return r


def test_gutschrift_steht_positiv_im_haben():
    z = extf.buchungszeilen(_gutschrift())[0]
    assert z["umsatz"] == "40,00"          # kein Minus in der Umsatzspalte
    assert z["sh"] == "H"
    assert extf._zeile(z).split(";")[:2] == ["40,00", "H"]


def test_eine_ausgabe_bleibt_im_soll():
    z = extf.buchungszeilen(_mit_satz(19))[0]
    assert z["sh"] == "S"
    assert extf._zeile(z).split(";")[1] == "S"


def test_gutschrift_im_mehrsatz_zieht_beide_zeilen_ins_haben():
    """Ein Beleg steht auf EINER Seite. Halb Soll und halb Haben wäre keine
    Gutschrift, sondern eine Umbuchung, die niemand erfasst hat."""
    r = _gutschrift(brutto=-27.40, steuertabelle=[
        {"satz": 19, "netto": -18.87, "ust": -3.58, "brutto": -22.45},
        {"satz": 7, "netto": -4.63, "ust": -0.32, "brutto": -4.95}])
    zeilen = extf.buchungszeilen(r)
    assert [(z["umsatz"], z["sh"]) for z in zeilen] == [("22,45", "H"),
                                                        ("4,95", "H")]


def test_gutschrift_zieht_auch_eine_positiv_gerechnete_position_mit():
    """Wenn die Steuertabelle das Vorzeichen verloren hat, entscheidet der
    Beleg — nicht die Position."""
    r = _gutschrift(brutto=-27.40, steuertabelle=[
        {"satz": 19, "brutto": 22.45}, {"satz": 7, "brutto": 4.95}])
    assert all(z["sh"] == "H" for z in extf.buchungszeilen(r))


def test_kassentage_stehen_immer_im_soll():
    z = extf.erloeszeilen([_blatt(einnahmenBar=100, ecZahlungen=50)])
    assert z and all(x["sh"] == "S" for x in z)
    assert all(extf._zeile(x).split(";")[1] == "S" for x in z)


def test_de_schreibt_nie_ein_minus():
    assert extf._de(-119.0) == "119,00"
    assert extf._de(119.0) == "119,00"
    assert extf._soll_haben(-0.01) == "H"
    assert extf._soll_haben(0.0) == "S"
    # Ein Betrag unterhalb eines halben Cents ist keine Gutschrift.
    assert extf._soll_haben(-0.001) == "S"
