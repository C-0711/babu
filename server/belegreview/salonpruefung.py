#!/usr/bin/env python3
"""Salonprüfung — aus einem Stapel Unterlagen wird ein eingerichteter Salon.

Wer mit babu anfängt, hat einen Ordner. Darin liegt alles: der letzte
Steuerbescheid, die Gewinnrechnung, der Mietvertrag, ein Jahr Kontoauszüge,
die Rechnungen vom Steuerberater. Bisher musste er das einzeln einsortieren
und die Stammdaten von Hand abtippen.

Dieses Modul dreht das um. Aus den gelesenen Unterlagen wird geerntet, was
babu ohnehin wissen muss — Steuernummer, Finanzamt, Rechtsform, Anschrift
für den Briefkopf, Umsatzsteuerpflicht, Abschlussart —, jedes Feld mit der
Quelle, aus der es stammt, und einer Sicherheit. Was leer ist, wird gesetzt;
was belegt ist, wird nie überschrieben, sondern vorgeschlagen. Dieselbe
Regel wie überall in babu: vorschlagen, nachrechnen, im Zweifel fragen.

Und ein Teil, den sonst niemand macht: **die Rechnungen des Steuerberaters
werden nachgerechnet.** Die Steuerberatervergütungsverordnung ist eine
Verordnung, keine Preisliste — sie gibt Rahmen vor, und wo eine Rechnung
darüber hinausgeht oder Pauschalen doppelt ansetzt, kann man das sehen.
Nicht um jemandem etwas zu unterstellen: eine Rechnung, die man versteht,
kann man bezahlen; eine, die man nicht versteht, bezahlt man auch.

Reines Rechnen, kein Netz, keine Dateien.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


# ── Was geerntet wird ────────────────────────────────────────────────────────

@dataclass
class Feld:
    """Ein Stammdatum samt Herkunft — die Einheit der Vorbelegung."""
    schluessel: str
    wert: object
    quelle: str                 # Dateiname, aus dem es stammt
    regel: str                  # warum babu das glaubt
    sicher: bool = True
    bereich: str = "einstellungen"   # wo im Portal es landet


@dataclass
class Befund:
    """Etwas, das an einer Rechnung auffällt."""
    schwere: str                # "hinweis" | "nachfragen" | "falsch"
    titel: str
    text: str
    betrag: float | None = None

    def __post_init__(self) -> None:
        if self.schwere not in ("hinweis", "nachfragen", "falsch"):
            raise ValueError(f"unbekannte Schwere: {self.schwere}")


@dataclass
class Pruefergebnis:
    felder: list[Feld] = field(default_factory=list)
    befunde: list[Befund] = field(default_factory=list)
    offen: list[str] = field(default_factory=list)


def _flach(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# ── Wohin ein Feld im Portal gehört ──────────────────────────────────────────
#
# Die Salonprüfung darf nicht nur die vier Felder füllen, die der
# Abschluss-Job bisher kannte. Alles, was auf den Unterlagen ohnehin steht
# und im Portal ein Eingabefeld hat, gehört hierher — sonst tippt es die
# Nutzerin doch wieder ab.

BEREICH = {
    # Einstellungen → Stammdaten
    "rechtsform": "einstellungen",
    "steuernummer": "einstellungen",
    "ust_idnr": "einstellungen",
    "finanzamt": "einstellungen",
    "kleinunternehmer": "einstellungen",
    "abschluss_art": "einstellungen",
    "versteuerung": "einstellungen",
    "wirtschaftsjahr": "einstellungen",
    # Briefkopf → was auf Rechnungen der Kundin steht
    "firma": "briefkopf",
    "inhaberin": "briefkopf",
    "strasse": "briefkopf",
    "plz": "briefkopf",
    "ort": "briefkopf",
    "telefon": "briefkopf",
    "email": "briefkopf",
    "iban": "briefkopf",
    "bic": "briefkopf",
    "bank": "briefkopf",
    # Berater → wer die Zahlen macht
    "steuerberater": "berater",
    "steuerberater_nr": "berater",
}

# Welche Unterlage bei einem Feld das letzte Wort hat. Ein Bescheid vom
# Finanzamt schlägt eine Gewinnrechnung, und die schlägt einen Briefbogen.
VORRANG = ("bescheid", "euer", "bwa", "susa", "anlagen", "vertrag",
           "kontoauszug", "rechnung", "sonstiges")


def _rang(art: str) -> int:
    try:
        return VORRANG.index(art)
    except ValueError:
        return len(VORRANG)


# ── Ernte: aus gelesenen Unterlagen werden Stammdaten ────────────────────────

# Steuernummern gibt es in Landesformaten: 93815/12345 (Baden-Württemberg),
# 181/815/08155 (Bayern), 133/8150/8159 (Nordrhein-Westfalen). Ein einziges
# Muster für alle wäre zu weit — deshalb großzügig suchen und danach über
# die Ziffernzahl (10 bis 13) prüfen.
STEUERNUMMER = re.compile(r"(?<![\d/])(\d{2,5}\s?/\s?\d{3,5}(?:\s?/\s?\d{4,5})?)(?![\d/])")
UST_IDNR = re.compile(r"\bDE\s?(\d{9})\b")
IBAN_DE = re.compile(r"\bDE\s?(?:\d[ ]?){20}\b")
BIC = re.compile(r"\b[A-Z]{4}DE[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")
# Auf derselben Zeile, und nicht hinter einem Schrägstrich: sonst liest sich
# die zweite Hälfte einer Steuernummer als Postleitzahl und der Name in der
# Zeile darunter als Ort.
PLZ_ORT = re.compile(r"(?<![\d/])(\d{5})[ \t]+([A-ZÄÖÜ][\wäöüß.\- ]{2,40})")
FINANZAMT = re.compile(r"Finanzamt\s+([A-ZÄÖÜ][\wäöüß.\- ]{2,40})")
TELEFON = re.compile(r"(?:Tel(?:efon)?\.?|Fon)[:\s]+([+\d][\d\s/()\-]{6,22})", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,10}\b")
RECHTSFORMEN = ("GmbH & Co. KG", "GmbH", "UG (haftungsbeschränkt)", "UG",
                "e.K.", "e.Kfr.", "OHG", "GbR", "AG", "KG")


def _erst(muster: re.Pattern, text: str, gruppe: int = 0) -> str | None:
    m = muster.search(text)
    return m.group(gruppe).strip() if m else None


def felder_aus_text(text: str, *, quelle: str, art: str = "sonstiges"
                    ) -> list[Feld]:
    """Was sich aus dem Klartext einer Unterlage sicher ablesen lässt.

    Bewusst über Muster, nicht über ein Sprachmodell: eine Steuernummer ist
    eine Steuernummer, und wenn babu sie falsch setzt, steht sie danach in
    jeder Rechnung. Was nicht eindeutig ist, wird gar nicht geerntet.
    """
    raus: list[Feld] = []

    def nimm(schluessel: str, wert, regel: str, sicher: bool = True) -> None:
        if wert in (None, ""):
            return
        raus.append(Feld(schluessel=schluessel, wert=wert, quelle=quelle,
                         regel=regel, sicher=sicher,
                         bereich=BEREICH.get(schluessel, "einstellungen")))

    for m in STEUERNUMMER.finditer(text):
        roh = re.sub(r"\s+", "", m.group(1))
        if 10 <= len(re.sub(r"\D", "", roh)) <= 13:
            nimm("steuernummer", roh, "Steuernummer im Text gefunden")
            break
    ust = _erst(UST_IDNR, text, 1)
    nimm("ust_idnr", f"DE{ust}" if ust else None,
         "Umsatzsteuer-Identifikationsnummer im Text gefunden")
    nimm("finanzamt", _erst(FINANZAMT, text, 1), "Zeile nennt das Finanzamt")

    iban = _erst(IBAN_DE, text)
    nimm("iban", re.sub(r"\s+", "", iban) if iban else None,
         "IBAN im Text gefunden")
    nimm("bic", _erst(BIC, text), "BIC im Text gefunden")

    m = PLZ_ORT.search(text)
    if m:
        nimm("plz", m.group(1), "Postleitzahl mit Ort gefunden")
        nimm("ort", m.group(2).strip(" .,"), "Ort hinter der Postleitzahl")

    tel = _erst(TELEFON, text, 1)
    nimm("telefon", re.sub(r"\s{2,}", " ", tel).strip() if tel else None,
         "Zeile nennt eine Telefonnummer")
    nimm("email", _erst(EMAIL, text), "E-Mail-Adresse im Text gefunden")

    for rf in RECHTSFORMEN:                       # längste zuerst, s. Liste
        if re.search(rf"\b{re.escape(rf)}", text):
            nimm("rechtsform", rf, f"„{rf}“ steht auf der Unterlage")
            break

    flach = _flach(text)
    if "kleinunternehmer" in flach or "§ 19" in text or "\u00a7 19 ustg" in flach:
        nimm("kleinunternehmer", True,
             "Die Unterlage nennt die Kleinunternehmerregelung")
    if "einnahmen" in flach and "uberschuss" in flach:
        nimm("abschluss_art", "EÜR", "Die Unterlage ist eine Einnahmen-"
             "Überschuss-Rechnung")
    elif "bilanz" in flach and "gewinn- und verlust" in flach:
        nimm("abschluss_art", "Bilanz", "Die Unterlage enthält eine Bilanz")
    if "ist-versteuerung" in flach or "istversteuerung" in flach:
        nimm("versteuerung", "ist", "Die Unterlage nennt die Ist-Versteuerung")
    elif "soll-versteuerung" in flach or "sollversteuerung" in flach:
        nimm("versteuerung", "soll", "Die Unterlage nennt die Soll-Versteuerung")

    for f in raus:
        f.regel += f" ({art})" if art != "sonstiges" else ""
    return raus


def felder_ernten(dokumente: list[dict]) -> list[Feld]:
    """Aus allen Unterlagen einen widerspruchsfreien Satz Stammdaten machen.

    `dokumente` sind Einträge mit mindestens `datei`, `art` und `text`.
    Sagen zwei Unterlagen dasselbe Feld verschieden, gewinnt die
    verlässlichere Art — und die unterlegene bleibt als Hinweis stehen,
    damit der Widerspruch nicht verschwindet.
    """
    kandidaten: dict[str, list[tuple[int, Feld]]] = {}
    for d in dokumente:
        art = d.get("art") or "sonstiges"
        for f in felder_aus_text(d.get("text") or "", quelle=d.get("datei") or "?",
                                 art=art):
            kandidaten.setdefault(f.schluessel, []).append((_rang(art), f))

    raus: list[Feld] = []
    for schluessel, liste in kandidaten.items():
        liste.sort(key=lambda p: p[0])
        beste = liste[0][1]
        andere = {str(f.wert) for _, f in liste[1:] if str(f.wert) != str(beste.wert)}
        if andere:
            beste.sicher = False
            beste.regel += (" — andere Unterlagen sagen "
                            + ", ".join(f"„{a}“" for a in sorted(andere)[:3]))
        raus.append(beste)
    raus.sort(key=lambda f: (f.bereich, f.schluessel))
    return raus


# ── Die Rechnung des Steuerberaters nachrechnen ──────────────────────────────
#
# Grundlage ist die Steuerberatervergütungsverordnung (StBVV). Sie ist eine
# Verordnung mit Rahmen, keine Preisliste: für jede Leistung gibt es einen
# Zehntel-Rahmen auf einen Gegenstandswert. Was hier geprüft wird, ist
# deshalb nicht „zu teuer", sondern „außerhalb des Rahmens" oder „doppelt".
#
# Die Gebührentabellen A–D selbst stehen NICHT hier — sie sind lang und
# ändern sich. Geprüft wird alles, was ohne Tabelle geht: die
# Zehntel-Rahmen, die Auslagenpauschale, die Umsatzsteuer, Doppelansätze
# und die Pflichtangaben. Wo die Tabelle nötig wäre, sagt babu das, statt
# eine Zahl zu erfinden.

ZEHNTEL_RAHMEN: dict[str, tuple[str, float, float, str]] = {
    # Paragraf: (Was, von, bis, Tabelle)
    "24": ("Steuererklärungen", 1 / 10, 6 / 10, "A"),
    "25": ("Einnahmen-Überschuss-Rechnung", 5 / 10, 20 / 10, "B"),
    "33": ("Buchführung", 2 / 10, 12 / 10, "C"),
    "34": ("Lohnbuchführung", 0, 0, "—"),
    "35": ("Jahresabschluss", 10 / 10, 40 / 10, "B"),
}

# § 16 StBVV: Entgelte für Post und Telekommunikation pauschal 20 % der
# Gebühren, höchstens 20 € in derselben Angelegenheit.
AUSLAGEN_ANTEIL = 0.20
AUSLAGEN_HOECHST = 20.0

PFLICHT_14_USTG = (
    ("rechnungsnummer", "eine fortlaufende Rechnungsnummer"),
    ("steuernummer", "die Steuernummer oder USt-IdNr. des Beraters"),
    ("datum", "das Rechnungsdatum"),
    ("zeitraum", "den Leistungszeitraum"),
)


@dataclass
class Position:
    """Eine Zeile auf der Rechnung des Beraters."""
    text: str
    betrag: float
    paragraf: str | None = None      # „33", „35", …
    zehntel: float | None = None     # 6/10 → 0.6
    gegenstandswert: float | None = None


def _zehntel_lesen(text: str) -> float | None:
    m = re.search(r"(\d{1,2})\s*/\s*10\b", text)
    return int(m.group(1)) / 10 if m else None


def _paragraf_lesen(text: str) -> str | None:
    m = re.search(r"§\s*(\d{1,2})", text)
    return m.group(1) if m else None


def position_aus_text(text: str, betrag: float) -> Position:
    """Eine Rechnungszeile deuten: welcher Paragraf, welcher Zehntelsatz."""
    return Position(text=text, betrag=betrag,
                    paragraf=_paragraf_lesen(text),
                    zehntel=_zehntel_lesen(text))


def steuerberater_pruefen(*, positionen: list[Position],
                          auslagen: float | None = None,
                          netto: float | None = None,
                          ust: float | None = None,
                          brutto: float | None = None,
                          angaben: dict | None = None,
                          pauschale: bool = False) -> list[Befund]:
    """Die Rechnung des Beraters nachrechnen — Befunde, keine Vorwürfe."""
    befunde: list[Befund] = []
    angaben = angaben or {}

    # ── Pflichtangaben nach § 14 UStG ──
    fehlend = [wort for schluessel, wort in PFLICHT_14_USTG
               if not angaben.get(schluessel)]
    if fehlend:
        befunde.append(Befund(
            "nachfragen", "Angaben fehlen auf der Rechnung",
            "Es fehlt " + ", ".join(fehlend) + ". Ohne diese Angaben ist die "
            "Rechnung nach § 14 UStG unvollständig, und die Vorsteuer daraus "
            "kann das Finanzamt streichen."))

    # ── Der Zehntel-Rahmen der StBVV ──
    for p in positionen:
        if not p.paragraf or p.zehntel is None:
            continue
        rahmen = ZEHNTEL_RAHMEN.get(p.paragraf)
        if not rahmen or rahmen[1] == rahmen[2] == 0:
            continue
        was, von, bis, tabelle = rahmen
        if p.zehntel > bis + 1e-9:
            befunde.append(Befund(
                "falsch", f"Über dem Rahmen: {was}",
                f"Angesetzt sind {p.zehntel * 10:.0f}/10. § {p.paragraf} StBVV "
                f"lässt für {was.lower()} {von * 10:.0f}/10 bis {bis * 10:.0f}/10 "
                f"zu (Tabelle {tabelle}). Das ist zu viel — bitte nachfragen.",
                betrag=p.betrag))
        elif p.zehntel < von - 1e-9:
            befunde.append(Befund(
                "hinweis", f"Unter dem Rahmen: {was}",
                f"Angesetzt sind {p.zehntel * 10:.0f}/10, der Rahmen beginnt bei "
                f"{von * 10:.0f}/10. Das ist zu deinen Gunsten — nur zur Kenntnis.",
                betrag=p.betrag))
        elif p.zehntel >= bis - 1e-9:
            befunde.append(Befund(
                "nachfragen", f"Am oberen Rand: {was}",
                f"Angesetzt ist der Höchstsatz {p.zehntel * 10:.0f}/10 von "
                f"{bis * 10:.0f}/10. Der ist zulässig, aber er will begründet "
                "sein — üblich ist die Mitte. Frag, was den Fall aufwendig "
                "gemacht hat.", betrag=p.betrag))

    # ── Dieselbe Leistung zweimal ──
    gesehen: dict[str, Position] = {}
    for p in positionen:
        schluessel = _flach(re.sub(r"[\d,./§\s-]+", " ", p.text)).strip()
        if len(schluessel) < 6:
            continue
        if schluessel in gesehen:
            befunde.append(Befund(
                "nachfragen", "Zweimal dasselbe?",
                f"„{p.text}“ steht zweimal auf der Rechnung "
                f"({gesehen[schluessel].betrag:.2f} € und {p.betrag:.2f} €). "
                "Wenn das zwei verschiedene Zeiträume sind, ist es richtig — "
                "dann sollte es dranstehen.", betrag=p.betrag))
        else:
            gesehen[schluessel] = p

    # ── Auslagenpauschale nach § 16 StBVV ──
    gebuehren = sum(p.betrag for p in positionen)
    if auslagen is not None and auslagen > 0 and gebuehren > 0:
        grenze = min(gebuehren * AUSLAGEN_ANTEIL, AUSLAGEN_HOECHST)
        if auslagen > grenze + 0.005:
            befunde.append(Befund(
                "falsch", "Auslagenpauschale zu hoch",
                f"Angesetzt sind {auslagen:.2f} €. § 16 StBVV erlaubt für Post "
                f"und Telekommunikation 20 % der Gebühren, höchstens 20 € je "
                f"Angelegenheit — hier also {grenze:.2f} €.",
                betrag=round(auslagen - grenze, 2)))

    # ── Pauschale und Einzelabrechnung nebeneinander ──
    if pauschale and any(p.zehntel is not None for p in positionen):
        befunde.append(Befund(
            "nachfragen", "Pauschale und Einzelgebühren zugleich",
            "Auf der Rechnung stehen eine Pauschalvergütung und daneben "
            "einzeln berechnete Gebühren. Eine Pauschale nach § 14 StBVV "
            "muss schriftlich vereinbart sein und deckt die vereinbarten "
            "Leistungen ab — was sie abdeckt, darf nicht noch einmal "
            "einzeln kommen. Frag, was in der Pauschale drin ist."))

    # ── Rechnet die Rechnung? ──
    if netto is not None and ust is not None and brutto is not None:
        if abs(netto + ust - brutto) > 0.011:
            befunde.append(Befund(
                "falsch", "Die Rechnung geht nicht auf",
                f"{netto:.2f} € + {ust:.2f} € ergibt {netto + ust:.2f} €, "
                f"ausgewiesen sind {brutto:.2f} €.",
                betrag=round(abs(netto + ust - brutto), 2)))
        elif netto > 0:
            satz = round(ust / netto * 100, 1)
            if abs(satz - 19) > 0.6:
                befunde.append(Befund(
                    "nachfragen", "Ungewöhnlicher Steuersatz",
                    f"Aus Netto und Steuer ergeben sich {satz:.1f} %. Auf "
                    "Beratungsleistungen liegen 19 %.",))

    if netto is not None and positionen:
        summe = gebuehren + (auslagen or 0)
        if abs(summe - netto) > 0.011:
            befunde.append(Befund(
                "nachfragen", "Die Posten ergeben nicht die Summe",
                f"Die einzelnen Posten ergeben {summe:.2f} €, als Netto "
                f"ausgewiesen sind {netto:.2f} €. Ein Posten fehlt in der "
                "Aufstellung oder ist doppelt gezählt.",
                betrag=round(abs(summe - netto), 2)))

    # ── Was ohne Tabelle nicht prüfbar ist, wird gesagt statt geraten ──
    ohne_wert = [p for p in positionen
                 if p.zehntel is not None and p.gegenstandswert is None]
    if ohne_wert:
        befunde.append(Befund(
            "hinweis", "Gegenstandswert steht nicht dabei",
            f"{len(ohne_wert)} Posten nennen einen Zehntelsatz, aber nicht den "
            "Gegenstandswert, auf den er sich bezieht. Ohne den lässt sich der "
            "Betrag nicht nachrechnen — er darf nach § 9 StBVV verlangt werden."))

    reihe = {"falsch": 0, "nachfragen": 1, "hinweis": 2}
    befunde.sort(key=lambda b: reihe[b.schwere])
    return befunde


# ── Der Bericht ──────────────────────────────────────────────────────────────

BEREICH_NAME = {"einstellungen": "Einstellungen", "briefkopf": "Dein Briefkopf",
                "berater": "Deine Kanzlei"}


def bericht(*, salon: str | None, dokumente: list[dict], felder: list[Feld],
            befunde: list[Befund], kennzahlen: dict | None = None,
            offen: list[str] | None = None) -> str:
    """Der Stand des Salons als Markdown — für Nina lesbar, nicht für Fachleute."""
    t: list[str] = []
    t.append(f"# Was babu über {salon or 'deinen Salon'} weiß")
    t.append("")
    t.append(f"Gelesen wurden {len(dokumente)} Unterlagen. Daraus ergibt sich, "
             "was unten steht — jede Angabe nennt die Unterlage, aus der sie "
             "stammt.")
    t.append("")

    if felder:
        for bereich in ("einstellungen", "briefkopf", "berater"):
            teil = [f for f in felder if f.bereich == bereich]
            if not teil:
                continue
            t.append(f"## {BEREICH_NAME[bereich]}")
            t.append("")
            t.append("| Feld | Wert | Woher |")
            t.append("|---|---|---|")
            for f in teil:
                wert = "Ja" if f.wert is True else "Nein" if f.wert is False else f.wert
                marke = "" if f.sicher else " ⚠"
                t.append(f"| {f.schluessel}{marke} | {_zelle(wert)} | "
                         f"{_zelle(f.quelle)} · {_zelle(f.regel)} |")
            t.append("")

    if befunde:
        t.append("## Die Rechnungen deiner Kanzlei")
        t.append("")
        t.append("babu rechnet sie nach. Das ist kein Vorwurf — eine Rechnung, "
                 "die man versteht, kann man bezahlen.")
        t.append("")
        for b in befunde:
            kopf = {"falsch": "**Das stimmt nicht:**",
                    "nachfragen": "**Bitte nachfragen:**",
                    "hinweis": "Hinweis:"}[b.schwere]
            zusatz = f" ({b.betrag:.2f} €)" if b.betrag is not None else ""
            t.append(f"- {kopf} {b.titel}{zusatz} — {b.text}")
        t.append("")

    if kennzahlen:
        t.append("## Deine Zahlen")
        t.append("")
        t.append("| Kennzahl | Wert |")
        t.append("|---|---|")
        for k, v in kennzahlen.items():
            if isinstance(v, (int, float)):
                t.append(f"| {k} | {v:,.2f} €|".replace(",", "␣")
                         .replace(".", ",").replace("␣", "."))
        t.append("")

    t.append("## Die Unterlagen")
    t.append("")
    t.append("| Unterlage | Erkannt als | Abgelegt unter |")
    t.append("|---|---|---|")
    for d in dokumente:
        t.append(f"| {_zelle(d.get('datei'))} | {_zelle(d.get('art_label') or d.get('art'))} "
                 f"| {_zelle(d.get('ablage') or '—')} |")
    t.append("")

    if offen:
        t.append("## Was noch fehlt")
        t.append("")
        for o in offen:
            t.append(f"- {o}")
        t.append("")
    return "\n".join(t) + "\n"


def _zelle(wert) -> str:
    return str("—" if wert is None else wert).replace("|", "\\|").replace("\n", " ")
