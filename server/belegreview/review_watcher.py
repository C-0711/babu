#!/usr/bin/env python3
"""BelegReview — Stufe 1b: der Rückkanal der Belegbox.

Beobachtet babu.git auf neue `aufnahme:`-Commits (docs/**), schickt jeden
Beleg durch PaddleOCR (GPU), extrahiert deutsche Beleg-Felder (Python-Port
der getesteten FeldParser-Heuristik der iOS-App: Steuertabelle mit
Kombinations-Auflösung, Beleg-Nr.-Kette, Bewirtungssignal) und committet
das Ergebnis als `review/<name>.json` + `.md` zurück — Commit `review: …`,
Autor `belegreview <review@gitchain.local>`, Push über das lokale
/git-Gateway. Der PAT kommt wie beim Eingang pro Push frisch aus
`~/gitchain-eingang/.pat_babu` (gleiche Vertrauensdomäne, Rotation ohne
Neustart).

Ground-Regel wie überall: nichts raten — was nicht sauber lesbar ist,
bleibt leer bzw. landet in `offen`.
"""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests

WURZEL = Path(__file__).resolve().parent
ARBEIT = WURZEL / "babu"
TMP = WURZEL / "tmp"
PATDATEI = Path.home() / "gitchain-eingang" / ".pat_babu"

GATEWAY = os.environ.get("BABU_GATEWAY", "http://127.0.0.1:7808").rstrip("/")
REF = os.environ.get("BABU_REF", "inspektor/ws-christoph0711.io/babu")
REMOTE = f"{GATEWAY}/git/{REF}.git"
TAKT = int(os.environ.get("REVIEW_TAKT", "15"))
AUTOR = "belegreview <review@gitchain.local>"
BILD_ENDUNGEN = {".jpg", ".jpeg", ".png"}
PDF_ENDUNGEN = {".pdf"}
HEIC_ENDUNGEN = {".heic"}
XML_ENDUNGEN = {".xml"}                      # E-Rechnung: Stub, XML-Lane folgt
BELEG_ENDUNGEN = BILD_ENDUNGEN | PDF_ENDUNGEN | HEIC_ENDUNGEN | XML_ENDUNGEN

sys.path.insert(0, str(WURZEL))
from doc_classify import classify_doc  # noqa: E402  (Kopie aus ~/OCR, standalone)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Git über das Gateway (Muster des Eingangs) ───────────────────────────────

def pat() -> str | None:
    try:
        t = PATDATEI.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return t if t.startswith("gcpat-") else None


def git_env() -> dict:
    env = dict(os.environ)
    t = pat()
    if t:
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = "Authorization: Bearer " + t
    return env


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ARBEIT), *args],
                          capture_output=True, text=True, env=git_env(), timeout=120)


def arbeitskopie_bereit() -> bool:
    if (ARBEIT / ".git").exists():
        f = git("fetch", "origin")
        if f.returncode != 0:
            log("fetch fehlgeschlagen: " + f.stderr.strip()[-200:])
            return False
        git("reset", "--hard", "origin/main")
        return True
    r = subprocess.run(["git", "clone", REMOTE, str(ARBEIT)],
                       capture_output=True, text=True, env=git_env(), timeout=120)
    if r.returncode != 0:
        log("clone fehlgeschlagen: " + r.stderr.strip()[-200:])
        return False
    return True


# ── PaddleOCR (einmal initialisiert, GPU) ────────────────────────────────────

_OCR = None


def ocr_engine():
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR
        # Deutsch gibt es in dieser Installation als PP-OCRv5-Modell.
        # CPU: beide H200 sind dauerhaft von vLLM belegt; Bons brauchen Sekunden.
        # Rotations-Korrektur: die 2024er-Bündel enthalten kopfüber gescannte
        # Thermobons — Dokument- und Zeilen-Orientierung mitlaufen lassen.
        try:
            _OCR = PaddleOCR(lang="german", ocr_version="PP-OCRv5", device="cpu",
                             use_doc_orientation_classify=True,
                             use_textline_orientation=True)
            log("PaddleOCR bereit (german, PP-OCRv5, CPU, Orientierung an)")
        except TypeError:   # ältere Signatur ohne Orientierungs-Parameter
            _OCR = PaddleOCR(lang="german", ocr_version="PP-OCRv5", device="cpu")
            log("PaddleOCR bereit (german, PP-OCRv5, CPU)")
    return _OCR


# ── Konvertierung: PDF/HEIC → Bild (Stufe 4) ────────────────────────────────

