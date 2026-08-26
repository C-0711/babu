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
from itertools import combinations

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
class Probe:
    """Eine Rechenprobe, die der Beleg an sich selbst besteht — oder nicht.

    Ein Beleg trägt seine eigene Wahrheit mit sich: die Posten müssen die
    Summe ergeben, Netto und Steuer den Bruttobetrag, die Steuer den
    ausgewiesenen Satz, und Gegeben minus Rückgeld das, was zu zahlen war.
    Dafür braucht es keine fremde Quelle und kein zweites Modell — nur das,
    was auf dem Blatt steht.

    Deshalb steht hier ein `name`: „Summenprobe nicht bestanden" sagt
    niemandem, wo er hinsehen soll. „Die Posten ergeben 33,61 €, ausgewiesen
    sind 90,00 €" sagt es.
    """
    name: str
    bestanden: bool
    erklaerung: str
    zeile_nr: int | None = None


@dataclass
class Steuerposition:
    """Netto, Steuer und Brutto zu einem Steuersatz — eine Buchungszeile.

    Ein Drogeriebon trägt 19 % und 7 % nebeneinander. Wer daraus einen Satz
    macht, bucht eine Zeile mit dem falschen Schlüssel und meldet eine
    falsche Voranmeldung. Also bleiben die Sätze getrennt.
    """
    satz: int
    netto: float
    ust: float
    brutto: float

    def als_dict(self) -> dict:
        return {"satz": self.satz, "netto": self.netto,
                "ust": self.ust, "brutto": self.brutto}


@dataclass
class Lesung:
    """Das Ergebnis: gedeutete Felder, die Zeilen, und was offen blieb."""
    zeilen: list[Zeile] = field(default_factory=list)
    felder: dict[str, Deutung] = field(default_factory=dict)
    offen: list[str] = field(default_factory=list)
    notizen: list[str] = field(default_factory=list)
    proben: list[Probe] = field(default_factory=list)
    steuerpositionen: list[Steuerposition] = field(default_factory=list)

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
               "stückpreis", "stueckpreis", "preis/stk",
               # Eine bezahlte Rechnung druckt unten „Offener Betrag 0,00" —
               # das ist der REST, nicht die Summe. Auch ein Teilrest (50,00)
               # darf nie gegen den Gesamtbetrag darüber gewinnen.
               "offener betrag", "restbetrag", "bereits gezahlt",
               "bereits bezahlt")

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

# Was ein Barbeleg unten druckt: was hingelegt wurde und was zurückkam.
# Bewusst eng gehalten — beide Wortgruppen müssen auf dem Beleg stehen,
# sonst wird nicht gerechnet.
GEGEBENWORT = ("gegeben", "bar gegeben", "gegeben bar", "barzahlung",
               "bar bezahlt", "erhalten")
RUECKGELDWORT = ("rückgeld", "rueckgeld", "wechselgeld", "zurück", "zurueck",
                 "retour")

# Sätze, mit denen ein Beleg sagt, dass er keine Umsatzsteuer trägt. Das ist
# keine Lücke, sondern eine Aussage — und sie gilt vor jeder Annahme.
KEIN_STEUERAUSWEIS = re.compile(
    r"kleinunternehmer"
    r"|§\s*19\s*(?:abs\.?\s*\d\s*)?ustg?"
    r"|nach\s*§\s*19\b"
    r"|kein[e]?[nr]?\s+(?:umsatz|mehrwert)steuer"
    r"|ohne\s+(?:umsatz|mehrwert)steuer"
    r"|(?:umsatz|mehrwert)steuer\s*(?:wird\s*)?nicht\s+(?:ausgewiesen|erhoben|berechnet)"
    r"|(?:umsatz|mehrwert)steuer[-\s]?(?:frei|befreit)"
    r"|steuerfrei"
    r"|nicht\s+umsatzsteuerpflichtig"
    r"|§\s*4\s*(?:nr\.?|abs)", re.I)

