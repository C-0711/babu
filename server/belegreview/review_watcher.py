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
from belegdeutung import Kasten, Lesung, deuten  # noqa: E402
from leseprotokoll import protokoll  # noqa: E402
import kontierung as kt  # noqa: E402


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


def ocr_dienst_kaesten(bildpfad: Path) -> list[Kasten]:
    """Erkannte Textstücke mit Position — oder ein Fehler für den Aufrufer."""
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
    return _kaesten_aus(d.get("rec_texts") or [], d.get("rec_scores") or [],
                        d.get("rec_polys") or d.get("dt_polys") or [])


def _kaesten_aus(texte, scores, polys) -> list[Kasten]:
    """Die drei Listen der Texterkennung zu Kästen zusammensetzen.

    Kommt kein Umriss mit, wird die Zeilennummer als Höhe eingesetzt: die
    Deutung braucht dann zwar keine Spalten mehr erkennen können, aber die
    Reihenfolge stimmt und der Beleg fällt nicht aus.
    """
    kaesten: list[Kasten] = []
    for i, text in enumerate(texte):
        konf = float(scores[i]) if i < len(scores) else 0.0
        try:
            xs = [float(punkt[0]) for punkt in polys[i]]
            ys = [float(punkt[1]) for punkt in polys[i]]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        except Exception:  # noqa: BLE001
            x0, y0, x1, y1 = 0.0, float(i) * 20, float(len(str(text)) * 10), float(i) * 20 + 18
        kaesten.append(Kasten(str(text), konf, x0, y0, x1, y1))
    return kaesten


def ocr_kaesten(bildpfad: Path) -> list[Kasten]:
    """Erkannte Textstücke samt Position, von oben nach unten.

    Die Position ist kein Beiwerk: erst mit ihr lässt sich eine Betrags-
    spalte von einer Zahl im Fließtext unterscheiden und ein groß gesetzter
    Firmenname von der Fußzeile. Ohne sie bliebe nur Raten.
    """
    global _OCR_QUELLE
    if OCR_DIENST:
        try:
            kaesten = ocr_dienst_kaesten(bildpfad)
            _OCR_QUELLE = "PP-OCRv6 (GPU-Dienst)"
            return sorted(kaesten, key=lambda k: (k.y0, k.x0))
        except Exception as ex:  # noqa: BLE001
            log(f"OCR-Dienst nicht verfügbar ({ex!r}) — die eingebaute Lane springt ein")

    _OCR_QUELLE = "PP-OCRv5 (CPU, eingebaut)"
    eng = ocr_engine()
    kaesten: list[Kasten] = []
    if hasattr(eng, "predict"):                    # PaddleOCR 3.x
        for res in eng.predict(str(bildpfad)):
            d = res if isinstance(res, dict) else getattr(res, "json", {}).get("res", {})
            kaesten += _kaesten_aus(d.get("rec_texts") or [],
                                    d.get("rec_scores") or [],
                                    d.get("rec_polys") or d.get("dt_polys") or [])
    else:                                          # PaddleOCR 2.x
        for seite in (eng.ocr(str(bildpfad), cls=True) or []):
            for box, (text, conf) in (seite or []):
                xs = [float(punkt[0]) for punkt in box]
                ys = [float(punkt[1]) for punkt in box]
                kaesten.append(Kasten(str(text), float(conf),
                                      min(xs), min(ys), max(xs), max(ys)))
    return sorted(kaesten, key=lambda k: (k.y0, k.x0))


def ocr_zeilen(bildpfad: Path) -> list[tuple[str, float]]:
    """Nur Text und Konfidenz — für alles, was die Position nicht braucht."""
    return [(k.text, k.konf) for k in ocr_kaesten(bildpfad)]


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