def pdf_zu_bild(quelle: Path, ziel: Path) -> int:
    """Seite 1 als PNG (~200 dpi); gibt die Seitenzahl zurück. pypdfium2 ist
    pip-only — kein Poppler-Systempaket nötig."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(quelle))
    try:
        seiten = len(doc)
        doc[0].render(scale=200 / 72).to_pil().save(ziel, "PNG")
    finally:
        doc.close()
    return seiten


def heic_zu_bild(quelle: Path, ziel: Path) -> None:
    from PIL import Image
    from pillow_heif import register_heif_opener
    register_heif_opener()
    Image.open(quelle).convert("RGB").save(ziel, "JPEG", quality=92)


# ── OCR-Dienst: PP-OCRv6 auf der GPU ────────────────────────────────────────
#
# Die eingebaute Lane lädt PP-OCRv5 in den eigenen Prozess und rechnet auf
# der CPU — gemessen 2,75 s je Beleg. Derselbe Zettel durch den Dienst:
# 0,03 s. Das ist nicht Feinschliff, das ist der Unterschied zwischen „das
# Foto ist gleich fertig" und „warte mal".
#
# `doc_ori` erkennt und korrigiert die Seitendrehung und kostet laut /caps
# nichts — bei Handyfotos ist das der häufigste Grund für unlesbare Belege.
#
# `unwarp` wird NICHT benutzt: der Dienst meldet es selbst als gemessen
# schädlich (91,3 % / 71,6 % / 48,7 % Zeichengleichheit). Wer es einschaltet,
# macht die Erkennung schlechter, nicht besser.
#
# Die eingebaute Lane bleibt als Rückfall. Ein Beleg, der nicht gelesen
# wird, weil ein Dienst gerade weg ist, wäre der schlechtere Tausch.

OCR_DIENST = os.environ.get("OCR_DIENST", "http://10.42.0.101:7833")
OCR_DIENST_FRIST = float(os.environ.get("OCR_DIENST_FRIST", "60"))
_OCR_QUELLE = "—"


def ocr_dienst_zeilen(bildpfad: Path) -> list[tuple[float, str, float]]:
    """(y, Text, Konfidenz) vom Dienst — oder ein Fehler, den der Aufrufer fängt."""
    grenze = "----babu-ocr"
    kopf = (f"--{grenze}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{bildpfad.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    koerper = kopf + bildpfad.read_bytes() + f"\r\n--{grenze}--\r\n".encode()
    r = requests.post(f"{OCR_DIENST}/ocr?doc_ori=1", data=koerper,
                      headers={"Content-Type":
                               f"multipart/form-data; boundary={grenze}"},
                      timeout=OCR_DIENST_FRIST)
    r.raise_for_status()
    antwort = r.json()
    if antwort.get("errorCode"):
        raise RuntimeError(f"OCR-Dienst: {antwort.get('errorMsg')}")
    ergebnisse = (antwort.get("result") or {}).get("ocrResults") or []
    if not ergebnisse:
        raise RuntimeError("OCR-Dienst lieferte keine Seite")

    # Nur die erste Seite: mehrseitige Bündel behandelt der Watcher schon
    # weiter oben als eigenen Fall.
    d = ergebnisse[0].get("prunedResult") or {}
    texte = d.get("rec_texts") or []
    scores = d.get("rec_scores") or []
    polys = d.get("rec_polys") or d.get("dt_polys") or []
    zeilen = []
    for i, text in enumerate(texte):
        conf = float(scores[i]) if i < len(scores) else 0.0
        try:
            y = float(min(punkt[1] for punkt in polys[i]))
        except Exception:  # noqa: BLE001
            y = float(i)
        zeilen.append((y, str(text), conf))
    return zeilen


def ocr_zeilen(bildpfad: Path) -> list[tuple[str, float]]:
    """Erkannte Zeilen (Text, Konfidenz), von oben nach unten."""
    global _OCR_QUELLE
    if OCR_DIENST:
        try:
            zeilen = ocr_dienst_zeilen(bildpfad)
            _OCR_QUELLE = "PP-OCRv6 (GPU-Dienst)"
            zeilen.sort(key=lambda z: z[0])
            return [(t, c) for _, t, c in zeilen]
        except Exception as ex:  # noqa: BLE001
            log(f"OCR-Dienst nicht verfügbar ({ex!r}) — die eingebaute Lane springt ein")

    _OCR_QUELLE = "PP-OCRv5 (CPU, eingebaut)"
    eng = ocr_engine()
    zeilen: list[tuple[float, str, float]] = []   # (y, text, conf)
    if hasattr(eng, "predict"):                    # PaddleOCR 3.x
        for res in eng.predict(str(bildpfad)):
            d = res if isinstance(res, dict) else getattr(res, "json", {}).get("res", {})
            texte = d.get("rec_texts") or []
            scores = d.get("rec_scores") or []
            polys = d.get("rec_polys")
            if polys is None:
                polys = d.get("dt_polys") or []
            for i, text in enumerate(texte):
                conf = float(scores[i]) if i < len(scores) else 0.0
                try:
                    y = float(min(p[1] for p in polys[i]))
                except Exception:  # noqa: BLE001
                    y = float(i)
                zeilen.append((y, str(text), conf))
    else:                                          # PaddleOCR 2.x
        for seite in (eng.ocr(str(bildpfad), cls=True) or []):
            for box, (text, conf) in (seite or []):
                y = float(min(p[1] for p in box))
                zeilen.append((y, str(text), float(conf)))
    zeilen.sort(key=lambda z: z[0])
    return [(t, c) for _, t, c in zeilen]


# ── Semantik: embeddinggemma-300m via vLLM (:11436, OpenAI-kompatibel) ──────
# Klassifikation läuft SEMANTISCH gegen den babu-Katalog (Belegbox-Grundregel);
# der Keyword-Klassifikator ist nur noch Dokumentklassen-Zusatzinfo.
# EmbeddingGemma erwartet Task-Präfixe: Katalog als Dokument, Beleg als Query.

EMBED_API = os.environ.get("EMBED_API", "http://127.0.0.1:11436/v1/embeddings")
EMBED_MODELL = os.environ.get("EMBED_MODELL", "embeddinggemma")
KATALOG_CACHE = WURZEL / "katalog_embeddinggemma.json"

# ── VLM-Lane: Gemma 4 (gemma4-mm via vLLM :11435) liest das BILD ─────────────
VLM_API = os.environ.get("VLM_API", "http://127.0.0.1:11435/v1/chat/completions")
VLM_MODELL = os.environ.get("VLM_MODELL", "gemma4-mm")

# code, SKR04-Konto, Label, Beschreibungstext fürs Embedding
BABU_KATALOG = [
    ("bewirtung", "6640", "Bewirtung",
     "Restaurant Gaststätte Gasthaus Café Bewirtung Speisen Getränke Menü Schnitzel Salat Wein Bier Trinkgeld Tisch Kellner Geschäftsessen"),
    ("kfz", "6530", "Kfz/Tanken",
     "Tankstelle Kraftstoff Diesel Benzin Super E10 Aral Shell Esso Jet Liter Zapfsäule Waschanlage Parkschein Parkhaus"),
    ("buerobedarf", "6815", "Bürobedarf",
     "Bürobedarf Kopierpapier Papier Toner Druckerpatrone Stifte Ordner Büromaterial Schreibwaren"),
    ("telekom", "6805", "Telefon/Internet",
     "Telefon Mobilfunk Internet DSL Glasfaser Telekom Vodafone O2 Tarif Kommunikation Rufnummer"),
    ("energie", "6325", "Energie",
     "Strom Gas Wasser Stadtwerke Energieversorger Abschlag Zählerstand Grundversorgung Netzentgelt"),
    ("fahrt", "6673", "Fahrtkosten",
     "Deutsche Bahn Fernverkehr ICE Ticket Fahrkarte Bahnfahrt ÖPNV Taxi Flug Bordkarte Reise"),
    ("literatur", "6820", "Fachliteratur",
     "Buchhandlung Verlag Fachbuch Fachzeitschrift Literatur Abonnement ISBN"),
    ("geschenk", "6610", "Geschenke",
     "Blumen Blumenstrauß Geschenk Präsent Aufmerksamkeit Gutschein Anlass"),
    ("it", "6837", "IT/Hosting",
     "Hosting Cloud Domain Software Lizenz SaaS IT-Dienstleistung Rechenzentrum "
     "Hetzner AWS Terminbuchung Online-Kalender Planity Buchungssystem Salonsoftware Monatsabo"),
    ("sonstiges", "6850", "Sonstiger Betriebsbedarf",
     "Quittung Kassenbon Einkauf Baumarkt Drogerie allgemeiner Betriebsbedarf"),
    # ── Salon-Katalog (SupremeBeauty): Konten vor Produktivgang vom
    #    Steuerberater bestätigen lassen — Texte sind die Embedding-Anker. ──
    ("wareneingang", "5400", "Wareneinkauf",
     "Friseurbedarf Haarfarbe Coloration Tönung Blondierung Shampoo Conditioner "
     "Haarpflege Styling Wella L'Oréal Schwarzkopf Henkel Kosmetik Nagellack Gel "
     "Wimpern Extensions Haarverlängerung Echthaar Slavic Hair delila Verkaufsware "
     "Großhandel Salonbedarf"),
    ("fremdleistung", "5900", "Fremdleistungen",
     "Stuhlmiete Untermiete Kosmetikerin selbständig Fremdleistung Subunternehmer "
     "freie Mitarbeiterin Nageldesignerin auf Rechnung Provision"),
    ("miete", "6310", "Miete Geschäftsräume",
     "Miete Salonräume Gewerbemiete Nebenkosten Pacht Vermieter monatliche Miete "
     "Ladenlokal Geschäftsräume"),
    ("reinigung", "6330", "Reinigung",
     "Reinigungsfirma Gebäudereinigung Handtuchservice Wäscheservice Mietwäsche "
     "Handtücher Umhänge Fensterputzer Reinigungsmittel"),
    ("versicherung", "6400", "Versicherungen",
     "Betriebshaftpflicht Inhaltsversicherung Geschäftsversicherung Police Beitrag "
     "Versicherungsschein Prämie Jahresbeitrag"),
    ("werbung", "6600", "Werbung",
     "Anzeige Social Media Ads Instagram Facebook Flyer Druck Visitenkarten "
     "Gutscheinkarten Werbung Marketing Kampagne"),
]


def embed_text(text: str, als_dokument: bool = False) -> list[float]:
    prompt = (f"title: none | text: {text[:6000]}" if als_dokument
              else f"task: search result | query: {text[:6000]}")
    r = requests.post(EMBED_API, json={"model": EMBED_MODELL, "input": prompt}, timeout=90)
    r.raise_for_status()
    return r.json()["data"][0]["embedding"]


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


_KATALOG_VEK: list[list[float]] | None = None


def katalog_vektoren() -> list[list[float]]:
    """Katalog-Embeddings, auf Platte gecacht (Schlüssel: Hash der Texte)."""
    global _KATALOG_VEK
    if _KATALOG_VEK is not None:
        return _KATALOG_VEK
    schluessel = hashlib.sha256(
        (EMBED_MODELL + json.dumps(BABU_KATALOG, ensure_ascii=False)).encode()).hexdigest()[:16]
    if KATALOG_CACHE.exists():
        try:
            cache = json.loads(KATALOG_CACHE.read_text())
            if cache.get("schluessel") == schluessel:
                _KATALOG_VEK = cache["vektoren"]
                return _KATALOG_VEK
        except Exception:  # noqa: BLE001
            pass
    log(f"embedde babu-Katalog ({EMBED_MODELL}) …")
    _KATALOG_VEK = [embed_text(f"{label}: {text}", als_dokument=True)
                    for _, _, label, text in BABU_KATALOG]
    KATALOG_CACHE.write_text(json.dumps(
        {"schluessel": schluessel, "vektoren": _KATALOG_VEK}))
    return _KATALOG_VEK


def semantik_klassifizieren(text: str) -> tuple[dict, list[float]]:
    """OCR-Text → (Semantik-Befund, Beleg-Vektor)."""
    vektor = embed_text(text)
    scores = sorted(
        ((round(_cos(vektor, kv), 4), i) for i, kv in enumerate(katalog_vektoren())),
        reverse=True)
    kandidaten = [{"code": BABU_KATALOG[i][0], "konto": BABU_KATALOG[i][1],
                   "label": BABU_KATALOG[i][2], "score": s} for s, i in scores[:3]]
    best = kandidaten[0]
    return {
        "modell": EMBED_MODELL,
        "belegart_code": best["code"],
        "belegart": best["label"],
        "konto_skr04": best["konto"],
        "konfidenz": best["score"],
        "kandidaten": kandidaten,
    }, vektor


def aehnlichster_beleg(vektor: list[float], eigener_stamm: str) -> dict | None:
    """Cosine gegen alle bisherigen Beleg-Embeddings in der Belegbox."""
    bester: dict | None = None
    for pfad in (ARBEIT / "review").glob("*.embedding.json"):
        stamm = pfad.name.removesuffix(".embedding.json")
        if stamm == eigener_stamm:
            continue
        try:
            daten = json.loads(pfad.read_text())
            andere = daten["vektor"]
            # Nur Vektoren desselben Modells vergleichen (Dim/Raum müssen passen).
            if daten.get("modell") != EMBED_MODELL or len(andere) != len(vektor):
                continue
        except Exception:  # noqa: BLE001
            continue
        s = round(_cos(vektor, andere), 4)
        if bester is None or s > bester["score"]:
            bester = {"datei": stamm, "score": s}
    return bester if bester and bester["score"] >= 0.6 else None


def vlm_lesen(bildpfad: Path) -> dict | None:
    """Gemma 4 liest das Beleg-BILD (Lane B): strukturiertes JSON, nichts raten."""
    import base64
    b64 = base64.b64encode(bildpfad.read_bytes()).decode()
    mime = "image/png" if bildpfad.suffix.lower() == ".png" else "image/jpeg"
    anweisung = (
        "Du liest einen deutschen Geschäftsbeleg (Foto). Antworte NUR mit einem "
        "JSON-Objekt ohne Markdown und ohne Erklärung, exakt diese Schlüssel "
        "(unlesbar/unbekannt = null): "
        '{"lieferant": string|null, "beleg_nr": string|null, "datum": "TT.MM.JJJJ"|null, '
        '"brutto": number|null, "netto": number|null, "ust": number|null, '
        '"trinkgeld": number|null, "zahlungsart": string|null, "bewirtung": boolean, '
        '"positionen_anzahl": number|null, "buchungstext": string|null}. '
        "Beträge als Dezimalzahl mit Punkt. brutto ist der Rechnungsbetrag OHNE Trinkgeld. "
        "buchungstext: eine sprechende Kurzbeschreibung für die Buchhaltung, max. 60 Zeichen, "
        "aus der ein Mensch später sofort erkennt, was das war — Art, Ort/Lieferant, "
        'z. B. "Bewirtung Restaurant Weingärtle Stuttgart". Rate nichts.'
    )
    payload = {
        "model": VLM_MODELL,
        "temperature": 0,
        "max_tokens": 500,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": anweisung},
        ]}],
    }
    r = requests.post(VLM_API, json=payload, timeout=180)
    r.raise_for_status()
    inhalt = r.json()["choices"][0]["message"]["content"].strip()
    inhalt = re.sub(r"^```(?:json)?\s*|\s*```$", "", inhalt)
    m = re.search(r"\{.*\}", inhalt, re.S)
    return json.loads(m.group(0)) if m else None


# ── Feld-Extraktion (Port der iOS-FeldParser-Heuristik, getestet am Gerät) ───

BETRAG_RE = re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b")
SATZ_RE = re.compile(r"\b(\d{1,2})(?:[.,]0{1,2})?\s*%")
GUELTIGE_SAETZE = {0, 5, 7, 16, 19}


def betrag(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def steuer_tabelle(text: str) -> list[dict]:
    """Token-Strom aus Raten und Beträgen; je Rate alle 3er-Kombinationen aus
    bis zu 3 Beträgen vor UND nach dem Satz-Token (begrenzt durch Nachbar-
    Raten) gegen Summenprobe + Satz-Plausibilität — nur eindeutige Treffer."""
    tokens: list[tuple[str, float]] = []
    muster = re.compile(SATZ_RE.pattern + "|" + BETRAG_RE.pattern)
    for m in muster.finditer(text):
        if m.group(1) is not None:
            satz = int(m.group(1))
            if satz in GUELTIGE_SAETZE:
                tokens.append(("satz", float(satz)))
        else:
            tokens.append(("betrag", betrag(m.group(0))))

    def pruefe_tripel(werte: list[float], satz: int) -> dict | None:
        b, n, u = sorted(werte, reverse=True)
        if abs(n + u - b) >= 0.011:
            return None
        erwartet = n * satz / 100
        if abs(u - erwartet) > max(0.03, erwartet * 0.02):
            return None
        return {"satz": satz, "netto": n, "ust": u, "brutto": b}

    zeilen: list[dict] = []
    for i, (art, wert) in enumerate(tokens):
        if art != "satz":
            continue
        satz = int(wert)

        def seite(richtung: int) -> list[float]:
            werte, j = [], i + richtung
            while 0 <= j < len(tokens) and len(werte) < 3:
                a, w = tokens[j]
                if a == "satz":
                    break
                werte.append(w)
                j += richtung
            return werte

        pool = seite(-1) + seite(1)
        treffer: list[dict] = []
        for a in range(len(pool)):
            for b_ in range(a + 1, len(pool)):
                for c in range(b_ + 1, len(pool)):
                    z = pruefe_tripel([pool[a], pool[b_], pool[c]], satz)
                    if z and not any(_gleich(z, t) for t in treffer):
                        treffer.append(z)
        if len(treffer) == 1:
            z = treffer[0]
            if not any(t["satz"] == z["satz"] and _gleich(t, z) for t in zeilen):
                zeilen.append(z)
    return zeilen


def _gleich(a: dict, b: dict) -> bool:
    return all(abs(a[k] - b[k]) < 0.011 for k in ("brutto", "netto", "ust"))


def felder_extrahieren(zeilen: list[tuple[str, float]]) -> dict:
    alle = [t for t, _ in zeilen]
    gesamt = "\n".join(alle)
    klein = gesamt.lower()
    f: dict = {"lieferant": None, "beleg_nr": None, "datum": None,
               "netto": None, "ust": None, "brutto": None, "ust_satz": 19,
               "summenprobe_ok": False, "bewirtungssignal": False, "offen": []}

    for z in alle[:5]:
        t = z.strip()
        if len(t) > 3 and re.search(r"[A-Za-zÄÖÜäöüß]", t) \
                and not re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}", t) \
                and not re.match(r"^\s*(rechnung|quittung|bon|beleg|kassenbon)\b", t, re.I):
            f["lieferant"] = t
            break

    m = re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b", gesamt)
    if m:
        f["datum"] = m.group(1)

    # Beleg-Nr.: Label → nacktes "-Nr.:" → RE-Token (Ziffer erzwungen)
    for muster, gruppe in [
        (r"\b(?:re(?:chn(?:ung)?)?s?|beleg|bon|quittungs?)[-.\s]*(?:nr|nummer)\.?\s*[:.]?\s*([\w/-]*\d[\w/-]*)", 1),
        (r"\bnr\.?\s*:\s*([\w/-]*\d[\w/-]*)", 1),
        (r"\bRE(?=[-\s]?[\w/]*\d)[-\s]?[\w/-]{3,}", 0),
        (r"\b(?:bon|beleg)\s*(\d{3,})", 1),
    ]:
        m = re.search(muster, gesamt, re.I)
        if m:
            f["beleg_nr"] = m.group(gruppe).strip()
            break

    if re.search(r"7\s*%", gesamt) and not re.search(r"19\s*%", gesamt):
        f["ust_satz"] = 7

    worte = ["trinkgeld", "inkgeld", "bewirtung", "restaurant", "gasthaus",
             "gaststätte", "gastronovi", "speisekarte"]
    f["bewirtungssignal"] = any(w in klein for w in worte) or bool(re.search(r"\btisch\b", klein))

    betraege = [betrag(x) for x in BETRAG_RE.findall(gesamt)]
    tabelle = steuer_tabelle(gesamt)
    tab_brutto = sum(z["brutto"] for z in tabelle)
    if tabelle and tab_brutto >= (max(betraege) if betraege else 0) * 0.75:
        f["netto"] = round(sum(z["netto"] for z in tabelle), 2)
        f["ust"] = round(sum(z["ust"] for z in tabelle), 2)
        f["brutto"] = round(tab_brutto, 2)
        f["summenprobe_ok"] = True
        f["ust_satz"] = max(tabelle, key=lambda z: z["netto"])["satz"]
        f["steuertabelle"] = tabelle
        if betraege and max(betraege) - f["brutto"] > 0.011:
            de = lambda x: f"{x:.2f}".replace(".", ",")
            f["offen"].append("Differenz Zahlbetrag " + de(max(betraege)) +
                              " vs. Brutto " + de(f["brutto"]) + " (vermutlich Trinkgeld)")
    elif betraege:
        mx = max(betraege)
        f["brutto"] = mx
        rest = [b for b in betraege if b < mx]
        for n in rest:
            for u in rest:
                if u != n and n > u and abs(n + u - mx) < 0.011:
                    f["netto"], f["ust"], f["summenprobe_ok"] = n, u, True
                    break
            if f["summenprobe_ok"]:
                break
        if f["netto"] is None and f["ust_satz"] > 0:
            s = f["ust_satz"] / 100
            f["netto"] = round(mx / (1 + s), 2)
            f["ust"] = round(mx - f["netto"], 2)
    return f


def _als_betrag(wert) -> float | None:
    """Was das Modell als Zahl meldet, robust in einen Betrag verwandeln."""
    if wert in (None, ""):
        return None
    try:
        if isinstance(wert, str):
            wert = wert.replace("€", "").replace(" ", "")
            if "," in wert:
                wert = wert.replace(".", "").replace(",", ".")
        betrag = round(float(wert), 2)
    except (TypeError, ValueError):
        return None
    return betrag if 0 <= betrag < 1_000_000 else None


def einschaetzung(f: dict, sem: dict | None, dokumentklasse: str) -> dict:
    """Steuerliche Ersteinschätzung: semantische Belegart (bge-m3) bestimmt das
    Konto; deterministische Signale (Bewirtung) übersteuern; der Keyword-
    Klassifikator liefert nur noch die Dokumentklasse als Zusatzinfo."""
    ks = "8" if f["ust_satz"] == 7 else ("0" if f["ust_satz"] == 0 else "9")
    e = {"belegart": dokumentklasse, "konto_skr04": None, "steuerschluessel": ks, "hinweise": []}

    if sem:
        e["belegart"] = f"{sem['belegart']} (semantisch, {sem['konfidenz']:.0%})"
        e["konto_skr04"] = sem["konto_skr04"]

    bewirtung = f["bewirtungssignal"] or (sem and sem["belegart_code"] == "bewirtung")
    if bewirtung:
        e["konto_skr04"] = "6640"
        e["hinweise"] += [
            "Bewirtungsbeleg: 70 % abziehbar (§4 Abs. 5 Nr. 2 EStG), Vorsteuer zu 100 %.",
            "Bewirtungsangaben ergänzen: Anlass, Teilnehmer, Unterschrift.",
        ]
        if any("Trinkgeld" in o for o in f["offen"]):
            e["hinweise"].append("Trinkgeld ist ohne Vorsteuer abziehbar — separat erfassen.")
    elif dokumentklasse == "Spendenbescheinigung":
        e["konto_skr04"] = None
        e["hinweise"].append("Zuwendungsbestätigung → Sonderausgaben (Anlage SA), kein Betriebsausgabenkonto.")
    elif dokumentklasse == "Lohnsteuerbescheinigung":
        e["hinweise"].append("LStB → Anlage N (eCodes via VaSt), kein Buchungsbeleg.")
    elif sem is None:
        e["konto_skr04"] = "6850"
        e["hinweise"].append("Semantik nicht verfügbar — Leistungsart prüfen (Vorschlag: sonstiger Betriebsbedarf).")
    if not f["summenprobe_ok"]:
        e["hinweise"].append("Summenprobe nicht bestanden — Beträge prüfen.")
    return e


# ── Verarbeitung ─────────────────────────────────────────────────────────────

def offene_belege() -> list[str]:
    r = git("ls-tree", "-r", "--name-only", "HEAD")
    if r.returncode != 0:
        return []
    dateien = r.stdout.splitlines()
    reviews = {Path(d).stem for d in dateien if d.startswith("review/") and d.endswith(".json")
               and not d.endswith(".embedding.json") and not d.endswith(".bewirtung.json")}
    return [d for d in dateien
            if d.startswith("docs/") and Path(d).suffix.lower() in BELEG_ENDUNGEN
            and Path(d).stem not in reviews]


def review_committen(name: str, review: dict, md_zeilen: list[str],
                     vektor: list[float] | None = None) -> bool:
    """Review-Dateien schreiben, committen, pushen (gemeinsamer Schlussakt)."""
    ordner = ARBEIT / "review"
    ordner.mkdir(exist_ok=True)
    (ordner / f"{name}.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    (ordner / f"{name}.md").write_text("\n".join(md_zeilen) + "\n", encoding="utf-8")
    zu_committen = [f"review/{name}.json", f"review/{name}.md"]
    if vektor is not None:
        (ordner / f"{name}.embedding.json").write_text(json.dumps(
            {"modell": EMBED_MODELL, "dim": len(vektor), "vektor": vektor}))
        zu_committen.append(f"review/{name}.embedding.json")
    git("add", *zu_committen)
    c = git("commit", "--author", AUTOR, "-m", f"review: {name}")
    if c.returncode != 0:
        log(f"commit fehlgeschlagen für {name}: {c.stderr.strip()[-150:]}")
        return False
    p = git("push", "origin", "main")
    if p.returncode != 0:
        log(f"push fehlgeschlagen ({name}), reset + neuer Versuch nächste Runde: "
            + p.stderr.strip()[-150:])
        git("fetch", "origin")
        git("reset", "--hard", "origin/main")
        return False
    return True


def stub_schreiben(pfad: str, grund: str, dokumentklasse: str = "unlesbar",
                   extra: dict | None = None) -> None:
    """Abschluss-Review ohne Lesung — beendet die Retry-Schleife und gibt der
    App/dem Portal einen Zustand, den sie menschlich erklären können."""
    name = Path(pfad).stem
    review = {
        "datei": pfad,
        "engine": "BelegReview-Stub",
        "gelesen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dauer_s": 0, "zeilen": 0, "ocr_konfidenz": 0,
        "dokumentklasse": dokumentklasse,
        "semantik": None, "vlm": None, "aehnlich": None,
        "felder": {"lieferant": None, "beleg_nr": None, "datum": None,
                   "netto": None, "ust": None, "brutto": None, "ust_satz": 19,
                   "summenprobe_ok": False, "bewirtungssignal": False,
                   "offen": [grund]},
        "einschaetzung": {"belegart": dokumentklasse, "konto_skr04": None,
                          "steuerschluessel": "9", "hinweise": [grund]},
        "ocr_text": "",
    }
    if extra:
        review.update(extra)
    md = [f"# BelegReview · {Path(pfad).name}", "", f"> {review['engine']}", "",
          f"- **Dokumentklasse:** {dokumentklasse}", f"- {grund}"]
    if review_committen(name, review, md):
        log(f"stub: {Path(pfad).name} — {dokumentklasse}")


def verarbeite(pfad: str) -> None:
    name = Path(pfad).stem
    TMP.mkdir(exist_ok=True)
    lokal = TMP / Path(pfad).name
    lokal.write_bytes((ARBEIT / pfad).read_bytes())

    endung = lokal.suffix.lower()
    if endung in XML_ENDUNGEN:
        stub_schreiben(pfad, "Kam als E-Rechnung — die Auswertung dafür folgt.",
                       dokumentklasse="E-Rechnung", extra={"lane": "xml"})
        return
    seiten = 1
    if endung in PDF_ENDUNGEN:
        bild = lokal.with_suffix(".png")
        seiten = pdf_zu_bild(lokal, bild)
        lokal = bild
    elif endung in HEIC_ENDUNGEN:
        bild = lokal.with_suffix(".jpg")
        heic_zu_bild(lokal, bild)
        lokal = bild

    t0 = time.time()
    zeilen = ocr_zeilen(lokal)
    dauer = time.time() - t0
    text = "\n".join(t for t, _ in zeilen)
    dokumentklasse = classify_doc(text, name=Path(pfad).name, pages=seiten)
    f = felder_extrahieren(zeilen)
    if seiten > 1:
        f["offen"].append(f"{seiten} Seiten — gelesen ist Seite 1. "
                          "Ein Bündel bitte als einzelne Belege einreichen.")

    # Semantik-Lane: embeddinggemma → Belegart/Konto + Ähnlichkeits-Historie.
    sem, vektor, aehnlich = None, None, None
    try:
        sem, vektor = semantik_klassifizieren(text)
        aehnlich = aehnlichster_beleg(vektor, name)
    except Exception as ex:  # noqa: BLE001 — Embed-Dienst weg → deterministisch weiter
        log(f"Semantik nicht verfügbar: {ex!r}")

    # VLM-Lane (Gemma 4 liest das Bild): füllt Lücken der deterministischen
    # Lane (Herkunft wird festgehalten) und liefert eine zweite Betrags-Lesung.
    vlm = None
    try:
        vlm = vlm_lesen(lokal)
    except Exception as ex:  # noqa: BLE001
        log(f"VLM nicht verfügbar: {ex!r}")
    # Wer entscheidet — und warum es umgedreht wurde.
    #
    # Bis 22.08.2026 durfte das Bildmodell nur drei Felder füllen, und auch
    # das nur, wenn die Regex nichts gefunden hatte. Den Betrag durfte es
    # überhaupt nicht setzen. Das ging schief, sobald ein Beleg mehr als
    # eine Zahl enthält: auf einer Parkquittung gewann der Steuersatz
    # („19,00 %" statt 3,50 €), auf einer Rechnung das Stammkapital aus der
    # Fußzeile (43.783,86 € statt 40,00 €), und als Lieferant stand das
    # Wort „Rechnungsadresse", weil das die erste Zeile war.
    #
    # Eine Regex sieht Zeichen, kein Dokument. Sie kann nicht wissen, dass
    # eine Prozentangabe kein Betrag ist, dass eine Fußzeile juristisches
    # Beiwerk ist oder dass auf einer Rechnung oben der Empfänger steht und
    # unten der Aussteller. Das Modell sieht genau das.
    #
    # Also führt jetzt das Modell, und die deterministische Lane wird zur
    # Gegenprobe. Wo beide etwas sagen und sich widersprechen, wird nicht
    # still entschieden, sondern gefragt — dasselbe Muster wie überall in
    # babu: vorschlagen, nachrechnen, im Zweifel nachfragen.
    regex_lesung = {k: f.get(k) for k in
                    ("lieferant", "beleg_nr", "datum", "brutto", "netto", "ust")}
    widerspruch: list[str] = []

    if vlm:
        for feld in ("lieferant", "beleg_nr", "datum"):
            wert = vlm.get(feld)
            if wert in (None, ""):
                continue
            wert = str(wert).strip()
            alt_wert = (f.get(feld) or "").strip()
            if alt_wert and alt_wert.lower() != wert.lower():
                widerspruch.append(
                    f"{feld}: gelesen „{wert}“, Textsuche fand „{alt_wert}“")
            f[feld] = wert
            f.setdefault("herkunft_vlm", []).append(feld)

        # Beträge: nur übernehmen, wenn sie in sich stimmig sind. Ein Modell,
        # das Netto und Umsatzsteuer nennt, die nicht zum Brutto passen, hat
        # geraten — dann bleibt die gerechnete Lane stehen.
        vlm_brutto = _als_betrag(vlm.get("brutto"))
        if vlm_brutto is not None and vlm_brutto > 0:
            if f.get("brutto") is not None and abs(vlm_brutto - f["brutto"]) > 0.011:
                widerspruch.append(
                    f"Betrag: gelesen {vlm_brutto:.2f} €, Textsuche fand "
                    f"{f['brutto']:.2f} €")
            f["brutto"] = vlm_brutto
            f.setdefault("herkunft_vlm", []).append("brutto")

            vlm_netto = _als_betrag(vlm.get("netto"))
            vlm_ust = _als_betrag(vlm.get("ust"))
            if (vlm_netto is not None and vlm_ust is not None
                    and abs(vlm_netto + vlm_ust - vlm_brutto) < 0.011):
                f["netto"], f["ust"] = vlm_netto, vlm_ust
                f["summenprobe_ok"] = True
                f.setdefault("herkunft_vlm", []).extend(["netto", "ust"])

                # Den Steuersatz nicht suchen, sondern ausrechnen. Die
                # Heuristik sucht „7 %" und findet „7,00 %" nicht — auf einem
                # Bäckerbon stand deshalb 19 % statt 7 %, und damit wäre die
                # Vorsteuer falsch. Aus stimmigem Netto und Steuer ergibt er
                # sich exakt; übernommen wird nur ein gesetzlicher Satz.
                if vlm_netto > 0:
                    satz = round(vlm_ust / vlm_netto * 100)
                    if satz in (0, 5, 7, 16, 19):
                        f["ust_satz"] = satz
                        f.setdefault("herkunft_vlm", []).append("ust_satz")
            elif f.get("netto") is None or abs(
                    (f.get("netto") or 0) + (f.get("ust") or 0) - vlm_brutto) > 0.011:
                # Die alte Aufteilung passt nicht mehr zum neuen Brutto.
                satz = f.get("ust_satz") or 0
                if satz > 0:
                    netto = round(vlm_brutto / (1 + satz / 100), 2)
                    f["netto"], f["ust"] = netto, round(vlm_brutto - netto, 2)
                else:
                    f["netto"], f["ust"] = vlm_brutto, 0.0
                f["summenprobe_ok"] = False

        if vlm.get("bewirtung") is True:
            f["bewirtungssignal"] = True

    f["regex_lesung"] = regex_lesung
    f["widerspruch"] = widerspruch

    e = einschaetzung(f, sem, dokumentklasse)
    if aehnlich:
        e["hinweise"].append(
            f"Ähnlichster früherer Beleg: {aehnlich['datei']} ({aehnlich['score']:.0%}).")
    # Widersprochen sich die beiden Lesungen, wird das sichtbar — und der
    # Beleg bekommt keinen stillen grünen Haken.
    if widerspruch:
        e["hinweise"].append(
            "Zwei Lesungen weichen ab (" + "; ".join(widerspruch)
            + "). Übernommen ist die Lesung aus dem Bild — bitte kurz ansehen.")
        f.setdefault("offen", []).append("Zwei Lesungen weichen ab — kurz prüfen.")

    review = {
        "datei": pfad,
        "engine": f"PaddleOCR {_OCR_QUELLE}",
        "gelesen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dauer_s": round(dauer, 2),
        "zeilen": len(zeilen),
        "ocr_konfidenz": round(sum(c for _, c in zeilen) / len(zeilen), 3) if zeilen else 0,
        "dokumentklasse": dokumentklasse,
        "semantik": sem,
        "vlm": vlm,
        "aehnlich": aehnlich,
        "felder": f,
        "einschaetzung": e,
        "ocr_text": text[:8000],
    }
    if seiten > 1:
        review["seiten"] = seiten

    md = [f"# BelegReview · {Path(pfad).name}", "",
          f"> {review['engine']} · {review['zeilen']} Zeilen · "
          f"ø Konfidenz {review['ocr_konfidenz']:.0%} · {dauer:.1f} s · "
          f"Semantik {EMBED_MODELL}{' · VLM ' + VLM_MODELL if vlm else ''}", "",
          f"- **Belegart:** {e['belegart']} · Dokumentklasse: {dokumentklasse}",
          f"- **Lieferant:** {f['lieferant'] or '—'}",
          f"- **Beleg-Nr.:** {f['beleg_nr'] or '—'}",
          f"- **Datum:** {f['datum'] or '—'}",
          f"- **Netto / USt / Brutto:** {f['netto']} / {f['ust']} / {f['brutto']} "
          f"(Satz {f['ust_satz']} %, Summenprobe {'✓' if f['summenprobe_ok'] else '✗'})",
          f"- **Konto (SKR04):** {e['konto_skr04'] or '—'} · Steuerschlüssel {e['steuerschluessel']}", ""]
    md += [f"- {h}" for h in e["hinweise"]]
    if f["offen"]:
        md += ["", "Offen:"] + [f"- {o}" for o in f["offen"]]

    if review_committen(name, review, md, vektor):
        log(f"review: {Path(pfad).name} — {e['belegart']}, brutto {f['brutto']}, {dauer:.1f}s OCR")


# Pro Datei zählen, nicht endlos wiederholen: nach 3 Fehlversuchen (~45 s,
# deckt Dienst-Schluckaufe ab) bekommt der Beleg einen unlesbar-Stub und die
# Nutzerin die Bitte um ein neues Foto — statt einer stillen Endlosschleife.
_FEHLVERSUCHE: dict[str, int] = {}


def hauptschleife() -> None:
    log(f"BelegReview-Watcher startet (Takt {TAKT}s, Remote {REMOTE})")
    while True:
        try:
            if arbeitskopie_bereit():
                for pfad in offene_belege():
                    try:
                        verarbeite(pfad)
                        _FEHLVERSUCHE.pop(pfad, None)
                    except Exception as ex:  # noqa: BLE001
                        n = _FEHLVERSUCHE.get(pfad, 0) + 1
                        _FEHLVERSUCHE[pfad] = n
                        log(f"Fehler bei {pfad} (Versuch {n}/3): {ex!r}")
                        if n >= 3:
                            try:
                                stub_schreiben(pfad, "Das Foto war schwer zu lesen — "
                                               "neu fotografieren hilft meistens.")
                                _FEHLVERSUCHE.pop(pfad, None)
                            except Exception as ex2:  # noqa: BLE001
                                log(f"Stub fehlgeschlagen für {pfad}: {ex2!r}")
        except Exception as e:  # noqa: BLE001
            log(f"Fehler: {e!r}")
        time.sleep(TAKT)


if __name__ == "__main__":
    hauptschleife()
