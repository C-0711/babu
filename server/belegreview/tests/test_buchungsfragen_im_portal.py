"""Portal zeigt strukturierte Fragen aus buchung.fragen statt generischer Texte.

Issue #66: Nina sah "was für infos fehlen dir noch zu diesem beleg?" — einen
generischen Platzhalter aus felder.offen statt der konkreten Frage aus
buchung.fragen: "Wofür wurden die Hair Extensions gekauft?"

Das Portal muss prüfen, ob buchung.fragen existiert und diese Fragen anzeigen.
"""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()


def test_portal_prueft_buchung_fragen():
    """Das Portal schaut auf d.buchung.fragen, nicht nur auf f.offen."""
    # Die Logik steht in ladeDetail
    detail_rumpf = re.search(
        r"async function ladeDetail\(stamm\)\{(.*?)^async function ",
        PORTAL, re.S | re.M).group(1)
    
    assert "buchungFrage" in detail_rumpf, \
        "buchung.fragen wird nicht ausgewertet"
    assert "d.buchung" in detail_rumpf and "fragen" in detail_rumpf, \
        "buchung.fragen-Objekt wird nicht gelesen"


def test_fragetext_hat_vorrang_vor_offen():
    """buchung.fragen[0].frage ersetzt offenSatz(offen[0])."""
    detail_rumpf = re.search(
        r"async function ladeDetail\(stamm\)\{(.*?)^async function ",
        PORTAL, re.S | re.M).group(1)
    
    # Es muss eine Prüfung geben: buchungFrage ? buchungFrage.frage : offenSatz(...)
    assert re.search(r"buchungFrage.*\?.*frage.*:.*offenSatz", detail_rumpf), \
        "buchungFrage.frage wird nicht bevorzugt"


def test_generische_offen_texte_werden_uebersetzt():
    """„Noch nicht gebucht — babu hat Fragen an dich" wird verständlicher."""
    offen_satz = re.search(
        r"function offenSatz\(o\)\{(.*?)^\}", PORTAL, re.S | re.M).group(1)
    
    # Der Filter sollte "noch nicht gebucht" oder "fragen an dich" erkennen
    assert re.search(r"noch nicht gebucht|fragen an dich", offen_satz, re.I), \
        "generische Backend-Texte werden nicht gefiltert"
    assert "Kurz ansehen" in offen_satz or "einordnen" in offen_satz, \
        "kein verständlicherer Ersatztext"
