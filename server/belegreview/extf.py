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
from dataclasses import dataclass, field

import skr04_automatik

import kontierung as kt

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


def buchungstext(review: dict) -> str:
    """Der rohe Buchungstext eines Belegs — eine Quelle für alle Wege.

    Wortgleich stand diese Bildung zweimal im Haus: hier in
    `buchungszeilen` (die Wahrheit für die Stapeldatei) und in
    `babu_web.datev_buchungssatz` (die Anzeige im Portal). Zwei Kopien
    derselben Regel driften auseinander, sobald jemand nur eine anfasst —
    und dann zeigt das Portal einen anderen Text, als in der Datei steht.

    Roh heißt: ohne Entschärfung und ohne die 60-Zeichen-Grenze. Beides
    gehört an die Stelle, die den Text in die Datei schreibt, nicht an
    seine Bildung.
    """
    v = review.get("vlm") or {}
    f = review.get("felder") or {}
    text = (v.get("buchungstext") or "").strip()
    if text:
        return text
    einordnung = ((review.get("semantik") or {}).get("belegart") or "").strip()
    lieferant = (v.get("lieferant") or f.get("lieferant") or "").strip()
    teile = _datum_teile(f.get("datum") or "")
    kurz = f"{teile[0]:02d}.{teile[1]:02d}." if teile else ""
    return " ".join(x for x in (einordnung, kurz, lieferant) if x)


def _de(betrag: float) -> str:
    return f"{betrag:.2f}".replace(".", ",")


def _datum_teile(datum: str | None) -> tuple[int, int, int] | None:
    """(Tag, Monat, Jahr) aus einem Belegdatum — zwei Formate im Haus:
    `TT.MM.JJJJ` (Altweg, vor dem Zielbild) und `JJJJ-MM-TT` (Zielbild-Weg,
    Gemma schreibt seit 27.08.2026 ISO, siehe `_review_aus_einschaetzung`
    in babu_web.py). Tolerant gegen Leerraum um die Teile. Unlesbares
    liefert None statt eine Exception — der Beleg bleibt dann ohne
    Belegdatum im Stapel, statt den ganzen Lauf abzubrechen."""
    text = str(datum or "").strip()
    for trenner, ordnung in ((".", (0, 1, 2)), ("-", (2, 1, 0))):
        teile = [t.strip() for t in text.split(trenner)]
        if len(teile) != 3 or not all(teile):
            continue
        try:
            tag, monat, jahr = (int(teile[i]) for i in ordnung)
        except ValueError:
            continue
        return tag, monat, jahr
    return None


def _ttmm(datum: str | None) -> str | None:
    """Belegdatum fürs EXTF-Feld (`TTMM`), formatunabhängig — siehe
    `_datum_teile`. None, wenn sich das Datum nicht lesen lässt."""
    teile = _datum_teile(datum)
    return f"{teile[0]:02d}{teile[1]:02d}" if teile else None


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

# ── Automatikkonten ──────────────────────────────────────────────────────────
#
# Im SKR04 rechnen die mit AV/AM gekennzeichneten Konten ihre Steuer selbst
# (skr04_automatik, aus dem Kontenrahmen gelesen). Ein Steuerschlüssel
# obendrauf ist ein Widerspruch, den erst der Import bei der Kanzlei
# meldet. Also: auf ein Automatikkonto kommt kein Schlüssel — und trägt die
# Zeile einen ANDEREN Satz als das Konto, gehört sie auf das Geschwister-
# konto mit diesem Satz (5300 Wareneingang 7 % neben 5400 mit 19 %,
# 4300 Erlöse 7 % neben 4400). Beide Paare stehen so im SKR04.
GESCHWISTER = {("5400", 7): "5300", ("5300", 19): "5400",
               ("4400", 7): "4300", ("4300", 19): "4400"}

