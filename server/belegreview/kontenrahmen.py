#!/usr/bin/env python3
"""Welcher Kontenrahmen gilt — und wann er sich ändern darf.

Bis 23.08.2026 stand die Antwort ausschließlich in `BABU_KONTENRAHMEN`. Das
ist der falsche Ort: der Kontenrahmen ist eine Entscheidung des Betriebs,
keine Einstellung des Dienstes. Er gehört neben Steuernummer und Rechtsform in
die Einrichtungsangaben — dort, wo Nina ihn sieht und ändern kann.

Deshalb hier zwei Dinge, und nur die:

1. **Woher der Rahmen kommt.** Die Betriebsangabe schlägt die Umgebung. Die
   Umgebungsvariable bleibt als Vorgabe für einen Betrieb, der noch nichts
   gewählt hat — sie ist Startwert, nicht Wahrheit.

2. **Wann er sich ändern darf.** Das ist die eigentliche Entscheidung dieses
   Moduls, und sie ist streng:

       Ein Wechsel wirkt zum 1. Januar. Nie mitten im Jahr.

   Begründung, kurz: SKR03 und SKR04 vergeben dieselbe Nummer für
   verschiedene Dinge. Wer im Juni wechselt, hat für dasselbe Wirtschaftsjahr
   Belege in beiden Rahmen — der Buchungsstapel ist dann nicht „ein bisschen
   uneinheitlich", er ist unbrauchbar, und zwar rückwirkend für die Monate,
   die schon exportiert wurden. Das fällt beim Steuerberater auf, nicht hier,
   und dann kostet es Stunden.

   Die einzige Ausnahme ist ein Jahr, in dem noch nichts gebucht ist: da gibt
   es nichts zu vermischen. Ein Betrieb, der babu im März in Betrieb nimmt und
   im April merkt, dass die Kanzlei SKR03 fährt, muss nicht bis Januar warten.

   Zusätzlich braucht jeder Wechsel eine **ausdrückliche Bestätigung**. Die
   Jahresbindung verhindert die Vermischung, die Bestätigung verhindert den
   versehentlichen Tipper — das sind zwei verschiedene Fehler, und die
   Jahresbindung allein fängt nur einen davon.

Dieses Modul rechnet nichts und schreibt nichts. Es beantwortet Fragen und
begründet die Antwort; wer speichert, ist der Aufrufer.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kontierung import RAHMEN

# Der Hausstand, wenn weder Betrieb noch Umgebung etwas Brauchbares sagen.
# SKR04 ist der Rahmen, mit dem babu ausgeliefert wird.
HAUSSTAND = "SKR04"

# Die drei Schlüssel in `einstellungen`. Sie gehören zusammen: ein Rahmen ohne
# sein Anfangsjahr wäre ein Schalter, und genau das soll er nicht sein.
#
#   kontenrahmen        der Rahmen, in dem JETZT gebucht wird
#   kontenrahmen_ab     das Jahr, ab dem er gilt
#   kontenrahmen_kommt  "JJJJ:SKRxx" — ein angekündigter Wechsel, der noch
#                       nicht wirkt
#
# Der angekündigte Wechsel ist der Grund für den dritten Schlüssel. Ein
# bestätigter Wechsel wird nicht sofort scharf, sonst wären wir wieder beim
# Schalter; er wird vorgemerkt und tritt am 1. Januar von selbst in Kraft —
# ohne dass jemand daran denken oder einen Dienst neu starten muss.
SCHLUESSEL = "kontenrahmen"
SCHLUESSEL_AB = "kontenrahmen_ab"
SCHLUESSEL_KOMMT = "kontenrahmen_kommt"


def vorgabe() -> str:
    """Was die Umgebung vorschlägt — Startwert für einen neuen Betrieb."""
    return _sauber(os.environ.get("BABU_KONTENRAHMEN")) or HAUSSTAND


def _sauber(wert) -> str | None:
    """Ein Rahmen, oder None. `skr03 ` ist SKR03, `SKR49` ist nichts."""
    if not wert:
        return None
    k = str(wert).strip().upper()
    return k if k in RAHMEN else None


def _jahr(roh) -> int | None:
    try:
        jahr = int(str(roh).strip())
    except (TypeError, ValueError):
        return None
    return jahr if 2000 <= jahr <= 2100 else None


def geplanter_wechsel(einstellungen: dict) -> tuple[int, str] | None:
    """Der vorgemerkte Wechsel als (Jahr, Rahmen) — oder None."""
    roh = str((einstellungen or {}).get(SCHLUESSEL_KOMMT) or "")
    if ":" not in roh:
        return None
    jahr_teil, rahmen_teil = roh.split(":", 1)
    jahr, rahmen = _jahr(jahr_teil), _sauber(rahmen_teil)
    return (jahr, rahmen) if jahr and rahmen else None


def aus_einstellungen(einstellungen: dict, vorgabe: str | None = None,
                      jahr: int | None = None) -> str:
    """Der Rahmen des Betriebs — die Betriebsangabe schlägt die Vorgabe.

    Ein vorgemerkter Wechsel tritt hier von selbst in Kraft, sobald sein Jahr
    erreicht ist. Niemand muss am 1. Januar etwas drücken, und niemand muss
    einen Dienst neu starten: der Watcher fragt ohnehin in jedem Takt nach.

    Eine unbrauchbare Angabe wird nicht geglaubt: lieber die Vorgabe als ein
    Rahmen, den es nicht gibt. Sichtbar wird der Unsinn trotzdem, weil das
    Feld im Portal weiter das zeigt, was gespeichert wurde.
    """
    geplant = geplanter_wechsel(einstellungen)
    if geplant and (jahr or _heute_jahr()) >= geplant[0]:
        return geplant[1]
    return (_sauber((einstellungen or {}).get(SCHLUESSEL))
            or _sauber(vorgabe)
            or HAUSSTAND)


def gilt_ab_aus_einstellungen(einstellungen: dict) -> int | None:
    """Ab welchem Jahr der geltende Rahmen gilt — None, wenn nie gesetzt."""
    geplant = geplanter_wechsel(einstellungen)
    if geplant and _heute_jahr() >= geplant[0]:
        return geplant[0]
    return _jahr((einstellungen or {}).get(SCHLUESSEL_AB))


def _heute_jahr() -> int:
    import time  # noqa: PLC0415
    return int(time.strftime("%Y"))


# ── Der Wechsel ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Bescheid:
    """Darf gewechselt werden, ab wann — und warum (oder warum nicht)."""
    erlaubt: bool
    gilt_ab: int | None
    begruendung: str
    rueckfrage: str | None = None

    @property
    def offen(self) -> bool:
        """True, solange gefragt werden muss statt geschaltet."""
        return self.rueckfrage is not None


def wechsel_pruefen(*, alt: str | None, neu: str, heute_jahr: int,
                    ab_jahr: int | None = None,
                    gebuchte_jahre=(),
                    bestaetigt: bool = False) -> Bescheid:
    """Darf der Betrieb von `alt` auf `neu` wechseln, und ab wann?

    `ab_jahr` ist der Wunsch des Betriebs; ohne Wunsch schlägt babu den
    nächsten 1. Januar vor. `gebuchte_jahre` sind die Jahre, in denen bereits
    Belege mit einem Konto liegen — nur sie machen einen Wechsel unmöglich.
    """
    ziel_rahmen = _sauber(neu)
    if ziel_rahmen is None:
        raise ValueError(f"unbekannter Kontenrahmen: {neu!r}")
    alt_rahmen = _sauber(alt)
    gebucht = {int(j) for j in gebuchte_jahre}

    # Erste Festlegung: es gibt nichts, womit sich etwas vermischen könnte.
    if alt_rahmen is None:
        return Bescheid(
            True, heute_jahr,
            f"Erstmalig festgelegt: {ziel_rahmen} ab {heute_jahr}. "
            f"Vorher hatte der Betrieb keinen eigenen Rahmen.")

    if alt_rahmen == ziel_rahmen:
        return Bescheid(True, ab_jahr,
                        f"{ziel_rahmen} war schon eingestellt — nichts zu tun.")

    ziel_jahr = int(ab_jahr) if ab_jahr else heute_jahr + 1

    if ziel_jahr < heute_jahr:
        return Bescheid(
            False, None,
            f"{ziel_jahr} ist vorbei. Ein Kontenrahmen lässt sich nicht "
            f"rückwirkend tauschen — was gebucht ist, bleibt gebucht.",
            rueckfrage=f"Soll {ziel_rahmen} ab dem 1. Januar "
                       f"{heute_jahr + 1} gelten?")

    if ziel_jahr == heute_jahr and gebucht & {heute_jahr}:
        return Bescheid(
            False, None,
            f"Für {heute_jahr} sind schon Belege gebucht. Ein Wechsel mitten "
            f"im Jahr brächte zwei Kontenrahmen in denselben Stapel — der ist "
            f"beim Steuerberater nicht mehr zu gebrauchen.",
            rueckfrage=f"Soll {ziel_rahmen} stattdessen ab dem 1. Januar "
                       f"{heute_jahr + 1} gelten?")

    if not bestaetigt:
        wann = ("sofort, weil für dieses Jahr noch nichts gebucht ist"
                if ziel_jahr == heute_jahr else f"ab dem 1. Januar {ziel_jahr}")
        return Bescheid(
            False, None,
            f"Wechsel von {alt_rahmen} auf {ziel_rahmen} — noch nicht "
            f"bestätigt.",
            rueckfrage=f"Der Kontenrahmen wechselt von {alt_rahmen} auf "
                       f"{ziel_rahmen}, und zwar {wann}. Alles, was bis dahin "
                       f"gebucht ist, bleibt im {alt_rahmen}. Wirklich "
                       f"umstellen?")

    return Bescheid(
        True, ziel_jahr,
        f"Wechsel von {alt_rahmen} auf {ziel_rahmen} zum 1. Januar "
        f"{ziel_jahr}. Belege bis dahin bleiben im {alt_rahmen}.")


# ── Was der Watcher liest ────────────────────────────────────────────────────

def gewaehlt(db_pfad, un: str | None = None, vorgabe: str | None = None) -> str:
    """Der Rahmen des Betriebs, direkt aus `portal.db` — für den Watcher.

    Der Watcher ist ein eigener Prozess ohne FastAPI; er importiert babu_web
    nicht (das zöge den halben Server mit). Deshalb liest er die eine Zeile
    selbst, nur lesend und fehlertolerant: gibt es die Datei nicht, ist sie
    gesperrt oder fehlt die Tabelle, bleibt es bei der Vorgabe. Ein
    unerreichbares Portal darf die Belegverarbeitung nicht anhalten.

    Ohne `un` gilt „eine Belegbox je Server": steht genau ein Rahmen in der
    Tabelle, ist das der des Betriebs. Stehen zwei verschiedene da, wird nicht
    gewürfelt — dann bleibt es bei der Vorgabe.
    """
    fallback = _sauber(vorgabe) or HAUSSTAND
    pfad = Path(db_pfad)
    if not pfad.exists():
        return fallback
    schluessel = (SCHLUESSEL, SCHLUESSEL_AB, SCHLUESSEL_KOMMT)
    platzhalter = ",".join("?" * len(schluessel))
    try:
        # Nur lesend öffnen: der Watcher darf die Portal-Datenbank unter
        # keinen Umständen anlegen oder verändern.
        conn = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, timeout=2)
        try:
            zeilen = list(conn.execute(
                f"SELECT un, schluessel, wert FROM einstellungen "
                f"WHERE schluessel IN ({platzhalter})"
                + (" AND un=?" if un else ""),
                (*schluessel, un) if un else schluessel))
        finally:
            conn.close()
    except sqlite3.Error:
        return fallback

    # Nach Betrieb sortieren, dann den Rahmen je Betrieb ausrechnen — der
    # vorgemerkte Wechsel gehört zu seinem Betrieb, nicht in einen Topf.
    je_betrieb: dict[str, dict] = {}
    for betrieb, schluessel_, wert in zeilen:
        je_betrieb.setdefault(betrieb, {})[schluessel_] = wert
    gefunden = {aus_einstellungen(e, vorgabe=fallback) for e in je_betrieb.values()}
    if len(gefunden) == 1:
        return gefunden.pop()
    return fallback
