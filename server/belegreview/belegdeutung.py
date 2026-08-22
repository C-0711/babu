#!/usr/bin/env python3
"""Belegdeutung — aus erkannten Kästen wird ein verstandener Beleg.

Die Texterkennung liefert nicht nur Zeichen, sondern zu jeder Zeile auch
ihren Ort auf dem Blatt und die Größe der Schrift. Genau daraus besteht ein
Beleg: oben groß der Aussteller, rechtsbündig eine Spalte mit Beträgen,
unten die Summe, darunter Kleingedrucktes. Wer nur die Zeichen aneinander-
reiht, wirft das alles weg und muss danach raten.

Dieses Modul wirft es nicht weg. Jede Deutung merkt sich, **aus welcher
Zeile** sie stammt, **welche Regel** gegriffen hat und **wie sicher** die
Erkennung dieser Zeile war. Das ist keine Zierde: es ist die Grundlage für
das Leseprotokoll, das Nina und Christoph hinter dem ⓘ öffnen. Was man
nicht nachlesen kann, kann man auch nicht glauben.

Warum das die alten Fehler nicht wiederholt:

* Auf einer Parkquittung stand als Betrag „19,00" — der Steuersatz. Eine
  Zahl, auf die ein Prozentzeichen folgt, ist hier kein Betrag.
* Auf einer Rechnung gewann das Stammkapital aus der Fußzeile über die
  40,00 € Rechnungsbetrag. Was unterhalb der Summe im Kleingedruckten
  steht, ist hier kein Betrag.
* Als Lieferant stand „Rechnungsadresse", weil das die erste Zeile war.
  Der Aussteller ist hier die groß gesetzte Zeile im Kopf — nicht die
  erste, und ausdrücklich nicht die Anschrift des Empfängers.

Reines Rechnen, kein Netz, keine Dateien: alles hier ist prüfbar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

# ── Was hereinkommt ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Kasten:
    """Ein erkanntes Textstück mit seinem Platz auf dem Blatt."""
    text: str
    konf: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def hoehe(self) -> float:
        return self.y1 - self.y0

    @property
    def mitte_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Zeile:
    """Mehrere Kästen, die auf derselben Höhe stehen — eine gelesene Zeile."""
    nr: int
    kaesten: list[Kasten]

    @property
    def text(self) -> str:
        return " ".join(k.text for k in self.kaesten).strip()

    @property
    def konf(self) -> float:
        return min((k.konf for k in self.kaesten), default=0.0)

    @property
    def hoehe(self) -> float:
        return max((k.hoehe for k in self.kaesten), default=0.0)

    @property
    def y0(self) -> float:
        return min((k.y0 for k in self.kaesten), default=0.0)

    @property
    def y1(self) -> float:
        return max((k.y1 for k in self.kaesten), default=0.0)

    @property
    def x0(self) -> float:
        return min((k.x0 for k in self.kaesten), default=0.0)

    @property
    def x1(self) -> float:
        return max((k.x1 for k in self.kaesten), default=0.0)


@dataclass
class Deutung:
    """Ein gedeuteter Wert samt Herkunft — die Einheit des Leseprotokolls."""
    wert: object
    regel: str
    zeile_nr: int | None = None
    zeilentext: str = ""
    konf: float = 0.0

    def __bool__(self) -> bool:
        return self.wert is not None


@dataclass
class Betrag:
    """Eine Geldzahl an ihrem Ort."""
    wert: float
    zeile_nr: int
    x1: float           # rechte Kante — Beträge stehen rechtsbündig
    roh: str


@dataclass
class Lesung:
    """Das Ergebnis: gedeutete Felder, die Zeilen, und was offen blieb."""
    zeilen: list[Zeile] = field(default_factory=list)
    felder: dict[str, Deutung] = field(default_factory=dict)
    offen: list[str] = field(default_factory=list)
    notizen: list[str] = field(default_factory=list)

    def wert(self, name: str):
        d = self.felder.get(name)
        return d.wert if d else None


# ── Wörter, die einen Beleg gliedern ─────────────────────────────────────────

# Zeilen, in denen die Endsumme steht. Reihenfolge egal — es gewinnt die
# unterste, weil Kassenbons Zwischensummen darüber drucken.
SUMMENWORT = ("gesamtbetrag", "gesamtsumme", "rechnungsbetrag", "zahlbetrag",
              "endbetrag", "zu zahlen", "zu zahlender betrag", "gesamt",
              "summe", "total", "bar", "betrag", "brutto", "endsumme")

# … außer wenn eines dieser Wörter danebensteht. Eine Zwischensumme ist
# keine Summe, und „Summe netto" ist nicht das, was bezahlt wurde.
KEINE_SUMME = ("zwischensumme", "zw.summe", "zwsumme", "nettosumme",
               "summe netto", "netto", "mwst", "mehrwertsteuer", "ust",
               "umsatzsteuer", "steuer", "rabatt", "skonto", "trinkgeld",
               "rückgeld", "rueckgeld", "zurück", "zurueck", "gegeben",
               "gutschein", "anzahlung", "guthaben", "pfand", "einzelpreis",
               "stückpreis", "stueckpreis", "preis/stk")

# Fußzeile: was hier steht, ist juristisches Beiwerk, kein Rechnungsbetrag.
FUSSZEILE = ("stammkapital", "handelsregister", "amtsgericht", "hrb", "hra",
             "geschäftsführer", "geschaeftsfuehrer", "ust-idnr", "ust-id",
             "umsatzsteuer-id", "steuernummer", "st.-nr", "st-nr", "iban",
             "bic", "swift", "gläubiger-id", "glaeubiger-id", "sitz der",
             "vorstand", "aufsichtsrat", "registergericht", "kontoinhaber",
             "bankverbindung")

STEUERWORT = ("mwst", "mehrwertsteuer", "ust", "umsatzsteuer", "steuer",
              "enthaltene", "enthalten", "inkl", "zzgl")

NETTOWORT = ("netto", "nettobetrag", "summe netto", "nettosumme",
             "gesamt netto", "warenwert")

# Kopfzeilen, die nie der Aussteller sind.
KEIN_LIEFERANT = (
    "rechnung", "rechnungsadresse", "rechnungsanschrift", "rechnung an",
    "quittung", "kassenbon", "kassenzettel", "beleg", "bon", "lieferschein",
    "gutschrift", "angebot", "kunde", "kundennummer", "kunden-nr", "empfänger",
    "empfaenger", "lieferadresse", "lieferanschrift", "an:", "herrn", "frau",
    "kopie", "original", "datum", "seite", "vielen dank", "danke",
    "steuerbeleg", "bewirtungsbeleg", "eigenbeleg", "zwischenrechnung")

# Ab hier steht die Anschrift des Empfängers — die nächsten Zeilen
# überspringen, sonst heißt der Lieferant wie die Kundin.
EMPFAENGER_START = ("rechnungsadresse", "rechnungsanschrift", "rechnung an",
                    "lieferadresse", "lieferanschrift", "kunde", "empfänger",
                    "empfaenger", "an:")

RECHTSFORM = ("gmbh", "mbh", "ag", "ug", "kg", "ohg", "gbr", "e.k.", "e. k.",
              "e.v.", "& co", "co. kg", "se", "ltd", "inc", "gmbh & co",
              "partg", "mbb", "kgaa")

NUMMERNWORT = ("rechnungsnummer", "rechnungs-nr", "rechnung nr", "rechnung-nr",
               "re-nr", "re.-nr", "belegnummer", "beleg-nr", "beleg nr",
               "quittungsnummer", "quittungs-nr", "bon-nr", "bonnummer",
               "bon nr", "kassenbon-nr", "rg-nr", "rechnungsnr", "nummer",
               "nr.", "no.", "invoice")

KEINE_NUMMER = ("kundennummer", "kunden-nr", "kd-nr", "steuernummer",
                "ust-idnr", "ust-id", "telefon", "tel.", "fax", "iban", "bic",
                "artikelnummer", "artikel-nr", "art.-nr", "seite",
                "auftragsnummer", "bestellnummer", "lieferschein",
                "mitarbeiter", "kasse", "terminal", "trace", "beleg-nr:kasse")

DATUMWORT = ("rechnungsdatum", "belegdatum", "bondatum", "datum",
             "ausstellungsdatum", "leistungsdatum", "kaufdatum", "vom")

GESETZLICHE_SAETZE = (0, 5, 7, 16, 19)

MONATE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4,
          "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
          "oktober": 10, "november": 11, "dezember": 12,
          "jan": 1, "feb": 2, "mrz": 3, "apr": 4, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12}


def _flach(s: str) -> str:
    """Kleingeschrieben und ohne Akzente — zum Vergleichen, nicht zum Zeigen."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _enthaelt(text: str, woerter) -> str | None:
    flach = _flach(text)
    for w in woerter:
        if _flach(w) in flach:
            return w
    return None


