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


# ── Weitere Bestände je Portal (seit 24.09.2026) ─────────────────────────────
#
# Jedes Portal (portale/) nennt seine Wissenscontainer als Verzeichnisnamen,
# das eigene zuletzt — Barber etwa ("kompendium", "kompendium-barber"). Der
# Hauptbestand oben bleibt, wie er ist; alle anderen liegen daneben im selben
# Format (atome.jsonl, vektoren.npy, grundwissen.md, kontierung-grundwissen.md)
# und werden erst beim ersten Zugriff geladen. Ohne `bestaende` verhält sich
# jede Funktion hier genau wie vor dem 24.09.2026.

HAUPTBESTAND = "kompendium"
_WEITERE: dict[str, tuple] = {}      # Name → (Vektoren, Offsets) oder ()
_WEITERE_TEXTE: dict[tuple[str, str], str] = {}


def verzeichnis(name: str) -> Path:
    """Wo ein Bestand liegt: der Hauptbestand wie bisher, jeder weitere als
    Geschwister daneben (Host `~/kompendium-barber`, Container
    `/data/kompendium-barber`)."""
    return VERZEICHNIS if name == HAUPTBESTAND else VERZEICHNIS.parent / name


def _weiteren_laden(name: str) -> tuple:
    """Memmap + Offsets eines weiteren Bestands, einmal je Prozess. Leer,
    wenn er fehlt oder Zeilen und Vektoren nicht zusammenpassen — dann
    schweigt er, wie der Hauptbestand."""
    if name in _WEITERE:
        return _WEITERE[name]
    with _LOCK:
        if name in _WEITERE:
            return _WEITERE[name]
        d = verzeichnis(name)
        stand: tuple = ()
        if (d / "vektoren.npy").exists() and (d / "atome.jsonl").exists():
            import numpy as np  # noqa: PLC0415
            vektoren = np.load(d / "vektoren.npy", mmap_mode="r")
            offsets, pos = [], 0
            with open(d / "atome.jsonl", "rb") as f:
                for zeile in f:
                    offsets.append(pos)
                    pos += len(zeile)
            if len(offsets) == vektoren.shape[0]:
                stand = (vektoren, offsets)
        _WEITERE[name] = stand
        return stand


def _ausgeschlossen(t: dict, ohne: tuple[str, ...]) -> bool:
    return bool(ohne) and (t.get("quelle") or "").startswith(ohne)


def _suchen_in(name: str, q, k: int, ohne: tuple[str, ...] = ()) -> list[dict]:
    if name == HAUPTBESTAND:
        treffer = suchen(list(q), k=k + 50 if ohne else k)
        return [t for t in treffer if not _ausgeschlossen(t, ohne)][:k]
    stand = _weiteren_laden(name)
    if not stand:
        return []
    import numpy as np  # noqa: PLC0415
    vektoren, offsets = stand
    scores = vektoren @ q
    treffer = []
    with open(verzeichnis(name) / "atome.jsonl", "rb") as f:
        for nr in np.argsort(-scores):
            if len(treffer) >= k:
                break
            f.seek(offsets[int(nr)])
            try:
                a = json.loads(f.readline())
            except ValueError:
                continue
            t = {"score": round(float(scores[nr]), 4), "quelle": a.get("quelle"),
                 "loc": a.get("loc"), "text": a.get("text") or ""}
            if not _ausgeschlossen(t, ohne):
                treffer.append(t)
    return treffer