# Bis 250 € brutto darf eine Rechnung als Kleinbetragsrechnung ohne
# getrennten Steuerausweis auskommen (§ 33 UStDV). Darüber fehlt etwas,
# wenn keine Steuer dasteht — dann wird gefragt.
KLEINBETRAGSGRENZE = 250.0

# Zwei Genauigkeiten, und der Unterschied ist keine Förmlichkeit:
# Posten addieren sich ohne Rundung, da ist ein Cent ein Lesefehler.
# Wo Prozente im Spiel sind, darf die letzte Stelle wandern.
CENT = 0.005
RUNDUNG = 0.011

MONATE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4,
          "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
          "oktober": 10, "november": 11, "dezember": 12,
          "jan": 1, "feb": 2, "mrz": 3, "apr": 4, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12}


def _flach(s: str) -> str:
    """Kleingeschrieben und ohne Akzente — zum Vergleichen, nicht zum Zeigen."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _de(x: float) -> str:
    """Ein Betrag, wie er in einem deutschen Satz steht: 1.234,56 €.

    Die Proben erklären sich in ganzen Sätzen, und darin gehört ein Betrag
    deutsch geschrieben — „33.61" liest im Zweifel jemand als 33 Cent.
    """
    return f"{x:,.2f} €".replace(",", "␣").replace(".", ",").replace("␣", ".")


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
        # Eine Rechnung über 0 € gibt es nicht — eine Null-Zeile ist kein
        # Kandidat. Bleibt gar nichts übrig, füllt später die Gegenprobe.
        if max(b.wert for b in bs) <= 0:
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
            if b.wert <= 0:
                continue  # eine Null ist nie „das, was zu zahlen war"
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


def _kein_steuerausweis(zeilen: list[Zeile]) -> Zeile | None:
    """Die Zeile, in der der Beleg sagt, dass er keine Umsatzsteuer trägt.

    „Kleinunternehmer nach § 19 UStG" ist keine fehlende Angabe, sondern
    eine gemachte: 0 %. Wer sie überliest und 19 % annimmt, zieht Vorsteuer
    aus einer Rechnung, die keine ausweist.
    """
    for z in zeilen:
        if KEIN_STEUERAUSWEIS.search(z.text):
            return z
    return None


def _tabellentripel(werte: tuple[float, float, float], satz: int
                    ) -> Steuerposition | None:
    """Drei Zahlen einer Steuerzeile — welche ist welche?

    Nicht die Spaltenüberschrift entscheidet das, sondern die Rechnung: der
    größte Wert ist der Bruttobetrag, die beiden anderen müssen ihn ergeben,
    und die kleinere muss zum Satz passen. So ist es gleichgültig, in
    welcher Reihenfolge die Kasse druckt — und die Reihenfolgen sind
    verschieden: der eine Bon schreibt Netto, Steuer, Brutto, der nächste
    Steuer, Brutto, Netto.
    """
    brutto, netto, ust = sorted(werte, reverse=True)
    if netto <= 0 or abs(netto + ust - brutto) > RUNDUNG:
        return None
    erwartet = netto * satz / 100
    if abs(ust - erwartet) > max(0.02, erwartet * 0.02):
        return None
    return Steuerposition(satz=satz, netto=netto, ust=ust, brutto=brutto)


def steuerpositionen_finden(zeilen: list[Zeile]) -> list[tuple[Steuerposition, Zeile]]:
    """Zeilen der Bauart „B 7 % 79,81 5,59 85,40“ — je Satz eine Position.

    Übernommen wird nur, was sich eindeutig auflösen lässt: passen in einer
    Zeile zwei verschiedene Dreiergruppen auf den Satz, wird geraten statt
    gelesen, und dann lieber gar nichts.
    """
    gefunden: list[tuple[Steuerposition, Zeile]] = []
    for z in zeilen:
        if _enthaelt(z.text, FUSSZEILE):
            continue
        satz = steuersatz_in_zeile(z)
        if satz is None:
            continue
        werte = [b.wert for b in betraege_in_zeile(z)]
        if len(werte) < 3:
            continue
        treffer: list[Steuerposition] = []
        for drei in combinations(werte, 3):
            p = _tabellentripel(drei, satz)
            if p and not any(_gleiche_position(p, t) for t in treffer):
                treffer.append(p)
        if len(treffer) == 1:
            gefunden.append((treffer[0], z))
    return gefunden


def _gleiche_position(a: Steuerposition, b: Steuerposition) -> bool:
    return all(abs(getattr(a, f) - getattr(b, f)) <= CENT
               for f in ("netto", "ust", "brutto"))


def deute_steuer(zeilen: list[Zeile], brutto: float | None,
                 gefunden: list[tuple[Steuerposition, Zeile]] | None = None
                 ) -> tuple[Deutung, Deutung, Deutung, list[str], list[Steuerposition]]:
    """Steuersatz, Steuerbetrag und Netto — gerechnet, nicht gesucht.

    Zurück kommen (satz, ust, netto, notizen, positionen). Der Satz wird, wo
    möglich, aus Netto und Steuer bestimmt statt aus der Prozentangabe:
    „7,00 %" fand die alte Textsuche nie, und ein falscher Satz macht die
    Vorsteuer falsch.

    Angenommen wird dabei nichts. Trägt der Beleg keine Umsatzsteuer, sind
    es 0 % — nicht 19 %. Der Unterschied ist Vorsteuer, die es nie gab.
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

    # Mehrere Sätze auf einem Beleg: der Drogeriemarkt druckt 19 % und 7 %
    # untereinander. Dann ist die Summe beider Zeilen die Wahrheit, und
    # jeder Satz behält seine eigene Zeile für den Export.
    gefunden = steuerpositionen_finden(zeilen) if gefunden is None else gefunden
    positionen = [p for p, _ in gefunden]
    if len({p.satz for p in positionen}) > 1:
        gross, z = max(gefunden, key=lambda pz: pz[0].netto)
        netto_d = Deutung(round(sum(p.netto for p in positionen), 2),
                          "Summe der Steuerzeilen", z.nr, z.text, z.konf)
        ust_d = Deutung(round(sum(p.ust for p in positionen), 2),
                        "Summe der Steuerzeilen", z.nr, z.text, z.konf)
        satz_d = Deutung(gross.satz, "größter Anteil der Steuertabelle",
                         z.nr, z.text, z.konf)
        aufzaehlung = ", ".join(
            f"{p.satz} % auf {_de(p.brutto)}" for p in sorted(
                positionen, key=lambda p: -p.netto))
        notizen.append(f"Zwei Steuersätze auf einem Beleg ({aufzaehlung}) — "
                       "gebucht wird je Satz eine eigene Zeile.")
        summe = round(sum(p.brutto for p in positionen), 2)
        if brutto is not None and abs(summe - brutto) > CENT:
            notizen.append(
                f"Die Steuerzeilen ergeben zusammen {_de(summe)}, als Betrag "
                f"steht {_de(brutto)} da.")
        return satz_d, ust_d, netto_d, notizen, positionen

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
                    return satz_d, ust_d, netto_d, notizen, positionen
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
                return satz_d, ust_d, netto_d, notizen, positionen
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

    # Kein Wort von Steuer auf dem ganzen Beleg? Dann sind es 0 %.
    #
    # Bis zum 23.08.2026 wurden hier 19 % angenommen und aus dem Brutto
    # herausgerechnet. Das ist im Salon regelmäßig falsch: Porto, Versiche-
    # rung, Miete, Beiträge, Bankgebühren und alles von Kleinunternehmern
    # tragen keine Umsatzsteuer. Was die Annahme erzeugte, war Vorsteuer,
    # die es nie gab — und die zieht man nicht ab, sie wird zurückgefordert.
    #
    # „Beziffert" heißt: irgendwo steht ein Steuersatz oder ein Betrag in
    # einer Steuer- oder Nettozeile. Der bloße Satz „keine Umsatzsteuer
    # ausgewiesen" enthält zwar das Wort, aber keine Zahl — und ist damit
    # genau das Gegenteil eines Steuerausweises.
    steuer_beziffert = bool(satz_d) or any(
        betraege_in_zeile(z) for z in steuerzeilen + nettozeilen)
    if brutto is not None and not steuer_beziffert:
        ansage = _kein_steuerausweis(zeilen)
        grund = ("Der Beleg weist keine Umsatzsteuer aus"
                 + (f": „{ansage.text}“" if ansage else ""))
        ort = (ansage.nr, ansage.text, ansage.konf) if ansage else (None, "", 0.0)
        satz_d = Deutung(0, grund, *ort)
        ust_d = Deutung(0.0, grund, *ort)
        netto_d = Deutung(brutto, "ohne Steuerausweis ist netto gleich brutto", *ort)
        notizen.append(grund + " — gebucht wird mit 0 %; es gibt keine "
                       "Vorsteuer abzuziehen.")
        return satz_d, ust_d, netto_d, notizen, positionen

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

    return satz_d, ust_d, netto_d, notizen, positionen


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
    """Satzzeichen am Rand entfernen — aber nicht den Punkt einer Abkürzung.

    „Blumen Hofmann e.K." wurde zu „Blumen Hofmann e.K": der Schlusspunkt
    gehört zur Rechtsform, nicht zur Zeichensetzung. Auf einer Rechnung ist
    das ein Zeichen zu wenig am Firmennamen.
    """
    t = re.sub(r"\s{2,}", " ", text).strip(" ,:;-—·|")
    while t.endswith(".") and not _abkuerzung(t):
        t = t[:-1].rstrip(" ,:;-—·|")
    return t.strip(" ,:;-—·|")[:80]