# ── Zeilen bilden ────────────────────────────────────────────────────────────

def zeilen_bilden(kaesten: list[Kasten], ueberlappung: float = 0.5) -> list[Zeile]:
    """Kästen, die sich senkrecht überlappen, gehören zur selben Zeile.

    Die Texterkennung liefert Wortgruppen, keine Zeilen. Erst wer sie nach
    Höhe zusammenlegt, kann „MwSt 19 %" und den Betrag rechts daneben als
    zusammengehörig erkennen — und genau das ist der Unterschied zwischen
    Lesen und Deuten.
    """
    if not kaesten:
        return []
    rest = sorted(kaesten, key=lambda k: (k.y0, k.x0))
    gruppen: list[list[Kasten]] = []
    for k in rest:
        for g in gruppen:
            oben = max(g[0].y0, k.y0)
            unten = min(max(x.y1 for x in g), k.y1)
            gemein = unten - oben
            kleiner = min(k.hoehe, min(x.hoehe for x in g)) or 1.0
            if gemein > 0 and gemein / kleiner >= ueberlappung:
                g.append(k)
                break
        else:
            gruppen.append([k])
    gruppen.sort(key=lambda g: min(k.y0 for k in g))
    return [Zeile(nr=i, kaesten=sorted(g, key=lambda k: k.x0))
            for i, g in enumerate(gruppen)]


