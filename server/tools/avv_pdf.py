#!/usr/bin/env python3
"""Einmalig: /app/avv.pdf aus avv.py erzeugen (fpdf2, nur auf dem Mac).

Das Ergebnis wird committet (server/babu-web/app/avv.pdf) — der Server
liefert die Datei nur aus, braucht deshalb KEINE PDF-Bibliothek im
Container. Neue AVV-Fassung = dieses Skript laufen lassen + committen.

Schriften: Helvetica ist Kern-PDF und Umlaut-fähig (latin-1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "belegreview"))
import avv  # noqa: E402

from fpdf import FPDF  # noqa: E402

titel, text = avv.TEXTE["avv"]

# Helvetica (Kern-PDF-Schrift) kennt latin-1 — die typografischen Zeichen
# des Vertrags fallen auf die ASCII/latin-1-Entsprechungen zurück. Der
# HTML-/Textfassung bleibt der feine Strich; das PDF ist die Druckkopie.
for a, b in (("—", "-"), ("„", '"'), ("“", '"'), ("’", "'"), ("·", "·")):
    text = text.replace(a, b)
titel = titel.replace("—", "-")

pdf = FPDF(format="A4")
pdf.set_auto_page_break(True, margin=22)
pdf.add_page()

pdf.set_font("Helvetica", "B", 16)
pdf.cell(0, 10, "babu · " + titel, new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(120)
pdf.cell(0, 6, "babu · 0711 Intelligence · Stuttgart", new_x="LMARGIN", new_y="NEXT")
pdf.ln(6)
pdf.set_text_color(30)

for absatz in text.split("\n\n"):
    a = absatz.strip()
    if not a:
        continue
    eingerueckt = a.startswith("    ")
    if eingerueckt:
        a = a[4:]
        x0 = pdf.l_margin + 14
    else:
        x0 = pdf.l_margin
    pdf.set_x(x0)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.multi_cell(0, 5.6, a)

pdf.ln(4)
pdf.set_x(pdf.l_margin)
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(120)
pdf.cell(0, 5, "babu ersetzt keine individuelle Steuerberatung. · mybabu.io",
         new_x="LMARGIN", new_y="NEXT")

ziel = Path(__file__).resolve().parents[1] / "babu-web" / "app" / "avv.pdf"
pdf.output(str(ziel))
print("geschrieben:", ziel, ziel.stat().st_size, "Bytes")
