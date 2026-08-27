"""Zehn Erkennungs- und Kontierungsfehler aus Ninas Anmerkungen.

Alle an echten Belegen gefunden (Liste vom 27.08.2026). Je Punkt steht
hier der Fall, den sie beschrieben hat — die Nummern sind die aus der
Checkliste.
"""
import sys
from pathlib import Path

import einsortieren
import gemma_buchung as gb
import kontierung as kt
import monatsabschluss as ma
import pytest
import vordrucke

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))


def _gebucht(**kw):
    roh = {"status": "gebucht", "dokumentklasse": "beleg",
           "kategorie": "verbrauchsmaterial", "lieferant": "Test",
           "datum": "2026-08-01", "betrag_eur": 119.0, "ust_satz": 19}
    roh.update(kw)
    return gb.buchung_pruefen(roh)


def _beleg(**kw):
    b = {"stamm": "s1", "lieferant": "Test", "brutto": 119.0, "netto": 100.0,
         "ust": 19.0, "ust_satz": 19, "kategorie": "verbrauchsmaterial",
         "konto_skr04": "6850", "status": "geprüft", "summenprobe_ok": True,
         "offen": []}
    b.update(kw)
    return b


# ————— P1-20, P1-16, P2-17: Behördenpost mit Zahlungspflicht ist ein Beleg —————

@pytest.mark.parametrize("text,warum", [
    ("Handwerkskammer Reutlingen — Jahresbeitrag 2026, Bescheid über die "
     "Festsetzung. Steuernummer 93815. Bitte überweisen Sie den Betrag.",
     "HWK-Pflichtbeitrag"),
    ("Stadt Stuttgart, Bescheid über Abfallgebühren 2026. Festgesetzt "
     "wird ein Betrag von 214,80 EUR. Rechtsbehelfsbelehrung.",
     "Abfallgebührenbescheid"),
    ("ARD ZDF Deutschlandradio Beitragsservice — Rundfunkbeitrag für Ihre "
     "Betriebsstätte. Festgesetzt.", "Rundfunkbeitrag"),
    ("Zahlungserinnerung — Mahnung Nr. 2 zur Rechnung 4711. Mahngebühr "
     "5,00 EUR. Bitte zahlen Sie bis zum 15.09.2026.", "Mahnung"),
])
def test_zu_zahlende_behoerdenpost_wird_beleg(text, warum):
    d = einsortieren.entscheiden(text)
    assert d["art"] == "beleg", f"{warum} gehört zu den Belegen, nicht: {d}"
    assert d["ziel"] == "docs"


def test_echte_behoerdenpost_bleibt_post_vom_amt():
    """Die Gegenprobe: ein Bescheid ohne Zahlungspflicht bleibt, wo er war."""
    d = einsortieren.entscheiden(
        "Finanzamt Stuttgart — Bescheid über die gesonderte Feststellung. "
        "Rechtsbehelfsbelehrung: Gegen diesen Bescheid ist der Einspruch "
        "gegeben. Eine Betriebsprüfung wird angeordnet.")
    assert d["art"] == "behoerde"


# ————— P1-29, P2-21, P1-23, P1-24, P2-22: neue Kategorien mit echten Konten —————

@pytest.mark.parametrize("code,skr04,skr03", [
    ("kammerbeitrag", "6420", "4380"),
    ("grundstueck", "6340", "4270"),
    ("abgaben", "6430", "4390"),
    ("steuerberatung", "6830", "4955"),
    ("rechtsberatung", "6825", "4950"),
])
def test_neue_kategorien_tragen_beide_rahmen(code, skr04, skr03):
    k = kt.KATEGORIEN[code]
    assert k.konto("SKR04") == skr04
    assert k.konto("SKR03") == skr03
    assert k.geprueft, "ungeprüfte Konten gehören nicht in Gemmas Katalog"