# ── Katalog: code, BUCHUNGSKATEGORIE, Label, Embedding-Text ──────────────────
#
# Bis 23.08.2026 stand hier in der zweiten Spalte ein festes SKR04-Konto. Das
# war der Fehler, den Nina benannt hat: der Belegtext entschied unmittelbar
# über das Sachkonto. Jetzt steht dort eine Kategorie aus kontierung.py, und
# das Konto ergibt sich erst daraus — im Kontenrahmen des Betriebs.
#
# Wo das Embedding die Verwendung gar nicht wissen KANN, steht die Kategorie
# in MEHRDEUTIG statt hier. Dann wird gefragt, nicht geraten.
BABU_KATALOG = [
    ("bewirtung", "bewirtung", "Bewirtung",
     "Restaurant Gaststätte Gasthaus Café Bewirtung Speisen Getränke Menü Schnitzel Salat Wein Bier Trinkgeld Tisch Kellner Geschäftsessen"),
    ("kfz", "kfz", "Kfz/Tanken",
     "Tankstelle Kraftstoff Diesel Benzin Super E10 Aral Shell Esso Jet Liter Zapfsäule Waschanlage Parkschein Parkhaus"),
    ("buerobedarf", "buerobedarf", "Bürobedarf",
     "Bürobedarf Kopierpapier Papier Toner Druckerpatrone Stifte Ordner Büromaterial Schreibwaren"),
    ("telekom", "telekom", "Telefon/Internet",
     "Telefon Mobilfunk Internet DSL Glasfaser Telekom Vodafone O2 Tarif Kommunikation Rufnummer"),
    ("energie", "energie", "Energie",
     "Strom Gas Wasser Stadtwerke Energieversorger Abschlag Zählerstand Grundversorgung Netzentgelt"),
    ("fahrt", "fahrt", "Fahrtkosten",
     "Deutsche Bahn Fernverkehr ICE Ticket Fahrkarte Bahnfahrt ÖPNV Taxi Flug Bordkarte Reise"),
    ("literatur", "literatur", "Fachliteratur",
     "Buchhandlung Verlag Fachbuch Fachzeitschrift Literatur Abonnement ISBN"),
    ("geschenk", "geschenk", "Geschenke",
     "Blumen Blumenstrauß Geschenk Präsent Aufmerksamkeit Gutschein Anlass"),
    ("it", "it", "IT/Hosting",
     "Hosting Cloud Domain Software Lizenz SaaS IT-Dienstleistung Rechenzentrum "
     "Hetzner AWS Terminbuchung Online-Kalender Planity Buchungssystem Salonsoftware Monatsabo"),
    ("sonstiges", "sonstiges", "Sonstiger Betriebsbedarf",
     "Quittung Kassenbon Einkauf Baumarkt Drogerie allgemeiner Betriebsbedarf"),
    # ── Salon-Katalog (SupremeBeauty): Konten vor Produktivgang vom
    #    Steuerberater bestätigen lassen — Texte sind die Embedding-Anker. ──
    ("wareneingang", None, "Wareneinkauf oder Verbrauch",
     "Friseurbedarf Haarfarbe Coloration Tönung Blondierung Shampoo Conditioner "
     "Haarpflege Styling Wella L'Oréal Schwarzkopf Henkel Kosmetik Nagellack Gel "
     "Wimpern Extensions Haarverlängerung Echthaar Slavic Hair delila Verkaufsware "
     "Großhandel Salonbedarf"),
    ("fremdleistung", "fremdleistung", "Fremdleistungen",
     "Stuhlmiete Untermiete Kosmetikerin selbständig Fremdleistung Subunternehmer "
     "freie Mitarbeiterin Nageldesignerin auf Rechnung Provision"),
    ("miete", "miete", "Miete Geschäftsräume",
     "Miete Salonräume Gewerbemiete Nebenkosten Pacht Vermieter monatliche Miete "
     "Ladenlokal Geschäftsräume"),
    ("reinigung", "reinigung", "Reinigung",
     "Reinigungsfirma Gebäudereinigung Handtuchservice Wäscheservice Mietwäsche "
     "Handtücher Umhänge Fensterputzer Reinigungsmittel"),
    ("versicherung", "versicherung", "Versicherungen",
     "Betriebshaftpflicht Inhaltsversicherung Geschäftsversicherung Police Beitrag "
     "Versicherungsschein Prämie Jahresbeitrag"),
    ("werbung", "werbung", "Werbung",
     "Anzeige Social Media Ads Instagram Facebook Flyer Druck Visitenkarten "
     "Gutscheinkarten Werbung Marketing Kampagne"),
    # Neu am 23.08.2026. Vorher fiel ein Föhn unter „sonstiges" und die Frage
    # nach GWG oder Anlage stellte sich nie — genau Ninas Punkt.
    ("ausstattung", None, "Geräte und Einrichtung",
     "Föhn Haartrockner Trockenhaube Friseurstuhl Bedienungsstuhl Waschbecken "
     "Waschsessel Spiegel Ladeneinrichtung Kasse Kassensystem iPad Tablet "
     "Laptop Drucker Klimagerät Heizstrahler Werkzeug Schere Haarschneide"
     "maschine Glätteisen Lockenstab Anschaffung Gerät Möbel"),
]

