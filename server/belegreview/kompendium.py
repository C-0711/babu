"""Das Branchen-Kompendium: Steuer, Recht und Zahlen der Friseur- und
Beautybranche, als Vektorbestand durchsuchbar.

89.760 Text-Atome aus 182 Quelldateien (AfA-Tabellen, BMF, Kontenpläne,
Branchenstatistik, juris), eingebettet mit EmbeddingGemma-300M — demselben
Modell und denselben Präfixen, mit denen babu seit dem 27.08. jeden Beleg
vektorisiert. Die Vektoren liegen als fp32-Memmap, die Texte als JSONL mit
Zeilen-Offsets: der Prozess hält nur ~270 MB Vektoren und 90k Offsets, die
Texte kommen per seek.

Fehlt das Verzeichnis (lokal, Tests), ist alles hier still: suchen() gibt
[] zurück, grundwissen() einen leeren String — der Chat läuft ohne
Kompendium genauso wie vorher.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

VERZEICHNIS = Path(os.environ.get("KOMPENDIUM_DIR",
                                  str(Path.home() / "kompendium")))

_LOCK = threading.Lock()
_VEKTOREN = None          # numpy-Memmap (n, d), L2-normalisiert
_OFFSETS: list[int] = []  # Byte-Offset je Atom-Zeile in atome.jsonl
_TEXTE: dict[str, str] = {}     # Dateiname → Inhalt, einmal je Prozess


def _laden() -> bool:
    """Memmap + Offset-Index einmal je Prozess; danach kostenlos."""
    global _VEKTOREN, _OFFSETS
    if _VEKTOREN is not None:
        return True
    npy = VERZEICHNIS / "vektoren.npy"
    jsonl = VERZEICHNIS / "atome.jsonl"
    if not (npy.exists() and jsonl.exists()):
        return False
    with _LOCK:
        if _VEKTOREN is not None:
            return True
        import numpy as np  # noqa: PLC0415
        vektoren = np.load(npy, mmap_mode="r")
        offsets = []
        stand = 0
        with open(jsonl, "rb") as f:
            for zeile in f:
                offsets.append(stand)
                stand += len(zeile)
        if len(offsets) != vektoren.shape[0]:
            return False
        _OFFSETS = offsets
        _VEKTOREN = vektoren
    return True


def atom(nr: int) -> dict | None:
    if not _laden() or not 0 <= nr < len(_OFFSETS):
        return None
    with open(VERZEICHNIS / "atome.jsonl", "rb") as f:
        f.seek(_OFFSETS[nr])
        try:
            return json.loads(f.readline())
        except ValueError:
            return None


def suchen(frage_vektor: list[float], k: int = 5) -> list[dict]:
    """Die k passendsten Atome zur (bereits eingebetteten) Frage.

    Brute-Force über alle 89.760 Vektoren — gemessen 20 ms; ein Index
    lohnt erst bei Millionen Atomen."""
    if not frage_vektor or not _laden():
        return []
    import numpy as np  # noqa: PLC0415
    q = np.asarray(frage_vektor, dtype=np.float32)
    norm = float(np.linalg.norm(q))
    if norm == 0:
        return []
    scores = _VEKTOREN @ (q / norm)
    treffer = []
    for nr in np.argsort(-scores)[:k]:
        a = atom(int(nr))
        if a:
            treffer.append({"score": round(float(scores[nr]), 4),
                            "quelle": a.get("quelle"), "loc": a.get("loc"),
                            "text": a.get("text") or ""})
    return treffer


def _datei(name: str, grenze: int) -> str:
    if name not in _TEXTE:
        try:
            _TEXTE[name] = (VERZEICHNIS / name).read_text()[:grenze]
        except OSError:
            _TEXTE[name] = ""
    return _TEXTE[name]


def grundwissen() -> str:
    """Der destillierte Branchen-Block für den stehenden Prompt-Anfang.

    Eine Datei, einmal gelesen, nie neu — Byte-Stabilität ist hier der
    Zweck: derselbe Anfang trifft bei jeder Frage den Prefix-Cache."""
    return _datei("grundwissen.md", 60000)


def kontierungswissen() -> str:
    """Was beim BUCHEN nachgeschlagen werden muss: Nutzungsdauern aus der
    AfA-Tabelle Nr. 94, die GWG-Grenzen und der Salon-Kontenplan.

    Steht im stehenden Teil des Buchungs-Prompts — damit weiß Gemma beim
    Buchen dasselbe wie der Chat, ohne dass es je Beleg neu gerechnet
    wird. Genau daran scheiterten die Anschaffungs-Fälle: ohne die
    Nutzungsdauer ist „Gerät oder GWG?" nicht zu entscheiden."""
    return _datei("kontierung-grundwissen.md", 30000)
