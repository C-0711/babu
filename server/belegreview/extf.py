"""EXTF-v13-Writer — DATEV-Format Buchungsstapel (Bauplan Phase 5).

Erzeugt einen importierbaren Buchungsstapel: EXTF-Kopfzeile (Format 700,
Kategorie 21 Buchungsstapel, Version 13), Spaltenzeile, eine Buchungszeile
je Steuersatz (Mehrsatz-Split: 19 % + 7 % auf einem Bon werden zwei Sätze —
der dm-Fall aus dem Testkorpus). Kodierung ist Sache des Aufrufers:
`als_bytes()` liefert CP1252 mit CRLF.

Abnahme laut Spec: fehlerfreier Import in einer echten DATEV-Instanz —
die Golden-File-Tests frieren das Format ein, der Import-Test beim
Steuerberater bleibt der letzte Schritt vor dem Produktivgang.
"""
import re
import time

BERATER = "0"        # per Env/Einstellung überschreibbar — vor Produktivgang setzen
MANDANT = "0"
SACHKONTENLAENGE = "4"
GEGENKONTO = "70099"
HERKUNFT = "BA"      # babu

SPALTEN = [
    "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs",
    "Basis-Umsatz", "WKZ Basis-Umsatz", "Konto", "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel", "Belegdatum", "Belegfeld 1", "Belegfeld 2", "Skonto",
    "Buchungstext", "Postensperre", "Diverse Adressnummer", "Geschäftspartnerbank",
    "Sachverhalt", "Zinssperre", "Beleglink",
    *(f"Beleginfo - {a} {i}" for i in range(1, 9) for a in ("Art", "Inhalt")),
    "KOST1 - Kostenstelle", "KOST2 - Kostenstelle", "Kost-Menge",
    "EU-Land u. UStID", "EU-Steuersatz", "Abw. Versteuerungsart",
    "Sachverhalt L+L", "Funktionsergänzung L+L", "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer", "BU 49 Funktionsergänzung",
    *(f"Zusatzinformation - {a} {i}" for i in range(1, 21) for a in ("Art", "Inhalt")),
    "Stück", "Gewicht", "Zahlweise", "Forderungsart", "Veranlagungsjahr",
    "Zugeordnete Fälligkeit", "Skontotyp", "Auftragsnummer", "Buchungstyp",
    "USt-Schlüssel (Anzahlungen)", "EU-Land (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen)", "EU-Steuersatz (Anzahlungen)",
    "Erlöskonto (Anzahlungen)", "Herkunft-Kz", "Leerfeld", "KOST-Datum",
    "SEPA-Mandatsreferenz", "Skontosperre", "Gesellschaftername",
    "Beteiligtennummer", "Identifikationsnummer", "Zeichnernummer",
    "Postensperre bis", "Bezeichnung SoBil-Sachverhalt",
    "Kennzeichen SoBil-Buchung", "Festschreibung", "Leistungsdatum",
    "Datum Zuord. Steuerperiode", "Fälligkeit", "Generalumkehr (GU)",
    "Steuersatz", "Land",
]


def _de(betrag: float) -> str:
    return f"{betrag:.2f}".replace(".", ",")


def _feld(wert: str | None) -> str:
    if wert is None or wert == "":
        return ""
    return '"' + str(wert).replace('"', "'") + '"'


def _belegfeld1(beleg_nr: str | None) -> str | None:
    if not beleg_nr:
        return None
    return re.sub(r"[^A-Za-z0-9$%&*+\-/]", "", beleg_nr)[:36] or None


def _bu(satz: int | None) -> str:
    return {7: "8", 0: ""}.get(satz, "9") if satz is not None else "9"


def buchungszeilen(review: dict) -> list[dict]:
    """Ein Review → 1..n Buchungssätze (je Steuersatz einer)."""
    f = review.get("felder") or {}
    e = review.get("einschaetzung") or {}
    v = review.get("vlm") or {}
    konto = e.get("konto_skr04")
    if not konto or f.get("brutto") is None:
        return []
    datum = f.get("datum") or ""
    teile = datum.split(".")
    belegdatum = f"{int(teile[0]):02d}{int(teile[1]):02d}" if len(teile) == 3 else None
    text = (v.get("buchungstext") or "").strip()
    if not text:
        einordnung = ((review.get("semantik") or {}).get("belegart") or "").strip()
        lieferant = (v.get("lieferant") or f.get("lieferant") or "").strip()
        kurz = f"{int(teile[0]):02d}.{int(teile[1]):02d}." if len(teile) == 3 else ""
        text = " ".join(x for x in (einordnung, kurz, lieferant) if x)
    basis = {"konto": konto, "gegenkonto": GEGENKONTO, "belegdatum": belegdatum,
             "belegfeld1": _belegfeld1(f.get("beleg_nr")), "text": text[:60]}

    tabelle = f.get("steuertabelle") or []
    if len(tabelle) > 1:
        # Mehrsatz-Split: der 19%+7%-Bon wird zwei Buchungen.
        return [dict(basis, umsatz=_de(z["brutto"]), bu=_bu(int(z["satz"])),
                     satz=int(z["satz"])) for z in tabelle]
    satz = f.get("ust_satz")
    return [dict(basis, umsatz=_de(f["brutto"]), bu=_bu(satz), satz=satz)]


def _zeile(b: dict) -> str:
    felder = [""] * len(SPALTEN)
    felder[0] = b["umsatz"]
    felder[1] = "S"
    felder[2] = "EUR"
    felder[6] = b["konto"]
    felder[7] = b["gegenkonto"]
    felder[8] = b["bu"]
    felder[9] = b["belegdatum"] or ""
    felder[10] = _feld(b["belegfeld1"])
    felder[13] = _feld(b["text"])
    return ";".join(felder)


def stapel(reviews: list[dict], monat: str, erzeugt: time.struct_time | None = None,
           berater: str = BERATER, mandant: str = MANDANT,
           festschreibung: bool = True) -> str:
    """Kompletter Stapel als Text (Zeilen mit CRLF verbinden macht als_bytes)."""
    erzeugt = erzeugt or time.localtime()
    jahr, mm = int(monat[:4]), int(monat[5:7])
    von = f"{jahr}{mm:02d}01"
    letzter = {1: 31, 2: 29 if jahr % 4 == 0 else 28, 3: 31, 4: 30, 5: 31, 6: 30,
               7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[mm]
    bis = f"{jahr}{mm:02d}{letzter}"
    stempel = time.strftime("%Y%m%d%H%M%S", erzeugt) + "000"
    kopf = [
        '"EXTF"', "700", "21", '"Buchungsstapel"', "13", stempel, "",
        f'"{HERKUNFT}"', '"babu"', "", berater, mandant, f"{jahr}0101",
        SACHKONTENLAENGE, von, bis, f'"babu {monat}"', '""', "1", "0",
        "1" if festschreibung else "0", '"EUR"',
        "", "", "", "", "", "", "", "", "",
    ]
    zeilen = [";".join(kopf), ";".join(SPALTEN)]
    for review in reviews:
        zeilen += [_zeile(b) for b in buchungszeilen(review)]
    return "\r\n".join(zeilen) + "\r\n"


def als_bytes(text: str) -> bytes:
    return text.encode("cp1252", errors="replace")
