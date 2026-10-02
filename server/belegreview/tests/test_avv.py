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
    # Parteien: babu und eine Lücke für den Betrieb
    assert "0711 Intelligence" in t
    assert "(Name des Betriebs" in t
    # Art.-28-Abs. 3-Pflichtpunkte (Stichproben, je einer reicht)
    for wort in ("Weisung", "Vertraulichkeit", "Sicherheit", "Löschung",
                 "Unterbeauftragte", "Kontroll", "Stuttgart"):
        assert wort in t, wort


def test_oeffentliche_fassung_nennt_keinen_betrieb():
    """Bis 03.10.2026 stand der Pilotbetrieb mit Anschrift und Steuernummer
    auf der öffentlichen Seite und im PDF."""
    t = avv.TEXTE["avv"][1]
    for wort in ("SupremeStudio", "Nina Baic", "Ludwigsburg", "71015"):
        assert wort not in t, wort
    # Das PDF ist komprimiert — der Text muss herausgelesen werden.
    pdfium = __import__("pytest").importorskip("pypdfium2")
    pdf = Path(__file__).resolve().parents[2] / "babu-web" / "app" / "avv.pdf"
    dok = pdfium.PdfDocument(str(pdf))
    inhalt = "".join(dok[i].get_textpage().get_text_range() for i in range(len(dok)))
    assert "Auftragsverarbeitung" in inhalt.replace("\r", "").replace("\n", " ")
    for wort in ("SupremeStudio", "Ludwigsburg", "71015"):
        assert wort not in inhalt, wort


def test_ausgefuellte_fassung_traegt_den_betrieb():
    p = avv.partei_aus({"betrieb_name": "Salon Sonne", "rechtsform": "GbR",
                        "anschrift": "Hauptstr. 1, 70173 Stuttgart",
                        "steuernummer": "99/123/45678", "finanzamt": "Stuttgart I"},
                       {"name": "Sonja Sonne", "email": "sonja@sonne.de"},
                       "2026-10-03T08:00:00Z")
    t = avv.text(p)
    for wort in ("Salon Sonne (GbR)", "Hauptstr. 1", "Sonja Sonne",
                 "sonja@sonne.de", "99/123/45678 (Finanzamt Stuttgart I)",
                 "Konto seit 03.10.2026"):
        assert wort in t, wort


def test_fehlende_angaben_bleiben_luecken():
    t = avv.text(avv.partei_aus({}, None))
    assert t.count("(noch nicht in den Betriebsangaben)") == 5


def test_pdf_existiert_und_ist_ein_pdf():
    pdf = Path(__file__).resolve().parents[2] / "babu-web" / "app" / "avv.pdf"
    assert pdf.is_file()
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_routen_sind_registriert():
    import babu_web  # noqa: E402
    pfade = {getattr(r, "path", "") for r in babu_web.app.routes}
    assert "/avv" in pfade
    assert "/avv/mein" in pfade
    assert "/app/{name}" in pfade
    assert "avv.pdf" in babu_web.APP_DATEIEN
