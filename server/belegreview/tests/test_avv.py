"""Der Auftragsverarbeitungsvertrag (seit 17.09.2026): Route, PDF, Inhalte.

Art. 28 DSGVO — Vertrag in Textform zwischen Betrieb und babu. Der Text
steht in avv.py (Parteienblock austauschbar), die HTML-Seite läuft über
/recht_seite mit, das PDF ist eine committete Datei unter /app/avv.pdf.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import avv  # noqa: E402


def test_avv_ist_kein_platzhalter():
    assert avv.fertig()


def test_avv_nennt_beide_parteien_und_die_pflichtpunkte():
    t = avv.TEXTE["avv"][1]
    # Parteien
    assert "SupremeStudio" in t and "Nina Baic" in t
    assert "0711 Intelligence" in t
    # Art.-28-Abs. 3-Pflichtpunkte (Stichproben, je einer reicht)
    for wort in ("Weisung", "Vertraulichkeit", "Sicherheit", "Löschung",
                 "Unterbeauftragte", "Kontroll", "Stuttgart", "Ludwigsburg"):
        assert wort in t, wort


def test_pdf_existiert_und_ist_ein_pdf():
    pdf = Path(__file__).resolve().parents[2] / "babu-web" / "app" / "avv.pdf"
    assert pdf.is_file()
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_routen_sind_registriert():
    import babu_web  # noqa: E402
    pfade = {getattr(r, "path", "") for r in babu_web.app.routes}
    assert "/avv" in pfade
    assert "/app/{name}" in pfade
    assert "avv.pdf" in babu_web.APP_DATEIEN
