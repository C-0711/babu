"""Sprachregel-Linter (Task Q.4): kein Technik-Vokabular in der Salon-UI.

Verbindliche Regel aus HANDOVER §1 / Spec: Vertrauen = ein grüner Haken,
keine Systemnamen, keine Geräte-/Server-Behauptungen.
"""
import re
from pathlib import Path

PORTAL = Path(__file__).resolve().parent.parent / "portal.html"

# Großgeschriebene Wortform = sichtbare Copy. Kleingeschriebene JS-Bezeichner
# (.commit, bild_oid …) sind erlaubt — die sieht niemand.
VERBOTEN = [r"\bServer\b", r"\bOCR\b", r"\bKI\b", r"\bModell\b", r"\bMerkle\b",
            r"\bHash\b", r"\bCommit\b", r"\bToken\b", r"\bPAT\b",
            r"\bConfidence\b", r"\bQueue\b", r"übermitteln"]


def test_keine_verbotenen_woerter():
    text = PORTAL.read_text()
    # Kommentare zählen nicht — die sieht die Nutzerin nicht.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    treffer = [(w, m.group(0)) for w in VERBOTEN
               for m in re.finditer(w, text)]
    assert not treffer, f"Technik-Vokabular in der Salon-UI: {treffer}"