# ── Beträge erkennen ─────────────────────────────────────────────────────────

# 1.234,56 · 1234,56 · 1 234.56 · 12,50 — mit genau zwei Nachkommastellen.
_GELD = re.compile(r"(?<![\d,.])(\d{1,3}(?:[.\s ]\d{3})+|\d+)[,.](\d{2})(?![\d])")
_PROZENT_DANACH = re.compile(r"^\s*(?:%|prozent)")
_DATUM_ZIFFERN = re.compile(r"\d{1,2}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{2,4}")


def _zahl(ganz: str, nachkomma: str) -> float:
    return float(ganz.replace(".", "").replace(" ", "").replace(" ", "")
                 + "." + nachkomma)


def betraege_in_zeile(z: Zeile) -> list[Betrag]:
    """Alle Geldbeträge einer Zeile — Prozentwerte und Daten ausgenommen.

    Der Fehler auf der Parkquittung entstand genau hier: „19,00 %" sieht wie
    ein Betrag aus, bis man das Zeichen dahinter anschaut.
    """
    gefunden: list[Betrag] = []
    for k in z.kaesten:
        text = k.text
        # Ein Datum liefert Zahlenpaare, die wie Beträge aussehen.
        maskiert = _DATUM_ZIFFERN.sub(lambda m: "#" * len(m.group(0)), text)
        for m in _GELD.finditer(maskiert):
            if _PROZENT_DANACH.match(maskiert[m.end():]):
                continue
            # Uhrzeit: 12.30 Uhr
            if re.match(r"\s*uhr", maskiert[m.end():], re.I):
                continue
            gefunden.append(Betrag(wert=_zahl(m.group(1), m.group(2)),
                                   zeile_nr=z.nr, x1=k.x1, roh=m.group(0)))
    return gefunden


