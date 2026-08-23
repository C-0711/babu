#!/usr/bin/env python3
"""Was Nina auffällt, wird ein Vorgang — ohne dass sie etwas dafür tut.

Nina merkt Dinge, die niemand sonst merkt: dass ein Beleg falsch gelesen
wurde, dass ein Knopf fehlt, dass etwas umständlich ist. Bisher musste sie
das erzählen, und dann musste es jemand aufschreiben. Dazwischen ging es
verloren.

Jetzt schreibt sie es dort auf, wo es ihr auffällt — in der App oder im
Portal —, und es wird ein Vorgang in Fixit. Sie sieht ein Feld und einen
Knopf; alles Weitere passiert hier.

Der Teil, der Arbeit spart, ist nicht das Weiterreichen, sondern der
Zusammenhang: aus welcher Ansicht kam das, welches Gerät, welche Fassung,
welcher Beleg lag gerade offen. Wer eine Meldung bearbeitet, sucht sonst
zuerst danach — und fragt zurück, was Nina längst vergessen hat.

Reines Formatieren: Text rein, Vorgang raus. Kein Netz, keine Dateien.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ── Was daraus wird ──────────────────────────────────────────────────────────

# Fixits Typen. „Wunsch" ist bei Fixit eine Aufgabe — es gibt dort keinen
# eigenen Typ dafür, und einen zu erfinden hieße, eine fremde Ordnung zu
# verbiegen.
TYP = {"fehler": "bug", "wunsch": "task"}

# Woher die Meldung kam → in welchen Bereich sie gehört. Dieselben vier
# Bereiche, die Fixit kennt (App, Betrieb, Kassenbuch, Web).
BEREICH = {"app": "App", "portal": "Web"}

# Wie lang eine Überschrift sein darf, bevor sie in einer Liste abbricht.
TITEL_MAX = 72


@dataclass
class Meldung:
    """Was Nina abgeschickt hat, samt allem, was drumherum bekannt war."""
    text: str
    art: str = "fehler"          # „fehler" oder „wunsch"
    quelle: str = "app"          # „app" oder „portal"
    ansicht: str | None = None   # wo sie war, z. B. „Dokumente" oder „#belege"
    beleg: str | None = None     # welcher Beleg offen lag
    von: str | None = None       # Konto
    geraet: str | None = None    # „iPhone 15 Pro Max, iOS 26.6" o. ä.
    fassung: str | None = None   # Build der App


def titel_aus(text: str) -> str:
    """Die Überschrift ist Ninas erster Satz — nicht ein erfundener.

    Wer eine Meldung liest, soll ihre Worte sehen. Ein zusammengefasster
    Titel klingt glatter und verliert genau das, woran sie es wiedererkennt.
    """
    sauber = " ".join(text.split())
    if not sauber:
        return "Rückmeldung ohne Text"
    # Bis zum ersten Satzende, sonst bis zur Längengrenze am Wortende.
    m = re.match(r"(.{10,%d}?[.!?])(\s|$)" % TITEL_MAX, sauber)
    if m:
        return m.group(1).rstrip(" .")
    if len(sauber) <= TITEL_MAX:
        return sauber.rstrip(" .")
    schnitt = sauber[:TITEL_MAX].rsplit(" ", 1)[0]
    return (schnitt or sauber[:TITEL_MAX]).rstrip(" .,") + " …"


def _zeile(name: str, wert) -> str | None:
    return f"    {name:<12} {wert}" if wert else None


def koerper_aus(m: Meldung) -> str:
    """Ninas Text, und darunter alles, was man sonst erfragen müsste."""
    t = [m.text.strip(), ""]
    t.append("— Wo das aufgefallen ist —")
    zeilen = [
        _zeile("Gemeldet in", "der App" if m.quelle == "app" else "dem Portal"),
        _zeile("Ansicht", m.ansicht),
        _zeile("Beleg", m.beleg),
        _zeile("Konto", m.von),
        _zeile("Gerät", m.geraet),
        _zeile("Fassung", m.fassung),
    ]
    t += [z for z in zeilen if z]
    t.append("")
    t.append("Diese Meldung kam über den Rückmeldeknopf. Nina hat sie in "
             "ihren eigenen Worten geschrieben; der Zusammenhang darunter "
             "wurde automatisch ergänzt.")
    return "\n".join(t)


def als_vorgang(m: Meldung, *, autor: str = "nina") -> dict:
    """Die Nutzlast für Fixits POST /api/issues.

    Bewusst OHNE `assignee`/`status`: das Formular von Fixit setzt dort von
    sich aus einen Agenten und „in Arbeit". Eine Meldung von Nina ist aber
    noch nicht entschieden — sie gehört in die Triage, damit ein Mensch
    liest, was sie geschrieben hat, bevor jemand daran arbeitet.
    """
    if m.art not in TYP:
        raise ValueError(f"unbekannte Art: {m.art}")
    if not m.text.strip():
        raise ValueError("leere Meldung")
    return {
        "actor": autor,
        "author": autor,
        "type": TYP[m.art],
        "title": titel_aus(m.text),
        "body": koerper_aus(m),
        "priority": "normal",
        "component": BEREICH.get(m.quelle, "App"),
        "status": "todo",
    }
