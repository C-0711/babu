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
    if monat is None and umsaetze:
        # Keine „Kontoauszug N/JJJJ"-Zeile gelesen (Foto, andere Bank) —
        # dann sagt es der Inhalt: der Monat, in dem die meisten Umsätze
        # liegen, ist der Monat des Auszugs.
        haeufig: dict[str, int] = {}
        for u in umsaetze:
            m = re.match(r"\d{2}\.(\d{2})\.(\d{4})", u.get("datum") or "")
            if m:
                schluessel = f"{m.group(2)}-{m.group(1)}"
                haeufig[schluessel] = haeufig.get(schluessel, 0) + 1
        if haeufig:
            monat = max(haeufig, key=lambda k: (haeufig[k], k))
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
    # Zusätzlich JEDE Position in Originalreihenfolge des Auszugs, mit
    # Status — daraus wird die Checkliste, auf der Nina abhakt.
    positionen: list[dict] = []
    frei = [dict(z) for z in belege if z.get("brutto") is not None]
    for u in umsaetze:
        if u["betrag"] >= 0:
            if any(w in (u.get("text") or "") + u.get("typ", "") for w in EINNAHME_WOERTER):
                einnahmen.append(u)
            positionen.append(dict(u, status="einnahme", stamm=None))
            continue
        if BANK_RE.search(u.get("text", "")):
            bank.append(u)
            positionen.append(dict(u, status="bank", stamm=None))
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
            positionen.append(dict(u, status="gedeckt", stamm=treffer.get("stamm")))
        else:
            fehlend.append(u)
            positionen.append(dict(u, status="fehlt", stamm=None))
    return {
        "gedeckt": gedeckt,
        "fehlend": fehlend,
        "bankgebuehren": bank,
        "einnahmen": einnahmen,
        "positionen": positionen,
        "einnahmen_summe": round(sum(u["betrag"] for u in einnahmen), 2),
        "fehlend_summe": round(sum(-u["betrag"] for u in fehlend), 2),
    }


# ---------------------------------------------------------------------------
# Die andere Richtung: Geldeingang ↔ gestellte Rechnung.
#
# babu kennt beide Seiten — den Eingang auf dem Auszug und die offene
# Forderung. Verbunden hat sie bisher niemand, also setzte die Inhaberin
# Haken, obwohl die Antwort zweimal im Haus lag.
#
# Vorgeschlagen wird, nicht entschieden: ein „bezahlt" verschiebt Umsatz in
# die Umsatzsteuer-Voranmeldung. Ein falscher Treffer wäre kein
# Schönheitsfehler, sondern eine falsche Anmeldung.
# ---------------------------------------------------------------------------

# So lange nach dem Rechnungsdatum wird ein Eingang noch zugeordnet.
ZAHLUNG_FRIST_TAGE = 120


def _iso(datum: str) -> str | None:
    """„02.09.2026" → „2026-09-02"."""
    teile = str(datum or "").split(".")
    if len(teile) != 3:
        return None
    try:
        return f"{int(teile[2]):04d}-{int(teile[1]):02d}-{int(teile[0]):02d}"
    except ValueError:
        return None


def _tage_zwischen(von: str, bis: str) -> int | None:
    import datetime as dt
    try:
        return (dt.date.fromisoformat(bis) - dt.date.fromisoformat(von)).days
    except (TypeError, ValueError):
        return None


def _name_passt(text: str, name: str) -> bool:
    """Steht die Empfängerin im Verwendungszweck? Ein Wort genügt — Banken
    kürzen Namen, und „Allgaier" allein ist schon ein starkes Zeichen."""
    haystack = " " + (text or "").lower() + " "
    teile = [t for t in (name or "").lower().split() if len(t) >= 4]
    return any(t in haystack for t in teile)


def rechnungen_abgleich(umsaetze: list[dict], rechnungen: list[dict]) -> dict:
    """Welcher Geldeingang gehört zu welcher offenen Rechnung?

    Zugeordnet wird über den Betrag (±2 ct) und das Zeitfenster; der Name im
    Verwendungszweck macht aus einem Vorschlag einen sicheren. Passen zwei
    offene Rechnungen gleich gut, wird NICHTS vorgeschlagen — dann steht die
    Mehrdeutigkeit da, statt einer geratenen Zuordnung.
    """
    offen = [r for r in (rechnungen or [])
             if isinstance(r, dict) and not r.get("bezahlt_am")
             and not r.get("storniert_durch") and r.get("brutto")]
    vergeben: set[str] = set()
    vorschlaege: list[dict] = []
    mehrdeutig: list[dict] = []
    ohne: list[dict] = []

    for u in umsaetze or []:
        betrag = float(u.get("betrag") or 0)
        if betrag <= 0:                       # Abbuchungen laufen woanders
            continue
        eingang = _iso(u.get("datum", ""))
        text = u.get("text") or ""

        passend = []
        for r in offen:
            if r["nummer"] in vergeben:
                continue
            if abs(float(r["brutto"]) - betrag) > 0.02:
                continue
            tage = _tage_zwischen(str(r.get("datum") or "")[:10], eingang or "")
            if tage is None or tage < 0 or tage > ZAHLUNG_FRIST_TAGE:
                continue
            passend.append(r)

        if not passend:
            ohne.append({"datum": eingang, "betrag": round(betrag, 2), "text": text})
            continue

        # Der Name entscheidet, wenn mehrere in Frage kommen.
        mit_namen = [r for r in passend
                     if _name_passt(text, (r.get("empfaenger") or {}).get("name", ""))]
        if len(mit_namen) == 1:
            treffer, sicher = mit_namen[0], True
        elif len(passend) == 1:
            treffer, sicher = passend[0], False
        else:
            mehrdeutig.append({
                "datum": eingang, "betrag": round(betrag, 2), "text": text,
                "nummern": [r["nummer"] for r in passend],
                "hinweis": "Mehrere offene Rechnungen über diesen Betrag — "
                           "welche ist es?"})
            continue

        empf = (treffer.get("empfaenger") or {}).get("name") or "Jemand"
        vergeben.add(treffer["nummer"])
        vorschlaege.append({
            "nummer": treffer["nummer"],
            "empfaenger": empf,
            "brutto": round(float(treffer["brutto"]), 2),
            "bezahlt_am": eingang,
            "sicher": sicher,
            "text": (f"{empf} hat am {u.get('datum')} bezahlt"
                     if sicher else
                     f"Ein Eingang über {betrag:.2f} € passt zu {empf}"
                     .replace(".", ",")),
            "verwendungszweck": text[:120],
        })

    return {"vorschlaege": vorschlaege, "ohne_zuordnung": ohne,
            "mehrdeutig": mehrdeutig}