def test_die_neuen_kategorien_stehen_in_gemmas_katalog():
    katalog = gb.katalog_text("SKR04")
    for code in ("kammerbeitrag", "grundstueck", "abgaben",
                 "steuerberatung", "rechtsberatung"):
        assert f"  {code}:" in katalog, code


# ————— P2-22: die BWA kennt ihre Konten, statt alles „Sonstiges" zu nennen —————

def test_keine_kategorie_faellt_mehr_unbeabsichtigt_in_sonstiges():
    bekannt = {k for _, _, konten in ma.KOSTENGRUPPEN for k in konten}
    bekannt.update(ma.NEUTRALE_KONTEN)
    unbekannt = sorted(k.skr04 for k in kt.KATEGORIEN.values()
                       if k.skr04 and k.skr04 not in bekannt)
    assert not unbekannt, f"ohne BWA-Gruppe: {unbekannt}"


def test_privatentnahme_ist_keine_betriebsausgabe():
    """Sie lag als „Sonstiges" in den Kosten und drückte das Ergebnis."""
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    ohne = ma.bwa("2026-08", erloese, [_beleg()])
    mit = ma.bwa("2026-08", erloese, [
        _beleg(),
        _beleg(stamm="p", kategorie="privat", konto_skr04="2100",
               brutto=500.0, netto=500.0, ust=0.0),
    ])
    assert mit["kosten_netto"] == ohne["kosten_netto"]
    assert mit["ergebnis"] == ohne["ergebnis"]
    # Verschwinden darf sie trotzdem nicht.
    assert mit["neutral_summe"] == 500.0
    assert mit["neutral"][0]["konto"] == "2100"


def test_geldtransit_und_ust_zahlung_zaehlen_nicht_als_kosten():
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    b = ma.bwa("2026-08", erloese, [
        _beleg(stamm="g", kategorie="geldtransit", konto_skr04="1460",
               brutto=300.0, netto=300.0, ust=0.0),
        _beleg(stamm="u", kategorie="ust_zahlung", konto_skr04="3820",
               brutto=127.0, netto=127.0, ust=0.0),
    ])
    assert b["kosten_netto"] == 0.0
    assert b["neutral_summe"] == 427.0


def test_beratungskosten_bekommen_ihre_eigene_zeile():
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    b = ma.bwa("2026-08", erloese, [
        _beleg(stamm="stb", kategorie="steuerberatung", konto_skr04="6830",
               brutto=357.0, netto=300.0, ust=57.0)])
    gruppen = {g["schluessel"]: g for g in b["gruppen"]}
    assert "beratung" in gruppen, gruppen
    assert "sonstiges" not in gruppen
    assert gruppen["beratung"]["netto"] == 300.0


# ————— P1-21: keine erfundene Umsatzsteuer auf hoheitliche Gebühren —————

def test_hoheitliche_gebuehren_liefern_keine_vorsteuer():
    vorsteuer, befunde = vordrucke.vorsteuer_geprueft([
        _beleg(stamm="hwk", kategorie="kammerbeitrag", konto_skr04="6420",
               brutto=238.0, netto=200.0, ust=38.0),
        _beleg(stamm="abfall", kategorie="grundstueck", konto_skr04="6340",
               brutto=119.0, netto=100.0, ust=19.0),
    ])
    assert vorsteuer["vorsteuer"] == 0.0
    gesperrt = [b for b in befunde if b["folge"] == "keine_vorsteuer"]
    assert len(gesperrt) == 2
    assert "nicht steuerbar" in gesperrt[0]["befund"]


# ————— P1-26: Gutschriften mindern, statt ein zweites Mal zu belasten —————

def test_gutschrift_dreht_das_vorzeichen_genau_einmal():
    e = _gebucht(gutschrift=True, betrag_eur=119.0, kategorie="wareneinkauf",
                 positionen=[{"bezeichnung": "Retoure Shampoo",
                              "betrag": 119.0, "ust_satz": 19,
                              "kategorie": "wareneinkauf"}])
    b = e["buchung"]
    assert b["gutschrift"] is True
    assert b["betrag_eur"] == -119.0
    assert b["positionen"][0]["betrag"] == -119.0
    # Auch die Steuertabelle trägt das Minus — sonst stünde in Kz 66 ein Plus.
    assert b["steuersaetze"][0]["ust"] == -19.0