def steuersatz_in_zeile(z: Zeile) -> int | None:
    """Ein Prozentsatz in dieser Zeile, sofern er ein gesetzlicher ist."""
    for m in re.finditer(r"(\d{1,2})(?:[.,](\d{1,2}))?\s*%", z.text):
        satz = int(m.group(1))
        if satz in GESETZLICHE_SAETZE:
            return satz
    return None


# ── Die Betragsspalte ────────────────────────────────────────────────────────

def betragsspalte(betraege: list[Betrag], blattbreite: float) -> float | None:
    """Die rechte Kante, an der die Beträge ausgerichtet sind.

    Auf einer Rechnung stehen Beträge in einer Spalte. Wer diese Spalte
    kennt, erkennt eine Zahl im Fließtext als das, was sie ist: keine.
    Bei zwei oder drei Beträgen gibt es keine Spalte — dann lieber nichts
    behaupten.
    """
    if len(betraege) < 3 or blattbreite <= 0:
        return None
    toleranz = blattbreite * 0.04
    beste, bestzahl = None, 0
    for b in betraege:
        nah = [a for a in betraege if abs(a.x1 - b.x1) <= toleranz]
        if len(nah) > bestzahl:
            beste, bestzahl = sum(a.x1 for a in nah) / len(nah), len(nah)
    if bestzahl < 3 or beste is None or beste < blattbreite * 0.45:
        return None
    return beste


# ── Die einzelnen Felder ─────────────────────────────────────────────────────

def deute_summe(zeilen: list[Zeile], spalte: float | None,
                blattbreite: float) -> tuple[Deutung, list[str]]:
    """Was am Ende zu zahlen war."""
    notizen: list[str] = []
    alle: list[tuple[Zeile, list[Betrag]]] = [(z, betraege_in_zeile(z)) for z in zeilen]

    # 1. Eine Zeile, die es ausdrücklich sagt — die unterste gewinnt.
    kandidaten = []
    for z, bs in alle:
        if not bs:
            continue
        if _enthaelt(z.text, FUSSZEILE):
            continue
        wort = _enthaelt(z.text, SUMMENWORT)
        if not wort:
            continue
        verbot = _enthaelt(z.text, KEINE_SUMME)
        if verbot:
            # „Gesamtbetrag brutto" enthält „brutto" — das ist kein Verbot.
            if not (verbot in ("netto", "brutto") and wort in
                    ("gesamtbetrag", "gesamtsumme", "rechnungsbetrag",
                     "zahlbetrag", "endbetrag", "zu zahlen")):
                continue
        kandidaten.append((z, bs, wort))
    if kandidaten:
        z, bs, wort = kandidaten[-1]
        b = max(bs, key=lambda x: x.wert)
        return (Deutung(wert=b.wert, regel=f"Zeile nennt „{wort}“",
                        zeile_nr=z.nr, zeilentext=z.text, konf=z.konf), notizen)

    # 2. Keine solche Zeile: der größte Betrag in der Betragsspalte, aber nur
    #    oberhalb des Kleingedruckten. So verliert das Stammkapital.
    fussab = None
    for z in zeilen:
        if _enthaelt(z.text, FUSSZEILE):
            fussab = z.nr
            break
    frei = []
    for z, bs in alle:
        if fussab is not None and z.nr >= fussab:
            continue
        if _enthaelt(z.text, KEINE_SUMME) or _enthaelt(z.text, FUSSZEILE):
            continue
        for b in bs:
            if spalte is None or abs(b.x1 - spalte) <= blattbreite * 0.04:
                frei.append((z, b))
    if fussab is not None:
        notizen.append(f"Ab Zeile {fussab + 1} steht Kleingedrucktes — "
                       "Beträge von dort zählen nicht.")
    if frei:
        z, b = max(frei, key=lambda p: p[1].wert)
        regel = ("größter Betrag in der Betragsspalte" if spalte is not None
                 else "größter Betrag oberhalb des Kleingedruckten")
        return (Deutung(wert=b.wert, regel=regel, zeile_nr=z.nr,
                        zeilentext=z.text, konf=z.konf), notizen)
    return Deutung(wert=None, regel="kein Betrag gefunden"), notizen


