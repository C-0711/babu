"""Der Weltblock: alles, was babu über diesen Salon weiß.

Er steht im stehenden Anfang des Chat-Prompts und ist byte-stabil, solange
sich die Box nicht ändert — deshalb kostet er trotz seiner Größe je Frage
fast nichts (Prefix-Cache von vLLM). Was hier geprüft wird:

1. **Die Bereiche, die bis zum 08.09.2026 fehlten**, sind drin —
   Kontoauszüge, Vorjahr, Einzelposten je Beleg, der Inhalt der Post.
   Jeder einzelne war da (in der Box, im Index, als Sidecar) und kam
   nirgends an.
2. **Die Ordnung bleibt**: Beleg-Register hinten, älteste zuerst. Ein
   neuer Beleg darf den Text nur verlängern, nie vorn umsortieren.
3. **Die Größe hat eine Grenze, die jemand prüft.** Bis heute stand
   `BUDGET` auf 14.000 und wurde von `weltblock()` nie angesehen; bei Nina
   wog der Block 25.515 Zeichen, ohne dass es auffiel.
"""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import wissen  # noqa: E402


def _welt(**mehr) -> dict:
    welt = {
        "einstellungen": {"betrieb_name": "Salon Nina"},
        "belege": [], "kassenblaetter": [], "vertraege": [], "rechnungen": [],
        "team": [], "fristen": [], "zahlen": {}, "dokumente": [],
    }
    welt.update(mehr)
    return welt


# ————— Kontoauszüge —————

BANK = {
    "2026-05": {"buchungen": 74, "eingang": 19402.11, "ausgang": 15003.42,
                "erloes_brutto": 17745.60, "quellen": {"Salonkee": 17745.60},
                "sonstige": 1656.51, "sonstige_anzahl": 3},
    "2026-06": {"buchungen": 68, "eingang": 13011.02, "ausgang": 12440.00,
                "erloes_brutto": 12292.40, "quellen": {"Salonkee": 12292.40},
                "sonstige": 718.62, "sonstige_anzahl": 2},
}


def test_die_kontoauszuege_stehen_im_block():
    """485 Buchungen lagen in der Box und fehlten dem Chat komplett — auf
    „was hat Salonkee im Mai ausgezahlt?" konnte er nichts sagen."""
    text = wissen.weltblock(_welt(bank=BANK))
    assert "KONTOAUSZÜGE" in text
    assert "2026-05" in text and "74 Buchungen" in text
    assert "Salonkee" in text and "17.745,60 €" in text


def test_uebrige_eingaenge_stehen_getrennt_und_gelten_nicht_als_umsatz():
    """Verbindliche Vorgabe: Erstattungen und Rückzahlungen sind kein
    Umsatz. Sie werden ausgewiesen, damit sichtbar ist, dass es sie gibt —
    nicht mitgezählt."""
    text = wissen.weltblock(_welt(bank=BANK))
    assert "kein Umsatz" in text
    assert "1.656,51 €" in text


def test_ohne_kontoauszug_steht_nichts_da():
    assert "KONTOAUSZÜGE" not in wissen.weltblock(_welt())


# ————— Das Vorjahr —————

VORJAHR = {
    "jahr": 2024,
    "zahlen": {"umsatz": 172807.0, "gewinn": 16441.0, "wareneinsatz": 21050.0,
               "personal": 78900.0, "raumkosten": 15600.0, "ust_zahllast": None},
    "unsicher": ["ust_zahllast"],
    "afa_liste": [{"bezeichnung": "Friseurstuhl hydraulisch", "wert": 890.0,
                   "angeschafft": "2022-03-14", "restwert": 445.0}],
}


def test_das_vorjahr_steht_im_block():
    """„Läuft es besser als letztes Jahr?" ist die Frage, die eine
    Inhaberin wirklich hat."""
    text = wissen.weltblock(_welt(vorjahr=VORJAHR))
    assert "2024" in text
    assert "172.807,00 €" in text and "16.441,00 €" in text
    assert "Wareneinsatz" in text and "Personal" in text


def test_unsicher_gelesene_zahlen_werden_als_solche_benannt():
    """Sonst gibt der Chat eine Vermutung als Tatsache aus."""
    text = wissen.weltblock(_welt(vorjahr=VORJAHR))
    assert "Nicht sicher gelesen" in text and "ust_zahllast" in text


def test_die_abschreibungsliste_kommt_mit():
    text = wissen.weltblock(_welt(vorjahr=VORJAHR))
    assert "Friseurstuhl hydraulisch" in text and "445,00 €" in text


def test_ein_leeres_vorjahr_erzeugt_keinen_abschnitt():
    assert "abgeschlossene Jahr" not in wissen.weltblock(
        _welt(vorjahr={"jahr": 2024, "zahlen": {"umsatz": None}}))


# ————— Einzelposten je Beleg —————