# Wo das Embedding die Verwendung nicht wissen KANN: Kandidaten und die Frage,
# die sie auflöst. Lieber einmal fragen als jedes Mal falsch buchen.
MEHRDEUTIG = {
    "wareneingang": (("wareneinkauf", "verbrauchsmaterial"),
                     "Nimmt die Kundin das mit, oder wird es im Salon "
                     "aufgebraucht?"),
    "ausstattung": (("gwg", "anlagevermoegen", "sonstiges"),
                    "Was hat ein Stück netto gekostet — und kannst du es "
                    "allein benutzen?"),
}

# Der Kontenrahmen des Betriebs. Eine Entscheidung, kein Belegmerkmal: er gilt
# für alles oder für nichts. SKR03 und SKR04 dürfen sich nie im selben Stapel
# begegnen (kontierung.gehoert_zum_rahmen prüft das).
KONTENRAHMEN = os.environ.get("BABU_KONTENRAHMEN", "SKR04")


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
    kandidaten = [{"code": BABU_KATALOG[i][0], "kategorie": BABU_KATALOG[i][1],
                   "label": BABU_KATALOG[i][2], "score": s} for s, i in scores[:3]]
    best = kandidaten[0]
    return {
        "modell": EMBED_MODELL,
        "belegart_code": best["code"],
        "belegart": best["label"],
        # Was der Text hergibt: eine Kategorie oder — bei mehrdeutigen — nichts.
        # Ein Konto steht hier bewusst NICHT mehr; das entscheidet kontieren().
        "kategorie": best["kategorie"],
        "konfidenz": best["score"],
        "kandidaten": kandidaten,
    }, vektor


def kontieren(sem: dict | None, f: dict) -> kt.Entscheidung:
    """Aus Semantik und gelesenen Beträgen ein Konto — oder eine Rückfrage.

    Die Reihenfolge ist Ninas: erst die Verwendung (die steckt in der
    Kategorie), dann das Konto im Kontenrahmen des Betriebs. Wo die Verwendung
    aus dem Beleg nicht hervorgeht, kommt eine Frage zurück, kein Konto.
    """
    rahmen = KONTENRAHMEN
    if not sem:
        return kt.Entscheidung(
            None, None, rahmen,
            "Semantik nicht verfügbar.",
            rueckfrage="Wofür war das? (Weiterverkauf, Verbrauch, Gerät, …)")

    code = sem.get("belegart_code")
    if code in MEHRDEUTIG:
        moeglich, frage = MEHRDEUTIG[code]
        if code == "ausstattung":
            # Die Betragskaskade kann die Frage oft selbst beantworten.
            # `selbstaendig_nutzbar` steht drin, sobald jemand die Rückfrage
            # beantwortet hat — dann rechnet die Kaskade sie zu Ende, statt
            # dieselbe Frage ein zweites Mal zu stellen.
            return kt.entscheiden(
                verwendung="betriebsausstattung",
                netto_je_stueck=f.get("netto"),
                selbstaendig_nutzbar=f.get("selbstaendig_nutzbar"),
                rahmen=rahmen)
        return kt.Entscheidung(
            None, None, rahmen,
            f"Der Beleg lässt beides zu: {' oder '.join(moeglich)}.",
            rueckfrage=frage)

    kategorie = sem.get("kategorie")
    if not kategorie or kategorie not in kt.KATEGORIEN:
        return kt.Entscheidung(
            None, None, rahmen, "Keine Kategorie erkannt.",
            rueckfrage="Wofür war das?")
    return kt._fertig(kategorie, rahmen,
                      f"Aus dem Belegtext erkannt: {kt.KATEGORIEN[kategorie].name}.")


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


