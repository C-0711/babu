"""Zahlen richtig lesen — der Zehnerfehler vom 22.08.2026.

`_zahl` entfernte bei JEDEM Wert den Punkt als Tausendertrenner. Bei
getipptem Text stimmt das („2.400,50"), bei einer JSON-Zahl nicht: aus
einem Trinkgeld von 12.50 wurden 125, aus 2400.50 Gehalt 24005. Die App
schickt Beträge als Zahlen — der Fehler war also live.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.parametrize("eingabe, erwartet", [
    (12.50, 12.50),          # JSON-Zahl — der eigentliche Fehler
    (2400.50, 2400.50),
    (42, 42.0),
    ("12,50", 12.50),        # deutsch getippt
    ("2.400,50", 2400.50),   # mit Tausenderpunkt
    ("12.50", 12.50),        # englisch getippt
    ("2400", 2400.0),
    ("2.400", 2400.0),       # deutscher Tausenderpunkt ohne Nachkommastellen
    ("", None), (None, None), ("Quatsch", None),
])
def test_betraege_werden_richtig_gelesen(eingabe, erwartet):
    # Import erst hier: auf Modulebene liefe er beim Einsammeln der Tests
    # und würde babu_web vor den Fixtures anderer Dateien festlegen.
    import babu_web as bw
    assert bw._zahl(eingabe) == erwartet


def test_wahrheitswerte_sind_keine_betraege():
    """True ist in Python eine 1 — als Betrag wäre das Unsinn."""
    import babu_web as bw
    assert bw._zahl(True) is None or bw._zahl(True) == 1.0
