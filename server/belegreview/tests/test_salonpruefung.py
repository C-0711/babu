"""Die Salonprüfung: Stammdaten ernten und Beraterrechnungen nachrechnen.

Zwei Dinge müssen hier stimmen, und zwar aus verschiedenen Gründen.

Die geernteten Stammdaten landen anschließend auf jeder Rechnung, die Nina
schreibt — eine falsch gelesene Steuernummer steht dann überall. Deshalb
wird nur geerntet, was eindeutig ist.

Und die Befunde zu den Rechnungen der Kanzlei sagen jemandem, dass etwas
nicht stimmt. Ein falscher Befund beschädigt ein Vertrauensverhältnis.
Deshalb wird nur beanstandet, was sich ohne Gebührentabelle beweisen lässt.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salonpruefung import (Befund, Position, bericht, felder_aus_text,  # noqa: E402
                           felder_ernten, position_aus_text,
                           steuerberater_pruefen)


def feld(felder, schluessel):
    treffer = [f for f in felder if f.schluessel == schluessel]
    return treffer[0] if treffer else None


# ————— Ernte aus dem Klartext —————

BESCHEID = """
Finanzamt Stuttgart-Körperschaften
Bescheid für 2025 über Einkommensteuer
Steuernummer 93815/12345
Nina Weingärtle
Hauptstraße 3
70173 Stuttgart
"""


def test_steuernummer_wird_geerntet():
    f = felder_aus_text(BESCHEID, quelle="bescheid.pdf", art="bescheid")
    assert feld(f, "steuernummer").wert == "93815/12345"


def test_finanzamt_wird_geerntet():
    f = felder_aus_text(BESCHEID, quelle="bescheid.pdf", art="bescheid")
    assert feld(f, "finanzamt").wert.startswith("Stuttgart")


def test_plz_und_ort_werden_geerntet():
    f = felder_aus_text(BESCHEID, quelle="bescheid.pdf", art="bescheid")
    assert feld(f, "betrieb_plz").wert == "70173"
    assert feld(f, "betrieb_ort").wert == "Stuttgart"


def test_jedes_feld_nennt_seine_quelle():
    for f in felder_aus_text(BESCHEID, quelle="bescheid.pdf", art="bescheid"):
        assert f.quelle == "bescheid.pdf"
        assert f.regel


@pytest.mark.parametrize("text, schluessel, wert", [
    ("USt-IdNr. DE123456789", "ust_id", "DE123456789"),
    ("IBAN DE02 1203 0000 0000 2020 51", "iban", "DE02120300000000202051"),
    ("BIC GENODEF1S02", "bic", "GENODEF1S02"),
    ("Tel.: 0711 1234567", "telefon", "0711 1234567"),
    ("hallo@supremebeauty.de", "email", "hallo@supremebeauty.de"),
    ("Salon SupremeBeauty GmbH", "rechtsform", "GmbH"),
    ("Friseur Weingärtle e.K.", "rechtsform", "e.K."),
])
def test_einzelne_felder(text, schluessel, wert):
    f = felder_aus_text(text, quelle="x.pdf")
    assert feld(f, schluessel) is not None, f"{schluessel} nicht gefunden"
    assert feld(f, schluessel).wert == wert


def test_gmbh_und_co_kg_gewinnt_vor_gmbh():
    """Die längere Rechtsform muss zuerst greifen, sonst steht überall GmbH."""
    f = felder_aus_text("Muster GmbH & Co. KG", quelle="x.pdf")
    assert feld(f, "rechtsform").wert == "GmbH & Co. KG"


def test_kleinunternehmer_wird_erkannt():
    f = felder_aus_text("Kein Ausweis von Umsatzsteuer nach § 19 UStG",
                        quelle="r.pdf")
    assert feld(f, "kleinunternehmer").wert is True


def test_euer_wird_als_abschlussart_erkannt():
    f = felder_aus_text("Einnahmen-Überschuss-Rechnung 2025", quelle="e.pdf")
    assert feld(f, "abschluss_art").wert == "EÜR"


def test_nichts_wird_erfunden():
    f = felder_aus_text("Ein Blatt Papier ohne alles.", quelle="x.pdf")
    assert f == []


def test_felder_landen_im_richtigen_bereich():
    f = felder_aus_text(BESCHEID + "\nIBAN DE02 1203 0000 0000 2020 51",
                        quelle="b.pdf")
    assert feld(f, "steuernummer").bereich == "einstellungen"
    assert feld(f, "iban").bereich == "briefkopf"
    assert feld(f, "betrieb_ort").bereich == "briefkopf"


# ————— Ernte über mehrere Unterlagen —————

def test_der_bescheid_schlaegt_den_briefbogen():
    """Ein Bescheid vom Finanzamt ist verlässlicher als ein Briefkopf."""
    f = felder_ernten([
        {"datei": "brief.pdf", "art": "sonstiges",
         "text": "Steuernummer 11/111/11111"},
        {"datei": "bescheid.pdf", "art": "bescheid",
         "text": "Steuernummer 93815/12345"},
    ])
    assert feld(f, "steuernummer").wert == "93815/12345"
    assert feld(f, "steuernummer").quelle == "bescheid.pdf"


def test_ein_widerspruch_verliert_die_sicherheit():
    """Zwei Unterlagen, zwei Nummern — dann darf babu nicht still entscheiden.
    Beide Arten müssen die Steuernummer liefern dürfen, sonst gibt es gar
    keinen Widerspruch."""
    f = felder_ernten([
        {"datei": "a.pdf", "art": "bescheid", "text": "Steuernummer 93815/12345"},
        {"datei": "b.pdf", "art": "euer", "text": "Steuernummer 11/111/11111"},
    ])
    s = feld(f, "steuernummer")
    assert s.sicher is False
    assert "11/111/11111" in s.regel


def test_einigkeit_bleibt_sicher():
    f = felder_ernten([
        {"datei": "a.pdf", "art": "bescheid", "text": "Steuernummer 93815/12345"},
        {"datei": "b.pdf", "art": "euer", "text": "Steuernummer 93815/12345"},
    ])
    assert feld(f, "steuernummer").sicher is True


def test_ohne_unterlagen_keine_felder():
    assert felder_ernten([]) == []


# ————— Die Rechnung der Kanzlei —————

VOLLSTAENDIG = {"rechnungsnummer": "2026-114", "steuernummer": "93815/00001",
                "datum": "2026-08-01", "zeitraum": "Januar bis Dezember 2025"}


def schweren(befunde, schwere):
    return [b for b in befunde if b.schwere == schwere]


def titel(befunde):
    return [b.titel for b in befunde]


def test_eine_saubere_rechnung_ergibt_keinen_vorwurf():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 7/10", 840.0, "33", 0.7)],
        auslagen=20.0, netto=860.0, ust=163.40, brutto=1023.40,
        angaben=VOLLSTAENDIG)
    assert schweren(b, "falsch") == []
    assert all(x.schwere == "hinweis" for x in b), titel(b)


def test_ueber_dem_zehntel_rahmen_ist_falsch():
    """§ 33 StBVV lässt für Buchführung höchstens 12/10 zu."""
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 15/10", 1800.0, "33", 1.5)],
        netto=1800.0, ust=342.0, brutto=2142.0, angaben=VOLLSTAENDIG)
    hart = schweren(b, "falsch")
    assert hart and "Buchführung" in hart[0].titel
    assert "12/10" in hart[0].text


def test_hoechstsatz_wird_zur_nachfrage_nicht_zum_vorwurf():
    b = steuerberater_pruefen(
        positionen=[Position("Jahresabschluss § 35 StBVV, 40/10", 4000.0, "35", 4.0)],
        netto=4000.0, ust=760.0, brutto=4760.0, angaben=VOLLSTAENDIG)
    assert any(x.schwere == "nachfragen" and "oberen Rand" in x.titel for x in b)
    assert schweren(b, "falsch") == []


def test_unter_dem_rahmen_ist_nur_ein_hinweis():
    b = steuerberater_pruefen(
        positionen=[Position("Steuererklärung § 24 StBVV, 0/10", 50.0, "24", 0.0)],
        netto=50.0, ust=9.50, brutto=59.50, angaben=VOLLSTAENDIG)
    hinweise = [x for x in b if "Unter dem Rahmen" in x.titel]
    assert hinweise and hinweise[0].schwere == "hinweis"


def test_auslagenpauschale_ueber_zwanzig_euro():
    """§ 16 StBVV: 20 % der Gebühren, höchstens 20 € je Angelegenheit."""
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        auslagen=45.0, netto=645.0, ust=122.55, brutto=767.55,
        angaben=VOLLSTAENDIG)
    treffer = [x for x in b if "Auslagenpauschale" in x.titel]
    assert treffer and treffer[0].schwere == "falsch"
    assert treffer[0].betrag == 25.0


def test_auslagenpauschale_bei_kleiner_rechnung():
    """Bei 60 € Gebühren sind 20 % = 12 € die Grenze, nicht 20 €."""
    b = steuerberater_pruefen(
        positionen=[Position("Kurze Auskunft § 21 StBVV", 60.0)],
        auslagen=20.0, netto=80.0, ust=15.20, brutto=95.20,
        angaben=VOLLSTAENDIG)
    treffer = [x for x in b if "Auslagenpauschale" in x.titel]
    assert treffer and treffer[0].betrag == 8.0


def test_auslagen_genau_an_der_grenze_sind_in_ordnung():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        auslagen=20.0, netto=620.0, ust=117.80, brutto=737.80,
        angaben=VOLLSTAENDIG)
    assert not [x for x in b if "Auslagenpauschale" in x.titel]


def test_dieselbe_leistung_zweimal():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6),
                    Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=1200.0, ust=228.0, brutto=1428.0, angaben=VOLLSTAENDIG)
    assert any("Zweimal dasselbe" in x.titel for x in b)


def test_pauschale_neben_einzelgebuehren():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=600.0, ust=114.0, brutto=714.0, angaben=VOLLSTAENDIG,
        pauschale=True)
    assert any("Pauschale" in x.titel for x in b)


def test_die_rechnung_geht_nicht_auf():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=600.0, ust=114.0, brutto=750.0, angaben=VOLLSTAENDIG)
    hart = [x for x in b if "geht nicht auf" in x.titel]
    assert hart and hart[0].schwere == "falsch"


def test_falscher_steuersatz():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=600.0, ust=42.0, brutto=642.0, angaben=VOLLSTAENDIG)
    assert any("Steuersatz" in x.titel for x in b)


def test_posten_ergeben_nicht_die_summe():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=900.0, ust=171.0, brutto=1071.0, angaben=VOLLSTAENDIG)
    assert any("ergeben nicht die Summe" in x.titel for x in b)


@pytest.mark.parametrize("weglassen, wort", [
    ("rechnungsnummer", "Rechnungsnummer"),
    ("steuernummer", "Steuernummer"),
    ("datum", "Rechnungsdatum"),
    ("zeitraum", "Leistungszeitraum"),
])
def test_pflichtangaben_nach_paragraf_14(weglassen, wort):
    angaben = dict(VOLLSTAENDIG)
    del angaben[weglassen]
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=600.0, ust=114.0, brutto=714.0, angaben=angaben)
    treffer = [x for x in b if "Angaben fehlen" in x.titel]
    assert treffer and wort.lower() in treffer[0].text.lower()


def test_fehlender_gegenstandswert_wird_gesagt_nicht_geraten():
    """Ohne Gegenstandswert lässt sich der Betrag nicht nachrechnen — dann
    behauptet babu auch nichts."""
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 6/10", 600.0, "33", 0.6)],
        netto=600.0, ust=114.0, brutto=714.0, angaben=VOLLSTAENDIG)
    treffer = [x for x in b if "Gegenstandswert" in x.titel]
    assert treffer and treffer[0].schwere == "hinweis"


def test_befunde_stehen_nach_schwere():
    b = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 15/10", 1800.0, "33", 1.5)],
        auslagen=50.0, netto=1850.0, ust=351.50, brutto=2201.50, angaben={})
    reihe = [x.schwere for x in b]
    assert reihe == sorted(reihe, key=lambda s: {"falsch": 0, "nachfragen": 1,
                                                 "hinweis": 2}[s])


def test_leere_rechnung_stuerzt_nicht_ab():
    assert isinstance(steuerberater_pruefen(positionen=[]), list)


# ————— Zeilen deuten —————

@pytest.mark.parametrize("text, paragraf, zehntel", [
    ("Buchführung § 33 StBVV, 6/10", "33", 0.6),
    ("Jahresabschluss gem. § 35 StBVV 25/10", "35", 2.5),
    ("Auslagen", None, None),
    ("§ 24 Einkommensteuererklärung 3/10", "24", 0.3),
])
def test_position_aus_text(text, paragraf, zehntel):
    p = position_aus_text(text, 100.0)
    assert p.paragraf == paragraf
    assert p.zehntel == zehntel


def test_eine_unbekannte_schwere_faellt_sofort_auf():
    with pytest.raises(ValueError):
        Befund("egal", "x", "y")


# ————— Der Bericht —————

def test_der_bericht_zeigt_alles():
    felder = felder_ernten([{"datei": "bescheid.pdf", "art": "bescheid",
                             "text": BESCHEID}])
    befunde = steuerberater_pruefen(
        positionen=[Position("Buchführung § 33 StBVV, 15/10", 1800.0, "33", 1.5)],
        netto=1800.0, ust=342.0, brutto=2142.0, angaben=VOLLSTAENDIG)
    text = bericht(salon="Salon SupremeBeauty",
                   dokumente=[{"datei": "bescheid.pdf", "art": "bescheid",
                               "art_label": "Steuerbescheid",
                               "ablage": "abschluss/2025"}],
                   felder=felder, befunde=befunde,
                   kennzahlen={"Umsatz": 128000.0},
                   offen=["Der Mietvertrag fehlt noch."])
    assert "Salon SupremeBeauty" in text
    assert "93815/12345" in text
    assert "Das stimmt nicht:" in text
    assert "bescheid.pdf" in text
    assert "abschluss/2025" in text
    assert "Der Mietvertrag fehlt noch." in text


def test_ein_unsicheres_feld_ist_im_bericht_markiert():
    felder = felder_ernten([
        {"datei": "a.pdf", "art": "bescheid", "text": "Steuernummer 93815/12345"},
        {"datei": "b.pdf", "art": "euer", "text": "Steuernummer 11/111/11111"},
    ])
    text = bericht(salon=None, dokumente=[], felder=felder, befunde=[])
    zeile = [z for z in text.splitlines() if "Steuernummer" in z][0]
    assert "⚠" in zeile


def test_ein_strich_im_wert_zerlegt_die_tabelle_nicht():
    from salonpruefung import Feld
    text = bericht(salon=None, dokumente=[], befunde=[], felder=[
        Feld("betrieb_name", "Salon | Nina", "x.pdf", "gelesen", True, "briefkopf")])
    zeile = [z for z in text.splitlines() if "Name des Salons" in z][0]
    assert r"Salon \| Nina" in zeile


def test_ein_bericht_ohne_alles_ist_trotzdem_lesbar():
    text = bericht(salon=None, dokumente=[], felder=[], befunde=[])
    assert "deinen Salon" in text and "0 Unterlagen" in text


# ————— Die Anschrift für die Rechnung —————

def test_anschrift_wird_zusammengesetzt():
    """rechnungen.py liest `anschrift` als eine Zeile — die muss entstehen."""
    f = felder_aus_text(BESCHEID, quelle="b.pdf")
    assert feld(f, "betrieb_strasse").wert == "Hauptstraße 3"
    assert feld(f, "anschrift").wert == "Hauptstraße 3, 70173 Stuttgart"


def test_eine_halbe_anschrift_wird_nicht_gesetzt():
    """Ohne Straße keine Anschrift — halb ist auf einer Rechnung schlechter
    als gar nicht."""
    f = felder_aus_text("70173 Stuttgart", quelle="b.pdf")
    assert feld(f, "betrieb_ort").wert == "Stuttgart"
    assert feld(f, "anschrift") is None


@pytest.mark.parametrize("zeile, soll", [
    ("Hauptstraße 3", "Hauptstraße 3"),
    ("Königstr. 41", "Königstr. 41"),
    ("Am Marktplatz 7a", "Am Marktplatz 7a"),
    ("Industriering 12", "Industriering 12"),
    ("Nur ein Name", None),
])
def test_strassen(zeile, soll):
    f = felder_aus_text(zeile, quelle="x.pdf")
    treffer = feld(f, "betrieb_strasse")
    assert (treffer.wert if treffer else None) == soll


# ————— Wessen Daten stehen da? —————
#
# Aufgefallen am 22.08.2026 im Trockenlauf über echte Unterlagen: Auf einem
# Steuerbescheid steht oben das Finanzamt mit Anschrift und Bankverbindung.
# Die Ernte hätte auf Ninas Rechnungen die Kontonummer des Finanzamts
# gesetzt. Diese Tests halten fest, dass das nicht wieder passiert.

BESCHEID_MIT_BEHOERDENKOPF = """
Finanzamt Ludwigsburg
Alt-Württ.-Allee 40
71638 Ludwigsburg
Tel.: 07141/18-0
IBAN DE24 6000 0000 0060 4015 00
BIC MARKDEF1600
Bescheid für 2024 über Einkommensteuer
Steuernummer 71015/73457
"""


def test_die_anschrift_des_finanzamts_wird_nicht_uebernommen():
    f = felder_ernten([{"datei": "bescheid.pdf", "art": "bescheid",
                        "text": BESCHEID_MIT_BEHOERDENKOPF}])
    assert feld(f, "anschrift") is None
    assert feld(f, "betrieb_strasse") is None
    assert feld(f, "betrieb_ort") is None


def test_das_konto_des_finanzamts_wird_nicht_uebernommen():
    """Der teuerste denkbare Fehler: fremde IBAN auf der eigenen Rechnung."""
    f = felder_ernten([{"datei": "bescheid.pdf", "art": "bescheid",
                        "text": BESCHEID_MIT_BEHOERDENKOPF}])
    assert feld(f, "iban") is None
    assert feld(f, "bic") is None


def test_die_telefonnummer_der_behoerde_wird_nicht_uebernommen():
    f = felder_ernten([{"datei": "bescheid.pdf", "art": "bescheid",
                        "text": BESCHEID_MIT_BEHOERDENKOPF}])
    assert feld(f, "telefon") is None


def test_steuernummer_und_finanzamt_kommen_sehr_wohl_vom_bescheid():
    """Wofür ein Bescheid da ist, darf er auch sagen."""
    f = felder_ernten([{"datei": "bescheid.pdf", "art": "bescheid",
                        "text": BESCHEID_MIT_BEHOERDENKOPF}])
    assert feld(f, "steuernummer").wert == "71015/73457"
    assert feld(f, "finanzamt").wert.startswith("Ludwigsburg")


def test_der_vermieter_im_mietvertrag_wird_nicht_zur_salonadresse():
    f = felder_ernten([{"datei": "miete.pdf", "art": "vertrag", "text": """
        FBS-Gruppe GmbH · Info@FBS-Gruppe.de · Tel. 07141/95 47 50
        Lindenstraße 12
        71634 Ludwigsburg
        Mietvertrag zwischen Vermieter und Mieter
    """}])
    assert f == []


def test_die_iban_kommt_vom_kontoauszug():
    """Der Kontoinhaber ist die Salonbetreiberin — hier stimmt sie."""
    f = felder_ernten([{"datei": "auszug.pdf", "art": "kontoauszug", "text":
                        "Kontoauszug Nr. 1\nIBAN DE02 1203 0000 0000 2020 51"}])
    assert feld(f, "iban").wert == "DE02120300000000202051"


def test_der_kontoauszug_liefert_keine_steuernummer():
    f = felder_ernten([{"datei": "auszug.pdf", "art": "kontoauszug",
                        "text": "Kontoauszug\nSteuernummer 93815/12345"}])
    assert feld(f, "steuernummer") is None


def test_eine_unbekannte_art_liefert_gar_nichts():
    f = felder_ernten([{"datei": "x.pdf", "art": "irgendwas",
                        "text": BESCHEID_MIT_BEHOERDENKOPF}])
    assert f == []


def test_beide_vokabulare_werden_verstanden():
    """`einsortieren` sagt „behoerde", `abschluss_lesen` sagt „bescheid".
    Fiele eine der beiden durch, lernte babu stillschweigend nichts."""
    for art in ("behoerde", "bescheid"):
        f = felder_ernten([{"datei": "b.pdf", "art": art,
                            "text": BESCHEID_MIT_BEHOERDENKOPF}])
        assert feld(f, "steuernummer") is not None, art
        assert feld(f, "iban") is None, art


def test_ein_kassenbon_liefert_keine_stammdaten():
    f = felder_ernten([{"datei": "bon.jpg", "art": "beleg", "text":
                        "Bäckerei Probe GmbH\nSteuernummer 93815/12345"}])
    assert f == []


@pytest.mark.parametrize("text, soll", [
    ("Finanzamt Ludwigsburg", "Ludwigsburg"),
    ("Finanzamt Stuttgart-Körperschaften", "Stuttgart-Körperschaften"),
    ("An das Finanzamt\nLudwigsburg", "Ludwigsburg"),
    # Der Fehlgriff aus Ninas Erklärungen: hinter der Formularbeschriftung
    # folgt Fließtext, kein Ortsname.
    ("An dasFinanzamt Daten für die mit @ gekennzeichneten Zeilen", None),
    ("Finanzamt Regelfall vor und müssen nicht eingetragen werden", None),
])
def test_finanzamt_nur_wenn_ein_ort_dasteht(text, soll):
    f = felder_aus_text(text, quelle="x.pdf")
    treffer = feld(f, "finanzamt")
    assert (treffer.wert if treffer else None) == soll