def deute_steuer(zeilen: list[Zeile], brutto: float | None
                 ) -> tuple[Deutung, Deutung, Deutung, list[str]]:
    """Steuersatz, Steuerbetrag und Netto — gerechnet, nicht gesucht.

    Zurück kommen (satz, ust, netto). Der Satz wird, wo möglich, aus Netto
    und Steuer bestimmt statt aus der Prozentangabe: „7,00 %" fand die alte
    Textsuche nie, und ein falscher Satz macht die Vorsteuer falsch.
    """
    notizen: list[str] = []
    satz_d = Deutung(wert=None, regel="kein Steuersatz gefunden")
    ust_d = Deutung(wert=None, regel="kein Steuerbetrag gefunden")
    netto_d = Deutung(wert=None, regel="kein Nettobetrag gefunden")

    # Eine Steuerzeile nennt entweder die Steuer beim Namen — oder sie ist
    # eine Steuertabelle: ein Satz und dahinter Netto, Steuer, Brutto. Bons
    # drucken die gern als „A 19% 33,61 6,39 40,00", ganz ohne das Wort.
    def ist_steuerzeile(z: Zeile) -> bool:
        if _enthaelt(z.text, FUSSZEILE):
            return False
        if _enthaelt(z.text, STEUERWORT):
            return True
        return (steuersatz_in_zeile(z) is not None
                and len(betraege_in_zeile(z)) >= 3)

    steuerzeilen = [z for z in zeilen if ist_steuerzeile(z)]
    nettozeilen = [z for z in zeilen
                   if _enthaelt(z.text, NETTOWORT)
                   and not _enthaelt(z.text, STEUERWORT)
                   and not _enthaelt(z.text, FUSSZEILE)]

    # Der Satz zuerst, unabhängig von Beträgen: „inkl. 19 % MwSt" steht oft
    # allein in einer Zeile, und daraus lässt sich alles Weitere rechnen.
    for z in reversed(steuerzeilen):
        satz = steuersatz_in_zeile(z)
        if satz is not None:
            satz_d = Deutung(satz, "Prozentangabe der Steuerzeile",
                             z.nr, z.text, z.konf)
            break

    # Der Steuerbetrag: in einer Steuerzeile die Zahl, die zum Satz passt.
    for z in reversed(steuerzeilen):
        bs = betraege_in_zeile(z)
        if not bs:
            continue
        satz = steuersatz_in_zeile(z)
        # Eine Steuertabellen-Zeile „19% 33,53 6,38 39,91": Netto, Steuer,
        # Brutto. Passt eine Aufteilung auf, ist sie eindeutig.
        if satz and len(bs) >= 3:
            for i in range(len(bs) - 2):
                n, s, b = bs[i].wert, bs[i + 1].wert, bs[i + 2].wert
                if abs(n + s - b) < 0.011 and n > 0 and abs(n * satz / 100 - s) < 0.02:
                    satz_d = Deutung(satz, f"Steuertabelle {satz} %, Aufteilung geht auf",
                                     z.nr, z.text, z.konf)
                    ust_d = Deutung(s, "Steuertabelle", z.nr, z.text, z.konf)
                    netto_d = Deutung(n, "Steuertabelle", z.nr, z.text, z.konf)
                    return satz_d, ust_d, netto_d, notizen
        if satz and brutto:
            # Welcher Betrag der Zeile ist die Steuer? Der, der zum Satz passt.
            erwartet = round(brutto - brutto / (1 + satz / 100), 2)
            treffer = [b for b in bs if abs(b.wert - erwartet) < 0.02]
            if treffer:
                ust_d = Deutung(treffer[0].wert, f"Steuerzeile, passt zu {satz} % vom Brutto",
                                z.nr, z.text, z.konf)
                satz_d = Deutung(satz, "Prozentangabe der Steuerzeile, durch die "
                                 "Summenprobe bestätigt", z.nr, z.text, z.konf)
                netto_d = Deutung(round(brutto - treffer[0].wert, 2),
                                  "Brutto minus Steuer", z.nr, z.text, z.konf)
                return satz_d, ust_d, netto_d, notizen
        if len(bs) == 1 and not ust_d:
            ust_d = Deutung(bs[0].wert, "einzige Zahl der Steuerzeile",
                            z.nr, z.text, z.konf)

    # Netto aus einer eigenen Nettozeile.
    if not netto_d:
        for z in reversed(nettozeilen):
            bs = betraege_in_zeile(z)
            if bs:
                netto_d = Deutung(max(b.wert for b in bs), "Zeile nennt Netto",
                                  z.nr, z.text, z.konf)
                break

    # Jetzt zusammenrechnen, was sich rechnen lässt.
    if brutto is not None:
        if ust_d and netto_d and abs(netto_d.wert + ust_d.wert - brutto) > 0.011:
            notizen.append(
                f"Netto {netto_d.wert:.2f} + Steuer {ust_d.wert:.2f} ergibt nicht "
                f"Brutto {brutto:.2f} — die Aufteilung ist unsicher.")
            netto_d = Deutung(None, "verworfen, Summenprobe scheiterte")
            ust_d = Deutung(None, "verworfen, Summenprobe scheiterte")
        if ust_d and not netto_d:
            netto_d = Deutung(round(brutto - ust_d.wert, 2), "Brutto minus Steuer",
                              ust_d.zeile_nr, ust_d.zeilentext, ust_d.konf)
        elif netto_d and not ust_d:
            ust_d = Deutung(round(brutto - netto_d.wert, 2), "Brutto minus Netto",
                            netto_d.zeile_nr, netto_d.zeilentext, netto_d.konf)
        elif not netto_d and not ust_d and satz_d:
            netto = round(brutto / (1 + satz_d.wert / 100), 2)
            netto_d = Deutung(netto, f"aus Brutto und {satz_d.wert} % gerechnet",
                              satz_d.zeile_nr, satz_d.zeilentext, satz_d.konf)
            ust_d = Deutung(round(brutto - netto, 2),
                            f"aus Brutto und {satz_d.wert} % gerechnet",
                            satz_d.zeile_nr, satz_d.zeilentext, satz_d.konf)

    # Den Satz zuletzt aus Netto und Steuer bestimmen — das ist der genaue Weg.
    if netto_d and ust_d and netto_d.wert:
        gerechnet = round(ust_d.wert / netto_d.wert * 100)
        if gerechnet in GESETZLICHE_SAETZE:
            if satz_d and satz_d.wert != gerechnet:
                notizen.append(
                    f"Die Prozentangabe sagt {satz_d.wert} %, aus Netto und Steuer "
                    f"ergeben sich {gerechnet} % — gerechnet wird mit {gerechnet} %.")
            satz_d = Deutung(gerechnet, "aus Netto und Steuer gerechnet",
                             ust_d.zeile_nr, ust_d.zeilentext, ust_d.konf)
        else:
            notizen.append(
                f"Aus Netto und Steuer ergeben sich {gerechnet} % — kein "
                "gesetzlicher Satz. Einer der beiden Beträge ist falsch "
                "gelesen; die Vorsteuer ist damit nicht verlässlich.")

    return satz_d, ust_d, netto_d, notizen


