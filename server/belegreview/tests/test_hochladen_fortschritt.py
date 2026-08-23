"""Hochladen: verkleinern, bevor es rausgeht — und sagen, dass es läuft.

Zwei getrennte Dinge aus Ninas Rückmeldung vom 22.08.2026.

Es dauert. Ein Telefonfoto sind schnell 5 MB, und es ging ungefähr in
Originalgröße raus. Verkleinern kostet keine Genauigkeit — gemessen halten
Beträge bis 620 px Seitenbreite durch (CLAUDE.md, Abschnitt 4) —, und es
geht um ein Vielfaches schneller. Der Weg dafür stand schon im Portal,
aber nur die Belege gingen ihn: die Salonprüfung, der Vertrag und der Brief
schickten das Foto unangetastet.

Und es sagt nichts. Ohne Fortschritt und ohne „fertig" wartet man doppelt
so lange, wie es dauert, weil man nicht weiß, ob überhaupt etwas passiert.

Geprüft wird an der Datei, weil das Portal eine einzige HTML-Datei ohne
Baukasten ist — dieselbe Art Prüfung wie in `test_portal_verdrahtung.py`.
"""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()


# ————— Verkleinern —————

def test_kein_hochladen_schickt_die_rohdatei():
    """Jeder Sendeweg geht durch `fuersNetzVerkleinern` — oder gar nicht.

    `body: datei` heißt: hier geht das Original raus. Bei einem PDF wäre das
    richtig (verkleinern kann es nicht), aber dann steht es hinter einer
    Auswahl, die nur PDF annimmt — und der Weg heißt trotzdem anders.
    """
    roh = re.findall(r"body:\s*datei\b", PORTAL)
    assert not roh, f"{len(roh)} Sendewege schicken die Datei unverkleinert"


def test_das_verkleinern_gibt_es_noch():
    """Gegenprobe, damit die Prüfung oben nicht ins Leere greift."""
    assert "async function fuersNetzVerkleinern(" in PORTAL


def test_verkleinert_wird_auf_eine_kante_die_die_erkennung_traegt():
    """Gemessen sind 100 % Geldwert-Recall bis 1240 px Seitenbreite.

    Die Kante ist die LANGE Seite; ein Hochformat 3:4 behält damit rund
    1650 px Breite. Wer sie unter 1654 setzt, unterschreitet die gemessene
    Reserve — dann bitte vorher neu messen, nicht schätzen.
    """
    m = re.search(r"const UPLOAD_KANTE = (\d+)", PORTAL)
    assert m, "UPLOAD_KANTE ist weg"
    assert int(m.group(1)) >= 1654, "unter die gemessene Reserve gerutscht"


# ————— Fortschritt —————

def test_es_gibt_einen_balken_je_datei():
    assert "function fortschrittZeile(" in PORTAL, "kein Fortschrittsbalken"
    assert ".upbalken" in PORTAL, "der Balken hat keine Gestalt"


def test_der_fortschritt_kommt_vom_senden_selbst():
    """`fetch` meldet keinen Sende-Fortschritt — dafür braucht es XHR.

    Ein Balken, der nur „angefangen/fertig" kennt, ist eine Lüge mit
    Animation.
    """
    assert "upload.addEventListener" in PORTAL


def test_am_ende_steht_ein_haken():
    assert re.search(r"fertig\s*\([^)]*\)", PORTAL), "kein Abschluss-Zustand"
    assert "upzeile fertig" in PORTAL or '"fertig"' in PORTAL


def test_jeder_sendeweg_nutzt_denselben_balken():
    """Belege, Salonprüfung, Vertrag, Brief, Kontoauszug — einer wie der andere."""
    assert len(re.findall(r"\bhochladenMitBalken\(", PORTAL)) >= 5, \
        "nicht alle Sendewege zeigen einen Balken"