# Die Erlösseite. Kasse und Geldtransit sind Finanzkonten (F) des SKR04,
# die Erlöskonten Automatikkonten — die Steuer kommt vom Konto.
KASSE = "1600"
GELDTRANSIT = "1460"
ERLOESKONTO = {19: "4400", 7: "4300"}
ERLOES_STEUERFREI = "4100"          # Steuerfreie Umsätze § 4 Nr. 8 ff. UStG
ERLOES_KLEINUNTERNEHMER = "4184"    # Steuerfreie Erlöse Kleinunternehmer § 19


def _bu(satz: int | None) -> str | None:
    """None heißt: unbekannter Satz — diese Zeile gehört nicht in den Stapel."""
    if satz is None:
        return "9"
    return BU_SCHLUESSEL.get(int(satz))


def _konto_und_rahmen(review: dict) -> tuple[str | None, str]:
    """Welches Konto der Beleg trägt — und aus welchem Rahmen es stammt.

    `konto`/`kontenrahmen` schreibt der Watcher seit BABU-57. Reviews von
    davor haben nur `konto_skr04`; die stammen aus einer Zeit, in der babu
    ausschließlich SKR04 kannte, also gelten sie als SKR04. Das ist keine
    Vermutung, sondern Aktenlage.
    """
    e = review.get("einschaetzung") or {}
    konto = e.get("konto") or e.get("konto_skr04")
    rahmen = e.get("kontenrahmen") or "SKR04"
    return (str(konto) if konto else None), rahmen


def buchungszeilen(review: dict) -> list[dict]:
    """Ein Review → 1..n Buchungssätze (je Steuersatz einer)."""
    f = review.get("felder") or {}
    e = review.get("einschaetzung") or {}
    v = review.get("vlm") or {}
    konto, rahmen = _konto_und_rahmen(review)
    if not konto or f.get("brutto") is None:
        return []
    datum = f.get("datum") or ""
    teile = _datum_teile(datum)
    belegdatum = _ttmm(datum)
    text = (v.get("buchungstext") or "").strip()
    if not text:
        einordnung = ((review.get("semantik") or {}).get("belegart") or "").strip()
        lieferant = (v.get("lieferant") or f.get("lieferant") or "").strip()
        kurz = f"{teile[0]:02d}.{teile[1]:02d}." if teile else ""
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
    zeilen = [_automatik_anpassen(z, rahmen) for z in zeilen]
    # Lieber eine Zeile weniger als eine mit dem falschen Steuerschlüssel:
    # was hier fehlt, fällt beim Abstimmen auf. Ein falscher Schlüssel nicht.
    brauchbar = [z for z in zeilen if z["bu"] is not None]
    for z in zeilen:
        if z["bu"] is None:
            print(f"[extf] Steuersatz {z['satz']} % unbekannt — Zeile "
                  f"'{z['text'][:40]}' bleibt aus dem Stapel", flush=True)
    return brauchbar


def _automatik_anpassen(z: dict, rahmen: str) -> dict:
    """Automatikkonto → kein Schlüssel; fremder Satz → Geschwisterkonto."""
    if rahmen != "SKR04" or z["bu"] is None:
        return z
    a = skr04_automatik.automatik(z["konto"])
    if not a:
        return z
    satz = 19 if z.get("satz") is None else int(z["satz"])   # wie _bu(None)
    if (a[1] or 0) == satz:
        return dict(z, bu="")
    ziel = GESCHWISTER.get((z["konto"], satz))
    if ziel:
        return dict(z, konto=ziel, bu="")
    print(f"[extf] Konto {z['konto']} rechnet {a[1]} % selbst, die Zeile "
          f"'{z['text'][:40]}' trägt {satz} % — Schlüssel bleibt, der Import "
          f"wird das melden", flush=True)
    return z