def deute_lieferant(zeilen: list[Zeile], blatthoehe: float) -> Deutung:
    """Wer den Beleg ausgestellt hat.

    Im Kopf des Blattes, und dort die groß gesetzte Zeile — kein Beleg
    druckt den Firmennamen kleiner als das Kleingedruckte. Die Anschrift
    des Empfängers wird übersprungen, sonst heißt der Lieferant wie die
    Kundin.
    """
    if not zeilen:
        return Deutung(None, "keine Zeilen")
    kopf_bis = min(zeilen[0].y0 + blatthoehe * 0.35, zeilen[-1].y1)
    kopf = [z for z in zeilen if z.y0 <= kopf_bis] or zeilen[:8]

    # Empfängerblock ausblenden: ab der Ansage die nächsten vier Zeilen.
    gesperrt: set[int] = set()
    for z in kopf:
        if _enthaelt(z.text, EMPFAENGER_START):
            gesperrt.update(range(z.nr, z.nr + 5))

    def taugt(z: Zeile) -> bool:
        t = z.text.strip()
        if z.nr in gesperrt or len(t) < 3:
            return False
        if _enthaelt(t, KEIN_LIEFERANT):
            return False
        if re.fullmatch(r"[\d\s.,:/€%+-]+", t):        # nur Zahlen
            return False
        if re.match(r"^\d{5}\s+\w", t):                # PLZ Ort
            return False
        if re.search(r"(str\.|straße|strasse|weg|platz|allee|gasse)\s*\d", _flach(t)):
            return False
        if sum(c.isdigit() for c in t) > len(t) / 2:
            return False
        return True

    moegliche = [z for z in kopf if taugt(z)]
    if not moegliche:
        return Deutung(None, "im Kopf stand kein Name, nur Anschrift oder Zahlen")

    # Eine Rechtsform ist ein sicheres Zeichen.
    for z in moegliche:
        if _enthaelt(z.text, RECHTSFORM):
            return Deutung(_saubern(z.text), "Zeile im Kopf mit Rechtsform",
                           z.nr, z.text, z.konf)

    # Sonst: die größte Schrift im Kopf. Bei gleicher Größe die oberste.
    groesste = max(z.hoehe for z in moegliche)
    if groesste > 0:
        gross = [z for z in moegliche if z.hoehe >= groesste * 0.9]
        if len(gross) < len(moegliche):
            z = gross[0]
            return Deutung(_saubern(z.text), "größte Schrift im Kopf",
                           z.nr, z.text, z.konf)
    z = moegliche[0]
    return Deutung(_saubern(z.text), "oberste brauchbare Zeile im Kopf",
                   z.nr, z.text, z.konf)