# Endungen, deren Punkt zum Namen gehört. Eine Liste statt eines Musters:
# „e.Kfr." und „GmbH." unterscheiden sich nicht in der Form, sondern darin,
# was sie bedeuten — und das weiß nur, wer die Rechtsformen kennt.
# Nur wirklich gepunktete Abkürzungen. „GmbH" und „KGaA" schreibt man ohne
# Schlusspunkt — stünde „mbh." hier, bliebe aus „Müller GmbH." fälschlich
# „Müller GmbH." stehen.
ABKUERZUNG_ENDE = ("e.k.", "e.kfr.", "e.kfm.", "i.g.", "co.", "u.a.", "a.d.")


def _abkuerzung(text: str) -> bool:
    flach = _flach(text)
    return any(flach.endswith(a) for a in ABKUERZUNG_ENDE)


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


# ── Die Rechenproben ─────────────────────────────────────────────────────────
#
# Nina, 22.08.2026: „Manchmal steht ein völlig falscher Endbetrag da." Das
# Tückische daran: die Zahl steht an der richtigen Stelle, sie ist plausibel,
# und Netto und Steuer lassen sich aus ihr zurückrechnen — die Rechnung geht
# scheinbar auf, weil sie sich selbst bestätigt.
#
# Auffliegen kann so ein Betrag nur an dem, was unabhängig von ihm auf dem
# Beleg steht: an den Einzelposten darüber und am Bargeld darunter. Deshalb
# genügt eine Probe nicht, es braucht die, die nicht aus dem Endbetrag
# abgeleitet sind.


