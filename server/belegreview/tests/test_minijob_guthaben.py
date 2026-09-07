"""Ninas Fall vom 07.09.2026: Beitragskontoauszug der Minijob-Zentrale mit
119 € Guthaben. babu gab ihn als „Lohn → Schreibtisch" ab, ohne das Guthaben
zu sehen und ohne die eine Frage, auf die es ankommt. Das Guthaben ist eine
Korrektur von Sozialabgaben: keine Einnahme, keine Umsatzsteuer, kein Lohn."""
import gemma_buchung as gb
import kontierung


def test_der_katalog_kennt_sozialabgaben_und_pauschsteuer():
    k = kontierung.KATEGORIEN["sozialabgaben"]
    assert k.konto("SKR04") == "6110" and k.konto("SKR03") == "4130"
    assert not k.geprueft                      # die Kanzlei bestätigt das Konto
    assert kontierung.KATEGORIEN["pauschsteuer_minijob"].konto("SKR04") == "6036"
    text = gb.katalog_text("SKR04")
    assert "sozialabgaben:" in text and "Minijob" in text and "KEIN Lohn" in text


def test_die_regel_nennt_nur_das_verhalten_und_verweist_aufs_wissen():
    r = gb.REGELN
    assert "Minijob-Zentrale" in r and 'NICHT status "abgeben"' in r
    assert "ausgezahlt oder mit dem nächsten Beitrag verrechnet" in r
    assert "Mit Beiträgen verrechnet" in r and "Noch offen" in r
    assert "Kontierungswissen" in r
    # Das Fachwissen (Umlagen, Prozentsätze, Konten) steht NICHT im Prompt …
    assert "Insolvenzgeldumlage" not in r and "U1" not in r


def test_das_fachwissen_steht_im_wissenscontainer():
    """… sondern in der Wissensdatei, deren Quelle jetzt im Repo liegt und
    die `kompendium.kontierungswissen()` stehend in jeden Buchungsprompt
    legt. Vorher lag sie nur auf dem Server, unversioniert."""
    from pathlib import Path
    quelle = Path(__file__).resolve().parents[3] / "werkzeuge" / "kompendium" / "kontierung-grundwissen.md"
    w = quelle.read_text(encoding="utf-8")
    assert "## Sozialabgaben und Minijob-Zentrale" in w
    for wort in ("Knappschaft-Bahn-See", "Insolvenzgeldumlage", "6110", "6036",
                 "keine Betriebseinnahme", "gutschrift: true", "Ausgezahlt", "verrechnet"):
        assert wort in w, wort
    # der Abschnitt steht VOR der generierten Kontenübersicht, damit das
    # Build-Skript ihn beim Anhängen nicht überschreibt
    assert w.index("## Sozialabgaben") < w.index("<!-- skr04-atome: kontenuebersicht start -->")
    assert len(w) < 30000                       # kompendium.kontierungswissen() kappt dort


def test_ein_guthaben_wird_zur_abgabenkorrektur_nicht_zur_einnahme():
    roh = {"status": "gebucht", "kategorie": "sozialabgaben", "dokumentklasse": "beleg",
           "lieferant": "Minijob-Zentrale", "datum": "2026-08-20",
           "buchungstext": "Minijob-Zentrale – Beitragskontoauszug / Guthaben 119,00 €, verrechnet",
           "betrag": 119.0, "waehrung": "EUR", "betrag_eur": 119.0, "ust_satz": 0,
           "gutschrift": True, "zahlungsart": "unbekannt",
           "positionen": [{"bezeichnung": "Pauschale KV/RV, Umlagen", "betrag": 110.0,
                           "ust_satz": 0, "kategorie": "sozialabgaben"},
                          {"bezeichnung": "Pauschale Lohnsteuer 2 %", "betrag": 9.0,
                           "ust_satz": 0, "kategorie": "pauschsteuer_minijob"}],
           "begruendung": "Guthaben aus der Beitragsberechnung, korrigiert die Abgaben."}
    e = gb.buchung_pruefen(roh)
    assert e["status"] == "gebucht"
    b = e["buchung"]
    assert b["konto"] == "6110" and b["ust_satz"] == 0 and b["gutschrift"] is True
    assert b["betrag_eur"] == -119.0                     # mindert den Aufwand
    assert [p["betrag"] for p in b["positionen"]] == [-110.0, -9.0]
    assert b["positionen"][1]["kategorie"] == "pauschsteuer_minijob"
    assert b["steuersaetze"] == [{"satz": 0, "brutto": -119.0, "netto": -119.0, "ust": 0.0}]
    assert not gb.gemischt(b)                            # 92 % eine Kategorie: keine Rückfrage


def test_die_frage_nach_der_verwendung_kommt_mit_drei_antworten_durch():
    roh = {"status": "fragen", "fragen": [{
        "frage": "Wurde das Guthaben von 119,00 € ausgezahlt oder mit dem nächsten Beitrag verrechnet?",
        "optionen": ["Ausgezahlt", "Mit Beiträgen verrechnet", "Noch offen"]}]}
    e = gb.buchung_pruefen(roh)
    assert e["status"] == "fragen"
    assert e["fragen"][0]["optionen"] == ["Ausgezahlt", "Mit Beiträgen verrechnet", "Noch offen"]


def test_ein_schreibtisch_hinweis_wird_nicht_mehr_bei_300_zeichen_abgeschnitten():
    lang = "x" * 500
    e = gb.buchung_pruefen({"status": "abgeben", "hinweis": lang})
    assert len(e["hinweis"]) == 500