def _saubern(text: str) -> str:
    t = re.sub(r"\s{2,}", " ", text).strip(" .,:;-—·|")
    return t[:80]


def deute_datum(zeilen: list[Zeile], heute: date | None = None) -> Deutung:
    """Das Belegdatum — bevorzugt aus einer Zeile, die es benennt."""
    heute = heute or date.today()

    def daten(z: Zeile) -> list[tuple[date, str]]:
        gefunden = []
        for m in re.finditer(r"\b(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{2,4})\b",
                             z.text):
            t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
            j = j + 2000 if j < 100 else j
            gefunden.append((t, mo, j, m.group(0)))
        for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", z.text):
            gefunden.append((int(m.group(3)), int(m.group(2)), int(m.group(1)),
                             m.group(0)))
        for m in re.finditer(r"\b(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]+)\.?\s+(\d{4})\b",
                             z.text):
            mo = MONATE.get(_flach(m.group(2)))
            if mo:
                gefunden.append((int(m.group(1)), mo, int(m.group(3)), m.group(0)))
        raus = []
        for t, mo, j, roh in gefunden:
            try:
                d = date(j, mo, t)
            except ValueError:
                continue
            if 2000 <= j and (d - heute).days <= 1:
                raus.append((d, roh))
        return raus

    benannt = [z for z in zeilen if _enthaelt(z.text, DATUMWORT)]
    for z in benannt:
        gef = daten(z)
        if gef:
            d, roh = gef[0]
            wort = _enthaelt(z.text, DATUMWORT)
            return Deutung(d.isoformat(), f"Zeile nennt „{wort}“: {roh}",
                           z.nr, z.text, z.konf)
    for z in zeilen:
        gef = daten(z)
        if gef:
            d, roh = gef[0]
            return Deutung(d.isoformat(), f"erstes brauchbares Datum: {roh}",
                           z.nr, z.text, z.konf)
    return Deutung(None, "kein Datum gefunden")


