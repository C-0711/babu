"""Abschluss-Lane — liest Jahresabschluss-Unterlagen für den Salon-Check.

Eigenständige Pipeline neben dem Beleg-Weg: EÜR, BWA, Steuerbescheide,
Anlagenverzeichnis und Summen-/Saldenlisten, als Text-PDF oder Scan, in
beliebiger Reihenfolge. Kein Import aus review_watcher (dessen Modulzustand
gehört dem pm2-Prozess); der LLM-Zugang ist hier bewusst dupliziert.

Der Aufrufer reicht ein `melden(feld)`-Callback herein — darüber erscheinen
extrahierte Werte einzeln im Portal („Zuschauen statt Abtippen").
"""
import io
import json
import os
import re

LLM_API = os.environ.get("BABU_LLM_API",
                         "http://127.0.0.1:11435/v1/chat/completions")
LLM_MODELL = os.environ.get("BABU_LLM_MODELL", "gemma4-mm")
LLM_TIMEOUT = 180
SEITEN_CAP = 40
TEXT_SCHWELLE = 200          # Zeichen auf Seite 1 → Text-Lane
BILD_MAX_KANTE = 1600
SUMMEN_TOLERANZ = 0.01       # 1 % für die Gewinn-Probe

ART_ANKER = [
    ("euer", re.compile(r"Einnahmen[\s-]*[üu]berschuss|Anlage\s+EÜR", re.I)),
    ("bwa", re.compile(r"Betriebswirtschaftliche\s+Auswertung|\bBWA\b")),
    ("bescheid", re.compile(r"Bescheid\s+f[üu]r\s+20\d\d\s+[üu]ber|"
                            r"(Einkommensteuer|Umsatzsteuer|Gewerbesteuer)bescheid", re.I)),
    ("anlagen", re.compile(r"Anlagen?(verzeichnis|spiegel)|AfA-?Liste", re.I)),
    ("susa", re.compile(r"Summen-?\s*und\s*Salden|Saldenliste", re.I)),
]
ARTEN = tuple(a for a, _ in ART_ANKER) + ("sonstiges",)

ART_LABEL = {"euer": "Gewinnrechnung", "bwa": "Monatsauswertung",
             "bescheid": "Steuerbescheid", "anlagen": "Anlagenliste",
             "susa": "Kontenliste", "sonstiges": "Unterlage"}

# Zielschema: welche Zahl aus welcher Dokumentart gilt (Vorrangreihenfolge).
ZAHL_VORRANG = {
    "umsatz": ("euer", "bwa", "susa"),
    "wareneinsatz": ("euer", "bwa", "susa"),
    "personal": ("euer", "bwa", "susa"),
    "raumkosten": ("euer", "bwa", "susa"),
    "afa": ("euer", "anlagen", "bwa"),
    "sonstige_kosten": ("euer", "bwa"),
    # Eigener Posten, seit dem ersten echten Abschluss: dort standen 15.518,40 €
    # für Steuerberatung, Abschluss und Buchführung gegen 16.441,48 € Gewinn.
    # In „sonstige_kosten" versteckt wäre das die wichtigste Zahl des Berichts
    # gewesen — und unsichtbar.
    "steuerberatung": ("euer", "susa", "bwa"),
    "gewinn": ("euer", "bescheid", "bwa"),
    "ust_zahllast": ("bescheid", "euer"),
    "est_vorauszahlungen": ("bescheid",),
}
STAMM_FELDER = ("rechtsform", "steuernummer", "finanzamt", "kleinunternehmer")


def betrag_zahl(wert) -> float | None:
    """'1.234,56 €' → 1234.56; nimmt auch fertige Zahlen entgegen."""
    if wert is None:
        return None
    if isinstance(wert, (int, float)):
        return float(wert)
    s = str(wert).strip().replace("€", "").replace(" ", "")
    if not s:
        return None
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d+(,\d+)?", s):
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- PDF-Zugriff

def seiten_text(pfad) -> list[str]:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pfad))
    try:
        return [seite.get_textpage().get_text_range()
                for seite in list(doc)[:SEITEN_CAP]]
    finally:
        doc.close()