def abschlussblock(zeilen: list[Zeile], tabellenzeilen: set[int]) -> int | None:
    """Ab welcher Zeile der Beleg zusammenrechnet, statt aufzulisten.

    Alles darüber sind Posten, alles darunter sind Summen. Die Grenze ist
    die erste Zeile, die einen Betrag trägt und dabei von Summe, Steuer oder
    Netto spricht — oder eine Steuertabellenzeile ist.
    """
    for z in zeilen:
        if z.nr in tabellenzeilen:
            return z.nr
        if not betraege_in_zeile(z) or _enthaelt(z.text, FUSSZEILE):
            continue
        if (_enthaelt(z.text, SUMMENWORT) or _enthaelt(z.text, STEUERWORT)
                or _enthaelt(z.text, NETTOWORT)):
            return z.nr
    return None


def einzelposten_probe(zeilen: list[Zeile], spalte: float | None,
                       blattbreite: float, brutto_d: Deutung,
                       netto: float | None,
                       tabellenzeilen: set[int]) -> Probe | None:
    """Ergeben die Posten über der Summe genau das, was ausgewiesen ist?

    Das ist die einzige Probe, die einen verlesenen Endbetrag wirklich
    fängt: die Posten stehen auf dem Blatt, unabhängig von ihm.

    Gerechnet wird nur, wo sich sauber rechnen lässt — es braucht eine
    Betragsspalte, und jede Postenzeile darf genau einen Betrag darin haben.
    Sobald ein Rabatt, ein Pfand oder eine Zwischensumme dazwischensteht,
    ist die Summe der Spalte nicht mehr der Rechnungsbetrag. Dann wird
    nichts behauptet: eine Probe, die falschen Alarm schlägt, wird nach dem
    dritten Mal nicht mehr gelesen.
    """
    if spalte is None or brutto_d.wert is None or brutto_d.zeile_nr is None:
        return None
    bis = brutto_d.zeile_nr
    grenze = abschlussblock(zeilen, tabellenzeilen)
    if grenze is not None:
        bis = min(bis, grenze)

    posten: list[tuple[Zeile, Betrag]] = []
    for z in zeilen:
        if z.nr >= bis:
            break
        if _enthaelt(z.text, FUSSZEILE):
            continue
        in_spalte = [b for b in betraege_in_zeile(z)
                     if abs(b.x1 - spalte) <= blattbreite * 0.04]
        if not in_spalte:
            continue
        if len(in_spalte) > 1:
            return None                     # keine saubere Spalte
        if (_enthaelt(z.text, KEINE_SUMME) or _enthaelt(z.text, SUMMENWORT)
                or _enthaelt(z.text, STEUERWORT) or _enthaelt(z.text, NETTOWORT)):
            return None                     # Rabatt, Pfand, Zwischensumme …
        if re.search(r"[-−]\s*\d", z.text):
            return None                     # Abzüge lassen sich nicht addieren
        posten.append((z, in_spalte[0]))

    if not posten:
        return None
    summe = round(sum(b.wert for _, b in posten), 2)
    gerechnet = " + ".join(f"{b.wert:.2f}".replace(".", ",") for _, b in posten)
    if abs(summe - brutto_d.wert) <= CENT:
        return Probe("Einzelposten", True,
                     f"Die Posten ergeben zusammen {_de(summe)} — genau den "
                     "ausgewiesenen Rechnungsbetrag", posten[-1][0].nr)
    if netto is not None and abs(summe - netto) <= CENT:
        return Probe("Einzelposten", True,
                     f"Die Posten ergeben zusammen {_de(summe)} — genau die "
                     "ausgewiesene Nettosumme", posten[-1][0].nr)
    ausgewiesen = _de(brutto_d.wert)
    if netto is not None and abs(netto - brutto_d.wert) > CENT:
        ausgewiesen += f" (netto {_de(netto)})"
    return Probe("Einzelposten", False,
                 f"Die Posten {gerechnet} ergeben {_de(summe)}, ausgewiesen "
                 f"sind {ausgewiesen}", posten[-1][0].nr)


