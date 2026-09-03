"""Monatsabschluss: BWA und UStVA-Entwurf — reine Rechnung, kein I/O.

Geprüft wird, was eine Voranmeldung falsch machen würde: Steuersätze,
Gutscheine, Kleinunternehmerin und Belege, die man nicht ansetzen darf.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monatsabschluss as ma  # noqa: E402


def blatt(**werte):
    grund = {"datum": "2026-08-01", "einnahmenBar": 0.0, "ecZahlungen": 0.0}
    grund.update(werte)
    return grund


def beleg(**werte):
    grund = {"stamm": "b1", "brutto": 119.0, "netto": 100.0, "ust": 19.0,
             "konto_skr04": "5400", "status": "geprüft", "summenprobe_ok": True}
    grund.update(werte)
    return grund


# ————— Welche Fragen das Kassenbuch stellen muss —————

def test_normaler_salon_bekommt_keine_zusatzfrage():
    p = ma.umsatz_profil({"kleinunternehmer": "Nein"})
    assert p["fragen"] == []
    assert p["braucht_ustva"] is True


def test_kleinunternehmerin_ohne_voranmeldung():
    p = ma.umsatz_profil({"kleinunternehmer": "Ja",
                          "ust_befreiung_medizinisch": "Ja"})
    assert p["braucht_ustva"] is False
    assert p["fragen"] == []          # ohne UStVA auch keine Aufteilung


def test_fusspflege_und_gutscheine_loesen_fragen_aus():
    p = ma.umsatz_profil({"ust_befreiung_medizinisch": "Ja",
                          "verkauft_gutscheine": "Ja"})
    felder = [f["feld"] for f in p["fragen"]]
    assert felder == ["umsatzFrei", "gutscheinVerkauf"]


# ————— Erlöse aus dem Kassenbuch —————

def test_erloese_ohne_aufteilung_sind_alle_19_prozent():
    e = ma.erloese_monat([blatt(einnahmenBar=300, ecZahlungen=700),
                          blatt(datum="2026-08-02", einnahmenBar=100)])
    assert e["brutto_19"] == 1100.0
    assert e["brutto_7"] == 0.0 and e["steuerfrei"] == 0.0
    assert e["tage"] == 2
    assert e["netto_gesamt"] == pytest.approx(924.37, abs=0.01)   # 1100/1,19


def test_fusspflege_wird_aus_dem_19er_umsatz_herausgerechnet():
    e = ma.erloese_monat([blatt(einnahmenBar=1000, umsatzFrei=200)])
    assert e["brutto_19"] == 800.0
    assert e["steuerfrei"] == 200.0
    # Steuerfreier Anteil bleibt netto wie brutto.
    assert e["netto_gesamt"] == pytest.approx(800 / 1.19 + 200, abs=0.01)


def test_gutschein_verkauf_ist_umsatz_einloesung_nicht():
    e = ma.erloese_monat([blatt(einnahmenBar=500, gutscheinVerkauf=100,
                                gutscheineEingeloest=80)])
    assert e["brutto_19"] == 600.0          # 500 Tagesumsatz + 100 verkauft
    assert e["gutschein_eingeloest"] == 80.0  # erfasst, aber nicht gezählt


# ————— Vorsteuer: nur was belastbar ist —————

def test_belege_ohne_saubere_summenprobe_zaehlen_nicht():
    v = ma.vorsteuer_monat([
        beleg(stamm="gut"),
        beleg(stamm="schief", summenprobe_ok=False),
        beleg(stamm="ohne-betrag", brutto=None),
        beleg(stamm="offen", status="nachfrage"),
    ])
    assert v["vorsteuer"] == 19.0 and v["belege_gezaehlt"] == 1
    assert {p["stamm"] for p in v["pruefliste"]} == {"schief", "ohne-betrag", "offen"}
    assert all(p["hinweis"] for p in v["pruefliste"])


def test_gutschrift_mindert_die_vorsteuer():
    """Seit 27.08.2026 trägt eine Gutschrift ihr Minus schon in den
    Beträgen — `gemma_buchung` setzt das Vorzeichen beim Buchen, damit
    Voranmeldung, BWA und Saldenliste keinen Sonderfall mehr brauchen."""
    kauf = beleg(stamm="kauf")
    retoure = beleg(stamm="retoure", gutschrift=True,
                    brutto=-kauf["brutto"], netto=-kauf["netto"],
                    ust=-kauf["ust"])
    v = ma.vorsteuer_monat([kauf, retoure])
    assert v["vorsteuer"] == 0.0
    assert v["netto_kosten"] == 0.0


# ————— Der Entwurf —————

def test_ustva_rechnet_zahllast_und_nennt_kennziffern():
    e = ma.erloese_monat([blatt(einnahmenBar=11900)])
    v = ma.vorsteuer_monat([beleg(ust=190.0, netto=1000.0, brutto=1190.0)])
    d = ma.ustva_entwurf("2026-08", e, v, ma.umsatz_profil({}))
    kz = {z["kz"]: z for z in d["zeilen"]}
    assert kz["81"]["netto"] == 10000.0 and kz["81"]["steuer"] == 1900.0
    assert kz["66"]["steuer"] == 190.0
    assert d["zahllast"] == 1710.0
    assert "zahlst" in d["satz"]
    assert d["stand"] == "entwurf"          # nie „fertig"


def test_erstattung_wird_als_solche_benannt():
    e = ma.erloese_monat([blatt(einnahmenBar=119)])
    v = ma.vorsteuer_monat([beleg(ust=500.0, netto=2631.58, brutto=3131.58)])
    d = ma.ustva_entwurf("2026-08", e, v, ma.umsatz_profil({}))
    assert d["zahllast"] < 0 and "zurück" in d["satz"]


def test_kleinunternehmerin_bekommt_keinen_entwurf():
    d = ma.ustva_entwurf("2026-08", ma.erloese_monat([blatt(einnahmenBar=500)]),
                         ma.vorsteuer_monat([]),
                         ma.umsatz_profil({"kleinunternehmer": "Ja"}))
    assert d["stand"] == "keine" and d["zeilen"] == []
    assert "§ 19" in d["hinweis"]


# ————— BWA —————

def test_bwa_gruppiert_kosten_und_rechnet_ergebnis():
    e = ma.erloese_monat([blatt(einnahmenBar=11900)])
    belege = [beleg(konto_skr04="5400", netto=1000.0, ust=190.0, brutto=1190.0),
              beleg(stamm="b2", konto_skr04="6310", netto=2000.0, ust=380.0, brutto=2380.0),
              beleg(stamm="b3", konto_skr04="6850", netto=500.0, ust=95.0, brutto=595.0)]
    d = ma.bwa("2026-08", e, belege)
    gruppen = {g["schluessel"]: g for g in d["gruppen"]}
    assert gruppen["material"]["netto"] == 1000.0
    assert gruppen["raum"]["netto"] == 2000.0
    assert d["umsatz_netto"] == 10000.0
    assert d["ergebnis"] == 6500.0
    assert gruppen["material"]["anteil"] == 10.0
    assert d["stand"] == "entwurf"


def test_bwa_vergleicht_mit_dem_vorjahr():
    e = ma.erloese_monat([blatt(einnahmenBar=11900)])
    d = ma.bwa("2026-08", e, [], vorjahr={"umsatz": 96000.0})
    assert d["vorjahr_monat"] == 8000.0
    assert d["vorjahr_delta"] == 2000.0


def test_bwa_ohne_umsatz_teilt_nicht_durch_null():
    d = ma.bwa("2026-08", ma.erloese_monat([]), [beleg()])
    assert d["umsatz_netto"] == 0.0
    assert d["ergebnis_anteil"] is None
    assert d["gruppen"][0]["anteil"] is None


# ————— Löhne: die größte Position kommt nicht über Belege —————

def test_bwa_sagt_wenn_loehne_fehlen():
    d = ma.bwa("2026-08", ma.erloese_monat([blatt(einnahmenBar=11900)]), [beleg()])
    assert any("Löhne" in f for f in d["fehlt"])


def test_bwa_rechnet_mit_hinterlegten_loehnen():
    e = ma.erloese_monat([blatt(einnahmenBar=11900)])
    d = ma.bwa("2026-08", e, [beleg(netto=1000.0, ust=190.0, brutto=1190.0)],
               personal_monat=4500.0)
    personal = d["gruppen"][0]
    assert personal["schluessel"] == "personal" and personal["geschaetzt"] is True
    assert personal["netto"] == 4500.0 and personal["anteil"] == 45.0
    assert d["ergebnis"] == 4500.0           # 10000 - 1000 - 4500
    assert d["fehlt"] == []


def test_lohnbeleg_zaehlt_als_personal():
    d = ma.bwa("2026-08", ma.erloese_monat([blatt(einnahmenBar=11900)]),
               [beleg(konto_skr04="6020", netto=3000.0, ust=0.0, brutto=3000.0)])
    assert d["gruppen"][0]["name"] == "Löhne und Gehälter"
    assert d["fehlt"] == []                  # dann fehlt der Hinweis zu Recht


# ————— Verträge: Kosten, die nie als Beleg kommen —————

def vertrag(**werte):
    grund = {"art": "miete", "art_name": "Mietvertrag", "partner": "Vermieter Weber",
             "konto_skr04": "6310", "betrag_monat": 1250.0}
    grund.update(werte)
    return grund


def test_vertrag_liefert_die_monatskosten():
    e = ma.erloese_monat([blatt(einnahmenBar=11900)])
    d = ma.bwa("2026-08", e, [], vertraege=[vertrag()])
    raum = [g for g in d["gruppen"] if g["schluessel"] == "raum"][0]
    assert raum["netto"] == 1250.0
    assert raum["aus_vertrag"] == "Vermieter Weber"
    assert d["kosten_netto"] == 1250.0
    # Dokumentiert, was die Ausgaben-Ansicht (P0-1) abfragen muss, um "0
    # Belege" bei reinen Vertragskosten nicht mehr anzuzeigen: die Gruppe
    # trägt "aus_vertrag" und hat keinen einzigen eigenen Beleg.
    assert raum["aus_vertrag"]
    assert raum["anzahl"] == 0


def test_kostengruppe_von_ist_eine_eigene_funktion():
    """P0-1: dieselbe Zuordnung, die bwa() intern benutzt, muss babu_web für
    die Belegliste stehen können — als eigene Funktion, nicht als lokale
    Dict-Comprehension in bwa()."""
    assert ma.kostengruppe_von("6640") == ("werbung", "Werbung, Bewirtung und Reisen")
    assert ma.kostengruppe_von(None) == ("sonstiges", "Sonstiges")
    assert ma.kostengruppe_von("") == ("sonstiges", "Sonstiges")
    assert ma.kostengruppe_von("gibtsnicht") == ("sonstiges", "Sonstiges")


def test_beleg_schlaegt_vertrag_keine_doppelten_kosten():
    e = ma.erloese_monat([blatt(einnahmenBar=11900)])
    mietbeleg = beleg(konto_skr04="6310", netto=1300.0, ust=0.0, brutto=1300.0)
    d = ma.bwa("2026-08", e, [mietbeleg], vertraege=[vertrag()])
    raum = [g for g in d["gruppen"] if g["schluessel"] == "raum"][0]
    assert raum["netto"] == 1300.0          # der echte Beleg gilt
    assert "aus_vertrag" not in raum
    assert d["kosten_netto"] == 1300.0      # nicht 2550


def test_vertrag_ohne_betrag_wird_ignoriert():
    d = ma.bwa("2026-08", ma.erloese_monat([blatt(einnahmenBar=1190)]), [],
               vertraege=[vertrag(betrag_monat=None)])
    assert d["kosten_netto"] == 0.0


# ————— Welche Verträge in einem Monat überhaupt gelten —————

def test_vertrag_der_erst_spaeter_beginnt_zaehlt_noch_nicht():
    kuenftig = vertrag(beginn="2026-10-01")
    gueltig, hinweise = ma.vertraege_fuer_monat([kuenftig], "2026-08")
    assert gueltig == []
    assert hinweise == []          # kein Hinweis nötig, er kommt ja erst


def test_abgelaufener_vertrag_zaehlt_nicht_mehr_und_sagt_es():
    alt = vertrag(art="leasing", art_name="Leasing", partner="Autohaus Renz",
                  konto_skr04="6530", beginn="2019-01-01", laufzeit_bis="2023-12-31")
    gueltig, hinweise = ma.vertraege_fuer_monat([alt], "2026-08")
    assert gueltig == []
    assert len(hinweise) == 1
    assert "31.12.2023" in hinweise[0]
    assert "Autohaus Renz" in hinweise[0]


def test_von_zwei_mietvertraegen_gilt_der_juengere():
    alt = vertrag(betrag_monat=1250.0, beginn="2019-05-01")
    neu = vertrag(betrag_monat=1400.0, beginn="2025-07-01")
    gueltig, _ = ma.vertraege_fuer_monat([alt, neu], "2026-08")
    assert len(gueltig) == 1
    assert gueltig[0]["betrag_monat"] == 1400.0


def test_miete_zaehlt_nach_mieterhoehung_nicht_doppelt():
    e = ma.erloese_monat([blatt(einnahmenBar=5000.0, ecZahlungen=5000.0)])
    alt = vertrag(betrag_monat=1250.0, beginn="2019-05-01")
    neu = vertrag(betrag_monat=1400.0, beginn="2025-07-01")
    d = ma.bwa("2026-08", e, [], vertraege=[alt, neu])
    raum = next(g for g in d["gruppen"] if g["schluessel"] == "raum")
    assert raum["netto"] == 1400.0


def test_arbeitsvertrag_und_team_ergeben_die_loehne_nur_einmal():
    e = ma.erloese_monat([blatt(einnahmenBar=5000.0, ecZahlungen=5000.0)])
    av = vertrag(art="arbeitsvertrag", art_name="Arbeitsvertrag", partner="Lena",
                 konto_skr04="6020", betrag_monat=2400.0)
    d = ma.bwa("2026-08", e, [], vertraege=[av], personal_monat=2400.0)
    personal = [g for g in d["gruppen"] if g["schluessel"] == "personal"]
    assert len(personal) == 1
    assert personal[0]["netto"] == 2400.0
    assert d["kosten_netto"] == 2400.0


def test_hinweis_zum_abgelaufenen_vertrag_steht_in_der_auswertung():
    e = ma.erloese_monat([blatt(einnahmenBar=5000.0, ecZahlungen=5000.0)])
    alt = vertrag(art="leasing", art_name="Leasing", partner="Autohaus Renz",
                  konto_skr04="6530", laufzeit_bis="2023-12-31")
    d = ma.bwa("2026-08", e, [], vertraege=[alt], personal_monat=1000.0)
    assert any("Autohaus Renz" in z for z in d["fehlt"])


def test_vertrag_ohne_daten_stoert_nicht():
    ohne = vertrag(betrag_monat=None)
    gueltig, hinweise = ma.vertraege_fuer_monat([ohne, {}], "2026-08")
    assert gueltig == [] and hinweise == []


def test_die_kostengruppen_nennen_ihre_konten():
    """Befund 03.09.2026: „Wohin dein Geld geht“ zeigte nur den Oberbegriff.
    Jede Gruppe trägt jetzt ihre Konten mit SKR04-Bezeichnung, Summe und
    Belegzahl — absteigend nach Betrag."""
    import monatsabschluss as ma
    import skr04_konten
    belege = [
        {"brutto": 119.0, "netto": 100.0, "ust": 19.0, "konto_skr04": "6640", "lieferant": "A"},
        {"brutto": 59.5, "netto": 50.0, "ust": 9.5, "konto_skr04": "6640", "lieferant": "B"},
        {"brutto": 23.8, "netto": 20.0, "ust": 3.8, "konto_skr04": "6600", "lieferant": "C"},
    ]
    b = ma.bwa("2026-08", ma.erloese_monat([]), belege)
    gruppe = next(g for g in b["gruppen"] if any(k["konto"] == "6640" for k in g["konten"]))
    konten = {k["konto"]: k for k in gruppe["konten"]}
    assert konten["6640"]["anzahl"] == 2 and konten["6640"]["netto"] == 150.0
    assert konten["6640"]["name"] == skr04_konten.name("6640")
    assert [k["konto"] for k in gruppe["konten"]][0] == "6640"   # größter Betrag zuerst
    assert sum(k["netto"] for k in gruppe["konten"]) == gruppe["netto"]


def test_kontoauszug_liefert_den_umsatz_wenn_kein_kassenbuch_da_ist():
    """Befund 03.09.2026 (Nina, Juli): kein Kassenbuch, aber fünf Auszahlungen
    von Salonkee auf dem Konto — das ist ihr Kartenumsatz. Erstattungen und
    Rückzahlungen sind kein Umsatz."""
    import monatsabschluss as ma
    umsaetze = [
        {"datum": "06.07.2026", "betrag": 785.78, "text": "Salonkee SA Account for SupremeStudio", "gegenpartei": ""},
        {"datum": "20.07.2026", "betrag": 1710.0, "text": "Salonkee SA Account for SupremeStudio", "gegenpartei": ""},
        {"datum": "06.07.2026", "betrag": 307.2, "text": "PayPal Europe MAKI OFF GmbH Ihr Einkauf", "gegenpartei": ""},
        {"datum": "16.07.2026", "betrag": 104.19, "text": "AXA easy Versicherung ERSTATTUNG", "gegenpartei": ""},
        {"datum": "02.07.2026", "betrag": -59.9, "text": "Salonkee Gebuehr", "gegenpartei": ""},
    ]
    b = ma.bank_erloese(umsaetze)
    assert b["brutto"] == 2495.78 and b["quellen"] == {"Salonkee": 2495.78}
    assert b["sonstige"] == 411.39 and b["sonstige_anzahl"] == 2
    e = ma.erloese_monat([], monat="2026-07", umsaetze=umsaetze)
    assert e["aus_bank"] == 2495.78 and e["brutto_19"] == 2495.78
    assert e["brutto_gesamt"] == 2495.78 and e["bank_quellen"] == {"Salonkee": 2495.78}
    # Mit Kassenbuch zählt die Bank nicht mit — die Karte steht dort schon.
    e2 = ma.erloese_monat([{"einnahmenBar": 100.0, "ecZahlungen": 2495.78}], monat="2026-07", umsaetze=umsaetze)
    assert e2["aus_bank"] == 0.0 and e2["brutto_gesamt"] == 2595.78
    # Kleinunternehmerin: steuerfrei, nicht 19 %.
    e3 = ma.erloese_monat([], monat="2026-07", umsaetze=umsaetze, kleinunternehmerin=True)
    assert e3["brutto_19"] == 0.0 and e3["steuerfrei"] == 2495.78


def test_bwa_nennt_die_quelle_wenn_der_umsatz_vom_kontoauszug_kommt():
    import monatsabschluss as ma
    e = ma.erloese_monat([], monat="2026-07",
                         umsaetze=[{"betrag": 100.0, "text": "Salonkee SA Auszahlung"}])
    d = ma.bwa("2026-07", e, [], None)
    assert d["umsatz_quelle"] == "Kontoauszug: Salonkee"
    assert d["umsatz_netto"] == 84.03
    e2 = ma.erloese_monat([{"einnahmenBar": 50.0}], monat="2026-07")
    assert ma.bwa("2026-07", e2, [], None)["umsatz_quelle"] is None