def seiten_bilder(pfad, max_kante: int = BILD_MAX_KANTE) -> list[bytes]:
    """Rendert PDF-Seiten (oder liest ein Bild) als JPEG-Bytes."""
    from PIL import Image
    p = str(pfad)
    if not p.lower().endswith(".pdf"):
        bild = Image.open(p).convert("RGB")
        bild.thumbnail((max_kante, max_kante))
        puffer = io.BytesIO()
        bild.save(puffer, "JPEG", quality=80)
        return [puffer.getvalue()]
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(p)
    bilder = []
    try:
        for seite in list(doc)[:SEITEN_CAP]:
            breite = seite.get_size()[0]
            bild = seite.render(scale=max_kante / max(breite, 1)).to_pil().convert("RGB")
            bild.thumbnail((max_kante, max_kante))
            puffer = io.BytesIO()
            bild.save(puffer, "JPEG", quality=80)
            bilder.append(puffer.getvalue())
    finally:
        doc.close()
    return bilder


# ------------------------------------------------------------------- LLM-Kern

def llm_json(nachrichten: list[dict], timeout: int = LLM_TIMEOUT) -> dict:
    """Chat-Completion, Antwort als JSON (Codezäune werden toleriert)."""
    import requests
    r = requests.post(LLM_API, timeout=timeout, json={
        "model": LLM_MODELL, "messages": nachrichten,
        "temperature": 0, "max_tokens": 1500,
    })
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("keine JSON-Antwort")
    return json.loads(m.group(0))


