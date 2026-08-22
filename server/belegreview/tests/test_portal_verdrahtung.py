"""Das Portal ist eine einzige HTML-Datei — falsche Verdrahtung fällt still aus.

Wer im Menü auf einen Namen zeigt, den `ansichten` nicht kennt, landet
wortlos wieder auf „Heute". Kein Fehler, keine Meldung, nur ein Knopf, der
nichts tut. Beim Anbauen der Kundenkartei war genau das eine Zeile weit weg:
die Ansicht war registriert, der Abschnitt fehlte fast.
"""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()


def _ansichten() -> set[str]:
    """Die Namen aus dem ansichten-Verzeichnis."""
    block = re.search(r"const ansichten = \{(.*?)\};", PORTAL, re.S).group(1)
    return set(re.findall(r"(\w+)\s*:", block))


def _abschnitte() -> set[str]:
    return set(re.findall(r'<section class="ansicht" id="a-(\w+)"', PORTAL))


def _menuziele() -> set[str]:
    return set(re.findall(r"menuGeh\('#(\w+)'\)", PORTAL)) | \
           set(re.findall(r'<button data-ziel="(\w+)"', PORTAL))


def test_jede_ansicht_hat_ihren_abschnitt():
    fehlt = _ansichten() - _abschnitte() - {"detail"}
    assert not fehlt, f"registriert, aber ohne <section>: {sorted(fehlt)}"


def test_jeder_abschnitt_ist_registriert():
    fehlt = _abschnitte() - _ansichten()
    assert not fehlt, f"<section> da, aber nicht in ansichten: {sorted(fehlt)}"


def test_jeder_menuknopf_fuehrt_irgendwohin():
    fehlt = _menuziele() - _ansichten()
    assert not fehlt, f"Menüziel ohne Ansicht — landet stumm auf Heute: {sorted(fehlt)}"


def test_die_neuen_wege_sind_da():
    """Gegenprobe, damit die Prüfungen oben nicht ins Leere greifen."""
    assert {"kundinnen", "preise", "termine"} <= _ansichten()
    assert "kundinnen" in _menuziele(), "die Kartei ist über das Menü nicht erreichbar"


def test_funktionen_hinter_den_ansichten_gibt_es():
    """`ansichten` verweist auf Funktionen — fehlt eine, bricht das Laden."""
    block = re.search(r"const ansichten = \{(.*?)\};", PORTAL, re.S).group(1)
    for name in re.findall(r":\s*(lade\w+)", block):
        assert re.search(rf"(async )?function {name}\s*\(", PORTAL), \
            f"{name}() ist eingetragen, aber nirgends definiert"
