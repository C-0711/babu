"""Aus dem Termin abrechnen — und wie das Geld ins Kassenbuch kommt.

babu kennt den Termin und (neu) den Preis. Nach der Behandlung ein Tipp:
bar oder Karte. Was babu daraus NICHT macht: das Kassenbuch selbst
schreiben. Die Tagessummen bleiben das, was die Inhaberin abends bestätigt
— babu legt sie nur fertig hin. Eine Kasse, die sich selbst bucht, ist
etwas anderes als ein Kassenbuch, und dieser Unterschied ist steuerlich
keine Kleinigkeit.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import abrechnung as ab  # noqa: E402


def leistung(name="Schnitt", preis=42.0, minuten=45, satz=19):
    return {"name": name, "preis": preis, "minuten": minuten, "ust_satz": satz}


def termin(preis=42.0, zahlart="bar", abgerechnet="2026-09-03",
           leistung_="Schnitt", id=1):
    return {"id": id, "start": "2026-09-03T10:00", "minuten": 45,
            "kundin": "Frau Holder", "leistung": leistung_, "preis": preis,
            "zahlart": zahlart, "abgerechnet": abgerechnet}


# ————— Was eine Leistung sein muss —————

def test_eine_leistung_braucht_namen_und_preis():
    with pytest.raises(ab.AbrechnungFehler):
        ab.leistung_pruefen({"name": "", "preis": 42})
    with pytest.raises(ab.AbrechnungFehler):
        ab.leistung_pruefen({"name": "Schnitt", "preis": 0})


def test_unsinniger_preis_wird_abgewiesen():
    for p in (-5, 100000, "viel"):
        with pytest.raises(ab.AbrechnungFehler):
            ab.leistung_pruefen({"name": "Schnitt", "preis": p})


def test_deutsche_schreibweise_geht():
    l = ab.leistung_pruefen({"name": "Farbe", "preis": "89,50", "minuten": "120"})
    assert l["preis"] == 89.5 and l["minuten"] == 120


def test_ohne_dauer_gilt_eine_stunde():
    assert ab.leistung_pruefen({"name": "Beratung", "preis": 30})["minuten"] == 60


def test_steuersatz_faellt_auf_neunzehn_zurueck():
    assert ab.leistung_pruefen({"name": "X", "preis": 10})["ust_satz"] == 19
    assert ab.leistung_pruefen({"name": "X", "preis": 10, "ust_satz": 7})["ust_satz"] == 7
    assert ab.leistung_pruefen({"name": "X", "preis": 10, "ust_satz": 5})["ust_satz"] == 19


# ————— Abrechnen —————

def test_abrechnen_braucht_eine_zahlart():
    with pytest.raises(ab.AbrechnungFehler):
        ab.zahlart_pruefen("bitcoin")
    assert ab.zahlart_pruefen("bar") == "bar"
    assert ab.zahlart_pruefen("karte") == "karte"


# ————— Der Vorschlag fürs Kassenbuch —————

def test_die_tagessummen_werden_vorgeschlagen():
    tag = ab.tagesvorschlag("2026-09-03", [
        termin(preis=42.0, zahlart="bar"),
        termin(preis=89.5, zahlart="karte", id=2),
        termin(preis=25.0, zahlart="bar", id=3),
    ])
    assert tag["bar"] == 67.0
    assert tag["karte"] == 89.5
    assert tag["zusammen"] == 156.5
    assert tag["termine"] == 3


def test_nicht_abgerechnete_termine_zaehlen_nicht():
    tag = ab.tagesvorschlag("2026-09-03", [
        termin(preis=42.0), termin(preis=99.0, abgerechnet=None, id=2)])
    assert tag["bar"] == 42.0 and tag["termine"] == 1
    assert tag["offen"] == 1


def test_ein_anderer_tag_zaehlt_nicht_mit():
    t = termin(preis=42.0)
    t["abgerechnet"] = "2026-09-04"
    assert ab.tagesvorschlag("2026-09-03", [t])["zusammen"] == 0.0


def test_sieben_prozent_wird_getrennt_ausgewiesen():
    """Pflegeprodukte laufen mit 7 % — das Kassenbuch fragt danach."""
    t = termin(preis=21.4, id=4)
    t["ust_satz"] = 7
    tag = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0), t])
    assert tag["umsatz7"] == 21.4
    assert tag["zusammen"] == 63.4


def test_der_satz_sagt_was_zu_tun_ist():
    leer = ab.tagesvorschlag("2026-09-03", [])
    voll = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0)])
    assert "nichts" in leer["satz"].lower()
    assert "42" in voll["satz"].replace(",", ".")
    for s in (leer["satz"], voll["satz"]):
        assert s[0].isupper() or s[0].isdigit()


def test_babu_schreibt_das_kassenbuch_nicht_selbst():
    """Der Vorschlag ist ein Vorschlag — er trägt kein Datum der Buchung
    und keine Bestätigung. Das Kassenbuch bleibt die Bestätigung der
    Inhaberin."""
    tag = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0)])
    assert "gebucht" not in tag and "commit" not in tag
    assert tag["vorschlag"] is True


# ————— Aus dem Termin eine Rechnung —————

def test_aus_dem_termin_wird_eine_rechnungsposition():
    p = ab.rechnungsposition(termin(preis=89.5, leistung_="Farbe"))
    assert p["text"] == "Farbe"
    assert p["einzelpreis"] == 89.5
    assert p["ust_satz"] == 19


def test_ohne_preis_keine_position():
    with pytest.raises(ab.AbrechnungFehler):
        ab.rechnungsposition(termin(preis=None))


# ————— Der Punkt ist zweideutig (derselbe Fehler wie in der App) —————

@pytest.mark.parametrize("eingabe, erwartet", [
    (89.5, 89.5),            # echte Zahl — darf nie durch den Text-Parser
    (42, 42.0),
    ("89,50", 89.5),         # deutsch getippt
    ("1.250,00", 1250.0),    # mit Tausenderpunkt
    ("89.50", 89.5),         # englisch getippt
    ("1250", 1250.0),
])
def test_preise_werden_richtig_gelesen(eingabe, erwartet):
    assert ab.leistung_pruefen({"name": "X", "preis": eingabe})["preis"] == erwartet
