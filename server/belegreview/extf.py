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
import calendar
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


# Excel liest ein Feld, das mit einem dieser Zeichen beginnt, als FORMEL —
# auch in Anführungszeichen. Die Stapeldatei geht ans Steuerbüro und wird
# dort in Excel geöffnet; ein Lieferantenname wie `=cmd|'/c calc'!A1` wäre
# damit ein Angriff auf den Rechner der Kanzlei, nicht bloß ein hässlicher
# Buchungstext.
FORMELZEICHEN = ("=", "+", "-", "@", "\t", "\r", "\n")


def _entschaerfen(text: str) -> str:
    """Führendes Apostroph vor alles, was Excel für eine Formel hielte.

    Das Apostroph ist Excels eigene „das ist Text"-Markierung und wird beim
    Anzeigen nicht mitgedruckt. DATEV importiert das Feld als Buchungstext,
    also mit Apostroph — ein Zeichen mehr im Text ist der Preis dafür, dass
    aus dem Text kein Befehl wird.
    """
    return "'" + text if text[:1] in FORMELZEICHEN else text


def _belegfeld1(beleg_nr: str | None) -> str | None:
    """Belegfeld 1 lässt DATEV nur wenige Zeichen zu — ein Apostroph gehört
    nicht dazu. Ein führendes Rechenzeichen fällt deshalb weg, statt
    entschärft zu werden; im Inneren stört es Excel nicht."""
    if not beleg_nr:
        return None
    sauber = re.sub(r"[^A-Za-z0-9$%&*+\-/]", "", beleg_nr).lstrip("+-*/@=")
    return sauber[:36] or None


# Vorsteuer-Schlüssel je Steuersatz. Die Corona-Sätze 5 %/16 % erkennt der
# Watcher (GUELTIGE_SAETZE) — ohne eigenen Schlüssel wären sie im Stapel als
# 19 % gebucht, und der Import zöge stillschweigend zu viel Vorsteuer.
BU_SCHLUESSEL = {0: "", 5: "7", 7: "8", 16: "5", 19: "9"}


def _bu(satz: int | None) -> str | None:
    """None heißt: unbekannter Satz — diese Zeile gehört nicht in den Stapel."""
    if satz is None:
        return "9"
    return BU_SCHLUESSEL.get(int(satz))


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
             "belegfeld1": _belegfeld1(f.get("beleg_nr")),
             # Erst entschärfen, dann kürzen: sonst sprengte das Apostroph
             # die 60 Zeichen, die DATEV im Buchungstext annimmt.
             "text": _entschaerfen(text)[:60]}

    tabelle = f.get("steuertabelle") or []
    if len(tabelle) > 1:
        # Mehrsatz-Split: der 19%+7%-Bon wird zwei Buchungen.
        zeilen = [dict(basis, umsatz=_de(z["brutto"]), bu=_bu(int(z["satz"])),
                       satz=int(z["satz"])) for z in tabelle]
    else:
        satz = f.get("ust_satz")
        zeilen = [dict(basis, umsatz=_de(f["brutto"]), bu=_bu(satz), satz=satz)]
    # Lieber eine Zeile weniger als eine mit dem falschen Steuerschlüssel:
    # was hier fehlt, fällt beim Abstimmen auf. Ein falscher Schlüssel nicht.
    brauchbar = [z for z in zeilen if z["bu"] is not None]
    for z in zeilen:
        if z["bu"] is None:
            print(f"[extf] Steuersatz {z['satz']} % unbekannt — Zeile "
                  f"'{z['text'][:40]}' bleibt aus dem Stapel", flush=True)
    return brauchbar


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
    bis = f"{jahr}{mm:02d}{calendar.monthrange(jahr, mm)[1]}"
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