def gegenprobe_abgleichen(f: dict, vlm: dict | None) -> list[str]:
    """Die zweite Lesung mit der ersten vergleichen — melden, nicht ersetzen.

    Die Deutung hat Vorfahrt, weil sie zu jedem Wert die Zeile nennen kann.
    Die Gegenprobe darf deshalb nichts überschreiben. Sie darf zweierlei:
    eine Abweichung melden, damit ein Mensch hinsieht, und eine Lücke
    füllen, die die Deutung offen gelassen hat — dann aber sichtbar
    gekennzeichnet, weil für einen so gefüllten Wert keine Zeile benannt
    werden kann.

    Verändert `f` an Ort und Stelle und gibt die Abweichungen zurück.
    """
    widerspruch: list[str] = []
    if not isinstance(vlm, dict):
        return widerspruch

    for feld, klartext in (("lieferant", "Lieferant"),
                           ("beleg_nr", "Beleg-Nr."), ("datum", "Datum")):
        gegen, unser = vlm.get(feld), f.get(feld)
        if gegen in (None, "") or unser in (None, ""):
            continue
        a, b = str(gegen).strip(), str(unser).strip()
        if feld == "datum":
            a = _als_datum(a) or a
        if (a.lower() != b.lower() and a.lower() not in b.lower()
                and b.lower() not in a.lower()):
            widerspruch.append(f"{klartext}: die Gegenprobe liest „{a}“, "
                               f"gelesen wurde „{b}“")

    gegen_brutto = _als_betrag(vlm.get("brutto"))
    if (gegen_brutto is not None and f.get("brutto") is not None
            and abs(gegen_brutto - f["brutto"]) > 0.011):
        widerspruch.append(
            f"Rechnungsbetrag: die Gegenprobe liest {gegen_brutto:.2f} €, "
            f"gelesen wurden {f['brutto']:.2f} €")

    herkunft = f.setdefault("herkunft", {})
    aus_gegenprobe = {"regel": "aus der Gegenprobe übernommen, weil der Beleg "
                      "selbst nichts hergab", "zeile": None,
                      "zeilentext": "", "konf": 0.0}
    for feld in ("lieferant", "beleg_nr"):
        if f.get(feld) in (None, "") and vlm.get(feld):
            f[feld] = str(vlm[feld]).strip()
            herkunft[feld] = dict(aus_gegenprobe)
    if f.get("datum") in (None, "") and vlm.get("datum"):
        iso = _als_datum(str(vlm["datum"]))
        if iso:
            f["datum"] = iso
            herkunft["datum"] = dict(aus_gegenprobe)
    if f.get("brutto") is None and gegen_brutto is not None:
        f["brutto"] = gegen_brutto
        herkunft["brutto"] = dict(aus_gegenprobe)
        f.setdefault("offen", []).append(
            "Der Rechnungsbetrag stammt aus der Gegenprobe — auf dem Beleg "
            "war keine Summe zu finden. Bitte einmal ansehen.")

    if vlm.get("bewirtung") is True:
        f["bewirtungssignal"] = True
    return widerspruch


def vlm_zusammenfassung(bildpfad: Path, felder: dict) -> str | None:
    """Ein Satz, den ein Mensch liest — die Zusammenfassung zum grünen Haken.

    Das Bildmodell entscheidet keine Zahlen mehr; die kommen aus der Deutung
    und sind bis auf die Zeile nachweisbar. Was es kann und was keine Regel
    kann, ist sagen, *worum es geht*: „Farbe und Entwickler beim
    Friseurgroßhandel". Das steht neben dem Haken, damit man einen Beleg
    wiedererkennt, ohne ihn zu öffnen.
    """
    import base64
    b64 = base64.b64encode(bildpfad.read_bytes()).decode()
    mime = "image/png" if bildpfad.suffix.lower() == ".png" else "image/jpeg"
    bekannt = ", ".join(
        f"{name} {wert}" for name, wert in (
            ("Lieferant", felder.get("lieferant")),
            ("Betrag", f"{felder['brutto']:.2f} EUR" if felder.get("brutto") else None),
            ("Datum", felder.get("datum")))
        if wert)
    anweisung = (
        "Du siehst einen deutschen Geschäftsbeleg. Schreibe EINEN deutschen "
        "Satz, höchstens 120 Zeichen, der sagt, worum es geht — was gekauft "
        "oder bezahlt wurde und bei wem. Kein Markdown, keine Anführungs"
        "zeichen, keine Aufzählung, keine Wiederholung der Zahlen. "
        # Ohne diesen Satz kommt „Ich habe zwei Kaffee gekauft" heraus —
        # babu spricht dann in der Ich-Form über einen Einkauf, den die
        # Nutzerin gemacht hat. Der Satz steht neben jedem grünen Haken.
        "Schreibe sachlich in der dritten Person, ohne „ich“ und ohne „wir“ — "
        "am besten als knappe Feststellung, etwa „Zwei Kaffee beim Kiosk "
        "Sonnenschein“. "
        + (f"Bereits sicher gelesen: {bekannt}. " if bekannt else "")
        + "Wenn das Bild nichts hergibt, antworte genau: unklar")
    payload = {
        "model": VLM_MODELL, "temperature": 0, "max_tokens": 120,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": anweisung},
        ]}],
    }
    r = requests.post(VLM_API, json=payload, timeout=180)
    r.raise_for_status()
    satz = r.json()["choices"][0]["message"]["content"].strip()
    satz = re.sub(r"^```.*?\n|```$", "", satz, flags=re.S).strip().strip('"„“')
    satz = " ".join(satz.split())
    if not satz or satz.lower().startswith("unklar"):
        return None
    return satz[:160]


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


