#!/usr/bin/env python3
"""Das Anlagenverzeichnis — was über 800 € gekauft wurde, und was übrig ist.

`kontierung.py` entscheidet seit 22.08.2026 richtig, dass ein Gegenstand über
800 € netto je Stück Anlagevermögen ist. Danach verschwand er: keine Liste,
keine Nutzungsdauer, keine Abschreibung. Das ist die Lücke, die dieses Modul
schließt — und sie ist keine Kleinigkeit. Bei einer Betriebsprüfung ist das
Anlagenverzeichnis das Erste, wonach gefragt wird, und ohne Abschreibung
verschenkt der Betrieb jedes Jahr Betriebsausgaben.

Drei Dinge, die hier bewusst so sind:

1. **Die Nutzungsdauer wird nicht geraten.** Sie kommt aus der amtlichen
   AfA-Tabelle. Wo babu den Wert sicher kennt, steht er samt Quelle da; wo
   nicht, kommt eine Rückfrage statt einer Zahl — genau wie `kontierung.py`
   es mit `geprueft` hält. Eine erfundene Nutzungsdauer verschiebt Gewinn über
   Jahre und fällt niemandem auf, bis die Prüfung kommt.

   Was babu vom Friseurhandwerk NICHT weiß, weiß es ausdrücklich nicht: für
   Frisierstühle, Trockenhauben, Waschanlagen und bewegliche Ladeneinrichtung
   gibt es eine Branchentabelle, und die liegt hier nicht vor. Lieber eine
   Frage an die Steuerberatung als eine Zahl aus dem Bauch.

2. **Gerechnet wird in ganzen Cent, nie in Fließkomma.** Ein Cent Differenz im
   Anlagenverzeichnis ist ein Fehler in der Bilanz. Der Anschaffungswert steht
   als `int` in Cent, gerundet wird kaufmännisch über `geld.py`.

3. **Die Summe stimmt immer.** Die Jahresbeträge addieren sich exakt auf den
   Anschaffungswert; die Rundungsdifferenz trägt das letzte Jahr. Der
   Restbuchwert endet auf null.

Abgeschrieben wird linear und im Anschaffungsjahr zeitanteilig monatsgenau
(§ 7 Abs. 1 EStG): der Anschaffungsmonat zählt ganz mit, ein Kauf im Oktober
bringt also drei Zwölftel. Deshalb läuft ein Gut mit n Jahren Nutzungsdauer
über n+1 Kalenderjahre, wenn es nicht im Januar gekauft wurde.

Kein Erinnerungswert von 1 €: babu schreibt bis auf null ab. Wer den
Erinnerungswert führen will, trägt ihn in der Kanzlei nach — ihn hier
einzubauen hieße, eine Konvention zur Regel zu machen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import geld
from kontierung import GWG_GRENZE

MONATE = Decimal(12)


def cent(betrag) -> int:
    """Ein Euro-Betrag als ganze Cent, kaufmännisch gerundet."""
    return geld.rund_cent(geld.dez(str(betrag).replace(",", ".").strip()) * 100)


def euro(cent_betrag: int) -> Decimal:
    """Ganze Cent als Euro-`Decimal` — für Ausgabe und Vergleich."""
    return (Decimal(int(cent_betrag)) / 100).quantize(Decimal("0.01"))


# ── Die AfA-Tabelle, so weit babu sie sicher kennt ───────────────────────────

@dataclass(frozen=True)
class Nutzungsdauer:
    """Wie lange ein Gegenstand abgeschrieben wird — und woher das kommt."""
    code: str
    name: str
    jahre: int | None
    geprueft: bool = False
    quelle: str = ""
    hinweis: str = ""


_N = [
    # ── Bestätigt: allgemein verwendbare Anlagegüter ──────────────────────
    Nutzungsdauer(
        "computer", "Computer, Tablet, Drucker, Software", 1, geprueft=True,
        quelle="BMF-Schreiben vom 22.02.2022 (Computerhardware und Software)",
        hinweis="Im Anschaffungsjahr darf auch der volle Betrag abgesetzt "
                "werden; babu rechnet zeitanteilig, das ist der sichere Weg."),
    Nutzungsdauer(
        "bueromoebel", "Büromöbel", 13, geprueft=True,
        quelle="AfA-Tabelle AV (allgemein verwendbare Anlagegüter)"),
    Nutzungsdauer(
        "ladeneinbauten", "Ladeneinbauten und Schaufensteranlagen", 8,
        geprueft=True,
        quelle="AfA-Tabelle AV (allgemein verwendbare Anlagegüter)",
        hinweis="Fest eingebaut. Bewegliche Einrichtung ist etwas anderes — "
                "dafür gilt die Branchentabelle."),
    Nutzungsdauer(
        "pkw", "Personenkraftwagen", 6, geprueft=True,
        quelle="AfA-Tabelle AV (allgemein verwendbare Anlagegüter)"),

    # ── Nicht bestätigt: das Friseurhandwerk hat eine eigene Tabelle, und
    #    die liegt hier nicht vor. Kein Vorschlagswert — er sähe aus wie
    #    Wissen und wäre geraten.
    Nutzungsdauer(
        "frisierstuhl", "Frisierstuhl, Bedienungsstuhl", None,
        hinweis="Steht in der amtlichen AfA-Tabelle für das Friseurgewerbe. "
                "Deine Steuerberatung hat sie — einmal nachfragen, dann steht "
                "sie hier für immer."),
    Nutzungsdauer(
        "waschanlage", "Waschsessel, Waschbecken, Waschanlage", None,
        hinweis="Branchentabelle Friseurgewerbe. Bei fest verbauten Anlagen "
                "kann auch die Nutzungsdauer für Ladeneinbauten gelten — das "
                "gehört einmal geklärt."),
    Nutzungsdauer(
        "trockenhaube", "Trockenhaube, Klimazon, Trockenhelm", None,
        hinweis="Branchentabelle Friseurgewerbe — bitte bestätigen lassen."),
    Nutzungsdauer(
        "ladeneinrichtung", "Ladeneinrichtung (beweglich)", None,
        hinweis="Nicht dasselbe wie Ladeneinbauten. Was sich wegtragen lässt, "
                "läuft über die Branchentabelle."),
    Nutzungsdauer(
        "klimageraet", "Klimagerät", None,
        hinweis="Fest eingebaut oder mobil macht hier einen Unterschied — "
                "beides bitte in der AfA-Tabelle nachsehen lassen."),
    Nutzungsdauer(
        "sonstiges", "Etwas anderes", None,
        hinweis="Für alles, was oben nicht steht, braucht babu die "
                "Nutzungsdauer aus der AfA-Tabelle."),
]

NUTZUNGSDAUER: dict[str, Nutzungsdauer] = {n.code: n for n in _N}


def ungepruefte_nutzungsdauern() -> list[Nutzungsdauer]:
    """Was eine Steuerberatung noch bestätigen muss. Ehrlich statt still."""
    return [n for n in NUTZUNGSDAUER.values() if not n.geprueft]


# ── Ein Anlagegut ────────────────────────────────────────────────────────────

def _datum(roh) -> date | None:
    """`JJJJ-MM-TT` oder `TT.MM.JJJJ` — sonst nichts."""
    text = str(roh or "").strip()
    for form in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return date(*[int(t) for t in _zerlegen(text, form)])
        except (ValueError, TypeError):
            continue
    return None


def _zerlegen(text: str, form: str) -> tuple[int, int, int]:
    if form == "%Y-%m-%d":
        j, m, t = text.split("-")
    else:
        t, m, j = text.split(".")
    return int(j), int(m), int(t)


@dataclass
class Anlagegut:
    """Ein Gegenstand im Anlagevermögen.

    `wert_cent` ist der Anschaffungswert NETTO — die Vorsteuer ist keine
    Anschaffungskosten, sie wird im Anschaffungsmonat gezogen. Unterhalb der
    GWG-Grenze gibt es hier nichts zu suchen: was bis 800 € netto kostet, ist
    im Jahr der Anschaffung voll abgesetzt und wird nie ein Anlagegut.
    """
    bezeichnung: str
    angeschafft: str
    wert_cent: int
    nutzungsdauer: int | None = None
    art: str | None = None
    beleg: str | None = None          # Stamm des Belegs in der Belegbox
    notiz: str = ""
    abgang: str | None = None         # verkauft, verschrottet, entnommen
    kennung: int | None = None        # Zeilennummer in portal.db
    rueckfrage: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if int(self.wert_cent) <= cent(GWG_GRENZE):
            raise ValueError(
                f"{euro(self.wert_cent)} € netto liegt bei oder unter der "
                f"GWG-Grenze von {GWG_GRENZE} € — das ist kein Anlagegut, "
                f"sondern im Jahr der Anschaffung voll abgesetzt.")
        self.wert_cent = int(self.wert_cent)
        if self.nutzungsdauer is None and self.art in NUTZUNGSDAUER:
            self.nutzungsdauer = NUTZUNGSDAUER[self.art].jahre
        self.rueckfrage = self._was_fehlt()

    def _was_fehlt(self) -> str | None:
        if _datum(self.angeschafft) is None:
            return ("Wann hast du das gekauft? babu braucht das Datum als "
                    "Tag, Monat und Jahr — im Anschaffungsjahr wird "
                    "monatsgenau abgeschrieben.")
        if not self.nutzungsdauer or int(self.nutzungsdauer) < 1:
            art = NUTZUNGSDAUER.get(self.art or "")
            zusatz = f" {art.hinweis}" if art and art.hinweis else ""
            return (f"Über wie viele Jahre wird „{self.bezeichnung}“ "
                    f"abgeschrieben?{zusatz}")
        return None

    @property
    def datum(self) -> date | None:
        return _datum(self.angeschafft)

    @property
    def abgang_datum(self) -> date | None:
        return _datum(self.abgang)

    @property
    def quelle(self) -> str:
        """Woher die Nutzungsdauer kommt — leer, wenn von Hand eingetragen."""
        art = NUTZUNGSDAUER.get(self.art or "")
        if art and art.geprueft and art.jahre == self.nutzungsdauer:
            return art.quelle
        return ""

    @property
    def geprueft(self) -> bool:
        return bool(self.quelle)


# ── Der Abschreibungsplan ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Jahreszeile:
    jahr: int
    afa_cent: int
    restbuchwert_cent: int


def plan(gut: Anlagegut) -> list[Jahreszeile]:
    """Jahr für Jahr: Abschreibung und Restbuchwert.

    Leer, solange etwas fehlt — ein Plan aus einer geratenen Nutzungsdauer
    wäre schlimmer als gar keiner, weil er wie eine Auskunft aussähe.
    """
    if gut.rueckfrage or gut.datum is None or not gut.nutzungsdauer:
        return []

    jahre = int(gut.nutzungsdauer)
    gesamt = int(gut.wert_cent)
    voll = geld.dez(gesamt) / geld.dez(jahre)
    # Der Anschaffungsmonat zählt ganz mit: Kauf im Oktober = 13 − 10 = 3/12.
    erste_monate = MONATE - geld.dez(gut.datum.month) + 1

    zeilen: list[Jahreszeile] = []
    verbraucht = 0
    start = gut.datum.year
    # Ein Jahr mehr als die Nutzungsdauer: der im Anschaffungsjahr fehlende
    # Teil läuft hinten heraus. Bei einem Januarkauf ist die letzte Zeile null
    # und fällt unten weg.
    for versatz in range(jahre + 1):
        offen = gesamt - verbraucht
        if offen <= 0:
            break
        if versatz == 0:
            betrag = geld.rund_cent(voll * erste_monate / MONATE)
        elif versatz == jahre:
            betrag = offen                      # der Rest, auf den Cent
        else:
            betrag = geld.rund_cent(voll)
        betrag = min(betrag, offen)
        verbraucht += betrag
        zeilen.append(Jahreszeile(start + versatz, betrag, gesamt - verbraucht))
    return zeilen


def afa_im_jahr(gut: Anlagegut, jahr: int) -> int:
    """Die Abschreibung dieses Jahres in Cent — 0, wenn es keine gibt."""
    for z in plan(gut):
        if z.jahr == jahr:
            return z.afa_cent
    return 0


def restbuchwert_cent(gut: Anlagegut, jahr: int) -> int:
    """Was am 31.12. dieses Jahres noch in den Büchern steht."""
    zeilen = plan(gut)
    if not zeilen:
        return int(gut.wert_cent)
    if jahr < zeilen[0].jahr:
        return int(gut.wert_cent)      # gab es noch nicht
    letzter = zeilen[-1].restbuchwert_cent
    for z in zeilen:
        if z.jahr == jahr:
            return z.restbuchwert_cent
    return letzter


# ── Das Verzeichnis ──────────────────────────────────────────────────────────

def _im_jahr(gut: Anlagegut, jahr: int) -> bool:
    """War dieses Gut in diesem Jahr im Betrieb?

    Ein Abgang löscht nichts rückwirkend: was 2026 da war, steht 2026 im
    Verzeichnis, auch wenn es 2027 verkauft wurde. Sonst fehlte es genau in
    der Prüfung des Jahres, in dem es abgeschrieben wurde.
    """
    gekauft = gut.datum
    if gekauft is None or gekauft.year > jahr:
        return False
    weg = gut.abgang_datum
    return not (weg and weg.year < jahr)


def zeile(gut: Anlagegut, jahr: int) -> dict:
    """Ein Anlagegut als Zeile des Verzeichnisses."""
    return {
        "kennung": gut.kennung,
        "bezeichnung": gut.bezeichnung,
        "art": gut.art,
        "angeschafft": gut.angeschafft,
        "anschaffungswert": f"{euro(gut.wert_cent)}",
        "anschaffungswert_cent": int(gut.wert_cent),
        "nutzungsdauer": gut.nutzungsdauer,
        "nutzungsdauer_quelle": gut.quelle,
        "nutzungsdauer_geprueft": gut.geprueft,
        "afa": f"{euro(afa_im_jahr(gut, jahr))}",
        "afa_cent": afa_im_jahr(gut, jahr),
        "restbuchwert": f"{euro(restbuchwert_cent(gut, jahr))}",
        "restbuchwert_cent": restbuchwert_cent(gut, jahr),
        "beleg": gut.beleg,
        "abgang": gut.abgang,
        "notiz": gut.notiz,
        "rueckfrage": gut.rueckfrage,
    }


def verzeichnis(gueter: list[Anlagegut], jahr: int) -> dict:
    """Das Anlagenverzeichnis eines Jahres, fertig zum Anzeigen und Ausgeben."""
    zeilen = [zeile(g, jahr) for g in gueter if _im_jahr(g, jahr)]
    return {
        "jahr": jahr,
        "anlagen": zeilen,
        "offen": sum(1 for z in zeilen if z["rueckfrage"]),
        "summe": {
            "anschaffungswert_cent": sum(z["anschaffungswert_cent"] for z in zeilen),
            "afa_cent": sum(z["afa_cent"] for z in zeilen),
            "restbuchwert_cent": sum(z["restbuchwert_cent"] for z in zeilen),
            "anschaffungswert": f"{euro(sum(z['anschaffungswert_cent'] for z in zeilen))}",
            "afa": f"{euro(sum(z['afa_cent'] for z in zeilen))}",
            "restbuchwert": f"{euro(sum(z['restbuchwert_cent'] for z in zeilen))}",
        },
    }


# ── Ausgabe ──────────────────────────────────────────────────────────────────

CSV_KOPF = ("Bezeichnung", "Anschaffungsdatum", "Anschaffungswert netto",
            "Nutzungsdauer (Jahre)", "AfA im Jahr", "Restbuchwert 31.12.",
            "Quelle Nutzungsdauer", "Beleg", "Offen")


def _zahl(betrag: str) -> str:
    """Deutsche Notation — Komma nur, wo wirklich eine Zahl steht.

    Getrennt vom Textfeld, weil ein blindes Punkt-zu-Komma aus
    „Frisierstuhl Nr. 3" ein „Nr, 3" machte und aus der Quellenangabe
    „22.02.2022" ein „22,02,2022".
    """
    return str(betrag).replace(".", ",")


# Excel liest ein Feld, das mit einem dieser Zeichen beginnt, als FORMEL.
# Dieselbe Falle wie beim Buchungsstapel (extf.FORMELZEICHEN): das
# Verzeichnis geht ans Steuerbüro und wird dort in Excel geöffnet, und die
# Bezeichnung tippt Nina frei. Hier bewusst noch einmal, statt extf zu
# importieren — das Anlagenverzeichnis soll nicht am DATEV-Writer hängen.
FORMELZEICHEN = ("=", "+", "-", "@", "\t", "\r", "\n")


def _text(wert) -> str:
    """Ein Freitextfeld: kein Spaltentrenner, keine Zeilenumbrüche, keine Formel."""
    sauber = str(wert or "").replace(";", ",").replace("\r", " ").replace("\n", " ")
    return ("'" + sauber) if sauber[:1] in FORMELZEICHEN else sauber


def als_csv(gueter: list[Anlagegut], jahr: int) -> str:
    """Das Verzeichnis als CSV — das, was in den Jahresabschluss geht.

    Semikolon und CRLF wie beim Buchungsstapel: die Datei wird beim
    Steuerberater in Excel geöffnet, und dort ist das die Sprache.
    """
    v = verzeichnis(gueter, jahr)
    zeilen = [";".join(CSV_KOPF)]
    for z in v["anlagen"]:
        zeilen.append(";".join((
            _text(z["bezeichnung"]),
            _text(z["angeschafft"]),
            _zahl(z["anschaffungswert"]),
            str(z["nutzungsdauer"] or ""),
            _zahl(z["afa"]),
            _zahl(z["restbuchwert"]),
            _text(z["nutzungsdauer_quelle"]),
            _text(z["beleg"]),
            _text(z["rueckfrage"]),
        )))
    s = v["summe"]
    zeilen.append(";".join(("Summe", "", _zahl(s["anschaffungswert"]), "",
                            _zahl(s["afa"]), _zahl(s["restbuchwert"]),
                            "", "", "")))
    return "\r\n".join(zeilen) + "\r\n"
