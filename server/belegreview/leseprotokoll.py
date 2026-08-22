#!/usr/bin/env python3
"""Das Leseprotokoll — was hinter dem ⓘ steht.

Ein Beleg, den babu gelesen hat, wird zu Zahlen in einer Buchhaltung. Wer
diese Zahlen verantwortet, muss nachsehen können, woher sie kommen: aus
welcher Zeile, nach welcher Regel, wie sicher erkannt. Sonst bleibt nur
Vertrauen, und Vertrauen ist beim Finanzamt kein Beleg.

Deshalb schreibt babu zu jedem Beleg eine Markdown-Datei, die alles zeigt:
jede erkannte Zeile mit ihrer Konfidenz, jedes Feld mit seiner Herkunft,
die Steuerrechnung als Rechnung, und am Ende, was offen blieb. Sie ist für
Nina und Christoph geschrieben, nicht für Fachleute — deshalb steht neben
jeder Regel, was sie bedeutet.

Reines Formatieren: Text rein, Text raus.
"""
from __future__ import annotations

from datetime import datetime

from belegdeutung import Deutung, Lesung


def _geld(x) -> str:
    if x is None:
        return "—"
    return f"{x:,.2f} €".replace(",", "␣").replace(".", ",").replace("␣", ".")


def _konf(c: float) -> str:
    """Konfidenz als Wort — Prozentzahlen liest niemand gern."""
    if c >= 0.95:
        return "sicher"
    if c >= 0.85:
        return "gut"
    if c >= 0.70:
        return "brauchbar"
    if c >= 0.50:
        return "unsicher"
    return "kaum lesbar"


def _herkunft(d: Deutung | None) -> str:
    if d is None or d.wert is None:
        return "— " + (d.regel if d else "nicht gelesen")
    ort = f"Zeile {d.zeile_nr + 1}" if d.zeile_nr is not None else "gerechnet"
    return f"{ort} · {d.regel}"


