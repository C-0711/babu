"""Wissensschicht für hochgeladene DATEV-Dokumente — Themen, Seiten, Atome.

Anderes Modul als `wissen.py` (das ist das Fallwissen des Chats über den
Salon — Namensgleichheit wäre verwirrend, deshalb hier bewusst
`datev_wissen`). Reine Logik ohne Server-Zustand: kein Git, kein
Embedding-Aufruf, kein Threading — das macht `babu_web._wissen_job`
(Phase 3). Nur `seiten_lesen()` braucht für Scans einen OCR-Aufruf, und
den reicht der Aufrufer als Funktion herein, statt dass dieses Modul
`babu_web` importiert und das `_LLM_SEMAPHORE` kennen müsste.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

# ── Themen ───────────────────────────────────────────────────────────────
#
# Ein erster Entwurf, keine geprüfte Taxonomie (siehe Planungsdokument).
# Falsch einsortierte Dokumente lassen sich über „Verschieben" in der
# Ablage korrigieren.
THEMEN: dict[str, tuple[str, tuple[str, ...]]] = {
    "kontenrahmen":   ("Kontenrahmen", ("kontenrahmen", "skr04", "skr03",
                        "kontenplan", "sachkonto", "kontenklasse")),
    "steuerschluessel": ("Steuerschlüssel", ("steuerschlüssel", "steuerschluessel",
                        "automatikkonto", "vorsteuerschlüssel", "buchungsschlüssel")),
    "buchungsstapel": ("Buchungsstapel und Schnittstelle", ("buchungsstapel", "extf",
                        "schnittstelle", "datev-format", "stapelbeschreibung")),
    "afa":            ("Anlagen und AfA", ("afa", "absetzung für abnutzung",
                        "nutzungsdauer", "anlagevermögen", "abschreibung", "gwg")),
    "umsatzsteuer":   ("Umsatzsteuer", ("umsatzsteuer", "vorsteuer", "ustva",
                        "reverse charge", "innergemeinschaftlich")),
    "lohn":           ("Lohn", ("lohnsteuer", "lohnabrechnung", "sozialversicherung",
                        "minijob", "lohnkonto")),
    "jahresabschluss": ("Jahresabschluss und EÜR", ("jahresabschluss", "eür", "euer",
                        "bilanz", "gewinnermittlung", "susa", "bwa")),
    "sonstiges":      ("Sonstiges", ()),
}


def thema_erkennen(text: str) -> str:
    """Welches Thema am besten zum Text passt — gewichtete Substring-Suche
    wie `einsortieren`, hier ohne Gewichte: ein Treffer zählt einen Punkt.

    Nur der Anfang zählt (die ersten 4000 Zeichen) — Titel, Inhaltsverzeichnis
    und die ersten Absätze sagen mehr als ein 300-seitiges Handbuch in
    Gänze. Bei Gleichstand (auch 0:0) gewinnt „sonstiges" — raten wäre
    schlimmer als ehrlich zuzugeben, dass nichts eindeutig passt."""
    ausschnitt = (text or "")[:4000].lower()
    bestes_thema = "sonstiges"
    hoechste_punktzahl = 0
    for schluessel, (_, stichworte) in THEMEN.items():
        if schluessel == "sonstiges":
            continue
        punkte = sum(1 for wort in stichworte if wort in ausschnitt)
        if punkte > hoechste_punktzahl:
            hoechste_punktzahl = punkte
            bestes_thema = schluessel
    return bestes_thema


# ── Seiten lesen ─────────────────────────────────────────────────────────
#
# Anders als `babu_web.klartext_der_unterlage` (eine Gesamtzeichenkette)
# braucht die Wissensschicht den Seitenbezug für Zitate — ein Chunk muss
# wissen, von welcher Seite er kommt.
WISSEN_SEITEN_MAX = 120     # Deckel für sehr lange DATEV-Handbücher
WISSEN_OCR_MAX = 20         # höchstens so viele Seiten je Dokument per OCR
TEXTEBENE_SCHWELLE = 120    # wie babu_web.TEXTEBENE_SCHWELLE — ab hier gilt
                            # eine Seite als textlich tragfähig


def seiten_lesen(pfad: str | Path,
                 ocr: Callable[[bytes, str], str] | None = None) -> list[str]:
    """Der Text jeder Seite einer hochgeladenen Unterlage.

    `.pdf`: erst die Textebene (schnell, kostenlos); Seiten, die darunter
    bleiben (Scan, Foto), werden — wenn `ocr` übergeben wurde — einzeln
    gerendert und abgeschrieben, höchstens `WISSEN_OCR_MAX` Stück. Ohne
    `ocr`-Parameter bleibt eine dünne Seite dünn: das hält diese Funktion
    ohne Server und ohne Sprachmodell testbar.
    `.md`/`.txt`: die ganze Datei als eine „Seite" — deckt den Bulk-Import
    von Markdown-Hilfeseiten ab, ohne PDF-Rendering.
    `.jpg`/`.jpeg`/`.png`: eine Seite, direkt über `ocr` (ohne `ocr`: leer).
    """
    pfad = Path(pfad)
    endung = pfad.suffix.lower()

    if endung in (".md", ".txt"):
        try:
            return [pfad.read_text(encoding="utf-8", errors="replace")]
        except OSError:
            return [""]

    if endung in (".jpg", ".jpeg", ".png"):
        if ocr is None:
            return [""]
        try:
            daten = pfad.read_bytes()
        except OSError:
            return [""]
        try:
            return [ocr(daten, pfad.name) or ""]
        except Exception:  # noqa: BLE001 — ein Blatt bleibt leer, der Rest läuft weiter
            return [""]

    if endung != ".pdf":
        return []

    import abschluss_lesen  # noqa: PLC0415 — leichtgewichtig, keine Zirkel

    try:
        seiten = list(abschluss_lesen.seiten_text(pfad))[:WISSEN_SEITEN_MAX]
    except Exception:  # noqa: BLE001
        seiten = []
    if ocr is None:
        return seiten

    bilder: list[bytes] | None = None
    per_ocr_gelesen = 0
    ausgabe: list[str] = []
    for i, text in enumerate(seiten):
        if len(text.strip()) < TEXTEBENE_SCHWELLE and per_ocr_gelesen < WISSEN_OCR_MAX:
            if bilder is None:
                try:
                    bilder = list(abschluss_lesen.seiten_bilder(pfad))
                except Exception:  # noqa: BLE001
                    bilder = []
            if i < len(bilder):
                try:
                    gelesen = ocr(bilder[i], f"{i + 1}-{pfad.name}")
                    per_ocr_gelesen += 1
                    if gelesen and len(gelesen.strip()) > len(text.strip()):
                        text = gelesen
                except Exception:  # noqa: BLE001
                    pass
        ausgabe.append(text)
    return ausgabe


# ── Chunking ─────────────────────────────────────────────────────────────
WISSEN_CHUNK_ZEICHEN = 3200   # ~800 Token bei ~4 Zeichen/Token
WISSEN_CHUNK_MIN = 200        # kürzere Rest-Absätze nicht als eigenes Atom
WISSEN_ATOME_MAX = 400        # Deckel je Dokument


def atome_bauen(seiten: list[str]) -> list[dict]:
    """Seiten in zitierfähige Atome zerlegen — reine Funktion, keine I/O.

    Je Seite: an Leerzeilen in Absätze splitten, Absätze greedy zu Blöcken
    von bis zu `WISSEN_CHUNK_ZEICHEN` zusammenfassen. Ein zu kurzer
    Rest-Block (unter `WISSEN_CHUNK_MIN`) wird an den vorherigen Block
    derselben Seite angehängt statt ein eigenes, mageres Atom zu werden.

    `loc` folgt derselben Konvention wie das Kompendium-Test-Fixture:
    `"S{Seite}#{Index}"`, Seite 1-basiert, Index 0-basiert je Seite.
    Bricht bei `WISSEN_ATOME_MAX` ab — der Rest des Dokuments bleibt
    unindiziert, die Datei selbst bleibt trotzdem vollständig einsehbar."""
    atome: list[dict] = []
    for seitennr, seite in enumerate(seiten, start=1):
        absaetze = [a.strip() for a in re.split(r"\n\s*\n", seite or "") if a.strip()]
        bloecke: list[str] = []
        aktuell = ""
        for absatz in absaetze:
            kandidat = f"{aktuell}\n\n{absatz}" if aktuell else absatz
            if aktuell and len(kandidat) > WISSEN_CHUNK_ZEICHEN:
                bloecke.append(aktuell)
                aktuell = absatz
            else:
                aktuell = kandidat
        if aktuell:
            bloecke.append(aktuell)

        zusammengefasst: list[str] = []
        for block in bloecke:
            if zusammengefasst and len(block) < WISSEN_CHUNK_MIN:
                zusammengefasst[-1] = f"{zusammengefasst[-1]}\n\n{block}"
            else:
                zusammengefasst.append(block)

        for index, block in enumerate(zusammengefasst):
            if len(atome) >= WISSEN_ATOME_MAX:
                print(f"[datev_wissen] Deckel {WISSEN_ATOME_MAX} Atome erreicht — "
                     "Rest des Dokuments bleibt unindiziert, aber einsehbar.",
                     flush=True)
                return atome
            atome.append({"loc": f"S{seitennr}#{index}", "text": block})
    return atome
