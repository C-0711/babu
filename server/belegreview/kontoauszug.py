"""Kontoauszug-Lane (Stufe 6) — KSK-GiroBusiness-Auszüge sind Text-PDFs.

Parst die Umsatzliste (Datum+Typ-Zeile, Beschreibungszeilen, Betrag allein
auf eigener Zeile; Soll negativ) und liefert das Material für den
Zahlungsabgleich: „Für diese Abbuchung fehlt der Beleg."
"""
import re

DATUM_TYP_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s*(.+)$")
BETRAG_RE = re.compile(r"^\s*(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
AUSZUG_RE = re.compile(r"Kontoauszug\s+(\d{1,2})/(\d{4})")
KONTO_RE = re.compile(r"GiroBusiness\s+(\d+)")
FUSS_WOERTER = ("Postanschrift", "BIC-Code", "Vorstand", "Handelsregister")


def _betrag(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parse_text(text: str) -> dict:
    zeilen = text.replace("\r\n", "\n").split("\n")
    umsaetze: list[dict] = []
    monat = None
    konto = None
    aktuell: dict | None = None
    beschreibung: list[str] = []
    for zeile in zeilen:
        m = AUSZUG_RE.search(zeile)
        if m and monat is None:
            monat = f"{m.group(2)}-{int(m.group(1)):02d}"
        m = KONTO_RE.search(zeile)
        if m and konto is None:
            konto = m.group(1)

        m = DATUM_TYP_RE.match(zeile.strip())
        if m and "Kontostand" not in zeile:
            aktuell = {"datum": m.group(1), "typ": m.group(2).strip()}
            beschreibung = []
            continue
        if aktuell is None:
            continue
        m = BETRAG_RE.match(zeile)
        if m:
            aktuell["betrag"] = _betrag(m.group(1))
            aktuell["text"] = " ".join(beschreibung)[:300]
            aktuell["gegenpartei"] = (beschreibung[0].strip()[:80]
                                      if beschreibung else aktuell["typ"])
            umsaetze.append(aktuell)
            aktuell = None
            continue
        if any(w in zeile for w in FUSS_WOERTER):
            aktuell = None
            continue
        if zeile.strip():
            beschreibung.append(zeile.strip())
    return {"konto": konto, "monat": monat, "umsaetze": umsaetze}


def parse_pdf(pfad) -> dict:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pfad))
    try:
        text = "\n".join(seite.get_textpage().get_text_range() for seite in doc)
    finally:
        doc.close()
    return parse_text(text)


BANK_RE = re.compile(r"(KREISSPARKASSE|Sparkasse).*(Entgelt|Abschluss)", re.I)
EINNAHME_WOERTER = ("SUMUP", "Gutschrift")


def abgleich(umsaetze: list[dict], belege: list[dict],
             toleranz_tage: int = 10) -> dict:
    """Abbuchungen ↔ Belege: Betrag (±2 ct) + Datumsnähe. Bankentgelte zählen
    nicht als fehlend (der Auszug selbst ist der Beleg)."""
    def _tag(d: str) -> int | None:
        t = d.split(".")
        if len(t) != 3:
            return None
        try:
            return int(t[2]) * 372 + int(t[1]) * 31 + int(t[0])
        except ValueError:
            return None

    fehlend, gedeckt, bank, einnahmen = [], [], [], []
    frei = [dict(z) for z in belege if z.get("brutto") is not None]
    for u in umsaetze:
        if u["betrag"] >= 0:
            if any(w in (u.get("text") or "") + u.get("typ", "") for w in EINNAHME_WOERTER):
                einnahmen.append(u)
            continue
        if BANK_RE.search(u.get("text", "")):
            bank.append(u)
            continue
        soll = round(-u["betrag"], 2)
        utag = _tag(u["datum"])
        treffer = None
        for z in frei:
            if abs((z["brutto"] or 0) - soll) > 0.02:
                continue
            btag = _tag(z.get("datum") or "")
            if utag is not None and btag is not None and abs(utag - btag) > toleranz_tage:
                continue
            treffer = z
            break
        if treffer is not None:
            frei.remove(treffer)
            gedeckt.append({"umsatz": u, "stamm": treffer.get("stamm")})
        else:
            fehlend.append(u)
    return {
        "gedeckt": gedeckt,
        "fehlend": fehlend,
        "bankgebuehren": bank,
        "einnahmen": einnahmen,
        "einnahmen_summe": round(sum(u["betrag"] for u in einnahmen), 2),
        "fehlend_summe": round(sum(-u["betrag"] for u in fehlend), 2),
    }
