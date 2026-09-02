"""Reine Logik der Wissensschicht: Themen erkennen, Seiten lesen, Chunking.

Kein Server, kein Embedding-Dienst — `datev_wissen.py` ist bewusst frei von
Server-Zustand, damit sich Themenerkennung und Chunking ohne Box und ohne
vLLM testen lassen.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import datev_wissen  # noqa: E402


# ── thema_erkennen ───────────────────────────────────────────────────────

def test_thema_erkennen_kontenrahmen():
    text = "Der SKR04-Kontenrahmen gliedert sich in zehn Kontenklassen. " \
          "Jedes Sachkonto trägt eine vierstellige Kontonummer."
    assert datev_wissen.thema_erkennen(text) == "kontenrahmen"


def test_thema_erkennen_steuerschluessel():
    text = "Automatikkonten übernehmen den passenden Vorsteuerschlüssel " \
          "automatisch — der Steuerschlüssel steht im Buchungssatz."
    assert datev_wissen.thema_erkennen(text) == "steuerschluessel"


def test_thema_erkennen_afa():
    text = "Die AfA-Tabelle nennt die Nutzungsdauer für Anlagevermögen; " \
          "GWG bis 800 Euro werden sofort abgeschrieben."
    assert datev_wissen.thema_erkennen(text) == "afa"


def test_thema_erkennen_lohn():
    text = "Die Lohnabrechnung führt Lohnsteuer und Sozialversicherung " \
          "ab; ein Minijob bleibt im Lohnkonto gesondert ausgewiesen."
    assert datev_wissen.thema_erkennen(text) == "lohn"


def test_thema_erkennen_jahresabschluss():
    text = "Die EÜR ersetzt bei kleinen Betrieben die Bilanz; Summen- " \
          "und Saldenliste (SuSa) und BWA gehören zur Gewinnermittlung."
    assert datev_wissen.thema_erkennen(text) == "jahresabschluss"


def test_thema_erkennen_ohne_treffer_ist_sonstiges():
    assert datev_wissen.thema_erkennen("Ein Text ohne jedes Fachwort.") == "sonstiges"
    assert datev_wissen.thema_erkennen("") == "sonstiges"


def test_thema_erkennen_schaut_nur_auf_den_anfang():
    # Ein Treffer weit hinter den ersten 4000 Zeichen zählt nicht.
    text = "Vorwort ohne Fachwort. " + "Fülltext. " * 1000 + "Kontenrahmen SKR04."
    assert datev_wissen.thema_erkennen(text) == "sonstiges"


# ── atome_bauen ──────────────────────────────────────────────────────────

def test_atome_bauen_loc_format():
    # Der zweite Absatz sprengt für sich allein schon den Chunk — beide
    # bleiben deshalb getrennte Blöcke statt zu einem zu verschmelzen.
    riesig = "B" * (datev_wissen.WISSEN_CHUNK_ZEICHEN + 100)
    atome = datev_wissen.atome_bauen([f"Erster Absatz.\n\n{riesig}"])
    assert [a["loc"] for a in atome] == ["S1#0", "S1#1"]
    assert atome[0]["text"] == "Erster Absatz."
    assert atome[1]["text"] == riesig


def test_atome_bauen_zweite_seite_zaehlt_neu():
    seiten = ["Seite eins.", "Seite zwei."]
    atome = datev_wissen.atome_bauen(seiten)
    assert [a["loc"] for a in atome] == ["S1#0", "S2#0"]


def test_atome_bauen_chunk_grenze():
    # Zwei Absätze, die zusammen über WISSEN_CHUNK_ZEICHEN gehen, werden
    # zu zwei Blöcken statt einem.
    a = "A" * (datev_wissen.WISSEN_CHUNK_ZEICHEN - 100)
    b = "B" * 500
    atome = datev_wissen.atome_bauen([f"{a}\n\n{b}"])
    assert len(atome) == 2
    assert atome[0]["text"] == a
    assert atome[1]["text"] == b


def test_atome_bauen_kurzer_rest_wird_angehaengt():
    # `a` allein passt noch in einen Block, aber zusammen mit `kurz` würde
    # der Chunk gesprengt — `kurz` landet als eigener, magerer Block und
    # wird danach (weil unter WISSEN_CHUNK_MIN) an den vorherigen angehängt
    # statt ein eigenes Atom zu werden.
    a = "A" * (datev_wissen.WISSEN_CHUNK_ZEICHEN - 5)
    kurz = "kurz"  # weit unter WISSEN_CHUNK_MIN
    atome = datev_wissen.atome_bauen([f"{a}\n\n{kurz}"])
    assert len(atome) == 1
    assert atome[0]["text"] == f"{a}\n\n{kurz}"


def test_atome_bauen_deckel_greift():
    seiten = [f"Absatz {i}." * 5 + "\n\n" + f"Absatz {i}b." * 5 for i in range(1000)]
    atome = datev_wissen.atome_bauen(seiten)
    assert len(atome) == datev_wissen.WISSEN_ATOME_MAX


def test_atome_bauen_leere_seite_liefert_nichts():
    assert datev_wissen.atome_bauen(["", "   \n\n  "]) == []


# ── seiten_lesen ─────────────────────────────────────────────────────────

def test_seiten_lesen_markdown(tmp_path):
    datei = tmp_path / "hilfe.md"
    datei.write_text("# Titel\n\nEin Absatz Text.")
    assert datev_wissen.seiten_lesen(datei) == ["# Titel\n\nEin Absatz Text."]


def test_seiten_lesen_txt(tmp_path):
    datei = tmp_path / "notiz.txt"
    datei.write_text("Reiner Text.")
    assert datev_wissen.seiten_lesen(datei) == ["Reiner Text."]


def test_seiten_lesen_bild_ohne_ocr_ist_leer(tmp_path):
    datei = tmp_path / "beleg.png"
    datei.write_bytes(b"\x89PNG\r\n")
    assert datev_wissen.seiten_lesen(datei) == [""]


def test_seiten_lesen_bild_mit_ocr(tmp_path):
    datei = tmp_path / "beleg.jpg"
    datei.write_bytes(b"\xff\xd8\xff")
    gesehen = {}

    def ocr(jpeg: bytes, name: str) -> str:
        gesehen["jpeg"] = jpeg
        gesehen["name"] = name
        return "abgeschriebener Text"

    assert datev_wissen.seiten_lesen(datei, ocr=ocr) == ["abgeschriebener Text"]
    assert gesehen["jpeg"] == b"\xff\xd8\xff"
    assert gesehen["name"] == "beleg.jpg"


def test_seiten_lesen_unbekannte_endung_ist_leer(tmp_path):
    datei = tmp_path / "sonstwas.xyz"
    datei.write_text("x")
    assert datev_wissen.seiten_lesen(datei) == []


def test_seiten_lesen_pdf_nutzt_textebene(tmp_path, monkeypatch):
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text",
                        lambda pfad: ["Seite mit ordentlich viel Textebene, "
                                     "lang genug um die Schwelle zu reißen " * 3,
                                     "Seite zwei, auch mit Text " * 3])
    datei = tmp_path / "handbuch.pdf"
    datei.write_bytes(b"%PDF-1.4")
    seiten = datev_wissen.seiten_lesen(datei)
    assert len(seiten) == 2
    assert "Textebene" in seiten[0]


def test_seiten_lesen_pdf_ruft_ocr_nur_bei_duennen_seiten(tmp_path, monkeypatch):
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text",
                        lambda pfad: ["genug Text auf dieser Seite, "
                                     "definitiv über der Schwelle " * 3, ""])
    monkeypatch.setattr(abschluss_lesen, "seiten_bilder",
                        lambda pfad: [b"bild1", b"bild2"])
    aufrufe = []

    def ocr(jpeg: bytes, name: str) -> str:
        aufrufe.append((jpeg, name))
        return "abgeschrieben"

    datei = tmp_path / "handbuch.pdf"
    datei.write_bytes(b"%PDF-1.4")
    seiten = datev_wissen.seiten_lesen(datei, ocr=ocr)
    assert len(aufrufe) == 1          # nur die zweite (dünne) Seite
    assert aufrufe[0][0] == b"bild2"
    assert seiten[1] == "abgeschrieben"
    assert "genug Text" in seiten[0]  # erste Seite bleibt bei der Textebene


def test_seiten_lesen_pdf_ohne_ocr_laesst_duenne_seiten_duenn(tmp_path, monkeypatch):
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text", lambda pfad: ["", "auch dünn"])
    datei = tmp_path / "scan.pdf"
    datei.write_bytes(b"%PDF-1.4")
    assert datev_wissen.seiten_lesen(datei) == ["", "auch dünn"]