def _als_datum(wert) -> str | None:
    """TT.MM.JJJJ der Gegenprobe auf die ISO-Schreibweise bringen.

    Ohne das meldete jedes Datum einen Widerspruch, nur weil zwei Lanes es
    verschieden schreiben — und ein Warnhinweis, der immer erscheint, wird
    nicht gelesen.
    """
    if not wert:
        return None
    t = str(wert).strip()
    m = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", t)
    if m:
        tag, monat, jahr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        jahr = jahr + 2000 if jahr < 100 else jahr
        try:
            return datetime(jahr, monat, tag).date().isoformat()
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    return t if m else None


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


def felder_aus_lesung(lesung: Lesung) -> dict:
    """Aus der Deutung den Feldsatz machen, den Review, App und Export lesen.

    Zwei Dinge kommen hier aus der Deutung mit, die früher unterwegs
    verlorengingen:

    * **Die Rechenproben.** Sie stehen einzeln mit Namen und Erklärung im
      Review, damit eine Rückfrage sagen kann, *welche* Probe nicht aufging.
    * **Die Steuertabelle.** Der Export teilt einen Bon mit 19 % und 7 % in
      zwei Buchungszeilen — dafür muss er die Sätze einzeln bekommen. Seit
      die Deutung die Führung hat, kam hier nichts mehr an, und jeder
      Mehrsatz-Bon wurde auf einen Schlüssel gebucht.
    """
    f = {
        "lieferant": lesung.wert("lieferant"),
        "beleg_nr": lesung.wert("beleg_nr"),
        "datum": lesung.wert("datum"),
        "netto": lesung.wert("netto"),
        "ust": lesung.wert("ust"),
        "brutto": lesung.wert("brutto"),
        "ust_satz": lesung.wert("ust_satz"),
        "summenprobe_ok": bool(lesung.wert("summenprobe_ok")),
        "bewirtungssignal": False,
        "offen": list(lesung.offen),
        "herkunft": {name: {"regel": d.regel, "zeile": d.zeile_nr,
                            "zeilentext": d.zeilentext, "konf": round(d.konf, 3)}
                     for name, d in lesung.felder.items() if d.wert is not None},
        "notizen": list(lesung.notizen),
        "proben": [{"name": p.name, "bestanden": p.bestanden,
                    "erklaerung": p.erklaerung, "zeile": p.zeile_nr}
                   for p in lesung.proben],
    }
    if lesung.steuerpositionen:
        f["steuertabelle"] = [p.als_dict() for p in lesung.steuerpositionen]
    if f["ust_satz"] is None:
        # Ohne erkennbaren Satz wird nicht 19 % angenommen: die Annahme
        # erzeugte Vorsteuer, die auf keinem Beleg stand. 0 % kostet im
        # Zweifel Abzug, 19 % kosten im Zweifel eine Nachzahlung.
        f["ust_satz"] = 0
    return f


