"""Abschluss-Lane: Lane-Wahl, Art-Erkennung, Extraktion, Summenproben.

Synthetische PDFs werden zur Testzeit gebaut (Minimal-PDF mit Textebene);
das LLM ist überall gemockt — echte Abschluss-Dokumente bleiben lokal.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import abschluss_lesen as al  # noqa: E402


def _text_pdf(zeilen: list[str]) -> bytes:
    """Minimal-PDF (eine Seite, Helvetica/WinAnsi) mit echter Textebene."""
    inhalt = ["BT /F1 12 Tf 72 760 Td 14 TL"]
    for z in zeilen:
        s = z.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        inhalt.append(f"({s}) Tj T*")
    inhalt.append("ET")
    strom = "\n".join(inhalt).encode("latin-1")
    objekte = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(strom)).encode() + b" >>\nstream\n"
        + strom + b"\nendstream",
    ]
    puffer = b"%PDF-1.4\n"
    stellen = []
    for i, obj in enumerate(objekte, 1):
        stellen.append(len(puffer))
        puffer += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(puffer)
    puffer += f"xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n".encode()
    for s in stellen:
        puffer += f"{s:010d} 00000 n \n".encode()
    puffer += (f"trailer\n<< /Size {len(objekte) + 1} /Root 1 0 R >>\n"
               f"startxref\n{xref}\n%%EOF\n").encode()
    return puffer


EUER_ZEILEN = [
    "Einnahmenüberschussrechnung 2024",
    "Salon Testlocke, Ludwigsburg",
    "Betriebseinnahmen gesamt: 100.000,00",
    "Wareneinkauf: 11.000,00",
    "Personalkosten: 48.000,00",
    "Raumkosten: 12.000,00",
    "Abschreibungen: 3.000,00",
    "Sonstige Kosten: 6.000,00",
    "Gewinn: 20.000,00",
    "Steuernummer 71/123/45678, Finanzamt Ludwigsburg",
] + ["Fülltext für die Textebene der Seite."] * 6


def test_betrag_zahl():
    assert al.betrag_zahl("1.234,56 €") == 1234.56
    assert al.betrag_zahl("-300,10") == -300.10
    assert al.betrag_zahl(20000) == 20000.0
    assert al.betrag_zahl("20000.5") == 20000.5
    assert al.betrag_zahl("") is None
    assert al.betrag_zahl("kein Betrag") is None


def test_art_anker_ohne_llm():
    def kein_llm(*a, **k):
        raise AssertionError("Anker müssen ohne Hilfe reichen")
    assert al.art_erkennen("… Einnahmenüberschussrechnung …", llm=kein_llm) == "euer"
    assert al.art_erkennen("Betriebswirtschaftliche Auswertung", llm=kein_llm) == "bwa"
    assert al.art_erkennen("Bescheid für 2024 über Einkommensteuer",
                           llm=kein_llm) == "bescheid"
    assert al.art_erkennen("Anlagenverzeichnis zum 31.12.", llm=kein_llm) == "anlagen"
    assert al.art_erkennen("Summen- und Saldenliste", llm=kein_llm) == "susa"
    assert al.art_erkennen("", llm=kein_llm) == "sonstiges"


def test_art_llm_fallback():
    assert al.art_erkennen("Irgendein Brief", llm=lambda n, **k: {"art": "bwa"}) == "bwa"
    assert al.art_erkennen("Irgendein Brief",
                           llm=lambda n, **k: {"art": "quatsch"}) == "sonstiges"


def test_dokument_lesen_text_lane(tmp_path):
    pdf = tmp_path / "euer-2024.pdf"
    pdf.write_bytes(_text_pdf(EUER_ZEILEN))

    def llm(nachrichten, **k):
        # Volltext muss beim LLM ankommen — daran hängt die Extraktion.
        assert "Betriebseinnahmen" in nachrichten[-1]["content"]
        return {"umsatz": "100.000,00", "wareneinsatz": 11000,
                "personal": 48000, "raumkosten": 12000, "afa": 3000,
                "sonstige_kosten": 6000, "gewinn": 20000,
                "ust_zahllast": None, "steuernummer": "71/123/45678",
                "finanzamt": "Ludwigsburg", "rechtsform": None}

    gemeldet = []
    d = al.dokument_lesen(pdf, jahr=2024, melden=gemeldet.append, llm=llm)
    assert d["lane"] == "text"
    assert d["art"] == "euer"
    assert d["werte"]["umsatz"] == 100000.0
    assert d["werte"]["steuernummer"] == "71/123/45678"
    assert "ust_zahllast" not in d["werte"]          # null → gar nicht melden
    schluessel = [f["schluessel"] for f in gemeldet]
    assert "umsatz" in schluessel and "finanzamt" in schluessel
    assert all(f["sicher"] for f in gemeldet)
    assert any("euer-2024.pdf" in f["quelle"] for f in gemeldet)


def test_dokument_lesen_scan_lane(tmp_path):
    from PIL import Image
    bild = tmp_path / "bescheid.jpg"
    Image.new("RGB", (800, 1100), "white").save(bild)

    antworten = [
        {"art": "bescheid", "text": "Einkünfte aus Gewerbebetrieb: 20.000"},
        {"gewinn": 20000, "est_vorauszahlungen": 2000,
         "ust_zahllast": None, "steuernummer": "71/123/45678",
         "finanzamt": "Ludwigsburg", "rechtsform": "Einzelunternehmen"},
    ]
    d = al.dokument_lesen(bild, jahr=2024, melden=None,
                          llm=lambda n, **k: antworten.pop(0))
    assert d["lane"] == "scan"
    assert d["art"] == "bescheid"
    assert d["werte"]["est_vorauszahlungen"] == 2000.0
    assert not antworten                              # beide Calls verbraucht


def test_zusammenfuehren_mit_proben():
    euer = {"datei": "euer.pdf", "art": "euer", "seiten": 6, "lane": "text",
            "werte": {"umsatz": 100000.0, "wareneinsatz": 11000.0,
                      "personal": 48000.0, "raumkosten": 12000.0,
                      "afa": 3000.0, "sonstige_kosten": 6000.0,
                      "gewinn": 20000.0, "steuernummer": "71/123/45678"},
            "afa_liste": []}
    bescheid = {"datei": "b.pdf", "art": "bescheid", "seiten": 2, "lane": "scan",
                "werte": {"gewinn": 20000.0, "est_vorauszahlungen": 2000.0,
                          "finanzamt": "Ludwigsburg"},
                "afa_liste": []}
    kn = al.zusammenfuehren([euer, bescheid], jahr=2024)
    assert kn["zahlen"]["gewinn"] == 20000.0          # EÜR hat Vorrang
    assert kn["zahlen"]["est_vorauszahlungen"] == 2000.0
    assert kn["stammdaten"]["finanzamt"] == "Ludwigsburg"
    assert kn["pruefungen"]["summenprobe_ok"] is True
    assert kn["pruefungen"]["bescheid_abgleich_ok"] is True
    assert kn["unsicher"] == []
    assert [q["art"] for q in kn["quellen"]] == ["euer", "bescheid"]


def test_summenprobe_schlaegt_an():
    euer = {"datei": "euer.pdf", "art": "euer", "seiten": 6, "lane": "text",
            "werte": {"umsatz": 100000.0, "wareneinsatz": 11000.0,
                      "personal": 48000.0, "raumkosten": 12000.0,
                      "afa": 3000.0, "sonstige_kosten": 6000.0,
                      "gewinn": 35000.0},                 # passt nicht
            "afa_liste": []}
    kn = al.zusammenfuehren([euer], jahr=2024)
    assert kn["pruefungen"]["summenprobe_ok"] is False
    assert "gewinn" in kn["unsicher"]


def test_bescheid_widerspricht_euer():
    euer = {"datei": "euer.pdf", "art": "euer", "seiten": 6, "lane": "text",
            "werte": {"gewinn": 20000.0}, "afa_liste": []}
    bescheid = {"datei": "b.pdf", "art": "bescheid", "seiten": 2, "lane": "scan",
                "werte": {"gewinn": 31000.0}, "afa_liste": []}
    kn = al.zusammenfuehren([euer, bescheid], jahr=2024)
    assert kn["pruefungen"]["bescheid_abgleich_ok"] is False
    assert "gewinn" in kn["unsicher"]


def test_seiten_text_liest_minimal_pdf(tmp_path):
    pdf = tmp_path / "probe.pdf"
    pdf.write_bytes(_text_pdf(EUER_ZEILEN))
    seiten = al.seiten_text(pdf)
    assert len(seiten) == 1
    assert "Einnahmenüberschussrechnung" in seiten[0]
    assert len(seiten[0]) >= al.TEXT_SCHWELLE