def suchen_in(frage_vektor: list[float], bestaende: tuple[str, ...],
              k: int = 5, ohne: tuple[str, ...] = ()) -> list[dict]:
    """Die k passendsten Atome über mehrere Bestände zusammen. `ohne`:
    Quellen-Präfixe, die übersprungen werden (der Buchungsweg lässt die
    Gesetzestexte aus — sie sind für den Chat da)."""
    if not frage_vektor:
        return []
    import numpy as np  # noqa: PLC0415
    q = np.asarray(frage_vektor, dtype=np.float32)
    norm = float(np.linalg.norm(q))
    if norm == 0:
        return []
    q = q / norm
    alle = [t for name in bestaende for t in _suchen_in(name, q, k, ohne)]
    # Dieselbe Norm kann in zwei Beständen liegen (Branchen-Container und
    # Bundesrecht) — gleicher Text zählt einmal.
    aus, gesehen = [], set()
    for t in sorted(alle, key=lambda t: -t["score"]):
        schluessel = " ".join((t["text"] or "").split())
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            aus.append(t)
    return aus[:k]


def _eigene_datei(bestaende: tuple[str, ...], datei: str, grenze: int) -> str:
    """Grundwissen kommt aus dem EIGENEN Bestand des Portals (dem letzten).
    Fehlt er, ist es leer — ein Portal leiht sich kein fremdes Grundwissen."""
    name = bestaende[-1] if bestaende else HAUPTBESTAND
    if name == HAUPTBESTAND:
        return _datei(datei, grenze)
    if (name, datei) not in _WEITERE_TEXTE:
        try:
            _WEITERE_TEXTE[(name, datei)] = (verzeichnis(name) / datei).read_text()[:grenze]
        except OSError:
            _WEITERE_TEXTE[(name, datei)] = ""
    return _WEITERE_TEXTE[(name, datei)]


def grundwissen_von(bestaende: tuple[str, ...]) -> str:
    """Wie `grundwissen()`, aber aus dem eigenen Bestand eines Portals."""
    return _eigene_datei(bestaende, "grundwissen.md", 60000)


def kontierungswissen_von(bestaende: tuple[str, ...]) -> str:
    """Wie `kontierungswissen()`, aber aus dem eigenen Bestand eines Portals."""
    return _eigene_datei(bestaende, "kontierung-grundwissen.md", 30000)


# ── Wortlaut einer genannten Vorschrift (seit 25.09.2026) ────────────────────
#
# Das ganze Bundesrecht liegt in `kompendium-bundesrecht` (6.137 Gesetze und
# Verordnungen, 105.204 Normen). In die Vektorsuche des Chats gehört es NICHT:
# gemessen am 25.09.2026 verdrängen dort Seearbeitsgesetz, Waffengesetz und
# Tarifverträge für Pädagogen die richtige Vorschrift — auch mit Reranker
# (~/.beleglex/messungen/20260925-bundesrecht/). Nennt die Frage aber eine
# Vorschrift („§ 647 BGB", „§ 7 SGB IV", „AO § 146b"), wird ihr Wortlaut
# direkt nachgeschlagen — so ist jede Norm erreichbar, ohne Rauschen.

import re as _re  # noqa: E402

BUNDESRECHT = "kompendium-bundesrecht"
_KOPF = _re.compile(r"^(.+?)\s+§\s*(\d+[a-z]?)\b")
_ROEMISCH = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
             "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIV": 14}
_ABK = r"([A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{1,20})(?:\s+([IVX]{1,4}|\d{1,2})\b)?"
_FRAGE = [
    _re.compile(r"§\s*(?P<nr>\d+[a-z]?)(?:\s+(?:Abs\.?|Absatz)\s*(?P<abs>\d+[a-z]?))?"
                r"(?:\s+(?:S\.|Satz)\s*\d+)?(?:\s+Nr\.?\s*(?P<num>\d+[a-z]?))?\s+"
                + _ABK.replace("(", "(?P<abk>", 1).replace("(?:\\s+([IVX]", "(?:\\s+(?P<buch>[IVX]", 1)),
    _re.compile(_ABK.replace("(", "(?P<abk>", 1).replace("(?:\\s+([IVX]", "(?:\\s+(?P<buch>[IVX]", 1)
                + r"\s+§\s*(?P<nr>\d+[a-z]?)"),
]
_NORMEN: dict[str, dict] = {}


