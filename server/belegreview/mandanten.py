#!/usr/bin/env python3
"""mandanten — Kanzlei, Mandant, Mitgliedschaft.

Bis hierher kannte der Server genau einen Betrieb: eine Belegbox, ein
Kontenrahmen, eine Berater-Nummer aus der Umgebung. Eine Kanzlei betreut
aber viele Betriebe, und jeder bringt seine eigene Box, seinen eigenen
Kontenrahmen und seine eigenen DATEV-Nummern mit. Drei Tabellen halten
das (Plan 21, Abschnitt 1.2):

    kanzlei           wer betreut
    mandant           wen, mit welcher Box und welchen Stammdaten
    kanzlei_mitglied  welche Sachbearbeiter für die Kanzlei arbeiten dürfen

Was hier bewusst NICHT passiert:

* **Keine zweite Fremdschlüsselkaskade durch die 18 bestehenden Tabellen.**
  Die bleiben mandantenneutral an `un` hängen. `mandant_id` ist ein
  Auflösungsschlüssel — „welche Box, welcher Kontenrahmen" — mehr nicht.
* **Keine automatische Box.** Ein neuer Mandant steht auf
  `box_ausstehend`, bis jemand von Hand eine Box eingerichtet und sie mit
  `box_verknuepfen` eingetragen hat. Das Belegbox-Gateway ist ein fremdes
  Projekt und wird nicht ferngesteuert.

Zum SQL: Platzhalter sind `?`, die Typen sind die, die `_db()` in
`babu_web.py` seit jeher benutzt (`INTEGER PRIMARY KEY AUTOINCREMENT`,
`TEXT`, Zeitstempel als ISO-Text). Nichts davon ist SQLite-eigen, was die
DB-Schicht nicht ohnehin schon übersetzen muss — ein `TIMESTAMPTZ
DEFAULT now()` wäre es gewesen. `schema()` läuft an EINER Stelle, am Ende
von `_db()`, und zwar nach `nutzer`: die Fremdschlüssel zeigen dorthin,
und Postgres verlangt die Zieltabelle zum Anlegezeitpunkt.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from typing import Callable

# Der Lebenslauf eines Mandanten. `box_ausstehend` ist der Normalzustand
# nach der Anlage — nicht ein Fehler, sondern der Hinweis, dass die Box
# noch von Hand kommen muss.
STATUS = ("box_ausstehend", "aktiv", "pausiert", "beendet")
MITGLIED_ROLLEN = ("inhaber", "sachbearbeiter")

# Kanzlei-Seite OHNE Fremdschlüssel auf nutzer(email): der Betreiber und
# Kanzlei-Zugänge kommen auch per PAT (BABU_ERLAUBT/BABU_ROLLEN, z. B.
# „christoph0711.io") und haben dann keine nutzer-Zeile. Postgres prüfte
# den Schlüssel wirklich — der erste Mandant im Betrieb fiel mit 500
# (03.09.2026). Die Mandanten-Seite (besitzer_un) behält ihn: den Salon
# legt die Route immer als Konto an. Migration 0003 nimmt ihn im Bestand weg.
_KANZLEI = """CREATE TABLE IF NOT EXISTS kanzlei
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     name TEXT NOT NULL,
     inhaber_un TEXT NOT NULL,
     angelegt TEXT NOT NULL)"""

_MANDANT = """CREATE TABLE IF NOT EXISTS mandant
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     kanzlei_id INTEGER NOT NULL REFERENCES kanzlei(id),
     name TEXT NOT NULL,
     besitzer_un TEXT NOT NULL REFERENCES nutzer(email),
     box_ref TEXT,
     kontenrahmen TEXT,
     berater_nr TEXT,
     mandant_nr TEXT,
     status TEXT NOT NULL DEFAULT 'box_ausstehend'
       CHECK (status IN ('box_ausstehend','aktiv','pausiert','beendet')),
     angelegt TEXT NOT NULL,
     UNIQUE (kanzlei_id, besitzer_un))"""

_MANDANT_INDEX = """CREATE INDEX IF NOT EXISTS mandant_kanzlei
    ON mandant (kanzlei_id, status)"""

_MITGLIED = """CREATE TABLE IF NOT EXISTS kanzlei_mitglied
    (kanzlei_id INTEGER NOT NULL REFERENCES kanzlei(id),
     un TEXT NOT NULL,
     rolle TEXT NOT NULL DEFAULT 'sachbearbeiter'
       CHECK (rolle IN ('inhaber','sachbearbeiter')),
     angelegt TEXT NOT NULL,
     PRIMARY KEY (kanzlei_id, un))"""

# Spalten in Abfragereihenfolge — einmal hier, damit `_zeile` und die
# SELECTs nicht auseinanderlaufen können.
MANDANT_SPALTEN = ("id", "kanzlei_id", "name", "besitzer_un", "box_ref",
                   "kontenrahmen", "berater_nr", "mandant_nr", "status",
                   "angelegt")
KANZLEI_SPALTEN = ("id", "name", "inhaber_un", "angelegt")


def schema(c) -> None:
    """Die drei Tabellen anlegen. Idempotent, aus `_db()` heraus gerufen."""
    c.execute(_KANZLEI)
    c.execute(_MANDANT)
    c.execute(_MANDANT_INDEX)
    c.execute(_MITGLIED)


# ---------------------------------------------------------------------------
# Verbindung: entweder die durchgereichte, oder die des Portals.
# ---------------------------------------------------------------------------

_VERBINDUNG: Callable | None = None


def verbindung_quelle(fn: Callable) -> None:
    """`babu_web` meldet hier seinen `_db()`-Kontext an.

    Anmeldung statt Import, sonst importierten sich beide Dateien
    gegenseitig. Wer `c=` selbst mitgibt, braucht das hier gar nicht — so
    laufen die Tests ohne Portal-Datenbank.
    """
    global _VERBINDUNG
    _VERBINDUNG = fn


@contextlib.contextmanager
def _sitzung(c):
    """Eine offene Verbindung — die mitgegebene oder eine eigene.

    Wird `c` mitgegeben, gehört sie dem Aufrufer: kein Schloss, kein
    Commit, kein Schließen. Das ist der Weg für alles, was ohnehin schon
    in einem `with _DB_LOCK, _db() as c`-Block steht — ein zweites Mal
    dasselbe Schloss zu nehmen hinge für immer.
    """
    if c is not None:
        yield c
        return
    if _VERBINDUNG is None:
        raise RuntimeError("keine Datenbank angemeldet — c= mitgeben "
                           "oder mandanten.verbindung_quelle() setzen")
    with _VERBINDUNG() as eigene:
        yield eigene


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _zeile(spalten: tuple, roh) -> dict | None:
    return dict(zip(spalten, roh)) if roh else None


# ---------------------------------------------------------------------------
# Zugriffe
# ---------------------------------------------------------------------------

def kanzlei_anlegen(name: str, inhaber_un: str, c=None) -> int:
    """Neue Kanzlei; der Anlegende ist zugleich ihr erstes Mitglied.

    Beides in einem Schritt, weil eine Kanzlei ohne Mitglied niemand
    bedienen könnte — und der häufigste Weg, sich selbst auszusperren,
    ist ein vergessener zweiter Aufruf.
    """
    with _sitzung(c) as cc:
        cur = cc.execute(
            "INSERT INTO kanzlei (name, inhaber_un, angelegt) VALUES (?, ?, ?)",
            (name, inhaber_un, _jetzt_iso()))
        kanzlei_id = int(cur.lastrowid)
        cc.execute("INSERT INTO kanzlei_mitglied (kanzlei_id, un, rolle, angelegt) "
                   "VALUES (?, ?, ?, ?)",
                   (kanzlei_id, inhaber_un, "inhaber", _jetzt_iso()))
        return kanzlei_id


def kanzlei_holen(kanzlei_id: int, c=None) -> dict | None:
    with _sitzung(c) as cc:
        roh = cc.execute("SELECT id, name, inhaber_un, angelegt FROM kanzlei "
                         "WHERE id = ?", (kanzlei_id,)).fetchone()
    return _zeile(KANZLEI_SPALTEN, roh)


def mitglied_anlegen(kanzlei_id: int, un: str, rolle: str = "sachbearbeiter",
                     c=None) -> None:
    """Einen Sachbearbeiter zur Kanzlei stellen."""
    if rolle not in MITGLIED_ROLLEN:
        raise ValueError(f"unbekannte Rolle: {rolle}")
    with _sitzung(c) as cc:
        cc.execute("INSERT INTO kanzlei_mitglied (kanzlei_id, un, rolle, angelegt) "
                   "VALUES (?, ?, ?, ?)", (kanzlei_id, un, rolle, _jetzt_iso()))


def mandant_anlegen(kanzlei_id: int, name: str, besitzer_un: str,
                    kontenrahmen: str | None = None,
                    berater_nr: str | None = None,
                    mandant_nr: str | None = None, c=None) -> int:
    """Neuer Mandant — ohne Box, Status `box_ausstehend`.

    Die Box kommt später und von Hand (`box_verknuepfen`). Bis dahin ist
    der Mandant angelegt, aber ohne Belege: das ist ein sichtbarer
    Zwischenzustand, kein halbfertiger Datensatz.
    """
    with _sitzung(c) as cc:
        cur = cc.execute(
            "INSERT INTO mandant (kanzlei_id, name, besitzer_un, box_ref, "
            "kontenrahmen, berater_nr, mandant_nr, status, angelegt) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?, 'box_ausstehend', ?)",
            (kanzlei_id, name, besitzer_un, kontenrahmen, berater_nr,
             mandant_nr, _jetzt_iso()))
        return int(cur.lastrowid)


def mandant_holen(mandant_id: int, c=None) -> dict | None:
    with _sitzung(c) as cc:
        roh = cc.execute(
            "SELECT id, kanzlei_id, name, besitzer_un, box_ref, kontenrahmen, "
            "berater_nr, mandant_nr, status, angelegt FROM mandant WHERE id = ?",
            (mandant_id,)).fetchone()
    return _zeile(MANDANT_SPALTEN, roh)


def mandanten_von_kanzlei(kanzlei_id: int, status: str | None = None,
                          c=None) -> list[dict]:
    """Alle Mandanten einer Kanzlei, nach Namen — optional nach Status."""
    sql = ("SELECT id, kanzlei_id, name, besitzer_un, box_ref, kontenrahmen, "
           "berater_nr, mandant_nr, status, angelegt FROM mandant "
           "WHERE kanzlei_id = ?")
    werte: list = [kanzlei_id]
    if status is not None:
        sql += " AND status = ?"
        werte.append(status)
    sql += " ORDER BY name"
    with _sitzung(c) as cc:
        rohe = cc.execute(sql, tuple(werte)).fetchall()
    return [_zeile(MANDANT_SPALTEN, r) for r in rohe]


def mandanten_fuer(un: str, c=None) -> list[dict]:
    """Alle Mandanten, für die dieser Zugang arbeiten darf.

    Über die Kanzleien, in denen er Mitglied ist — nicht über seine Rolle.
    Das ist dieselbe Grenze wie in `kanzlei_mitglied`, nur andersherum
    gefragt: dort „darf ich zu diesem einen?", hier „welche sind es
    überhaupt?". Beides muss dieselbe Antwort geben, deshalb steht die
    Verknüpfung nur hier in der Datei und nicht in den Aufrufern.

    Eine leere Liste heißt: dieser Zugang betreut keinen fremden Betrieb.
    Im heutigen Ein-Betrieb ist das jeder — auch die Kanzlei-Rolle, denn
    ohne `kanzlei`-Zeilen gibt es nichts zu betreuen.
    """
    sql = ("SELECT m.id, m.kanzlei_id, m.name, m.besitzer_un, m.box_ref, "
           "m.kontenrahmen, m.berater_nr, m.mandant_nr, m.status, m.angelegt "
           "FROM mandant m JOIN kanzlei_mitglied km "
           "ON km.kanzlei_id = m.kanzlei_id WHERE km.un = ? ORDER BY m.name")
    with _sitzung(c) as cc:
        rohe = cc.execute(sql, (un,)).fetchall()
    return [_zeile(MANDANT_SPALTEN, r) for r in rohe]


def kanzlei_mitglied(un: str, mandant_id: int, c=None) -> bool:
    """Darf dieser Zugang für diesen Mandanten arbeiten?

    Die Frage, an der ab Phase 3 die Mandantentrennung hängt: nicht „ist
    das eine Kanzlei-Rolle" (dann sähe jede Kanzlei jede Box), sondern
    „gehört dieser Zugang zu DER Kanzlei, die DIESEN Mandanten betreut".
    """
    with _sitzung(c) as cc:
        roh = cc.execute(
            "SELECT 1 FROM kanzlei_mitglied km JOIN mandant m "
            "ON m.kanzlei_id = km.kanzlei_id WHERE km.un = ? AND m.id = ?",
            (un, mandant_id)).fetchone()
    return roh is not None


def mandant_besitzer_un(mandant_id: int, c=None) -> str | None:
    """Wem gehören die Daten dieses Mandanten — der Salon, nicht die Kanzlei."""
    with _sitzung(c) as cc:
        roh = cc.execute("SELECT besitzer_un FROM mandant WHERE id = ?",
                         (mandant_id,)).fetchone()
    return str(roh[0]) if roh else None


def box_verknuepfen(mandant_id: int, box_ref: str, c=None) -> None:
    """Die eingerichtete Box eintragen — damit wird der Mandant `aktiv`.

    Der eine Schritt, der aus einem angelegten Mandanten einen
    arbeitsfähigen macht. Beides in einem UPDATE, damit es keinen Mandanten
    mit Box und Status `box_ausstehend` geben kann.
    """
    with _sitzung(c) as cc:
        cc.execute("UPDATE mandant SET box_ref = ?, status = 'aktiv' WHERE id = ?",
                   (box_ref, mandant_id))


def status_setzen(mandant_id: int, status: str, c=None) -> None:
    if status not in STATUS:
        raise ValueError(f"unbekannter Status: {status}")
    with _sitzung(c) as cc:
        cc.execute("UPDATE mandant SET status = ? WHERE id = ?",
                   (status, mandant_id))
