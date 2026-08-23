#!/usr/bin/env python3
"""Aus den Zahlen eines Jahres wird ein Bericht, den die Inhaberin versteht.

Das ist die Stufe nach `abschluss_lesen.py`: dort werden aus EÜR, Bescheid
und Kontenliste Zahlen; hier wird daraus etwas, das jemandem etwas sagt.

Der Anlass steht im Auftrag: wer babu ausprobiert, lädt auf der Startseite
seine letzten Jahre hoch und bekommt dafür einen Bericht. Dieser Bericht ist
das Versprechen — er muss also stimmen, und er muss die Dinge benennen, die
sonst niemand benennt.

Drei Regeln, an denen sich hier alles ausrichtet:

1. **Rechnen statt behaupten.** Jede Zahl im Bericht lässt sich aus den
   gelesenen Werten nachrechnen. Wo eine Angabe fehlt, fehlt die Aussage —
   sie wird nicht geschätzt.

2. **Kein erfundener Branchenvergleich.** „Ihr Wareneinsatz liegt über dem
   Branchenschnitt" klingt gut und ist ohne Quelle gelogen. Quoten werden
   ausgerechnet und hingestellt; bewertet wird nur, was sich aus dem Beleg
   selbst ergibt (ein Aufwand, der den Gewinn auffrisst; eine Probe, die
   nicht aufgeht; ein Verlust).

3. **Eine Abweichung ist erst ein Fehler, wenn sie keine Erklärung hat.**
   Beim ersten echten Abschluss, an dem das hier entstanden ist, wichen EÜR
   und Umsatzsteuererklärung um 10 Cent voneinander ab. Kein Fehler: das
   Formular rundet die Bemessungsgrundlage auf volle Euro. Ein naiver
   Prüfer hätte Alarm geschlagen. Deshalb kennt die Gegenprobe diesen Fall
   und erklärt ihn, statt ihn zu melden.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from geld import CENT, dez

# Der Regelsteuersatz. Steht hier als Konstante, weil die Gegenprobe ihn
# braucht — nicht, weil er geraten würde: welcher Satz galt, steht im Beleg.
REGELSATZ = Decimal("0.19")

# Ab welchem Anteil am Gewinn ein einzelner Kostenblock eine eigene Aussage
# wert ist. Kein Branchenwert, sondern eine Betrachtungsschwelle: wer die
# Hälfte seines Gewinns für eine einzige Sache ausgibt, sollte davon wissen.
AUFFAELLIG_AB = Decimal("0.30")


def _d(wert) -> Decimal | None:
    """Zahl aus dem Lesen → Decimal. Bei Geld hat float nichts zu suchen."""
    if wert is None:
        return None
    try:
        return dez(str(wert).replace(",", ".").strip())
    except Exception:  # noqa: BLE001
        return None


def cent(wert) -> Decimal:
    """Auf den Cent, kaufmännisch — geld.py liefert float, hier bleibt Decimal."""
    return dez(wert).quantize(CENT, rounding=ROUND_HALF_UP)


def _quote(teil, ganzes) -> Decimal | None:
    t, g = _d(teil), _d(ganzes)
    if t is None or not g:
        return None
    return t / g


def _prozent(q: Decimal | None, stellen: int = 1) -> str:
    if q is None:
        return "—"
    return f"{q * 100:.{stellen}f} %".replace(".", ",")


def _eur(wert) -> str:
    w = _d(wert)
    if w is None:
        return "—"
    s = f"{cent(w):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{s} €"


# ── Was der Bericht sagt ─────────────────────────────────────────────────────

@dataclass
class Kennzahl:
    """Eine ausgerechnete Zahl mit ihrem Anteil und dem Vorjahr daneben."""
    name: str
    wert: Decimal | None
    anteil_am_umsatz: Decimal | None = None
    vorjahr: Decimal | None = None

    @property
    def veraenderung(self) -> Decimal | None:
        """Wie viel mehr oder weniger als im Vorjahr, als Anteil."""
        if self.wert is None or not self.vorjahr:
            return None
        return (self.wert - self.vorjahr) / abs(self.vorjahr)


@dataclass
class Befund:
    """Etwas, das jemandem auffallen sollte — mit dem Rechenweg dabei."""
    schwere: str            # "hinweis" | "achtung" | "ernst"
    titel: str
    text: str
    rechenweg: str = ""


@dataclass
class Probe:
    """Eine Gegenprobe zwischen zwei Angaben, die zueinander passen müssen."""
    name: str
    bestanden: bool
    erklaerung: str
    erklaerbar: bool = False   # abweichend, aber mit bekannter Ursache


# ── Die Kennzahlen ───────────────────────────────────────────────────────────

# Was aus den gelesenen Feldern eine Zeile im Bericht wird. Die Namen sind die
# aus abschluss_lesen.py; steht ein Feld nicht drin, fehlt die Zeile.
ZEILEN = [
    ("umsatz", "Umsatz (netto)"),
    ("wareneinsatz", "Wareneinkauf"),
    ("personal", "Personal"),
    ("raumkosten", "Raum und Energie"),
    ("steuerberatung", "Steuerberatung und Buchführung"),
    ("afa", "Abschreibungen"),
    ("sonstige_kosten", "Übrige Kosten"),
    ("gewinn", "Gewinn"),
]


def kennzahlen(jahr: dict, vorjahr: dict | None = None) -> list[Kennzahl]:
    """Die Zahlen des Jahres, jede mit Anteil am Umsatz und Vorjahreswert."""
    vor = vorjahr or {}
    umsatz = _d(jahr.get("umsatz"))
    raus = []
    for schluessel, name in ZEILEN:
        wert = _d(jahr.get(schluessel))
        if wert is None:
            continue
        raus.append(Kennzahl(
            name=name, wert=wert,
            anteil_am_umsatz=None if schluessel == "umsatz" else _quote(wert, umsatz),
            vorjahr=_d(vor.get(schluessel))))
    return raus


# ── Die Gegenproben ──────────────────────────────────────────────────────────

def ust_gegenprobe(umsatz_netto, erklaerte_ust, satz: Decimal = REGELSATZ) -> Probe:
    """Passt die erklärte Umsatzsteuer zum Umsatz?

    Die Falle, die hier eingebaut ist, stammt aus dem ersten echten Fall:
    das Erklärungsformular trägt die Bemessungsgrundlage in VOLLEN EURO ein.
    Aus 172.807,49 € Umsatz werden dort 172.807 €, und daraus 32.833,33 €
    statt 32.833,42 €. Neun Cent Unterschied, die nach einem Lesefehler
    aussehen und keiner sind. Wer das nicht kennt, meldet einen Fehler, wo
    das Formular nur seine eigene Regel befolgt.
    """
    u, ust = _d(umsatz_netto), _d(erklaerte_ust)
    if u is None or ust is None:
        return Probe("Umsatzsteuer zum Umsatz", False,
                     "Nicht prüfbar — es fehlt eine der beiden Zahlen.")
    genau = cent(u * satz)
    auf_volle_euro = cent(int(u) * satz)
    if abs(genau - ust) <= Decimal("0.01"):
        return Probe("Umsatzsteuer zum Umsatz", True,
                     f"{_eur(u)} × {_prozent(satz, 0)} = {_eur(genau)} — passt.")
    if abs(auf_volle_euro - ust) <= Decimal("0.01"):
        return Probe(
            "Umsatzsteuer zum Umsatz", True,
            f"{_eur(ust)} statt {_eur(genau)} — die Differenz von "
            f"{_eur(abs(genau - ust))} kommt daher, dass die Erklärung die "
            f"Bemessungsgrundlage auf volle Euro abschneidet "
            f"({_eur(u)} → {int(u)} €). Das ist so vorgesehen.",
            erklaerbar=True)
    return Probe("Umsatzsteuer zum Umsatz", False,
                 f"Erwartet {_eur(genau)}, erklärt sind {_eur(ust)} — "
                 f"{_eur(abs(genau - ust))} Unterschied. Das erklärt sich "
                 f"nicht durch Rundung.")


def gewinn_gegenprobe(jahr: dict) -> Probe:
    """Einnahmen minus Ausgaben — kommt der ausgewiesene Gewinn heraus?

    Bewusst nur dann, wenn ALLE Posten vorliegen. Eine Probe über eine
    unvollständige Summe ist keine Probe, sondern ein Zufallsgenerator.
    """
    umsatz = _d(jahr.get("umsatz"))
    gewinn = _d(jahr.get("gewinn"))
    posten = ("wareneinsatz", "personal", "raumkosten", "steuerberatung",
              "afa", "sonstige_kosten")
    werte = {p: _d(jahr.get(p)) for p in posten}
    fehlend = [p for p, w in werte.items() if w is None]
    if umsatz is None or gewinn is None or fehlend:
        return Probe("Gewinn aus Einnahmen minus Ausgaben", False,
                     "Nicht prüfbar — es fehlen: " +
                     ", ".join(fehlend or ["Umsatz oder Gewinn"]) + ".")
    kosten = sum(abs(w) for w in werte.values())
    erwartet = cent(umsatz - kosten)
    # Fünf Cent, nicht ein Euro: über sechs Posten summieren sich Rundungen
    # auf wenige Cent, mehr nicht. Wer hier einen Euro durchgehen lässt,
    # findet den fehlenden Posten nie.
    if abs(erwartet - gewinn) <= Decimal("0.05"):
        return Probe("Gewinn aus Einnahmen minus Ausgaben", True,
                     f"{_eur(umsatz)} − {_eur(kosten)} = {_eur(erwartet)}, "
                     f"ausgewiesen {_eur(gewinn)} — passt.")
    return Probe("Gewinn aus Einnahmen minus Ausgaben", False,
                 f"{_eur(umsatz)} − {_eur(kosten)} = {_eur(erwartet)}, "
                 f"ausgewiesen ist {_eur(gewinn)}. Es fehlt ein Posten von "
                 f"{_eur(abs(erwartet - gewinn))}.")


def proben(jahr: dict) -> list[Probe]:
    """Alles, was sich aus dem Jahr selbst nachrechnen lässt."""
    raus = [gewinn_gegenprobe(jahr)]
    if jahr.get("ust_erklaert") is not None:
        raus.append(ust_gegenprobe(jahr.get("umsatz"), jahr.get("ust_erklaert")))
    return raus


# ── Die Befunde ──────────────────────────────────────────────────────────────

def befunde(jahr: dict, vorjahr: dict | None = None) -> list[Befund]:
    """Was jemandem auffallen sollte. Nur, was sich belegen lässt."""
    raus: list[Befund] = []
    umsatz = _d(jahr.get("umsatz"))
    gewinn = _d(jahr.get("gewinn"))
    beratung = _d(jahr.get("steuerberatung"))

    # ── Der teuerste Posten, den niemand hinterfragt ──────────────────────
    #
    # Das ist der Grund, warum es babu gibt, und es ist keine Behauptung,
    # sondern eine Division. Beim ersten echten Abschluss: 15.518,40 € für
    # Steuerberatung und Buchführung gegen 16.441,48 € Gewinn.
    if beratung and gewinn and gewinn > 0:
        anteil = beratung / gewinn
        if anteil >= AUFFAELLIG_AB:
            schwere = "ernst" if anteil >= Decimal("0.60") else "achtung"
            raus.append(Befund(
                schwere,
                "Die Steuerberatung kostet einen großen Teil des Gewinns",
                f"Für Steuerberatung, Abschluss und Buchführung sind "
                f"{_eur(beratung)} angefallen. Der Gewinn des Jahres beträgt "
                f"{_eur(gewinn)} — das sind {_prozent(anteil, 0)} des Gewinns "
                f"für die Verwaltung des Gewinns.",
                f"{_eur(beratung)} ÷ {_eur(gewinn)} = {_prozent(anteil)}"))
    if beratung and gewinn is not None and gewinn <= 0:
        raus.append(Befund(
            "ernst", "Steuerberatung trotz Verlust",
            f"Das Jahr endet mit {_eur(gewinn)}, für Steuerberatung und "
            f"Buchführung sind trotzdem {_eur(beratung)} angefallen."))

    # ── Verlust ───────────────────────────────────────────────────────────
    if gewinn is not None and gewinn < 0:
        raus.append(Befund(
            "ernst", "Das Jahr endet mit einem Verlust",
            f"Unter dem Strich stehen {_eur(gewinn)}."))

    # ── Wovon am meisten weggeht ──────────────────────────────────────────
    if umsatz:
        for schluessel, name in (("wareneinsatz", "Der Wareneinkauf"),
                                 ("personal", "Das Personal"),
                                 ("raumkosten", "Raum und Energie")):
            wert = _d(jahr.get(schluessel))
            q = _quote(wert, umsatz)
            if q is None:
                continue
            if q >= Decimal("0.50"):
                raus.append(Befund(
                    "achtung", f"{name} bindet die Hälfte des Umsatzes",
                    f"{_eur(wert)} von {_eur(umsatz)} — {_prozent(q)}.",
                    f"{_eur(wert)} ÷ {_eur(umsatz)} = {_prozent(q)}"))

    # ── Was sich gegenüber dem Vorjahr bewegt hat ─────────────────────────
    if vorjahr:
        vu = _d(vorjahr.get("umsatz"))
        if umsatz and vu:
            v = (umsatz - vu) / vu
            if abs(v) >= Decimal("0.20"):
                richtung = "gewachsen" if v > 0 else "zurückgegangen"
                raus.append(Befund(
                    "hinweis", f"Der Umsatz ist deutlich {richtung}",
                    f"Von {_eur(vu)} auf {_eur(umsatz)} — {_prozent(abs(v))} "
                    f"{'mehr' if v > 0 else 'weniger'}.",
                    f"({_eur(umsatz)} − {_eur(vu)}) ÷ {_eur(vu)} = {_prozent(v)}"))

    # ── Was die Proben sagen ──────────────────────────────────────────────
    for p in proben(jahr):
        if not p.bestanden and "Nicht prüfbar" not in p.erklaerung:
            raus.append(Befund("achtung", f"Gegenprobe: {p.name}",
                               p.erklaerung))

    return raus


# ── Der Bericht ──────────────────────────────────────────────────────────────

def bericht(jahr: dict, vorjahr: dict | None = None, *,
            titel: str = "Deine Auswertung", nur_anriss: bool = False) -> str:
    """Der Bericht als Markdown.

    `nur_anriss` ist der Teil, der auf der Startseite und in der E-Mail
    gezeigt wird, bevor sich jemand anmeldet: die Kennzahlen und der erste
    Befund. Der Rest kommt nach der Anmeldung — nicht als Trick, sondern
    weil dort erst feststeht, wem die Zahlen gehören.
    """
    z = [f"# {titel}", ""]
    jahreszahl = jahr.get("jahr")
    if jahreszahl:
        z.append(f"Für das Jahr **{jahreszahl}**.")
        z.append("")

    kz = kennzahlen(jahr, vorjahr)
    if kz:
        hat_vorjahr = any(k.vorjahr is not None for k in kz)
        kopf = "| | Betrag | Anteil am Umsatz |"
        trenn = "|---|---:|---:|"
        if hat_vorjahr:
            kopf += " Vorjahr |"
            trenn += "---:|"
        z += [kopf, trenn]
        for k in kz:
            zeile = f"| {k.name} | {_eur(k.wert)} | {_prozent(k.anteil_am_umsatz)} |"
            if hat_vorjahr:
                zeile += f" {_eur(k.vorjahr) if k.vorjahr is not None else '—'} |"
            z.append(zeile)
        z.append("")

    bf = befunde(jahr, vorjahr)
    if nur_anriss:
        bf = bf[:1]
    if bf:
        z += ["## Was auffällt", ""]
        for b in bf:
            z.append(f"**{b.titel}**")
            z.append("")
            z.append(b.text)
            if b.rechenweg:
                z.append("")
                z.append(f"> {b.rechenweg}")
            z.append("")

    if nur_anriss:
        z += ["---", "",
              "Der vollständige Bericht enthält alle Befunde, die Gegenproben "
              "und die Zahlen, die babu für dein Profil übernehmen kann.", ""]
        return "\n".join(z)

    pr = proben(jahr)
    if pr:
        z += ["## Die Gegenproben", "",
              "Der Abschluss prüft sich selbst — dafür braucht es keine "
              "fremde Quelle.", ""]
        for p in pr:
            zeichen = "✓" if p.bestanden else "×"
            wenn_erklaerbar = " *(erklärbar)*" if p.erklaerbar else ""
            z.append(f"- {zeichen} **{p.name}**{wenn_erklaerbar} — {p.erklaerung}")
        z.append("")

    return "\n".join(z)


# ── Was davon ins Profil darf ────────────────────────────────────────────────

# Die Felder, die sich aus einem Abschluss in die Stammdaten übernehmen
# lassen — und NUR die. Dieselbe Vorsicht wie in salonpruefung.ERLAUBT_JE_ART:
# aus einem Steuerbescheid lässt sich auch die Bankverbindung des Finanzamts
# lesen, und die gehört ganz sicher nicht in die Stammdaten des Salons.
UEBERNEHMBAR = ("betrieb_name", "rechtsform", "steuernummer", "finanzamt",
                "anschrift", "kleinunternehmer", "kontenrahmen",
                "gewerbesteuerpflichtig", "ist_versteuerung")


def uebernehmbare_felder(gelesen: dict) -> dict:
    """Was aus dem Gelesenen ins Profil darf — geputzt und begrenzt."""
    return {k: v for k, v in (gelesen or {}).items()
            if k in UEBERNEHMBAR and v not in (None, "", [])}