def protokoll(lesung: Lesung, *, datei: str, engine: str, dauer_s: float,
              zusammenfassung: str | None = None,
              belegart: str | None = None, konto: str | None = None,
              steuerschluessel: str | None = None,
              gegenprobe: dict | None = None,
              widerspruch: list[str] | None = None,
              dokumentklasse: str | None = None,
              gelesen_am: str | None = None) -> str:
    """Das vollständige Protokoll als Markdown."""
    f = lesung.felder
    z = lesung.zeilen
    benutzt = {d.zeile_nr for d in f.values()
               if isinstance(d, Deutung) and d.zeile_nr is not None}

    t: list[str] = []
    t.append(f"# {datei}")
    t.append("")
    if zusammenfassung:
        t.append(f"**{zusammenfassung.strip()}**")
        t.append("")
    t.append("Dieses Protokoll zeigt vollständig, was babu auf dem Beleg gelesen "
             "hat und wie daraus die Zahlen wurden. Jede Angabe nennt die Zeile, "
             "aus der sie stammt.")
    t.append("")

    # ── Was babu daraus gemacht hat ──
    t.append("## Das Ergebnis")
    t.append("")
    t.append("| Feld | Wert | Woher |")
    t.append("|---|---|---|")
    zeilen_def = [
        ("Lieferant", f.get("lieferant"), lambda d: d.wert or "—"),
        ("Beleg-Nr.", f.get("beleg_nr"), lambda d: d.wert or "—"),
        ("Datum", f.get("datum"), lambda d: _datum_lang(d.wert)),
        ("Rechnungsbetrag", f.get("brutto"), lambda d: _geld(d.wert)),
        ("davon netto", f.get("netto"), lambda d: _geld(d.wert)),
        ("davon Umsatzsteuer", f.get("ust"), lambda d: _geld(d.wert)),
        ("Steuersatz", f.get("ust_satz"),
         lambda d: f"{d.wert} %" if d.wert is not None else "—"),
    ]
    for name, d, zeig in zeilen_def:
        wert = zeig(d) if d and d.wert is not None else "—"
        t.append(f"| {name} | {wert} | {_herkunft(d)} |")
    if belegart:
        t.append(f"| Belegart | {belegart} | Bedeutungsvergleich mit dem babu-Katalog |")
    if konto:
        t.append(f"| Konto (SKR04) | {konto} | folgt aus der Belegart |")
    if steuerschluessel:
        t.append(f"| Steuerschlüssel | {steuerschluessel} | folgt aus dem Steuersatz |")
    t.append("")

    # ── Die Rechnung, nachgerechnet ──
    brutto = f.get("brutto").wert if f.get("brutto") else None
    netto = f.get("netto").wert if f.get("netto") else None
    ust = f.get("ust").wert if f.get("ust") else None
    satz = f.get("ust_satz").wert if f.get("ust_satz") else None
    t.append("## Die Steuerrechnung")
    t.append("")
    if netto is not None and ust is not None and brutto is not None:
        stimmt = abs(netto + ust - brutto) < 0.011
        t.append(f"    Netto      {_geld(netto):>14}")
        t.append(f"  + Steuer     {_geld(ust):>14}"
                 + (f"   ({satz} % von {_geld(netto)})" if satz else ""))
        t.append("    " + "─" * 25)
        t.append(f"  = Brutto     {_geld(brutto):>14}   "
                 + ("✓ geht auf" if stimmt else "✗ geht NICHT auf"))
        t.append("")
        if not stimmt:
            t.append("Die Aufteilung passt nicht zum Rechnungsbetrag. Solange das "
                     "so ist, ist die Vorsteuer nicht verlässlich — bitte den "
                     "Beleg ansehen.")
            t.append("")
    elif brutto is not None:
        t.append(f"Rechnungsbetrag: **{_geld(brutto)}**. Eine belastbare "
                 "Aufteilung in Netto und Steuer war nicht zu ermitteln.")
        t.append("")
        for n in lesung.notizen:
            if "Summenprobe" in n or "ergibt nicht" in n or "gesetzlicher Satz" in n:
                t.append(f"> {n}")
                t.append("")
        t.append("Ohne gesicherte Aufteilung ist die Vorsteuer nicht "
                 "verlässlich — bitte den Beleg ansehen.")
        t.append("")
    else:
        t.append("Auf dem Beleg war kein Betrag zu finden.")
        t.append("")

    # ── Wie babu den Beleg gelesen hat ──
    if lesung.notizen:
        t.append("## Wie babu den Beleg gelesen hat")
        t.append("")
        for n in lesung.notizen:
            t.append(f"- {n}")
        t.append("")

    # ── Die Gegenprobe ──
    if gegenprobe or widerspruch:
        t.append("## Die Gegenprobe")
        t.append("")
        t.append("Zusätzlich sieht sich ein Bildmodell denselben Beleg an. Es "
                 "entscheidet nichts — es meldet nur, wenn es etwas anderes "
                 "liest.")
        t.append("")
        if gegenprobe:
            t.append("| Feld | Gegenprobe |")
            t.append("|---|---|")
            for schluessel, name in (("lieferant", "Lieferant"),
                                     ("beleg_nr", "Beleg-Nr."),
                                     ("datum", "Datum"),
                                     ("brutto", "Rechnungsbetrag"),
                                     ("netto", "netto"), ("ust", "Umsatzsteuer")):
                wert = gegenprobe.get(schluessel)
                if wert not in (None, ""):
                    t.append(f"| {name} | {wert} |")
            t.append("")
        if widerspruch:
            t.append("**Abweichungen:**")
            t.append("")
            for w in widerspruch:
                t.append(f"- {w}")
            t.append("")
            t.append("Gültig ist, was oben steht — das ist die Lesung aus dem "
                     "Beleg selbst, mit Zeilenangabe. Die Abweichung ist ein "
                     "Grund hinzusehen, keine Korrektur.")
            t.append("")
        else:
            t.append("Keine Abweichung — beide lesen dasselbe.")
            t.append("")

    # ── Offen ──
    if lesung.offen:
        t.append("## Was offen ist")
        t.append("")
        for o in lesung.offen:
            t.append(f"- {o}")
        t.append("")

    # ── Der volle Text ──
    t.append("## Jede erkannte Zeile")
    t.append("")
    t.append(f"{len(z)} Zeilen. Ein **›** markiert eine Zeile, aus der oben ein "
             "Wert stammt.")
    t.append("")
    t.append("| # | | Text | Erkennung |")
    t.append("|---:|---|---|---|")
    for zl in z:
        marke = "›" if zl.nr in benutzt else ""
        text = zl.text.replace("|", "\\|") or "&nbsp;"
        t.append(f"| {zl.nr + 1} | {marke} | {text} | {_konf(zl.konf)} "
                 f"({zl.konf:.0%}) |")
    t.append("")

    # ── Technik ──
    t.append("## Technik")
    t.append("")
    t.append(f"- Texterkennung: {engine}")
    t.append(f"- Dauer der Erkennung: {dauer_s:.2f} s")
    if dokumentklasse:
        t.append(f"- Dokumentklasse: {dokumentklasse}")
    if z:
        schnitt = sum(x.konf for x in z) / len(z)
        t.append(f"- Erkennungsgüte im Schnitt: {schnitt:.0%} ({_konf(schnitt)})")
    t.append(f"- Gelesen am: {_zeit_lang(gelesen_am)}")
    t.append("")
    return "\n".join(t) + "\n"


MONATSNAMEN = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember")


def _datum_lang(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso).date()
    except ValueError:
        return iso
    return f"{d.day}. {MONATSNAMEN[d.month - 1]} {d.year}"


def _zeit_lang(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return (f"{d.day}. {MONATSNAMEN[d.month - 1]} {d.year}, "
            f"{d.hour:02d}:{d.minute:02d} Uhr")