def erloeszeilen(kassenblaetter: list[dict], kleinunternehmerin: bool = False
                 ) -> list[dict]:
    """Die Erlösseite: jedes Kassenblatt wird zu Tageseinnahmen.

    Bis 02.09.2026 enthielt der Stapel nur die Belege — für die Kanzlei
    die halbe Buchhaltung. Jetzt je Kassentag: Kasse an Erlöse, getrennt
    nach Steuersatz (19 % ist, was nicht 7 % oder steuerfrei war, plus
    verkaufte Gutscheine — dieselbe Rechnung wie monatsabschluss.
    erloese_monat), und der Kartenumsatz geht per Geldtransit wieder aus
    der Kasse: die Bank bekommt ihn erst mit dem Kontoauszug.

    Das Kassenblatt trennt Bar und Karte NICHT nach Steuersatz — deshalb
    läuft alles über die Kasse statt Karte direkt an Erlöse; das wäre
    eine Aufteilung, die niemand erfasst hat.

    Für die Kleinunternehmerin (§ 19 UStG) gibt es keinen Steuerausweis:
    alles auf 4184, sonst rechnete DATEV aus 4400 Umsatzsteuer heraus.
    """
    aus: list[dict] = []
    for b in sorted(kassenblaetter, key=lambda x: x.get("datum") or ""):
        datum = str(b.get("datum") or "")
        if len(datum) != 10:
            continue
        belegdatum = datum[8:10] + datum[5:7]
        bar = float(b.get("einnahmenBar") or 0)
        ec = float(b.get("ecZahlungen") or 0)
        frei = float(b.get("umsatzFrei") or 0)
        sieben = float(b.get("umsatz7") or 0)
        gutschein = float(b.get("gutscheinVerkauf") or 0)
        neunzehn = max(0.0, bar + ec - frei - sieben) + gutschein
        if kleinunternehmerin:
            frei, neunzehn, sieben = frei + neunzehn + sieben, 0.0, 0.0
        frei_konto = ERLOES_KLEINUNTERNEHMER if kleinunternehmerin else ERLOES_STEUERFREI
        basis = {"belegdatum": belegdatum,
                 "belegfeld1": _belegfeld1("KB" + datum.replace("-", "")),
                 "bu": "", "satz": None}
        for betrag, konto, text in (
                (neunzehn, ERLOESKONTO[19], "Tageseinnahmen 19 %"),
                (sieben, ERLOESKONTO[7], "Tageseinnahmen 7 %"),
                (frei, frei_konto, "Tageseinnahmen steuerfrei")):
            if round(betrag, 2) > 0:
                aus.append(dict(basis, konto=KASSE, gegenkonto=konto,
                                umsatz=_de(betrag), text=text))
        if round(ec, 2) > 0:
            aus.append(dict(basis, konto=GELDTRANSIT, gegenkonto=KASSE,
                            umsatz=_de(ec), text="Kartenumsatz an Geldtransit"))
    return aus


# ── Der Mischungs-Melder ─────────────────────────────────────────────────────
#
# BABU-57. Der Buchungsstapel ist die Stelle, an der babus Konten das Haus
# verlassen. Was hier durchrutscht, fällt beim Steuerberater auf — nach dem
# Import, und dann ist es Handarbeit. Also wird hier geprüft, und zwar an der
# einzigen Stelle, an der sich alle Konten eines Monats gleichzeitig ansehen
# lassen.
#
# Drei Fälle, drei verschiedene Antworten:
#
#   1. Das Konto gehört zum eingestellten Rahmen  → in Ordnung.
#   2. Das Konto gehört nachweislich zum ANDEREN  → Vermischung, Abbruch.
#   3. babu kennt das Konto überhaupt nicht       → durchlassen, vermerken.
#
# Fall 3 ist Absicht. `kontierung.gehoert_zum_rahmen()` ist bewusst
# konservativ und kennt nur die Konten, die babu selbst vergibt. Eine
# handkorrigierte Kontierung (8400 Erlöse, ein Konto aus der Kanzlei) wäre
# damit „fremd" — sie deshalb aus dem Stapel zu werfen hieße, fremde und
# vermutlich richtige Arbeit stillschweigend wegzuwerfen. Der Melder sucht
# Vermischung, er überstimmt keine Kontierung.