def deute_nummer(zeilen: list[Zeile]) -> Deutung:
    """Die Belegnummer — nur aus einer Zeile, die sie auch so nennt."""
    for z in zeilen:
        if _enthaelt(z.text, KEINE_NUMMER):
            continue
        wort = _enthaelt(z.text, NUMMERNWORT)
        if not wort:
            continue
        # Alles nach dem Wort; die Nummer steht rechts davon.
        flach = _flach(z.text)
        pos = flach.find(_flach(wort)) + len(wort)
        rest = z.text[pos:].lstrip(" .:#-–—")
        m = re.match(r"([A-Za-z]{0,4}[-/]?\d[\w\-/.]{0,24})", rest)
        if not m:
            continue
        nr = m.group(1).rstrip(".,;:")
        if _DATUM_ZIFFERN.fullmatch(nr) or re.fullmatch(r"\d{1,3}[,.]\d{2}", nr):
            continue
        if len(re.sub(r"\D", "", nr)) < 1:
            continue
        return Deutung(nr, f"Zeile nennt „{wort}“", z.nr, z.text, z.konf)
    return Deutung(None, "keine Zeile nennt eine Belegnummer")


# ── Das Ganze ────────────────────────────────────────────────────────────────

def deuten(kaesten: list[Kasten], heute: date | None = None) -> Lesung:
    """Aus erkannten Kästen einen verstandenen Beleg machen."""
    zeilen = zeilen_bilden(kaesten)
    lesung = Lesung(zeilen=zeilen)
    if not zeilen:
        lesung.offen.append("Auf dem Bild war kein Text zu erkennen.")
        return lesung

    linker_rand = min(z.x0 for z in zeilen)
    blattbreite = max(z.x1 for z in zeilen) - linker_rand
    blatthoehe = max(z.y1 for z in zeilen) - min(z.y0 for z in zeilen)

    alle_betraege = [b for z in zeilen for b in betraege_in_zeile(z)]
    spalte = betragsspalte(alle_betraege, blattbreite)
    if spalte is not None:
        # Der Anteil zählt vom linken Textrand, nicht vom Blattnullpunkt —
        # sonst stünden im Protokoll Angaben wie „109 % der Blattbreite".
        anteil = (spalte - linker_rand) / blattbreite if blattbreite else 0
        lesung.notizen.append(
            f"Die Beträge stehen in einer Spalte (rechte Kante bei "
            f"{min(max(anteil, 0), 1):.0%} der Blattbreite).")

    brutto_d, notizen = deute_summe(zeilen, spalte, blattbreite)
    lesung.notizen += notizen
    satz_d, ust_d, netto_d, notizen = deute_steuer(zeilen, brutto_d.wert)
    lesung.notizen += notizen

    lesung.felder = {
        "lieferant": deute_lieferant(zeilen, blatthoehe),
        "beleg_nr": deute_nummer(zeilen),
        "datum": deute_datum(zeilen, heute),
        "brutto": brutto_d,
        "netto": netto_d,
        "ust": ust_d,
        "ust_satz": satz_d,
    }

    probe = (brutto_d and netto_d and ust_d
             and abs(netto_d.wert + ust_d.wert - brutto_d.wert) < 0.011)
    lesung.felder["summenprobe_ok"] = Deutung(
        bool(probe),
        "Netto + Steuer = Brutto" if probe else "Netto + Steuer ergibt nicht Brutto")

    for name, klartext in (("lieferant", "Wer den Beleg ausgestellt hat"),
                           ("datum", "Das Belegdatum"),
                           ("brutto", "Der Rechnungsbetrag")):
        if not lesung.felder[name]:
            lesung.offen.append(f"{klartext} ist nicht sicher zu lesen.")
    if brutto_d and not probe:
        lesung.offen.append("Netto und Steuer gehen nicht auf — Beträge prüfen.")

    schwach = [z for z in zeilen if z.konf < 0.6]
    if schwach and len(schwach) > len(zeilen) / 3:
        lesung.offen.append(
            f"{len(schwach)} von {len(zeilen)} Zeilen wurden nur unsicher "
            "erkannt — ein schärferes Foto würde helfen.")

    return lesung