def bargeld_probe(zeilen: list[Zeile], brutto: float | None
                  ) -> tuple[Probe | None, list[str]]:
    """Gegeben minus Rückgeld muss sein, was zu zahlen war.

    Ein Barbeleg trägt seine Kontrolle unten mit sich. Wer 50 € hinlegt und
    5,50 € zurückbekommt, hat 44,50 € bezahlt — steht oben etwas anderes,
    ist eine der drei Zahlen falsch gelesen.

    Umgekehrt gilt das nicht: wer mehr gibt, als er zurückbekommt und zahlen
    musste, hat Trinkgeld gegeben. Das ist kein Lesefehler, sondern eine
    Notiz wert.
    """
    if brutto is None:
        return None, []

    def betrag_aus(woerter) -> tuple[float, Zeile] | None:
        for z in reversed(zeilen):
            if _enthaelt(z.text, FUSSZEILE) or not _enthaelt(z.text, woerter):
                continue
            bs = betraege_in_zeile(z)
            if bs:
                return max(b.wert for b in bs), z
        return None

    gegeben = betrag_aus(GEGEBENWORT)
    rueck = betrag_aus(RUECKGELDWORT)
    if gegeben is None or rueck is None:
        return None, []
    bezahlt = round(gegeben[0] - rueck[0], 2)
    if abs(bezahlt - brutto) <= CENT:
        return Probe("Bargeld", True,
                     f"Gegeben {_de(gegeben[0])} minus Rückgeld "
                     f"{_de(rueck[0])} ergibt {_de(bezahlt)} — den "
                     "ausgewiesenen Betrag", rueck[1].nr), []
    if bezahlt > brutto:
        return None, [f"Gegeben {_de(gegeben[0])} minus Rückgeld "
                      f"{_de(rueck[0])} ergibt {_de(bezahlt)}, zu zahlen waren "
                      f"{_de(brutto)} — die Differenz von "
                      f"{_de(round(bezahlt - brutto, 2))} ist vermutlich "
                      "Trinkgeld."]
    return Probe("Bargeld", False,
                 f"Gegeben {_de(gegeben[0])} minus Rückgeld {_de(rueck[0])} "
                 f"ergibt {_de(bezahlt)}, ausgewiesen sind {_de(brutto)}",
                 rueck[1].nr), []