class RahmenVermischung(Exception):
    """SKR03 und SKR04 in einem Stapel. Kein Import, sondern ein Fehler."""


@dataclass
class Befund:
    """Was die Rahmenprüfung über einen Stapel sagt."""
    rahmen: str
    vermischt: list[str] = field(default_factory=list)   # Konten aus dem anderen Rahmen
    unbekannt: list[str] = field(default_factory=list)   # von babu nie vergeben
    belege: list[str] = field(default_factory=list)      # wo die Vermischung steckt

    @property
    def sauber(self) -> bool:
        return not self.vermischt

    def meldung(self) -> str:
        """Ein Satz, den Nina versteht, und die Belege dazu."""
        return (f"Dieser Stapel ist auf {self.rahmen} eingestellt, enthält aber "
                f"Konten aus dem anderen Kontenrahmen: "
                f"{', '.join(self.vermischt)}. Betroffen: "
                f"{', '.join(self.belege)}. Zwei Kontenrahmen in einem Stapel "
                f"kann die Kanzlei nicht importieren.")


def _stamm(review: dict) -> str:
    datei = str(review.get("datei") or "")
    return datei.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "(unbenannter Beleg)"


def rahmen_pruefen(reviews: list[dict], rahmen: str) -> Befund:
    """Stammen alle Konten dieses Stapels aus `rahmen`?"""
    anderer = next(r for r in kt.RAHMEN if r != rahmen)
    befund = Befund(rahmen=rahmen)
    for review in reviews:
        konto, beleg_rahmen = _konto_und_rahmen(review)
        if not konto:
            continue
        # Der Beleg sagt selbst, in welchem Rahmen er kontiert wurde. Das ist
        # das verlässlichere Zeugnis als die Nummer: es gilt auch für Konten,
        # die babu nicht selbst vergeben hat.
        widerspruch = beleg_rahmen != rahmen
        if kt.gehoert_zum_rahmen(konto, rahmen) and not widerspruch:
            continue
        if widerspruch or kt.gehoert_zum_rahmen(konto, anderer):
            if konto not in befund.vermischt:
                befund.vermischt.append(konto)
            befund.belege.append(_stamm(review))
        elif konto not in befund.unbekannt:
            befund.unbekannt.append(konto)
    return befund


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
           festschreibung: bool = True, rahmen: str | None = None,
           kassenblaetter: list[dict] | None = None,
           kleinunternehmerin: bool = False) -> str:
    """Kompletter Stapel als Text (Zeilen mit CRLF verbinden macht als_bytes).

    Mit `rahmen` läuft der Mischungs-Melder mit: ein Konto aus dem anderen
    Kontenrahmen bricht den Export ab, statt ihn zu erzeugen. Ohne `rahmen`
    bleibt alles wie vorher — der Melder ist eine Zutat, kein Umbau.

    `kassenblaetter` bringt die Erlösseite mit (erloeszeilen) — nur für
    SKR04: die SKR03-Konten der Erlösseite liegen babu nicht als Quelle
    vor, und geraten wird nicht.
    """
    if rahmen:
        befund = rahmen_pruefen(reviews, rahmen)
        if not befund.sauber:
            raise RahmenVermischung(befund.meldung())
        for konto in befund.unbekannt:
            print(f"[extf] Konto {konto} hat babu nicht selbst vergeben — "
                  f"gegen {rahmen} nicht prüfbar, geht unverändert mit",
                  flush=True)
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
    if kassenblaetter:
        if rahmen == "SKR03":
            print(f"[extf] {len(kassenblaetter)} Kassenblätter bleiben aus dem "
                  f"SKR03-Stapel — Erlöskonten nur für SKR04 hinterlegt",
                  flush=True)
        else:
            zeilen += [_zeile(b) for b in erloeszeilen(kassenblaetter,
                                                       kleinunternehmerin)]
    return "\r\n".join(zeilen) + "\r\n"


def als_bytes(text: str) -> bytes:
    return text.encode("cp1252", errors="replace")