def test_gutschrift_mindert_vorsteuer_und_kosten():
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    belege = [_beleg(stamm="kauf"),
              _beleg(stamm="retoure", gutschrift=True, brutto=-59.5,
                     netto=-50.0, ust=-9.5)]
    vorsteuer = ma.vorsteuer_monat(belege)
    assert vorsteuer["vorsteuer"] == 9.5           # 19,00 − 9,50
    b = ma.bwa("2026-08", erloese, belege)
    assert b["kosten_netto"] == 50.0               # 100,00 − 50,00


def test_ein_normaler_beleg_bleibt_positiv():
    b = _gebucht()["buchung"]
    assert b["gutschrift"] is False
    assert b["betrag_eur"] == 119.0


# ————— P1-11, P1-12, P1-19, P1-15, P1-13, P1-24: die Regeln im Prompt —————

@pytest.mark.parametrize("kern", [
    "Reverse Charge",                 # P1-19 keine erfundene Vorsteuer
    "Skonto-ANGEBOT",                 # P1-11 Angebot ist kein Abzug
    "RECHNUNGSDATUM",                 # P1-12 nicht die Fälligkeit
    "Mahnung oder Zahlungserinnerung",  # P1-16 Mahnung ist ein Beleg
    "Mahngebühren",                   # P1-15 keine Umsatzsteuer
    "ZUSAMMENHÄNGENDES Schema",       # P1-13 Summenlogik
    "„19 %“ ist niemals 19,00 €",     # P1-02 Prozent ist kein Betrag
    "gutschrift",                     # P1-26 Gutschrift als Kennzeichen
    "kammerbeitrag",                  # P1-20/P1-29 Kammerbeitrag
])
def test_die_regel_steht_im_prompt(kern):
    prompt = gb.voller_prompt("Profil", ["Zeile"], [])
    assert kern in prompt, kern


def test_flugkosten_hinweis_nennt_die_internationale_ausnahme():
    hinweis = kt.KATEGORIEN["fahrt"].hinweis
    assert "Flug" in hinweis
    assert "KEINE deutsche" in hinweis      # P2-18


def test_gemma_nennt_keine_kontonummern_in_der_begruendung():
    """Live-Fund vom 28.08.: Gemma schrieb „Materialeinsatz (SKR04 5400)",
    gebucht wurde aber korrekt auf 5100. Die Nummer kommt aus dem Katalog,
    nicht aus dem Modell — in der Begründung hat sie nichts zu suchen."""
    prompt = gb.voller_prompt(gb.profil_text({}), ["Zeile"], [])
    assert "KEINE Kontonummer" in prompt


# ————— Runde 2: die nächsten sieben Punkte —————

@pytest.mark.parametrize("art,text", [
    ("beleg", "Allianz Versicherung — Beitragsrechnung zum Versicherungsschein "
              "4711. Jahresbeitrag 2026. Laufzeit 01.01. bis 31.12.2026. "
              "Beitrag 486,00 EUR. Bitte überweisen Sie den Betrag."),
    ("beleg", "Leasingvertrag Nr. 88123 — Monatliche Rate August 2026. "
              "Vertragslaufzeit 48 Monate. Rate netto 210,00 EUR. "
              "Zu zahlen 249,90 EUR."),
    ("vertrag", "Mietvertrag zwischen Herrn Müller und Frau Nina. "
                "Mietgegenstand: Ladenlokal. Vertragsbeginn 01.01.2026, "
                "Kündigungsfrist drei Monate. Es wird vereinbart, dass ..."),
    ("vertrag", "Versicherungsschein Nr. 4711. Vertragsbeginn 01.01.2026. "
                "Kündigungsfrist drei Monate. Es wird vereinbart, dass der "
                "Versicherungsschutz ..."),
])
def test_die_rechnung_zu_einem_vertrag_ist_ein_beleg(art, text):
    """Eine Beitrags- oder Leasingrechnung nennt Versicherungsschein,
    Laufzeit und Vertragsnummer — und landete deshalb im Vertragsfach,
    wo sie in der Auswertung fehlte."""
    assert einsortieren.entscheiden(text)["art"] == art, text[:50]


