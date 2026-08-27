"""Gemma bucht — aber der Katalog hat das letzte Wort.

Drei Zusagen, die nicht brechen dürfen: Eine Kontonummer kommt NIE vom
Modell, sondern immer aus dem geprüften Katalog. Ein Fragenpaket kommt
EINMAL und als Multiple Choice. Und wer zu viel fragt, bucht nicht mehr —
der Beleg gehört dann auf den Schreibtisch.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemma_buchung  # noqa: E402


# ————— Profil und Katalog —————

def test_profil_nennt_kleinunternehmerin_nur_wenn_sie_eine_ist():
    mit = gemma_buchung.profil_text({"kleinunternehmer": "Ja"})
    ohne = gemma_buchung.profil_text({"kleinunternehmer": "Nein"})
    assert "kein Vorsteuerabzug" in mit
    assert "soweit ausgewiesen" in ohne


def test_katalog_traegt_nur_bestaetigte_konten():
    text = gemma_buchung.katalog_text("SKR04")
    assert "geldtransit" in text          # die wichtige Nicht-Aufwand-Klasse
    assert "gutschein" not in text        # Konto noch nicht bestätigt
    assert "6850" not in text             # Nummern bekommt das Modell nie


def test_prompt_traegt_beleg_profil_und_alte_antworten():
    p = gemma_buchung.voller_prompt(
        "PROFILTEXT", ["Zeile eins"],
        [{"frage": "Privat oder Salon?", "antwort": "Salon"}])
    assert "PROFILTEXT" in p and "Zeile eins" in p
    assert "Privat oder Salon?" in p and "Salon" in p
    assert "Multiple Choice" in p


# ————— Der Katalog hat das letzte Wort —————

def test_kategorie_wird_zur_kontonummer_aus_dem_katalog():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "geldtransit", "betrag": 650,
         "betrag_eur": 650, "ust_satz": 0, "buchungstext": "Kasse an Bank"})
    assert e["status"] == "gebucht"
    assert e["buchung"]["konto"] == "1460"       # SKR04, aus kontierung.py
    assert e["buchung"]["kategorie_name"] == "Geldtransit"


def test_erfundene_kategorie_wird_zur_rueckfrage_nicht_zur_buchung():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "wellness-oase", "betrag": 799})
    assert e["status"] == "fragen"
    assert e["fragen"][0]["optionen"]            # Multiple Choice, nicht offen


def test_unmoeglicher_steuersatz_faellt_auf_null():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "sonstiges", "betrag": 10,
         "betrag_eur": 10, "ust_satz": 16})
    assert e["buchung"]["ust_satz"] == 0


def test_fremdwaehrung_bleibt_sichtbar():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "fahrt", "betrag": 55.74,
         "waehrung": "aed", "betrag_eur": 13.9, "ust_satz": 0})
    assert e["buchung"]["waehrung"] == "AED"
    assert e["buchung"]["betrag_eur"] == 13.9


# ————— Einzelpositionen —————

def test_positionen_werden_gelesen_und_gesaeubert():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "buerobedarf", "betrag": 485.7,
         "betrag_eur": 485.7, "ust_satz": 19, "positionen": [
             {"bezeichnung": "Stifte", "betrag": 12.5, "ust_satz": 19,
              "kategorie": "buerobedarf"},
             {"bezeichnung": "Beistelltisch", "betrag": 299.0, "ust_satz": 19,
              "kategorie": "erfundene_kategorie"},
             {"bezeichnung": "kaputt", "betrag": "keine Zahl"},
         ]})
    p = e["buchung"]["positionen"]
    assert len(p) == 2
    assert p[0]["kategorie"] == "buerobedarf"
    assert p[1]["kategorie"] is None            # erfunden → leer, nie geraten


def test_gemischte_positionen_ohne_hauptkategorie_erkannt():
    einheitlich = {"positionen": [
        {"kategorie": "buerobedarf", "betrag": 400.0},
        {"kategorie": "gwg", "betrag": 50.0}]}
    gemischt = {"positionen": [
        {"kategorie": "buerobedarf", "betrag": 200.0},
        {"kategorie": "gwg", "betrag": 285.7}]}
    assert gemma_buchung.gemischt(einheitlich) is False   # 89 % dominiert
    assert gemma_buchung.gemischt(gemischt) is True       # 59 % — fragen!


# ————— Das Fragenpaket —————

def test_fragenpaket_wird_beschnitten_und_bereinigt():
    e = gemma_buchung.buchung_pruefen({"status": "fragen", "fragen": [
        {"frage": "  Privat oder Salon?  ", "optionen": ["Privat", "Salon", ""]},
        {"frage": "", "optionen": ["egal"]},
        {"frage": "Bar oder Karte?", "optionen": ["Bar", "Karte"]},
    ]})
    assert e["status"] == "fragen"
    assert [f["frage"] for f in e["fragen"]] == ["Privat oder Salon?", "Bar oder Karte?"]
    assert e["fragen"][0]["optionen"] == ["Privat", "Salon"]


def test_zu_viele_antworten_heisst_schreibtisch(monkeypatch):
    monkeypatch.setattr(gemma_buchung, "_gemma",
                        lambda p, bild=None: pytest.fail("darf nicht mehr fragen"))
    e = gemma_buchung.runde(["x"], {}, [{"frage": "f", "antwort": "a"}] * 8)
    assert e["status"] == "aufgeben"


def test_kauderwelsch_vom_modell_wird_zur_hoeflichen_frage(monkeypatch):
    monkeypatch.setattr(gemma_buchung, "_gemma",
                        lambda p, bild=None, system=None: {"status": "??"})
    e = gemma_buchung.runde(["x"], {}, [])
    assert e["status"] == "fragen"
    assert e["fragen"][0]["frage"]


def test_prompt_kennt_mehrseitige_belege():
    """Die Endsumme eines Bündels steht auf dem letzten Blatt — die Regel
    steht immer im Prompt und konditioniert sich selbst auf Seiten-Marker."""
    p = gemma_buchung.voller_prompt("P", ["— Seite 1 von 2 —", "Übertrag 120,00",
                                         "— Seite 2 von 2 —", "Gesamt 189,61"], [])
    assert "Seiten-Marker" in p and "LETZTEN" in p


def test_prompt_traegt_kontobewegungen_und_nachbarbelege():
    p = gemma_buchung.voller_prompt(
        "P", ["Gesamtsumme 55,74 AED"], [],
        umsaetze=[{"datum": "21.02.2026", "betrag": -13.9,
                   "text": "PayPal Uber BV"}],
        nachbarn=[{"datum": "2026-02-21", "brutto": 55.74,
                   "lieferant": "Uber"}])
    assert "KONTOBEWEGUNGEN" in p and "PayPal Uber BV" in p
    assert "WEITERE BELEGE" in p and "Uber" in p
    # Ohne Kontext tauchen die Abschnitte gar nicht erst auf.
    leer = gemma_buchung.voller_prompt("P", ["x"], [])
    assert "KONTOBEWEGUNGEN" not in leer and "WEITERE BELEGE" not in leer


# ————— Die Direkt-Route: das Telefon schickt Profil und Lesung —————

@pytest.fixture()
def direkt_klient(monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "_box_wache", lambda request: ("nina@0711.io", None))
    monkeypatch.setattr(babu_web, "db_einstellungen",
                        lambda un: {"betrieb_name": "Serverstand"})
    monkeypatch.setattr(babu_web, "kontenrahmen_von", lambda un: "SKR04")
    return babu_web, TestClient(babu_web.app, base_url="https://testserver")


def test_direktroute_nutzt_das_mitgeschickte_profil(direkt_klient, monkeypatch):
    bw, c = direkt_klient
    gesehen = {}

    def falsche_runde(zeilen, einstellungen, antworten, rahmen, *rest, **_):
        gesehen.update(zeilen=zeilen, profil=einstellungen, rahmen=rahmen)
        return {"status": "gebucht", "buchung": {"konto": "6850"}}

    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)
    r = c.post("/api/buchung/einschaetzung", json={
        "profil": {"betrieb_name": "Struwwelpeter", "kleinunternehmer": "Nein",
                   "steuernummer": "geht niemanden an"},
        "zeilen": ["Gesamtsumme 55,74 AED", "  ", "Uber"]})
    assert r.status_code == 200, r.text
    assert gesehen["zeilen"] == ["Gesamtsumme 55,74 AED", "Uber"]
    # Nur die Einschätzungs-Felder reisen mit — nicht die Steuernummer.
    assert gesehen["profil"] == {"betrieb_name": "Struwwelpeter",
                                 "kleinunternehmer": "Nein"}
    assert gesehen["rahmen"] == "SKR04"


def test_direktroute_ohne_profil_faellt_auf_den_serverstand(direkt_klient, monkeypatch):
    bw, c = direkt_klient
    gesehen = {}

    def falsche_runde(zeilen, einstellungen, antworten, rahmen, *rest, **_):
        gesehen.update(profil=einstellungen)
        return {"status": "gebucht", "buchung": {}}

    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)
    r = c.post("/api/buchung/einschaetzung", json={"zeilen": ["x"]})
    assert r.status_code == 200, r.text
    assert gesehen["profil"] == {"betrieb_name": "Serverstand"}


def test_direktroute_ohne_lesung_sagt_es_ehrlich(direkt_klient):
    bw, c = direkt_klient
    r = c.post("/api/buchung/einschaetzung", json={"profil": {}})
    assert r.status_code == 422
    assert "Lesung" in r.json()["fehler"]


# ————— Der stehende Kontext: Verträge und Personal —————

def test_prompt_traegt_vertraege_und_personal():
    p = gemma_buchung.voller_prompt(
        "P", ["Überweisung Miete Juli 1.076,95"], [],
        vertraege=[{"art_name": "Miete Geschäftsräume",
                    "partner": "Weber Immobilien", "betrag_monat": 1076.95}],
        personal=[{"name": "Jana Allgaier", "kosten_monat": 2400.0}])
    assert "LAUFENDE VERTRÄGE" in p and "Weber Immobilien" in p and "1076.95" in p
    assert "PERSONAL" in p and "Jana Allgaier" in p and "LOHN" in p
    leer = gemma_buchung.voller_prompt("P", ["x"], [])
    assert "LAUFENDE VERTRÄGE" not in leer and "PERSONAL" not in leer


def test_lohn_wird_abgegeben_statt_gebucht():
    e = gemma_buchung.buchung_pruefen(
        {"status": "abgeben", "hinweis": "Das ist der Monatslohn von Jana — "
         "Löhne bucht der Lohnlauf."})
    assert e["status"] == "aufgeben"
    assert "Lohnlauf" in e["hinweis"]


def test_direktroute_gibt_gemma_vertraege_und_personal(direkt_klient, monkeypatch):
    bw, c = direkt_klient
    monkeypatch.setattr(bw, "vertraege_aktuell", lambda: [
        {"art": "miete", "art_name": "Miete Geschäftsräume",
         "partner": "Weber", "betrag_monat": 1076.95}])
    monkeypatch.setattr(bw, "team_liste", lambda un: [
        {"name": "Jana", "kosten_monat": 2400.0, "aktiv": True},
        {"name": "Weg", "kosten_monat": 1.0, "aktiv": False}])
    gesehen = {}

    def falsche_runde(zeilen, einstellungen, antworten, rahmen,
                      umsaetze=None, nachbarn=None, markdown=None, bild=None,
                      vertraege=None, personal=None, offene_abbuchungen=None):
        gesehen.update(vertraege=vertraege, personal=personal)
        return {"status": "gebucht", "buchung": {}}

    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)
    r = c.post("/api/buchung/einschaetzung", json={"zeilen": ["Miete Juli"]})
    assert r.status_code == 200, r.text
    assert gesehen["vertraege"] == [{"art_name": "Miete Geschäftsräume",
                                     "partner": "Weber", "betrag_monat": 1076.95}]
    assert gesehen["personal"] == [{"name": "Jana", "kosten_monat": 2400.0}]


# ————— Die Steuertabelle: Mischsätze je Position, Fremdwährung gesperrt —————

def test_mischsatz_wird_zur_steuertabelle_mit_fuehrendem_satz():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "sonstiges", "betrag": 22.96,
         "betrag_eur": 22.96, "ust_satz": 0, "positionen": [
             {"bezeichnung": "Wasser", "betrag": 17.52, "ust_satz": 7,
              "kategorie": "sonstiges"},
             {"bezeichnung": "Spülmittel", "betrag": 5.44, "ust_satz": 19,
              "kategorie": "verbrauchsmaterial"}]})
    b = e["buchung"]
    assert b["ust_satz"] == 7                       # führender Satz, nicht 0
    tabelle = {z["satz"]: z for z in b["steuersaetze"]}
    assert tabelle[7]["brutto"] == 17.52 and tabelle[7]["ust"] == 1.15
    assert tabelle[19]["brutto"] == 5.44 and tabelle[19]["ust"] == 0.87
    assert b["steuersaetze"][0]["satz"] == 7        # absteigend nach Anteil


def test_fremdwaehrung_bekommt_keine_steuertabelle_und_satz_null():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "fahrt", "betrag": 55.74,
         "waehrung": "AED", "betrag_eur": 14.2, "ust_satz": 19, "positionen": [
             {"bezeichnung": "Fahrpreis", "betrag": 45.74, "ust_satz": 19,
              "kategorie": "fahrt"}]})
    b = e["buchung"]
    assert b["steuersaetze"] == []
    assert b["ust_satz"] == 0                       # keine deutsche Vorsteuer


# ————— Die Katalog-Lücken vom Prüflauf: Fortbildung und Porto —————

def test_fortbildung_und_porto_stehen_im_katalog():
    text = gemma_buchung.katalog_text("SKR04")
    assert "fortbildung: Fortbildung und Seminare" in text
    assert "porto: Porto und Versand" in text
    # Der Kurs über 799 € landete ohne diese Kategorie auf „Fachliteratur".
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "dokumentklasse": "beleg", "kategorie": "fortbildung", "betrag": 799,
         "betrag_eur": 799, "ust_satz": 0})
    assert e["buchung"]["konto"] == "6821"
    assert e["buchung"]["kategorie_name"] == "Fortbildung und Seminare"


def test_beide_kategorien_kennen_auch_skr03():
    import kontierung as kt
    assert kt.KATEGORIEN["fortbildung"].konto("SKR03") == "4945"
    assert kt.KATEGORIEN["porto"].konto("SKR03") == "4910"


# ————— Zielbild: Klassifizierungsfrage und Kontoabgleich im Prompt —————

def test_prompt_fragt_die_dokumentklasse_ab():
    p = gemma_buchung.voller_prompt("P", ["Zeile"], [])
    assert "dokumentklasse" in p
    assert "kontoauszug" in p and "behoerde" in p


def test_prompt_traegt_die_ungedeckten_abbuchungen():
    p = gemma_buchung.voller_prompt(
        "P", ["Zeile"], [],
        offene_abbuchungen=[{"datum": "11.02.2026", "betrag": -818.38,
                             "text": "DELILA GMBH RG 34572"}])
    assert "UNGEDECKTE ABBUCHUNGEN" in p
    assert "818.38" in p or "818,38" in p
    assert "DELILA" in p


def test_buchung_ohne_dokumentklasse_wird_abgewiesen():
    """Ohne Klasse kann die Ablage kein Fach wählen — dann wird gefragt,
    nicht geraten."""
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "kategorie": "sonstiges", "betrag": 10,
         "betrag_eur": 10, "ust_satz": 0})
    assert e["status"] == "fragen"
    assert any("Dokument" in f["frage"] for f in e["fragen"])


def test_erfundene_dokumentklasse_wird_abgewiesen():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "kategorie": "sonstiges", "betrag": 10,
         "betrag_eur": 10, "ust_satz": 0, "dokumentklasse": "liebesbrief"})
    assert e["status"] == "fragen"


def test_die_klasse_steht_in_der_buchung():
    e = gemma_buchung.buchung_pruefen(
        {"status": "gebucht", "kategorie": "sonstiges", "betrag": 10,
         "betrag_eur": 10, "ust_satz": 0, "dokumentklasse": "beleg"})
    assert e["status"] == "gebucht"
    assert e["buchung"]["dokumentklasse"] == "beleg"


# ————— Visions Geometrie: Zeilen mit Ort, Müll fliegt über conf —————

def test_zeilen_normalisieren_rendert_ort_und_filtert_muell():
    """Der Kalugahair-Fall vom 27.08.: das „^"-Müllzeichen kam mit conf 0.3,
    KALUGAHAIR mit 1.0 — und der Ort macht aus Zeilen Spalten."""
    import babu_web
    roh = [
        {"text": "^", "conf": 0.3, "box": [1.8, 7.7, 1.4, 1.0]},
        {"text": "KALUGAHAIR", "conf": 1.0, "box": [13.1, 8.0, 18.9, 3.0]},
        {"text": "$173.50", "conf": 0.98, "box": [70.2, 31.6, 8.0, 1.4]},
        "Altformat-Zeile bleibt Altformat",
    ]
    zeilen = babu_web._zeilen_normalisieren(roh)
    assert zeilen == ["[x13 y8] KALUGAHAIR",
                      "[x70 y32] $173.50",
                      "Altformat-Zeile bleibt Altformat"]


def test_einschaetzung_nimmt_beide_zeilenformate(direkt_klient, monkeypatch):
    bw, c = direkt_klient
    gesehen = {}

    def falsche_runde(zeilen, einstellungen, antworten, rahmen,
                      umsaetze=None, nachbarn=None, markdown=None, bild=None,
                      vertraege=None, personal=None, offene_abbuchungen=None):
        gesehen["zeilen"] = zeilen
        return {"status": "gebucht", "buchung": {}}

    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)
    r = c.post("/api/buchung/einschaetzung", json={
        "zeilen": [{"text": "Miete Juli", "conf": 0.99, "box": [10.0, 20.0, 30.0, 2.0]}]})
    assert r.status_code == 200, r.text
    assert gesehen["zeilen"] == ["[x10 y20] Miete Juli"]
    r2 = c.post("/api/buchung/einschaetzung", json={"zeilen": ["Miete Juli"]})
    assert r2.status_code == 200
    assert gesehen["zeilen"] == ["Miete Juli"]


def test_prompt_kennt_die_neuen_fachregeln():
    """Ninas Anmerkungen vom 27.08.: Geldtransit, FA-Bescheide positionsweise,
    Bewirtung/Aufmerksamkeit/Geschenk, Summen-Plausibilität."""
    p = gemma_buchung.voller_prompt("P", ["x"], [])
    assert "geldtransit" in p and "SumUp" in p
    assert "ust_zahlung" in p and "POSITIONSWEISE" in p
    assert "aufmerksamkeit" in p and "70/30" in p
    assert "Netto + USt = Brutto" in p


def test_katalog_traegt_die_neuen_kategorien():
    text = gemma_buchung.katalog_text("SKR04")
    assert "materialeinsatz" in text and "Extensions" in text
    assert "aufmerksamkeit" in text
    assert "ust_zahlung" in text
    text03 = gemma_buchung.katalog_text("SKR03")
    assert "materialeinsatz" in text03