BELEGE = [
    {"stamm": "b1", "lieferant": "Wella", "brutto": 341.5, "monat": "2026-07",
     "datum": "2026-07-03", "belegart": "Wareneinkauf", "konto_skr04": "5400",
     "posten": [{"bezeichnung": "Koleston Perfect 60ml", "betrag": 12.9},
                {"bezeichnung": "Blondor Freelights", "betrag": 39.0}]},
    {"stamm": "b0", "lieferant": "Edeka", "brutto": 12.9, "monat": "2026-06",
     "datum": "2026-06-02", "belegart": "Sonstiges"},
]


def test_die_einzelposten_stehen_beim_beleg():
    """Bis heute stand je Beleg nur eine Zeile — auf „was habe ich bei
    Wella gekauft?" kam nur der Gesamtbetrag."""
    text = wissen.weltblock(_welt(belege=BELEGE))
    assert "Koleston Perfect 60ml" in text and "12,90 €" in text
    assert "Blondor Freelights" in text


def test_lange_bons_werden_bei_den_posten_gekappt_und_das_steht_da():
    viele = [{"bezeichnung": f"Artikel {i}", "betrag": 1.0} for i in range(30)]
    text = wissen.weltblock(_welt(belege=[dict(BELEGE[0], posten=viele)]))
    assert f"und {30 - wissen.POSTEN_JE_BELEG} weitere Posten" in text
    assert "Artikel 0" in text and "Artikel 29" not in text


# ————— Die Post mit Inhalt —————

def test_die_post_traegt_ihre_erklaerung():
    """Die Erklärungen liegen vollständig als Sidecar neben jedem Brief —
    im Block stand bisher nur die Überschrift."""
    text = wissen.weltblock(_welt(dokumente=[{
        "art": "behoerde", "titel": "Umsatzsteuer-Vorauszahlung 2. Quartal",
        "erklaerung": {"einfach": "Das Finanzamt möchte die Umsatzsteuer für "
                                  "April bis Juni.",
                       "was_tun": ["Betrag überweisen", "Beleg ablegen"],
                       "bis_wann": "2026-08-10"}}]))
    assert "Worum es geht: Das Finanzamt möchte" in text
    assert "Betrag überweisen" in text
    assert "10.08.2026" in text


# ————— Ordnung und Größe —————

def test_das_register_bleibt_hinten_und_aelteste_zuerst():
    """Die Bedingung dafür, dass der Prefix-Cache trägt: ein neuer Beleg
    verlängert den Text nur am Ende."""
    text = wissen.weltblock(_welt(belege=BELEGE, bank=BANK, vorjahr=VORJAHR))
    assert text.index("KONTOAUSZÜGE") < text.index("BELEG-REGISTER")
    assert text.index("Edeka") < text.index("Wella")   # Juni vor Juli


def test_derselbe_bestand_ergibt_denselben_text():
    welt = _welt(belege=BELEGE, bank=BANK, vorjahr=VORJAHR)
    assert wissen.weltblock(welt) == wissen.weltblock(dict(welt))


def test_ein_neuer_beleg_laesst_alles_vor_dem_register_unveraendert():
    """Das ist der eigentliche Test auf Byte-Stabilität: nur so trifft die
    nächste Frage denselben Prefix-Cache.

    Genau bis zur Überschrift des Registers — die trägt die Anzahl und
    ändert sich mit jedem Beleg. Das ist hingenommen und der Grund, warum
    das Register ganz hinten steht: alles Teure davor (Anleitung,
    Branchenwissen, die übrigen Bereiche) bleibt gleich, neu gerechnet
    wird nur der Schwanz.
    """
    alt = wissen.weltblock(_welt(belege=BELEGE, bank=BANK))
    neu = wissen.weltblock(_welt(bank=BANK, belege=BELEGE + [
        {"stamm": "b2", "lieferant": "Neu", "brutto": 5.0, "monat": "2026-08",
         "datum": "2026-08-01", "belegart": "Sonstiges"}]))
    marke = "BELEG-REGISTER ("
    assert neu[:neu.index(marke)] == alt[:alt.index(marke)], \
        "der Anfang hat sich verschoben"
    # Und die alten Belegzeilen stehen unverändert und in derselben
    # Reihenfolge da, der neue kommt hinten dran.
    alte_zeilen = alt[alt.index(marke):].split("\n")[1:]
    neue_zeilen = neu[neu.index(marke):].split("\n")[1:]
    assert neue_zeilen[:len(alte_zeilen)] == alte_zeilen
    assert neue_zeilen[-1].endswith("Neu · 5,00 € · Sonstiges")


def test_der_block_waechst_nicht_unbegrenzt():
    """Die Grenze, die es bis zum 08.09.2026 nicht gab. Sie soll im Alltag
    nie greifen — aber greifen, bevor der Block das Kontextfenster frisst."""
    viele = [{"stamm": f"b{i:05d}", "lieferant": f"Lieferant {i}",
              "brutto": 100.0 + i, "monat": "2026-%02d" % (i % 12 + 1),
              "datum": "2026-%02d-01" % (i % 12 + 1), "belegart": "Wareneinkauf",
              "konto_skr04": "5400",
              "posten": [{"bezeichnung": f"Ware {j}", "betrag": 9.9}
                         for j in range(6)]}
             for i in range(6000)]
    text = wissen.weltblock(_welt(belege=viele))
    assert len(text) <= wissen.WELTBLOCK_BUDGET
    # Und die Kürzung wird benannt — ein stillschweigend abgeschnittener
    # Bestand wäre schlimmer, das Modell hielte den Rest für vollständig.
    assert "nicht mehr hineinpassen" in text