def _schluessel(abk: str) -> tuple[str, str]:
    """(voll, ohne Zahlen): „AO 1977" → („ao 1977", „ao"), „SGB 4" → („sgb 4", „sgb")."""
    voll = " ".join(abk.lower().split())
    return voll, " ".join(w for w in voll.split() if not w.isdigit())


def _normen_index(name: str) -> dict:
    """(Schlüssel, Nummer) → Zeilen im Bestand; einmal je Prozess."""
    if name in _NORMEN:
        return _NORMEN[name]
    index: dict = {}
    pfad = verzeichnis(name) / "atome.jsonl"
    if pfad.exists():
        with open(pfad, "rb") as f:
            for nr, zeile in enumerate(f):
                try:
                    a = json.loads(zeile)
                except ValueError:
                    continue
                m = _KOPF.match((a.get("text") or "").split("\n", 1)[0])
                if not m:
                    continue
                voll, kurz = _schluessel(m.group(1))
                for k in {voll, kurz}:
                    index.setdefault((k, m.group(2).lower()), []).append((nr, a.get("quelle") or ""))
    _NORMEN[name] = index
    return index


def genannte_normen(frage: str) -> list[tuple[str, str, str | None, str | None]]:
    """Die Vorschriften, die eine Frage nennt: [(Gesetz, Paragraf, Absatz, Nummer)]."""
    aus = []
    for muster in _FRAGE:
        for m in muster.finditer(frage or ""):
            abk, buch = m.group("abk"), m.group("buch")
            if sum(c.isupper() for c in abk) < 2:      # „Gilt § 7“ ist kein Gesetz
                continue
            if buch:
                abk = f"{abk} {_ROEMISCH.get(buch, buch)}"
            gd = m.groupdict()
            eintrag = (abk, m.group("nr"), gd.get("abs"), gd.get("num"))
            if all(e[:2] != eintrag[:2] for e in aus):
                aus.append(eintrag)
    return aus[:3]


def wortlaut(frage: str, bestand: str = BUNDESRECHT, grenze: int = 3000) -> list[dict]:
    """Der amtliche Wortlaut der Vorschriften, die die Frage nennt. Mehrdeutige
    Kürzel (zwei verschiedene Gesetze) werden nicht geraten."""
    normen = genannte_normen(frage)
    if not normen:
        return []
    index = _normen_index(bestand)
    if not index:
        return []
    aus = []
    for abk, nr, absatz, nummer in normen:
        voll, kurz = _schluessel(abk)
        treffer = index.get((voll, nr.lower())) or index.get((kurz, nr.lower())) or []
        quellen = {q for _, q in treffer}
        if len(quellen) != 1:
            continue
        zeilen = sorted(z for z, _ in treffer)
        texte = []
        with open(verzeichnis(bestand) / "atome.jsonl", "rb") as f:
            for z, zeile in enumerate(f):
                if z in zeilen:
                    texte.append(json.loads(zeile))
                if z > zeilen[-1]:
                    break
        kopf = texte[0]["text"].split("\n", 1)[0]
        rumpf = "\n".join(t["text"].split("\n", 1)[1] if "\n" in t["text"] else "" for t in texte)
        # Nennt die Frage Absatz oder Nummer, beginnt der Ausschnitt dort —
        # sonst fiele „§ 3 Nr. 51 EStG“ hinter die Grenze.
        start = 0
        for muster in ([rf"(?m)^\s*{_re.escape(nummer)}\.\s"] if nummer else []) + \
                      ([rf"\({_re.escape(absatz)}\)"] if absatz else []):
            m = _re.search(muster, rumpf)
            if m:
                start = m.start()
                break
        ausschnitt = ("… " if start else "") + rumpf[start:]
        aus.append({"quelle": texte[0]["quelle"], "loc": texte[0]["loc"], "kopf": kopf,
                    "text": (kopf + "\n" + ausschnitt)[:grenze]})
    return aus