def steuersatz_probe(netto: float | None, ust: float | None,
                     satz: int | None) -> Probe | None:
    """Passt die ausgewiesene Steuer zum ausgewiesenen Satz?

    Hier wird großzügiger gerechnet als bei den Posten: 7 % von 1,21 € sind
    8,47 Cent, auf dem Bon stehen 9. Das ist Rundung, kein Lesefehler. Sechs
    Euro Unterschied sind es nicht.
    """
    if netto is None or ust is None or satz is None or netto <= 0:
        return None
    erwartet = round(netto * satz / 100, 2)
    if abs(ust - erwartet) <= max(0.02, erwartet * 0.01):
        return Probe("Steuersatz", True,
                     f"{satz} % von {_de(netto)} sind {_de(erwartet)} — das "
                     "steht auch da")
    return Probe("Steuersatz", False,
                 f"{satz} % von {_de(netto)} wären {_de(erwartet)}, "
                 f"ausgewiesen sind {_de(ust)}")


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

    # Einmal suchen, zweimal gebraucht: die Deutung rechnet mit den Sätzen,
    # die Postenprobe muss wissen, wo die Steuertabelle anfängt.
    tabelle = steuerpositionen_finden(zeilen)
    brutto_d, notizen = deute_summe(zeilen, spalte, blattbreite)
    lesung.notizen += notizen
    satz_d, ust_d, netto_d, notizen, positionen = deute_steuer(
        zeilen, brutto_d.wert, tabelle)
    lesung.notizen += notizen
    lesung.steuerpositionen = positionen

    lesung.felder = {
        "lieferant": deute_lieferant(zeilen, blatthoehe),
        "beleg_nr": deute_nummer(zeilen),
        "datum": deute_datum(zeilen, heute),
        "brutto": brutto_d,
        "netto": netto_d,
        "ust": ust_d,
        "ust_satz": satz_d,
    }

    # ── Der Beleg rechnet sich selbst nach ──
    #
    # Vier Proben, und keine davon braucht eine fremde Quelle. Die erste
    # bestätigt sich unter Umständen selbst — Netto und Steuer stammen oft
    # aus dem Brutto —, deshalb zählen die anderen drei mit.
    if brutto_d.wert is not None:
        if netto_d.wert is not None and ust_d.wert is not None:
            geht_auf = abs(netto_d.wert + ust_d.wert - brutto_d.wert) <= RUNDUNG
            lesung.proben.append(Probe(
                "Netto + Steuer", geht_auf,
                f"Netto {_de(netto_d.wert)} plus Steuer {_de(ust_d.wert)} "
                + ("ergibt " if geht_auf else "ergibt nicht ")
                + _de(brutto_d.wert), brutto_d.zeile_nr))
        else:
            lesung.proben.append(Probe(
                "Netto + Steuer", False,
                "Netto und Steuer gehen nicht auf und wurden verworfen",
                brutto_d.zeile_nr))

    # Bei zwei Sätzen auf einem Beleg sagt die Summe nichts über den Satz —
    # 7 % von allem wäre falsch. Dann prüft jede Steuerzeile für sich.
    if len({p.satz for p in positionen}) > 1:
        for pos in positionen:
            p = steuersatz_probe(pos.netto, pos.ust, pos.satz)
            if p:
                lesung.proben.append(Probe(f"Steuersatz {pos.satz} %",
                                           p.bestanden, p.erklaerung))
    else:
        p = steuersatz_probe(netto_d.wert, ust_d.wert, satz_d.wert)
        if p:
            lesung.proben.append(p)
    p = einzelposten_probe(zeilen, spalte, blattbreite, brutto_d,
                           netto_d.wert, {z.nr for _, z in tabelle})
    if p:
        lesung.proben.append(p)
    p, hinweise = bargeld_probe(zeilen, brutto_d.wert)
    if p:
        lesung.proben.append(p)
    lesung.notizen += hinweise

    # Ohne die Netto-Steuer-Probe gibt es kein „geht auf": ein Beleg ohne
    # Betrag ist nicht geprüft, sondern ungelesen.
    hauptprobe = [p for p in lesung.proben if p.name == "Netto + Steuer"]
    probe_ok = bool(hauptprobe) and all(p.bestanden for p in lesung.proben)
    gescheitert = [p for p in lesung.proben if not p.bestanden]
    if gescheitert:
        regel = "; ".join(f"{p.name} geht nicht auf: {p.erklaerung}"
                          for p in gescheitert)
    elif lesung.proben:
        regel = "alle Proben gehen auf: " + ", ".join(p.name for p in lesung.proben)
    else:
        regel = "kein Betrag, nichts nachzurechnen"
    lesung.felder["summenprobe_ok"] = Deutung(probe_ok, regel)
    for p in lesung.proben:
        lesung.notizen.append(f"Probe {p.name}: {p.erklaerung}"
                              + ("." if p.bestanden else " — das geht nicht auf."))

    for name, klartext in (("lieferant", "Wer den Beleg ausgestellt hat"),
                           ("datum", "Das Belegdatum"),
                           ("brutto", "Der Rechnungsbetrag")):
        if not lesung.felder[name]:
            lesung.offen.append(f"{klartext} ist nicht sicher zu lesen.")
    # Welche Probe gescheitert ist, gehört in die Rückfrage. „Summenprobe
    # nicht bestanden" schickt Nina auf die Suche; „die Posten ergeben
    # 33,61 €, ausgewiesen sind 90,00 €" zeigt ihr die Zeile.
    for p in gescheitert:
        lesung.offen.append(f"{p.name}: {p.erklaerung} — bitte prüfen.")
    if (satz_d.wert == 0 and brutto_d.wert is not None
            and brutto_d.wert > KLEINBETRAGSGRENZE):
        lesung.offen.append(
            f"Auf dem Beleg steht keine Umsatzsteuer, der Betrag ist mit "
            f"{_de(brutto_d.wert)} aber über der Kleinbetragsgrenze von "
            f"{_de(KLEINBETRAGSGRENZE)} — bitte prüfen, ob eine Rechnung mit "
            "Steuerausweis fehlt.")

    schwach = [z for z in zeilen if z.konf < 0.6]
    if schwach and len(schwach) > len(zeilen) / 3:
        lesung.offen.append(
            f"{len(schwach)} von {len(zeilen)} Zeilen wurden nur unsicher "
            "erkannt — ein schärferes Foto würde helfen.")

    return lesung
