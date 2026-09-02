#!/usr/bin/env python3
"""Eine Datenbankschicht für zwei Dialekte — SQLite und Postgres.

Warum es diese Datei gibt (Plan 21, Abschnitt 1.3):

Der Portal-Zustand lag bisher in einer einzigen SQLite-Datei, und jeder
Schreibzugriff ging durch einen prozessweiten Mutex. Für einen Salon reicht
das. Für eine Kanzlei mit hunderten Mandanten ist der Mutex der Engpass, und
referentielle Integrität zwischen Kanzlei, Mandant und Nutzer lässt sich in
SQLite nur mit Disziplin herstellen, in Postgres deklarativ.

Diese Datei wechselt den Dialekt, **ohne dass sich Verhalten ändert**. Alle
Aufrufe laufen weiterhin durch `babu_web._db()`; die 111 `c.execute(...)`
darin bleiben Wort für Wort stehen. Was hier passiert, passiert dazwischen:

* `platzhalter()` übersetzt `?` nach `%s`, wenn Postgres spricht.
* `Zeiger` reicht `lastrowid` nach, das Postgres nicht kennt.
* `schema_anwenden()` legt das Schema aus `migrations/` an.

Ohne `BABU_DB_URL` bleibt alles wie es war: SQLite, dieselbe Datei, dieselben
Anweisungen. Das ist auch der Rückweg im Betrieb — Umgebungsvariable weg,
und `portal.db` ist wieder die Wahrheit.

---

**Warum die SQLite-Seite weiter die Inline-Statements in `_db()` benutzt**
(und nicht den Migrations-Runner):

`_db()` legt nicht nur Tabellen an, es rüstet auch Spalten nach —
`ALTER TABLE … ADD COLUMN` in try/except, dreizehn Stück. Das ist der
Mechanismus, mit dem die produktive `portal.db` über Monate gewachsen ist.
Ihn durch einen Runner zu ersetzen hieße, an einer Datei zu schrauben, die
seit Monaten Nina gehört — und Phase 1 soll nichts am Verhalten ändern.
Postgres dagegen fängt leer an und hat keine Altlast; dort ist die
Migrationsdatei die einzige Quelle.

Damit die beiden Wege nicht auseinanderlaufen, ist `_fuer_sqlite()` so
gebaut, dass `migrations/0001_initial.sql` **auch** gegen SQLite läuft —
`tests/test_db_dialekt.py` legt beide Schemata nebeneinander an und
vergleicht Tabellen und Spalten. Ein vergessenes Feld fällt damit auf,
ohne dass ein Postgres laufen muss.

---

**Hinweis für künftige SQL-Zeilen:** `platzhalter()` ersetzt jedes `?` im
Text. Heute ist das nachweislich sicher (geprüft: 276 `?` in 138
SQL-Literalen, alle Platzhalter; kein `%` in irgendeinem SQL-Literal). Wer
ein literales `?` oder `%` in SQL schreibt, bricht das. Ein Fragezeichen
gehört in einen Parameter, nicht in den Text.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

WURZEL = Path(__file__).resolve().parent
MIGRATIONEN = WURZEL / "migrations"

#: Verbindungszeichenfolge für Postgres. Leer = SQLite.
BABU_DB_URL = (os.environ.get("BABU_DB_URL") or "").strip()
#: "postgres" oder "sqlite". Wird beim Import einmal festgelegt.
DIALEKT = "postgres" if BABU_DB_URL else "sqlite"

#: Tabellen mit einer selbstvergebenen `id`. Postgres kennt kein
#: `lastrowid` — für genau diese Tabellen hängt `Zeiger` bei einem INSERT
#: ein `RETURNING id` an und legt das Ergebnis dort ab, wo der Code es
#: erwartet. Wächst das Schema, wächst diese Menge mit (der Test
#: `test_id_tabellen_vollstaendig` erzwingt das).
ID_TABELLEN = frozenset({
    "registrierungen", "team", "termin", "kundin", "behandlung", "leistung",
    "mitarbeiter", "wa_faden", "wa_nachricht", "gespraech", "nachricht",
    "anlagegut", "einladung", "meldung_puffer",
    # 0002: Plan 21, Phase 2 und §7
    "audit_log", "passwort_reset", "kanzlei", "mandant",
})


# ---------------------------------------------------------------------------
# Dialekt-Übersetzungen
# ---------------------------------------------------------------------------

def platzhalter(sql: str, dialekt: str | None = None) -> str:
    """`?` → `%s`, aber nur wenn Postgres spricht.

    Siehe die Warnung im Modul-Docstring: das ist eine reine Textersetzung.
    Sie ist sicher, solange kein SQL-Text ein literales `?` enthält.
    """
    if (dialekt or DIALEKT) != "postgres":
        return sql
    return sql.replace("?", "%s")


def upsert(tabelle: str, spalten: tuple[str, ...] | list[str],
           konflikt_spalten: tuple[str, ...] | list[str],
           dialekt: str | None = None) -> str:
    """Ein Einfügen, das ein vorhandenes Zeilchen überschreibt.

    SQLite kann das seit je als `INSERT OR REPLACE`; Postgres schreibt
    dafür `ON CONFLICT … DO UPDATE`. Die Platzhalter bleiben `?` — den
    Rest erledigt `platzhalter()` unterwegs.

    Ein Unterschied, der bleibt und der hier gemeint ist: `INSERT OR
    REPLACE` löscht die alte Zeile und schreibt eine neue (nicht genannte
    Spalten fallen auf ihren Default zurück), `ON CONFLICT DO UPDATE`
    ändert die vorhandene. Für die drei Aufrufstellen ist das gleich —
    sie nennen jedes Mal alle Spalten der Tabelle.
    """
    spalten = tuple(spalten)
    konflikt_spalten = tuple(konflikt_spalten)
    if not spalten:
        raise ValueError("upsert braucht Spalten")
    unbekannt = [s for s in konflikt_spalten if s not in spalten]
    if unbekannt:
        raise ValueError(f"Konfliktspalte nicht in der Spaltenliste: {unbekannt}")
    felder = ", ".join(spalten)
    werte = ", ".join("?" for _ in spalten)
    if (dialekt or DIALEKT) != "postgres":
        return f"INSERT OR REPLACE INTO {tabelle} ({felder}) VALUES ({werte})"
    rest = [s for s in spalten if s not in konflikt_spalten]
    if not rest:
        # Nichts zu ändern — dann reicht "tu nichts", sonst wäre das SET leer.
        tat = "DO NOTHING"
    else:
        tat = "DO UPDATE SET " + ", ".join(f"{s}=EXCLUDED.{s}" for s in rest)
    return (f"INSERT INTO {tabelle} ({felder}) VALUES ({werte}) "
            f"ON CONFLICT ({', '.join(konflikt_spalten)}) {tat}")


#: Postgres-Schreibweisen, die SQLite nicht kennt. Die Migrationsdateien
#: sind in Postgres-Dialekt geschrieben — das ist das Ziel; SQLite ist der
#: Rückweg und bekommt hier seine Übersetzung.
_NACH_SQLITE = (
    (re.compile(r"\bBIGINT\s+GENERATED\s+BY\s+DEFAULT\s+AS\s+IDENTITY\b", re.I),
     "INTEGER"),
    (re.compile(r"\bBIGINT\s+GENERATED\s+ALWAYS\s+AS\s+IDENTITY\b", re.I),
     "INTEGER"),
    (re.compile(r"\bDOUBLE\s+PRECISION\b", re.I), "REAL"),
    (re.compile(r"\bTIMESTAMPTZ\b", re.I), "TEXT"),
    (re.compile(r"\bJSONB\b", re.I), "TEXT"),
)
#: `INTEGER PRIMARY KEY` ist in SQLite der Alias auf die rowid und zählt von
#: selbst hoch — genau das, was IDENTITY in Postgres tut. `AUTOINCREMENT`
#: kommt dazu, damit gelöschte Nummern nicht neu vergeben werden (so steht
#: es heute in `_db()`).
_SQLITE_ID = re.compile(r"\bINTEGER\s+PRIMARY\s+KEY\b(?!\s+AUTOINCREMENT)", re.I)


def _fuer_sqlite(sql: str) -> str:
    """Postgres-DDL nach SQLite übersetzen (nur die paar Typen, die abweichen)."""
    for muster, ersatz in _NACH_SQLITE:
        sql = muster.sub(ersatz, sql)
    return _SQLITE_ID.sub("INTEGER PRIMARY KEY AUTOINCREMENT", sql)


def ddl(sql: str, dialekt: str | None = None) -> str:
    """Eine DDL-Anweisung im gewünschten Dialekt."""
    return sql if (dialekt or DIALEKT) == "postgres" else _fuer_sqlite(sql)


# ---------------------------------------------------------------------------
# Migrations-Runner — nummerierte SQL-Dateien, eine `schema_version`-Tabelle
# ---------------------------------------------------------------------------

_VERSION_TABELLE = """CREATE TABLE IF NOT EXISTS schema_version
    (nummer INTEGER PRIMARY KEY, datei TEXT NOT NULL, angewendet TEXT NOT NULL)"""

_DATEINAME = re.compile(r"^(\d{4})_.*\.sql$")


def _anweisungen(sql: str):
    """SQL an Semikolons zerlegen — Anführungszeichen und `--` respektiert.

    Kein Parser, aber genug für DDL: der einzige Fall, in dem ein Semikolon
    nicht trennt, ist eines in einer Zeichenkette oder in einem Kommentar.
    """
    stueck: list[str] = []
    in_string = False
    i = 0
    while i < len(sql):
        z = sql[i]
        if in_string:
            stueck.append(z)
            if z == "'":
                if i + 1 < len(sql) and sql[i + 1] == "'":   # '' = ein Hochkomma
                    stueck.append(sql[i + 1])
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if z == "'":
            in_string = True
            stueck.append(z)
            i += 1
            continue
        if z == "-" and sql[i:i + 2] == "--":
            ende = sql.find("\n", i)
            i = len(sql) if ende < 0 else ende
            continue
        if z == ";":
            text = "".join(stueck).strip()
            if text:
                yield text
            stueck = []
            i += 1
            continue
        stueck.append(z)
        i += 1
    rest = "".join(stueck).strip()
    if rest:
        yield rest


def migrationsdateien(verzeichnis: Path | None = None) -> list[tuple[int, Path]]:
    """Die nummerierten SQL-Dateien, aufsteigend."""
    ordner = verzeichnis or MIGRATIONEN
    if not ordner.is_dir():
        return []
    gefunden = []
    for pfad in sorted(ordner.iterdir()):
        m = _DATEINAME.match(pfad.name)
        if m:
            gefunden.append((int(m.group(1)), pfad))
    return sorted(gefunden)


def schema_anwenden(conn, dialekt: str | None = None,
                    verzeichnis: Path | None = None) -> list[str]:
    """Alle noch nicht angewendeten Migrationen fahren. Liefert ihre Namen.

    Idempotent: was in `schema_version` steht, wird übersprungen. `conn` ist
    eine rohe Verbindung (sqlite3 oder psycopg) — der Runner committet
    selbst, damit er auch außerhalb von `oeffnen()` benutzbar ist
    (Migrationsskript, Tests).
    """
    d = dialekt or DIALEKT
    cur = conn.cursor()
    cur.execute(ddl(_VERSION_TABELLE, d))
    cur.execute("SELECT nummer FROM schema_version")
    schon = {int(z[0]) for z in cur.fetchall()}
    gefahren: list[str] = []
    for nummer, pfad in migrationsdateien(verzeichnis):
        if nummer in schon:
            continue
        for anweisung in _anweisungen(ddl(pfad.read_text(encoding="utf-8"), d)):
            cur.execute(anweisung)
        cur.execute(
            platzhalter("INSERT INTO schema_version (nummer, datei, angewendet) "
                        "VALUES (?,?,?)", d),
            (nummer, pfad.name, datetime.now(timezone.utc).isoformat()))
        gefahren.append(pfad.name)
    conn.commit()
    return gefahren


# ---------------------------------------------------------------------------
# Verbindung und Zeiger
# ---------------------------------------------------------------------------

_INSERT_ZIEL = re.compile(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z_0-9]*)", re.I)
_HAT_RETURNING = re.compile(r"\bRETURNING\b", re.I)


class Zeiger:
    """Ein Cursor, der sich in beiden Dialekten gleich anfühlt.

    Der Code liest Zeilen als Tupel (`z[0]`) und holt nach einem INSERT die
    frische Nummer aus `lastrowid`. SQLite kann beides von Haus aus; für
    Postgres wird `RETURNING id` angehängt und das Ergebnis hier gemerkt.
    """

    def __init__(self, roh, lastrowid=None):
        self._roh = roh
        self._lastrowid = lastrowid

    @property
    def lastrowid(self):
        """Die frisch vergebene Nummer.

        SQLite führt sie am Cursor mit; für Postgres hat `execute()` sie
        über `RETURNING id` geholt und hier hinterlegt.
        """
        if self._lastrowid is not None:
            return self._lastrowid
        return getattr(self._roh, "lastrowid", None)

    def __iter__(self):
        return iter(self._roh)

    def fetchone(self):
        return self._roh.fetchone()

    def fetchall(self):
        return self._roh.fetchall()

    def fetchmany(self, groesse=None):
        return (self._roh.fetchmany() if groesse is None
                else self._roh.fetchmany(groesse))

    @property
    def rowcount(self):
        return self._roh.rowcount

    @property
    def description(self):
        return self._roh.description


class _ZeilenMitNamen:
    """Marke für `verbindung.row_factory` — „gib mir Zeilen mit Spaltennamen".

    Statt `sqlite3.Row` (das Postgres nichts sagt) und statt `dict_row` (das
    SQLite nichts sagt) steht an den Aufrufstellen diese eine Marke; welche
    der beiden Fabriken daraus wird, entscheidet der Dialekt.
    """

    def __repr__(self) -> str:      # pragma: no cover — nur fürs Auge
        return "db.ZEILEN_MIT_NAMEN"


ZEILEN_MIT_NAMEN = _ZeilenMitNamen()


class Verbindung:
    """Was `_db()` herausgibt: etwas mit `.execute(sql, params)`.

    Bewusst dünn. Es gibt keine Methode, die der Code nicht schon benutzt
    hat — `execute` und `row_factory`, mehr ist es nicht (nachgezählt:
    141 × `execute`, 2 × `row_factory`, sonst nichts).
    """

    def __init__(self, roh, dialekt: str):
        self._roh = roh
        self.dialekt = dialekt
        self._benannt = False

    # -- Zeilen mit Namen statt mit Nummern ---------------------------------
    # Zwei Stellen setzen `c.row_factory = sqlite3.Row`, um `zeile["abgang"]`
    # schreiben zu können. In Postgres macht das `dict_row` — der Zugriff
    # über den Spaltennamen ist derselbe.
    @property
    def row_factory(self):
        return getattr(self._roh, "row_factory", None)

    @row_factory.setter
    def row_factory(self, wert):
        self._benannt = wert is not None
        if self.dialekt == "sqlite":
            self._roh.row_factory = (sqlite3.Row if wert is ZEILEN_MIT_NAMEN
                                     else wert)

    def execute(self, sql: str, params=None) -> Zeiger:
        text = platzhalter(sql, self.dialekt)
        if self.dialekt == "sqlite":
            cur = (self._roh.execute(text) if params is None
                   else self._roh.execute(text, params))
            return Zeiger(cur)
        return self._pg_execute(text, params)

    def _pg_execute(self, text: str, params) -> Zeiger:
        from psycopg.rows import dict_row  # noqa: PLC0415
        cur = self._roh.cursor(row_factory=dict_row) if self._benannt \
            else self._roh.cursor()
        ziel = _INSERT_ZIEL.match(text)
        hole_id = bool(ziel and ziel.group(1).lower() in ID_TABELLEN
                       and not _HAT_RETURNING.search(text))
        if hole_id:
            text = text.rstrip().rstrip(";") + " RETURNING id"
        # params=None statt () — sonst versucht psycopg eine Interpolation,
        # die bei einem literalen % im Text fehlschlüge.
        cur.execute(text, params if params else None)
        neue = None
        if hole_id:
            zeile = cur.fetchone()
            if zeile is not None:
                neue = zeile["id"] if isinstance(zeile, dict) else zeile[0]
        return Zeiger(cur, neue)

    def commit(self):
        self._roh.commit()

    def rollback(self):
        self._roh.rollback()

    def close(self):
        self._roh.close()


def verbindung(sqlite_pfad: Path | str | None = None, dialekt: str | None = None,
               url: str | None = None):
    """Eine rohe Verbindung im aktuellen Dialekt.

    Postgres: psycopg3. SQLite: dieselbe Datei wie bisher — der Pfad kommt
    von außen, weil `babu_web.PORTAL_DB` zur Laufzeit umgesetzt wird
    (jeder Test bekommt seine eigene Datei).
    """
    if (dialekt or DIALEKT) == "postgres":
        import psycopg  # noqa: PLC0415
        zusatz = {}
        # Das Passwort steht NICHT in der URL und nicht in einer
        # Umgebungsvariablen (die stünde in `docker inspect`), sondern in
        # einer Datei, die Docker als Secret einhängt. psycopg bekommt es
        # als eigenen Parameter — nicht in die URL gespleißt, sonst müsste
        # jedes Sonderzeichen URL-kodiert werden.
        datei = (os.environ.get("BABU_DB_PASSWORT_DATEI") or "").strip()
        if datei and Path(datei).is_file():
            # rstrip nur auf Zeilenenden: das offizielle Postgres-Image
            # schneidet bei POSTGRES_PASSWORD_FILE genauso, und ein Passwort
            # darf auf ein Leerzeichen enden.
            zusatz["password"] = Path(datei).read_text(
                encoding="utf-8").rstrip("\r\n")
        return psycopg.connect(url or BABU_DB_URL, **zusatz)
    pfad = Path(sqlite_pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(pfad)


# Postgres-Verbindungen sind teuer genug, dass eine pro Aufruf sich rächt —
# und alles, was hier läuft, läuft ohnehin unter `_DB_LOCK`. Also je Thread
# eine, wiederverwendet. SQLite bleibt beim Öffnen je Aufruf: das war schon
# so, kostet dort fast nichts, und die Testsuite setzt den Dateipfad
# zwischendurch um.
_ORTLICH = threading.local()

#: Test-Haken. Die SQLite-Suite verlässt sich darauf, dass jeder Test eine
#: frische, leere `portal.db` bekommt. Gegen ein echtes Postgres gäbe es nur
#: eine Datenbank für alle 1725 Tests. `conftest.py` hängt hier eine
#: Funktion ein, die zu jedem SQLite-Pfad ein eigenes Postgres-Schema
#: liefert — damit bleibt die Isolation, ohne dass ein einziger Test sich
#: ändern muss. Im Betrieb ist der Haken None und es passiert nichts.
SCHEMA_HAKEN = None


def _pg_verbindung(sqlite_pfad, url: str | None):
    conn = getattr(_ORTLICH, "conn", None)
    if conn is not None and getattr(conn, "closed", False):
        conn = None
    if conn is None:
        conn = verbindung(dialekt="postgres", url=url)
        _ORTLICH.conn = conn
        _ORTLICH.schema = None
        _ORTLICH.gewandert = set()
    if SCHEMA_HAKEN is not None:
        schema = SCHEMA_HAKEN(sqlite_pfad)
        if schema != getattr(_ORTLICH, "schema", None):
            with conn.cursor() as cur:
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                cur.execute(f'SET search_path TO "{schema}"')
            conn.commit()
            _ORTLICH.schema = schema
        if not hasattr(_ORTLICH, "gewandert"):
            _ORTLICH.gewandert = set()
        if schema not in _ORTLICH.gewandert:
            schema_anwenden(conn, "postgres")
            _ORTLICH.gewandert.add(schema)
    return conn


_PG_SCHEMA_GEFAHREN = False


@contextmanager
def oeffnen(sqlite_pfad: Path | str | None = None, dialekt: str | None = None,
            url: str | None = None):
    """Eine Verbindung für die Dauer eines Blocks — commit am Ende.

    Dieselbe Zusage wie `with sqlite3.connect(…) as conn:` bisher: geht der
    Block sauber zu Ende, wird committet; fliegt etwas, wird zurückgerollt.
    Neu ist nur, dass die Verbindung danach auch wirklich zugemacht wird
    (SQLite; die Postgres-Verbindung lebt je Thread weiter).
    """
    global _PG_SCHEMA_GEFAHREN
    d = dialekt or DIALEKT
    if d == "postgres":
        roh = _pg_verbindung(sqlite_pfad, url)
        if SCHEMA_HAKEN is None and not _PG_SCHEMA_GEFAHREN:
            schema_anwenden(roh, "postgres")
            _PG_SCHEMA_GEFAHREN = True
        # Verschachtelte Blöcke im selben Thread teilen sich die Verbindung;
        # nur der äußerste schließt die Transaktion ab.
        tiefe = getattr(_ORTLICH, "tiefe", 0)
        _ORTLICH.tiefe = tiefe + 1
        v = Verbindung(roh, d)
        try:
            yield v
        except BaseException:
            if tiefe == 0:
                roh.rollback()
            _ORTLICH.tiefe = tiefe
            raise
        else:
            if tiefe == 0:
                roh.commit()
            _ORTLICH.tiefe = tiefe
        return

    roh = verbindung(sqlite_pfad, d, url)
    v = Verbindung(roh, d)
    try:
        yield v
    except BaseException:
        roh.rollback()
        roh.close()
        raise
    else:
        roh.commit()
        roh.close()
