"""Was auf den ausgelieferten Seiten stehen muss — und was nie (14.10.2026).

Vorgeschichte: `werbung/barber/seite_bauen.py` und `.../werkstatt/seite_bauen.py`
bauten die beiden Branchenseiten als Kopie der Friseur-Startseite. Am 14.10.2026
liefen 19 ihrer Ersetzungen ins Leere — die Vorlage `index.html` hatte sich um
ein ganzes Geschäftsmodell weiterbewegt (Speicherstufen statt Pakete, kein Buhl,
kein Salon-Check-Fragebogen). Die Seiten selbst waren richtig, weil sie direkt
gepflegt werden; der Erzeuger war der Teil, der hinterherhing.

Deshalb hängt der Schutz jetzt an den Seiten, nicht am Erzeuger. Diese Prüfung
hätte den Befund vom 13.10. gefunden: „ganz ohne eigenes Steuerbüro" stand noch
in zwei Seiten, zwei Tage nachdem der Satz ersetzt worden war.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

SEITEN = HIER.parent.parent / "babu-web"   # server/babu-web/
BRANCHEN = ("barber.html", "werkstatt.html")
ALLE = ("index.html",) + BRANCHEN

#: Steht in docs/master-prompt-nina-coo.md auf der Verbotsliste: widerspricht
#: dem eigenen Impressum und berührt das Steuerberatungsgesetz.
VERBOTEN = "ganz ohne eigenes Steuerbüro"

#: Die Pakete von vor dem 11.10.2026. Verkauft werden drei Speicherstufen.
ALTE_PAKETE = ("39 €", "79 €", "149 €", "Salon Plus", "Shop Plus")


def _seite(name: str) -> str:
    pfad = SEITEN / name
    if not pfad.exists():
        pytest.skip(f"{name} liegt hier nicht")
    return pfad.read_text(encoding="utf-8")


def _deutsch(text: str) -> str:
    """Nur der deutsche Teil — ohne das Übersetzungs-Wörterbuch am Ende.

    Im `var TR={…}` stehen deutsche Sätze als SCHLÜSSEL. Alte Schlüssel, zu
    denen es keinen deutschen Satz mehr gibt, greifen nie; sie zählen nicht
    als Fundstelle, sonst schlägt diese Prüfung auf totem Text an.
    """
    i = text.find("var TR=")
    return text[:i] if i > 0 else text


@pytest.mark.parametrize("name", ALLE)
def test_keine_seite_verspricht_den_verzicht_aufs_steuerbuero(name):
    assert VERBOTEN not in _seite(name), (
        f"{name} trägt den verbotenen Satz. babu ist keine Kanzlei — "
        "die Fassung heißt „mit oder ohne eigenes Steuerbüro“.")


@pytest.mark.parametrize("name", BRANCHEN)
def test_keine_branchenseite_zeigt_die_alten_pakete(name):
    d = _deutsch(_seite(name))
    gefunden = [p for p in ALTE_PAKETE if p in d]
    assert not gefunden, f"{name} zeigt noch {gefunden} — verkauft wird nach Speicher."


@pytest.mark.parametrize("name", BRANCHEN)
def test_jede_branchenseite_nennt_die_drei_stufen_mit_endpreis(name):
    d = _deutsch(_seite(name))
    for stufe, preis in (("1 GB", "9,99"), ("5 GB", "19,99"), ("100 GB", "99,00")):
        assert stufe in d, f"{name}: {stufe} fehlt"
        assert preis in d, f"{name}: der Preis {preis} zu {stufe} fehlt"


@pytest.mark.parametrize("name", BRANCHEN)
def test_keine_branchenseite_nennt_buhl(name):
    """Bis zur Klärung wird Buhl nicht genannt (Verbotsliste, 24.09.2026)."""
    assert "Buhl" not in _seite(name)


def test_die_erzeuger_sagen_ihren_stand():
    """Wer `seite_bauen.py` aufruft, soll nicht glauben, er bekomme die Seite.

    Die beiden Skripte bauten aus `index.html`; am 14.10.2026 passten 19 ihrer
    Ersetzungen nicht mehr. Der Hinweis gehört in die Datei, nicht in ein
    Gedächtnis — und wer sie wieder in Gang setzt, nimmt ihn heraus.
    """
    wurzel = HIER.parent.parent.parent / "werbung"
    for pfad in (wurzel / "barber" / "seite_bauen.py",
                 wurzel / "werkstatt" / "seite_bauen.py"):
        if not pfad.exists():
            continue
        kopf = pfad.read_text(encoding="utf-8")[:2000]
        assert "STILLGELEGT" in kopf, f"{pfad.name} nennt seinen Stand nicht"


def test_die_pruefung_schlaegt_auf_dem_alten_stand_an():
    """Negativkontrolle: die Prüfungen müssen auf dem Stand von vorgestern
    anschlagen, sonst prüfen sie nichts."""
    alt = f"<p>Am Monatsende ist deine Buchhaltung fertig — {VERBOTEN}.</p>"
    assert VERBOTEN in alt
    alt_preis = "<h3>Solo</h3><p>39 € im Monat</p>"
    assert [p for p in ALTE_PAKETE if p in alt_preis] == ["39 €"]