def test_die_posten_fallen_vor_dem_register_weg():
    """Wenn es eng wird, ist das Register die Auskunft und die Posten das
    Zusatzwissen — nicht umgekehrt."""
    belege = [{"stamm": f"b{i:04d}", "lieferant": f"Lieferant {i}",
               "brutto": 10.0, "monat": "2026-01", "datum": "2026-01-01",
               "belegart": "Ware",
               "posten": [{"bezeichnung": "x" * 50, "betrag": 1.0}
                          for _ in range(8)]}
              for i in range(300)]
    knapp = wissen.weltblock(_welt(belege=belege), budget=40000)
    assert "Lieferant 299" in knapp, "das Register wurde vor den Posten geopfert"
    assert "darauf:" not in knapp
    assert "nicht mehr hineinpassen" not in knapp


def test_ninas_groessenordnung_bleibt_weit_unter_der_grenze():
    """Gemessen am 08.09.2026: 25.515 Zeichen für 200 Belege. Der Test
    hält die Größenordnung fest, damit ein neuer Bereich nicht unbemerkt
    das Zehnfache daraus macht."""
    belege = [{"stamm": f"b{i:04d}", "lieferant": "Friseur Großhandel Wagner",
               "brutto": 141.0, "monat": "2026-07", "datum": "2026-07-03",
               "belegart": "Wareneinkauf", "konto_skr04": "5400",
               "posten": [{"bezeichnung": "Koleston Perfect 60ml", "betrag": 12.9},
                          {"bezeichnung": "Blondor Freelights", "betrag": 39.0}]}
              for i in range(200)]
    text = wissen.weltblock(_welt(belege=belege, bank=BANK, vorjahr=VORJAHR))
    assert len(text) < 60000, f"{len(text)} Zeichen — das ist aus dem Ruder"


# ————— Und kommt das auch wirklich aus der Box? —————
#
# Die Tests oben prüfen den Text. Diese hier prüfen die Naht davor: dass
# `babu_web` die drei neuen Bereiche überhaupt einsammelt. Genau daran lag
# es bisher — die Daten lagen alle in der Box, sie wurden nur nie geholt.

def test_die_belege_bekommen_ihre_posten_aus_dem_review():
    import babu_web as bw
    idx = {
        "belege": {"b1": {"stamm": "b1", "lieferant": "Wella", "brutto": 51.9},
                   "b2": {"stamm": "b2", "lieferant": "Edeka", "brutto": 12.9}},
        "reviews": {"b1": {"buchung": {"buchung": {"positionen": [
            {"bezeichnung": "Koleston Perfect 60ml", "betrag": 12.9}]}}}},
    }
    belege = {b["stamm"]: b for b in bw._belege_mit_posten(idx)}
    assert belege["b1"]["posten"][0]["bezeichnung"] == "Koleston Perfect 60ml"
    assert "posten" not in belege["b2"]
    # Der Index selbst bleibt unberührt — er wird an vielen Stellen gelesen.
    assert "posten" not in idx["belege"]["b1"]


def test_der_kontoauszug_wird_je_monat_ausgewertet():
    """Umsatz ist, was ein Kartenanbieter ausgezahlt hat — alles andere,
    was hereinkommt, wird nur ausgewiesen (verbindliche Vorgabe)."""
    import babu_web as bw
    idx = {"umsaetze": {"2026-05": [
        {"betrag": 4321.0, "text": "SALONKEE PAYOUT 05/2026"},
        {"betrag": 220.0, "text": "Erstattung Krankenkasse"},
        {"betrag": -890.0, "text": "Miete Mai"},
    ]}}
    m = bw._bank_je_monat(idx)["2026-05"]
    assert m["buchungen"] == 3
    assert m["eingang"] == 4541.0 and m["ausgang"] == 890.0
    assert m["erloes_brutto"] == 4321.0
    assert m["quellen"] == {"Salonkee": 4321.0}
    assert m["sonstige"] == 220.0 and m["sonstige_anzahl"] == 1


def test_das_vorjahr_kommt_aus_der_box(monkeypatch):
    import json

    import babu_web as bw
    monkeypatch.setattr(bw, "git_show", lambda pfad: (
        json.dumps({"jahr": None, "zahlen": {"umsatz": 172807.0}}).encode()
        if pfad.endswith("kennzahlen.json") else None))
    daten = bw._vorjahr_kennzahlen()
    assert daten["zahlen"]["umsatz"] == 172807.0
    # `jahr` steht in der Datei oft auf null — dann gilt der Ordner.
    assert isinstance(daten["jahr"], int)


def test_ohne_abschluss_bleibt_das_vorjahr_leer(monkeypatch):
    import babu_web as bw
    monkeypatch.setattr(bw, "git_show", lambda pfad: None)
    assert bw._vorjahr_kennzahlen() == {}
