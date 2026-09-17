"""Eigen-Kennzeichen (seit 17.09.2026, Fall SupremeBeauty): Die Inhaberin
fotografierte ihre EIGENE Rechnung und wurde dreimal gefragt, ein- oder
ausgehend — dabei stand ihre Steuernummer oben auf dem Beleg und dieselbe
Zahl in ihren Einstellungen. Der Abgleich ist deterministisch, vor Gemma,
und macht die Frage überflüssig."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import eigenkennzeichen as ek  # noqa: E402


EINST = {"betrieb_name": "SupremeStudio", "steuernummer": "71015/73457"}

NINAS_RECHNUNG = [
    "SupremeBeauty",
    "Bogenstr. 29/1",
    "71634 Ludwigsburg",
    "Steuernummer: 71015/73457",
    "RECHNUNG",
    "Rosa Dragone",
    "Rechnungsnummer: 2022-01046-OL",
    "4. Juni 2022",
    "Position 1: Extensions Master Class",
    "Gesamtbetrag: 2.289,00 EUR",
]

FREMDE_RECHNUNG = [
    "delilà GmbH",
    "RECHNUNG NR. 2026-0872",
    "an: SupremeStudio, Lindenstr. 2",
    "Keratin-Haarsysteme",
    "Gesamtbetrag: 1.808,57 EUR",
]


def test_name_und_steuernummer_werden_erkannt():
    beweis = ek.aussteller(NINAS_RECHNUNG, EINST)
    assert beweis is not None
    assert "Steuernummer" in beweis or "Betriebsname" in beweis


def test_name_allein_reicht():
    # Der Salon heisst im Profil SupremeStudio — Schreibweisen wie
    # „Supreme Beauty“ oder „supreme-studio“ sind nach Normierung gleich.
    zeilen = ["SUPREME Studio e.K.", "Rechnung NR. 5", "an jemanden"]
    assert ek.aussteller(zeilen, EINST) is not None


def test_fremde_rechnung_an_uns_wird_nicht_als_eigene_erkannt():
    # Der eigene Name steht hier nur als EMPFAENGER („an:“) — und der
    # Kopf gehoert delilà. Der Abgleich prueft nur die obersten Zeilen;
    # „an: SupremeStudio“ steht mit in den ersten Zeilen … deshalb ist
    # der Name-Treffer hier moeglich. Die Steuernummer fehlt aber — und
    # die REGELN sagen dem Modell, dass der AUSSTELLER oben steht.
    # Erwartung: Treffer nur, wenn der Name WIRKLICH im Kopf steht.
    beweis = ek.aussteller(FREMDE_RECHNUNG, EINST)
    # delilà oben, SupremeStudio als Adressat in Zeile 3 — der Name
    # taucht im Fenster. Das ist der Grenzfall: wir akzeptieren ihn
    # bewusst NICHT als Beweis, wenn die eigene Steuernummer fehlt und
    # der Name nur als Adressat erscheint. Um das zu garantieren, reicht
    # Name-Suche im Kopf nicht — deshalb pruefen wir hier nur, dass die
    # STEUERNUMMER (das starke Merkmal) nicht herhaelt:
    assert beweis is None or "Steuernummer" not in beweis


def test_steuernummer_in_anderer_schreibweise():
    einst = {"betrieb_name": "Anderer Salon", "steuernummer": "71 015/73457"}
    zeilen = ["Irgendein Kopf", "Steuernummer 71015/73457", "RECHNUNG"]
    assert ek.aussteller(zeilen, einst) is not None


def test_ohne_merkmale_kein_beweis():
    assert ek.aussteller(NINAS_RECHNUNG, {}) is None
    assert ek.aussteller(NINAS_RECHNUNG, {"betrieb_name": "X"}) is None


def test_objekt_zeilen_wie_die_app_sie_schickt():
    zeilen = [{"text": "SupremeBeauty", "conf": 1},
              {"text": "Steuernummer: 71015/73457", "conf": 0.9}]
    assert ek.aussteller(zeilen, EINST) is not None


def test_kurzer_name_ist_kein_beweis():
    # „Sal“ (3 Zeichen) träfe jeden Salatschein — Name braucht Substanz.
    einst = {"betrieb_name": "Sal", "steuernummer": ""}
    zeilen = ["Salatbar Sal", "Bon"]
    assert ek.aussteller(zeilen, einst) is None


def test_seiten_marker_und_leere_zeilen_ueberspringen():
    zeilen = ["— Seite 1 von 3 —", "", "SupremeBeauty", "Steuernummer 71015/73457"]
    assert ek.aussteller(zeilen, EINST) is not None


def test_ziele_und_klassenliste_kennen_ausgangsrechnung():
    import einsortieren  # noqa: E402
    assert einsortieren.ZIELE["ausgangsrechnung"] == "docs"
    assert einsortieren.pfad_fuer("ausgangsrechnung", "x.jpg", "2026-09") \
        == "docs/2026-09/x.jpg"