def test_das_auffangkonto_bekommt_konkurrenz():
    """Ninas P2-22: „Sonstiger Betriebsbedarf" wurde zu oft gewählt, weil
    es für Werkzeug, Wartung und Bankgebühren nichts Näheres gab."""
    for code, skr04 in (("werkzeug", "6845"), ("wartung", "6495"),
                        ("bankgebuehren", "6855")):
        assert kt.KATEGORIEN[code].konto("SKR04") == skr04
        assert f"  {code}:" in gb.katalog_text("SKR04")


def test_der_reisezweck_wird_erfragt():
    prompt = " ".join(gb.voller_prompt(gb.profil_text({}), ["Lufthansa"],
                                       []).split())
    assert "nach dem ANLASS der Reise" in prompt
    assert "Wozu war die Reise?" in prompt
    assert "War sie privat, ist es kategorie privat." in prompt


def test_guthaben_je_lieferant_wird_gerechnet():
    import babu_web as bw
    belege = [
        {"lieferant": "Wella", "brutto": -120.0, "gutschrift": True},
        {"lieferant": "Wella", "brutto": 50.0},
        {"lieferant": "Edeka", "brutto": 30.0},
    ]
    g = {x["lieferant"]: x for x in bw.guthaben_je_lieferant(belege)}
    assert "Edeka" not in g, "ohne Gutschrift kein Eintrag"
    assert g["Wella"]["guthaben"] == 120.0
    assert g["Wella"]["seither_bezahlt"] == 50.0
    assert g["Wella"]["vermutlich_offen"] == 70.0


def test_guthaben_steht_im_fallwissen_des_chats():
    import wissen
    text = wissen.kontext("Habe ich noch Guthaben bei Wella?", {
        "einstellungen": {"betrieb_name": "Salon Nina"},
        "guthaben": [{"lieferant": "Wella", "gutschriften": 1,
                      "guthaben": 120.0, "seither_bezahlt": 50.0,
                      "vermutlich_offen": 70.0}],
        "belege": [], "kassenblaetter": [], "vertraege": [], "rechnungen": [],
        "team": [], "fristen": [], "zahlen": {}, "dokumente": [],
    })
    assert "GUTSCHRIFTEN VON LIEFERANTEN" in text
    assert "Wella" in text and "70,00" in text


def test_die_belegarten_aus_ninas_beschwerde_haben_alle_eine_kategorie():
    """P2-23 nennt die Fälle beim Namen: Kammerbeiträge, Gebühren,
    Steuerberatung, Kundenbewirtung, Verbrauchsmaterial. Für jeden gibt
    es jetzt eine eigene Kategorie mit eigenem Konto — keiner landet mehr
    im Auffangkonto 6850."""
    erwartet = {"kammerbeitrag": "6420", "abgaben": "6430",
                "steuerberatung": "6830", "aufmerksamkeit": "6605",
                "verbrauchsmaterial": "5100"}
    for code, konto in erwartet.items():
        k = kt.KATEGORIEN[code]
        assert k.konto("SKR04") == konto, code
        assert k.konto("SKR04") != "6850"
        assert f"  {code}:" in gb.katalog_text("SKR04")


def test_der_export_enthaelt_nur_belege_keine_kassenblaetter():
    """Ninas Frage 5-2 — die Antwort steht im Code: der Buchungsstapel
    baut ausschließlich auf den Belegen des Monats auf."""
    import inspect

    import babu_web as bw
    quelle = inspect.getsource(bw.api_export)
    assert 'idx["belege"]' in quelle
    assert "kassenblaetter" not in quelle
