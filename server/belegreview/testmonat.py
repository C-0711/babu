"""Testmonat — 30 Tage babu für einen Salon, der über einen Ambassador-Code kommt.

Entwurf: docs/superpowers/specs/2026-10-02-testmonat-code-design.md

Der Testmonat hängt an der MANDANTENZEILE, nicht am Konto: `mandant.test_bis`
ist der letzte Testtag (ISO-Datum), `NULL` heißt „kein Test" — so steht es
für jeden Kanzlei-Mandanten, für den Bestand und für jeden gezeichneten
Salon. Wer nichts von diesem Modul weiß, sieht also keinen Unterschied.

Warum der Mandant: eine eigene Ablage entsteht nur für eine Mandantenzeile
(der Box-Anleger liest `mandant.status='box_ausstehend'`). Ein Testsalon ohne
Mandant hinge an der Default-Box — der Ablage eines anderen Betriebs. Genau
das ist im September schon einmal passiert. Deshalb werden Direktkunden
Mandanten einer festen Hauskanzlei „babu direkt".

Ab Tag 31 ist der Salon nicht ausgesperrt, er kann nur nichts mehr ÄNDERN:
lesen und herunterladen bleibt (Entscheidung Auftraggeber, 02.10.2026). Die
Sperre selbst sitzt in `babu_web._box_wache` und fragt `sperrt()`.
"""
from __future__ import annotations

import datetime as dt
import os

import mandanten

#: Kalendertage inklusive des Einlösetags.
TAGE = 30

#: Name der Hauskanzlei für Betriebe ohne eigenes Steuerbüro in babu.
DIREKT_NAME = "babu direkt"

#: Platzhalter-Inhaber, wenn `BABU_DIREKT_INHABER` fehlt — ein Name, unter
#: dem sich niemand anmelden kann. Dann verwaltet nur die Verwaltung.
DIREKT_PLATZHALTER = "babu-direkt"

#: Was nach Ablauf trotzdem schreiben darf: Rückmeldungen. Wer feststeckt,
#: muss es sagen können.
FREIE_PFADE = ("/api/rueckmeldung",)

LESEND = frozenset({"GET", "HEAD", "OPTIONS"})

VORBEI_TEXT = ("Dein Testmonat ist vorbei — du kannst alles weiter ansehen und "
               "herunterladen. Damit du wieder Belege erfassen kannst, schreib "
               "uns kurz, dann schalten wir dich frei.")


def heute() -> dt.date:
    """Der heutige Tag — eine Stelle, damit Wache und Anzeige dieselbe Uhr lesen."""
    return dt.date.today()


def ende_fuer_start(start: dt.date) -> dt.date:
    """Letzter Testtag, wenn heute eingelöst wird: 30 Tage inklusive heute."""
    return start + dt.timedelta(days=TAGE - 1)


def stand(test_bis: str | None, heute: dt.date) -> dict | None:
    """Wie steht der Testmonat? `None` heißt: kein Test (voller Kunde)."""
    if not test_bis:
        return None
    bis = dt.date.fromisoformat(str(test_bis)[:10])
    uebrig = max(0, (bis - heute).days + 1)
    return {"bis": bis.isoformat(), "tage_uebrig": uebrig, "vorbei": uebrig == 0}


def neues_ende(test_bis: str | None, tage: int, heute: dt.date) -> dt.date:
    """Verlängern: läuft der Test noch, hängt es an; sonst zählt es ab heute."""
    bisher = dt.date.fromisoformat(str(test_bis)[:10]) if test_bis else None
    basis = bisher if bisher and bisher >= heute else heute - dt.timedelta(days=1)
    return basis + dt.timedelta(days=tage)


def sperrt(methode: str, pfad: str, st: dict | None) -> bool:
    """Darf diese Anfrage nach Ablauf nicht mehr durch?"""
    if not st or not st["vorbei"]:
        return False
    if methode.upper() in LESEND:
        return False
    return not any(pfad.startswith(frei) for frei in FREIE_PFADE)


# ---------------------------------------------------------------------------
# Datenbank — immer mit `c=` aus einer offenen Sitzung oder über die
# angemeldete Verbindung von `mandanten` (die nimmt das Schloss selbst).
# ---------------------------------------------------------------------------

def direkt_kanzlei(c) -> int:
    """Die Hauskanzlei „babu direkt" — beim ersten Bedarf angelegt."""
    z = c.execute("SELECT id FROM kanzlei WHERE name=? ORDER BY id",
                  (DIREKT_NAME,)).fetchone()
    if z:
        return int(z[0])
    inhaber = (os.environ.get("BABU_DIREKT_INHABER", "").strip().lower()
               or DIREKT_PLATZHALTER)
    return mandanten.kanzlei_anlegen(DIREKT_NAME, inhaber, c=c)


def test_bis(mandant_id: int, c=None) -> str | None:
    with mandanten.sitzung(c) as cc:
        z = cc.execute("SELECT test_bis FROM mandant WHERE id=?",
                       (mandant_id,)).fetchone()
    return z[0] if z else None


def setzen(mandant_id: int, bis: dt.date | None, c) -> None:
    c.execute("UPDATE mandant SET test_bis=? WHERE id=?",
              (bis.isoformat() if bis else None, mandant_id))


def direkt_mandant_von(email: str, c) -> tuple[int, str | None] | None:
    """Der Mandant dieser Adresse in der Hauskanzlei — (id, test_bis)."""
    z = c.execute(
        "SELECT m.id, m.test_bis FROM mandant m JOIN kanzlei k "
        "ON k.id = m.kanzlei_id WHERE k.name=? AND m.besitzer_un=?",
        (DIREKT_NAME, email)).fetchone()
    return (int(z[0]), z[1]) if z else None