def einschaetzung(f: dict, sem: dict | None, dokumentklasse: str) -> dict:
    """Steuerliche Ersteinschätzung.

    Seit 23.08.2026 in Ninas Reihenfolge: die Semantik liefert eine
    BUCHUNGSKATEGORIE, kontieren() macht daraus im Kontenrahmen des Betriebs
    ein Konto — oder eine Rückfrage. Deterministische Signale (Bewirtung)
    übersteuern weiterhin; der Keyword-Klassifikator liefert nur noch die
    Dokumentklasse als Zusatzinfo.

    `konto_skr04` bleibt im Ausgabeformat, wird aber nur noch gefüllt, wenn der
    Betrieb wirklich SKR04 fährt. Ein SKR03-Konto unter diesem Namen wäre genau
    die Vermischung, die es nicht geben darf.
    """
    ks = "8" if f["ust_satz"] == 7 else ("0" if f["ust_satz"] == 0 else "9")
    e = {"belegart": dokumentklasse, "konto_skr04": None, "steuerschluessel": ks,
         "kontenrahmen": KONTENRAHMEN, "kategorie": None, "konto": None,
         "kontierung_grund": None, "rueckfrage": None, "hinweise": []}

    if sem:
        e["belegart"] = f"{sem['belegart']} (semantisch, {sem['konfidenz']:.0%})"

    ent = kontieren(sem, f)
    e["kategorie"] = ent.kategorie
    e["konto"] = ent.konto
    e["kontierung_grund"] = ent.begruendung
    e["rueckfrage"] = ent.rueckfrage
    if ent.rueckfrage:
        e["hinweise"].append(ent.rueckfrage)
    if ent.kategorie and not ent.geprueft:
        e["hinweise"].append(
            f"Konto für „{kt.KATEGORIEN[ent.kategorie].name}“ ist noch nicht "
            f"steuerlich bestätigt.")

    bewirtung = f["bewirtungssignal"] or (sem and sem["belegart_code"] == "bewirtung")
    if bewirtung:
        e["kategorie"] = "bewirtung"
        e["konto"] = kt.konto("bewirtung", KONTENRAHMEN)
        e["rueckfrage"] = None
        e["hinweise"] += [
            "Bewirtungsbeleg: 70 % abziehbar (§4 Abs. 5 Nr. 2 EStG), Vorsteuer zu 100 %.",
            "Bewirtungsangaben ergänzen: Anlass, Teilnehmer, Unterschrift.",
        ]
        if any("Trinkgeld" in o for o in f["offen"]):
            e["hinweise"].append("Trinkgeld ist ohne Vorsteuer abziehbar — separat erfassen.")
    elif dokumentklasse == "Spendenbescheinigung":
        e["konto"] = None
        e["kategorie"] = None
        e["hinweise"].append("Zuwendungsbestätigung → Sonderausgaben (Anlage SA), kein Betriebsausgabenkonto.")
    elif dokumentklasse == "Lohnsteuerbescheinigung":
        e["hinweise"].append("LStB → Anlage N (eCodes via VaSt), kein Buchungsbeleg.")
    elif sem is None:
        e["kategorie"] = "sonstiges"
        e["konto"] = kt.konto("sonstiges", KONTENRAHMEN)
        e["hinweise"].append("Semantik nicht verfügbar — Leistungsart prüfen (Vorschlag: sonstiger Betriebsbedarf).")
    if not f["summenprobe_ok"]:
        # „Summenprobe nicht bestanden" schickt Nina auf die Suche. Welche
        # Probe nicht aufging und mit welchen Zahlen, zeigt ihr die Zeile.
        gescheitert = [p for p in (f.get("proben") or []) if not p.get("bestanden")]
        if gescheitert:
            e["hinweise"].append("Rechenprobe nicht bestanden — " + "; ".join(
                f"{p['name']}: {p['erklaerung']}" for p in gescheitert) + ".")
        else:
            e["hinweise"].append("Summenprobe nicht bestanden — Beträge prüfen.")
    # Altes Feld weiterbedienen, aber nur wahrheitsgemäß: unter SKR03 bleibt es
    # leer, statt eine SKR03-Nummer als SKR04 auszugeben.
    if KONTENRAHMEN == "SKR04":
        e["konto_skr04"] = e["konto"]
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
    kaesten = ocr_kaesten(lokal)
    dauer = time.time() - t0
    zeilen = [(k.text, k.konf) for k in kaesten]
    text = "\n".join(t for t, _ in zeilen)
    dokumentklasse = classify_doc(text, name=Path(pfad).name, pages=seiten)

    # ── Wer entscheidet ──────────────────────────────────────────────────
    #
    # Die Deutung entscheidet. Sie arbeitet auf dem, was die Texterkennung
    # tatsächlich geliefert hat — Zeilen an ihrem Ort, in ihrer Größe — und
    # kann zu jeder Zahl sagen, aus welcher Zeile sie stammt und warum. Das
    # ist die Eigenschaft, auf die es hier ankommt: was in eine Buchhaltung
    # geht, muss nachweisbar sein, nicht nur plausibel.
    #
    # Bis zum 22.08.2026 war das zweimal anders geregelt und beide Male
    # falsch. Erst führte eine Textsuche, die Zeichen sah statt Dokumente —
    # sie hielt „19,00 %" für den Rechnungsbetrag und das Stammkapital aus
    # der Fußzeile für die Summe. Dann führte das Bildmodell, das zwar
    # versteht, aber nicht belegen kann, woher ein Wert kommt; für Zahlen,
    # die gebucht werden, ist das der falsche Tausch.
    #
    # Das Bildmodell behält zwei Aufgaben, für die es das bessere Werkzeug
    # ist: es liest denselben Beleg noch einmal und meldet Abweichungen,
    # und es schreibt den Satz, der neben dem grünen Haken steht.
    lesung = deuten(kaesten)
    f = felder_aus_lesung(lesung)

    # Das Bewirtungssignal bleibt eine Wortfrage („Restaurant", „Menü") und
    # ist damit an der Textsuche gut aufgehoben.
    try:
        f["bewirtungssignal"] = bool(felder_extrahieren(zeilen).get("bewirtungssignal"))
    except Exception as ex:  # noqa: BLE001
        log(f"Bewirtungssignal nicht ermittelbar: {ex!r}")

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

    # ── Die Gegenprobe: dasselbe Bild, zweite Meinung ────────────────────
    vlm = None
    try:
        vlm = vlm_lesen(lokal)
    except Exception as ex:  # noqa: BLE001
        log(f"Gegenprobe nicht verfügbar: {ex!r}")

    widerspruch = gegenprobe_abgleichen(f, vlm)
    f["widerspruch"] = widerspruch

    # ── Der Satz zum grünen Haken ────────────────────────────────────────
    zusammenfassung = None
    try:
        zusammenfassung = vlm_zusammenfassung(lokal, f)
    except Exception as ex:  # noqa: BLE001
        log(f"Zusammenfassung nicht verfügbar: {ex!r}")
    if not zusammenfassung and vlm and vlm.get("buchungstext"):
        zusammenfassung = str(vlm["buchungstext"]).strip()[:160]

    e = einschaetzung(f, sem, dokumentklasse)
    if aehnlich:
        e["hinweise"].append(
            f"Ähnlichster früherer Beleg: {aehnlich['datei']} ({aehnlich['score']:.0%}).")
    if widerspruch:
        e["hinweise"].append(
            "Die Gegenprobe liest etwas anderes (" + "; ".join(widerspruch)
            + "). Gültig ist die Lesung vom Beleg — bitte kurz ansehen.")
        f["offen"].append("Die Gegenprobe weicht ab — kurz prüfen.")

    gelesen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review = {
        "datei": pfad,
        "engine": f"PaddleOCR {_OCR_QUELLE}",
        "gelesen": gelesen,
        "dauer_s": round(dauer, 2),
        "zeilen": len(lesung.zeilen),
        "ocr_konfidenz": round(sum(c for _, c in zeilen) / len(zeilen), 3) if zeilen else 0,
        "dokumentklasse": dokumentklasse,
        "semantik": sem,
        "vlm": vlm,
        "zusammenfassung": zusammenfassung,
        "aehnlich": aehnlich,
        "felder": f,
        "einschaetzung": e,
        "ocr_text": text[:8000],
    }
    if seiten > 1:
        review["seiten"] = seiten

    md = protokoll(
        lesung, datei=Path(pfad).name, engine=review["engine"], dauer_s=dauer,
        zusammenfassung=zusammenfassung, belegart=e.get("belegart"),
        konto=e.get("konto_skr04"), steuerschluessel=e.get("steuerschluessel"),
        gegenprobe=vlm, widerspruch=widerspruch, dokumentklasse=dokumentklasse,
        gelesen_am=gelesen).split("\n")

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