def _bild_nachricht(prompt: str, jpeg: bytes) -> dict:
    import base64
    b64 = base64.b64encode(jpeg).decode()
    return {"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]}


# ------------------------------------------------------------ Klassifikation

def art_erkennen(seite1_text: str, llm=llm_json) -> str:
    for art, muster in ART_ANKER:
        if muster.search(seite1_text or ""):
            return art
    if not (seite1_text or "").strip():
        return "sonstiges"
    try:
        d = llm([
            {"role": "system", "content":
                "Du ordnest deutsche Steuer-Unterlagen ein. Antworte nur als "
                'JSON: {"art": "..."} mit genau einem Wert aus '
                f"{list(ARTEN)}."},
            {"role": "user", "content": seite1_text[:3000]},
        ])
        art = str(d.get("art", "")).strip()
        return art if art in ARTEN else "sonstiges"
    except Exception:
        return "sonstiges"


# --------------------------------------------------------------- Extraktion

_EXTRAKT_FELDER = {
    "euer": ("umsatz", "wareneinsatz", "personal", "raumkosten", "afa",
             "sonstige_kosten", "steuerberatung", "gewinn", "ust_zahllast",
             "steuernummer", "finanzamt", "rechtsform"),
    "bwa": ("umsatz", "wareneinsatz", "personal", "raumkosten", "afa",
            "sonstige_kosten", "steuerberatung", "gewinn"),
    "bescheid": ("gewinn", "ust_zahllast", "est_vorauszahlungen",
                 "steuernummer", "finanzamt", "rechtsform"),
    "susa": ("umsatz", "wareneinsatz", "personal", "raumkosten",
             "steuerberatung"),
    "anlagen": ("afa",),
    "sonstiges": (),
}

_FELD_ERKLAERUNG = """\
- umsatz: Betriebseinnahmen/Umsatzerlöse gesamt (netto) für das Jahr
- wareneinsatz: Waren-/Materialeinkauf (Friseurbedarf)
- personal: Löhne, Gehälter und Sozialabgaben gesamt
- raumkosten: Miete, Nebenkosten, Energie für die Geschäftsräume
- afa: Abschreibungen gesamt
- sonstige_kosten: alle übrigen Betriebsausgaben OHNE die Steuerberatung
- steuerberatung: Rechts-/Steuerberatung, Abschluss- und Prüfungskosten,
  Buchführungskosten zusammen (SKR04 6825, 6827, 6830) — falls getrennt
  ausgewiesen, sonst null
- gewinn: Gewinn/Überschuss bzw. "Einkünfte aus Gewerbebetrieb"
- ust_zahllast: Umsatzsteuer-Zahllast des Jahres
- est_vorauszahlungen: festgesetzte Einkommensteuer-Vorauszahlungen (Jahressumme)
- steuernummer, finanzamt, rechtsform: falls angegeben"""


def _extrakt_prompt(art: str, jahr: int | None) -> str:
    felder = ", ".join(_EXTRAKT_FELDER.get(art) or ())
    return (f"Dies ist eine deutsche Steuer-Unterlage ({ART_LABEL.get(art)}), "
            f"Jahr {jahr or 'unbekannt'}. Lies daraus diese Felder:\n"
            f"{_FELD_ERKLAERUNG}\n"
            f"Gib NUR JSON zurück mit den Schlüsseln [{felder}] und, wenn es "
            f"eine Anlagenliste gibt, zusätzlich \"afa_liste\": "
            f"[{{\"bezeichnung\", \"anschaffung\", \"wert\", \"restwert\"}}]. "
            f"Beträge als Zahl in Euro. Fehlende Werte: null. Rate NIE.")


def dokument_lesen(pfad, jahr: int | None = None, melden=None, llm=llm_json,
                   fortschritt=None) -> dict:
    """Liest EIN Dokument: Lane wählen, Art erkennen, Felder ziehen."""
    name = os.path.basename(str(pfad))
    ist_pdf = name.lower().endswith(".pdf")
    texte = seiten_text(pfad) if ist_pdf else []
    text_lane = bool(texte) and len((texte[0] or "").strip()) >= TEXT_SCHWELLE
    seite1 = texte[0] if texte else ""
    art = art_erkennen(seite1, llm=llm) if (text_lane or seite1.strip()) else None

    if text_lane:
        if fortschritt:
            fortschritt(f"Ich lese {ART_LABEL.get(art, 'deine Unterlage')} — "
                        f"{len(texte)} Seiten")
        roh = llm([
            {"role": "system", "content": "Du liest deutsche Steuer-Unterlagen "
                                          "präzise. Nur JSON, keine Erklärungen."},
            {"role": "user",
             "content": _extrakt_prompt(art, jahr) + "\n\n" +
                        "\n\n".join(t[:6000] for t in texte)},
        ])
        seiten_zahl = len(texte)
    else:
        bilder = seiten_bilder(pfad)
        seiten_zahl = len(bilder)
        seiten_json = []
        for i, jpeg in enumerate(bilder, 1):
            if art is None and i == 1:
                # Scan ohne Textebene: Art aus dem ersten Blatt erkennen.
                kopf = llm([_bild_nachricht(
                    "Was für eine deutsche Steuer-Unterlage ist das? Nur JSON: "
                    f'{{"art": eine aus {list(ARTEN)}, "text": "die wichtigsten '
                    f'Posten mit Beträgen"}}', jpeg)])
                art = kopf.get("art") if kopf.get("art") in ARTEN else "sonstiges"
                seiten_json.append(kopf.get("text") or "")
                continue
            if fortschritt:
                fortschritt(f"Ich lese {ART_LABEL.get(art, 'deine Unterlage')} — "
                            f"Seite {i} von {seiten_zahl}")
            d = llm([_bild_nachricht(
                "Lies alle Posten mit Beträgen von diesem Blatt. Nur JSON: "
                '{"text": "Posten: Betrag, je Zeile"}', jpeg)])
            seiten_json.append(d.get("text") or "")
        roh = llm([
            {"role": "system", "content": "Du liest deutsche Steuer-Unterlagen "
                                          "präzise. Nur JSON, keine Erklärungen."},
            {"role": "user",
             "content": _extrakt_prompt(art, jahr) + "\n\nAbgelesene Posten:\n" +
                        "\n".join(seiten_json)},
        ])

    werte = {}
    for feld in _EXTRAKT_FELDER.get(art) or ():
        if feld in STAMM_FELDER:
            wert = roh.get(feld)
            if feld == "kleinunternehmer":
                wert = bool(wert) if wert is not None else None
            elif wert is not None:
                wert = str(wert).strip()[:200] or None
        else:
            wert = betrag_zahl(roh.get(feld))
        if wert is None:
            continue
        werte[feld] = wert
        if melden:
            melden({"schluessel": feld, "wert": wert,
                    "quelle": f"{ART_LABEL.get(art, 'Unterlage')} ({name})",
                    "sicher": True})
    afa_liste = []
    for zeile in (roh.get("afa_liste") or []):
        if isinstance(zeile, dict):
            afa_liste.append({
                "bezeichnung": str(zeile.get("bezeichnung") or "")[:120],
                "anschaffung": str(zeile.get("anschaffung") or "")[:20],
                "wert": betrag_zahl(zeile.get("wert")),
                "restwert": betrag_zahl(zeile.get("restwert")),
            })
    return {"datei": name, "art": art or "sonstiges", "seiten": seiten_zahl,
            "lane": "text" if text_lane else "scan",
            "werte": werte, "afa_liste": afa_liste}


# ------------------------------------------------------------- Zusammenführen

def _summenproben(zahlen: dict, je_art: dict) -> tuple[dict, list[str]]:
    unsicher: list[str] = []
    pruefungen = {"summenprobe_ok": None, "abweichung_prozent": None,
                  "bescheid_abgleich_ok": None}
    kosten = [zahlen.get(k) for k in ("wareneinsatz", "personal", "raumkosten",
                                      "afa", "sonstige_kosten")]
    if zahlen.get("umsatz") and zahlen.get("gewinn") is not None and all(
            k is not None for k in kosten):
        erwartet = zahlen["umsatz"] - sum(kosten)
        abweichung = abs(erwartet - zahlen["gewinn"]) / max(abs(zahlen["umsatz"]), 1)
        pruefungen["summenprobe_ok"] = abweichung <= SUMMEN_TOLERANZ
        pruefungen["abweichung_prozent"] = round(abweichung * 100, 1)
        if not pruefungen["summenprobe_ok"]:
            unsicher.append("gewinn")
    euer_gewinn = (je_art.get("euer") or {}).get("gewinn")
    bescheid_gewinn = (je_art.get("bescheid") or {}).get("gewinn")
    if euer_gewinn is not None and bescheid_gewinn is not None:
        abw = abs(euer_gewinn - bescheid_gewinn) / max(abs(euer_gewinn), 1)
        pruefungen["bescheid_abgleich_ok"] = abw <= SUMMEN_TOLERANZ
        if not pruefungen["bescheid_abgleich_ok"] and "gewinn" not in unsicher:
            unsicher.append("gewinn")
    return pruefungen, unsicher


def zusammenfuehren(dokumente: list[dict], jahr: int | None = None) -> dict:
    """Ergebnisse je Dokument → ein kennzahlen.json (mit Vorrang + Proben)."""
    je_art: dict[str, dict] = {}
    for d in dokumente:
        je_art.setdefault(d["art"], {}).update(d.get("werte") or {})
    zahlen = {}
    for feld, vorrang in ZAHL_VORRANG.items():
        zahlen[feld] = next((je_art[a][feld] for a in vorrang
                             if feld in (je_art.get(a) or {})), None)
    stammdaten = {}
    for feld in STAMM_FELDER:
        stammdaten[feld] = next((w[feld] for a in ("bescheid", "euer", "bwa")
                                 for w in [je_art.get(a) or {}] if feld in w),
                                None)
    afa_liste = [z for d in dokumente for z in (d.get("afa_liste") or [])]
    pruefungen, unsicher = _summenproben(zahlen, je_art)
    return {
        "jahr": jahr,
        "quellen": [{"datei": d["datei"], "art": d["art"],
                     "seiten": d["seiten"], "lane": d["lane"]}
                    for d in dokumente],
        "stammdaten": stammdaten,
        "zahlen": zahlen,
        "afa_liste": afa_liste,
        "pruefungen": pruefungen,
        "unsicher": unsicher,
    }
