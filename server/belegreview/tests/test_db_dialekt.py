"""Die Datenbankschicht: übersetzt sie richtig, und ist das Schema dasselbe?

Drei Fragen, in dieser Reihenfolge:

1. **Übersetzt `db.py` korrekt?** Platzhalter, Upsert, Migrations-Runner —
   alles ohne Datenbank prüfbar, reine Textarbeit.
2. **Ergeben Inline-Statements und Migrationsdatei dasselbe Schema?** Das
   ist die Naht, an der die beiden Wege auseinanderlaufen könnten
   (`babu_web._sqlite_schema` gegen `migrations/0001_initial.sql`). Läuft
   ohne Postgres, weil die Migrationsdatei sich auch auf SQLite anwenden
   lässt.
3. **Tut Postgres wirklich, was wir annehmen?** Nur diese Tests tragen
   `@pytest.mark.pg` und werden übersprungen, wenn keine Instanz da ist.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import db  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Textarbeit
# ---------------------------------------------------------------------------

def test_platzhalter_sqlite_laesst_alles_stehen():
    sql = "SELECT a FROM t WHERE b=? AND c IN (?,?)"
    assert db.platzhalter(sql, "sqlite") == sql


def test_platzhalter_postgres_uebersetzt_jedes_fragezeichen():
    assert (db.platzhalter("SELECT a FROM t WHERE b=? AND c IN (?,?)", "postgres")
            == "SELECT a FROM t WHERE b=%s AND c IN (%s,%s)")


def test_kein_sql_literal_traegt_ein_echtes_fragezeichen():
    """Die Annahme, auf der `platzhalter()` steht — hier festgenagelt.

    `platzhalter()` ersetzt stumpf jedes `?`. Das ist nur sicher, solange
    kein SQL-Text ein Fragezeichen als Zeichen enthält (und kein `%`, das
    psycopg sonst als eigene Interpolation läse). Wer das bricht, soll es
    hier merken und nicht erst in der Produktion.
    """
    import ast  # noqa: PLC0415
    import io  # noqa: PLC0415
    import re  # noqa: PLC0415
    import tokenize  # noqa: PLC0415

    quelle = (HIER.parent / "babu_web.py").read_text(encoding="utf-8")
    sql_woerter = re.compile(
        r"\b(SELECT|INSERT INTO|UPDATE |DELETE FROM|CREATE TABLE|CREATE INDEX"
        r"|ALTER TABLE)\b")
    # Ein Fragezeichen ist ein Platzhalter, wenn links eine Klammer, ein
    # Komma, ein Gleichheitszeichen oder Leerraum steht und rechts ein
    # Komma, eine Klammer, Leerraum oder das Ende der Zeichenkette.
    platzhalter = re.compile(r"(?<=[(,=\s])\?(?=[,)\s]|$)")

    fremd, prozente, gezaehlt, literale = [], [], 0, 0
    for t in tokenize.generate_tokens(io.StringIO(quelle).readline):
        if t.type != tokenize.STRING:
            continue
        try:
            wert = ast.literal_eval(t.string)
        except Exception:                      # noqa: BLE001 — f-string
            wert = t.string
        if not isinstance(wert, str) or not sql_woerter.search(wert):
            continue
        literale += 1
        # Bei f-strings steht das schließende Anführungszeichen noch dran;
        # dann ist ein `?` am Ende kein Textende, sondern ein Platzhalter.
        pruef = wert.rstrip("\"'")
        erlaubt = {m.start() for m in platzhalter.finditer(pruef)}
        for m in re.finditer(r"\?", pruef):
            gezaehlt += 1
            if m.start() not in erlaubt:
                fremd.append(pruef[max(0, m.start() - 40):m.start() + 20])
        prozente += [wert] * wert.count("%")

    assert literale > 100, "die SQL-Literale wurden nicht gefunden"
    assert gezaehlt > 200, "die Platzhalter wurden nicht gefunden"
    assert fremd == [], f"literales ? in SQL — platzhalter() bricht daran: {fremd}"
    assert prozente == [], f"% in SQL — psycopg deutet das als Platzhalter: {prozente}"


def test_upsert_sqlite_ist_insert_or_replace():
    assert (db.upsert("lesestatus", ("un", "dokument", "zeit"),
                      ("un", "dokument"), "sqlite")
            == "INSERT OR REPLACE INTO lesestatus (un, dokument, zeit) "
               "VALUES (?, ?, ?)")


def test_upsert_postgres_ist_on_conflict():
    assert (db.upsert("lesestatus", ("un", "dokument", "zeit"),
                      ("un", "dokument"), "postgres")
            == "INSERT INTO lesestatus (un, dokument, zeit) VALUES (?, ?, ?) "
               "ON CONFLICT (un, dokument) DO UPDATE SET zeit=EXCLUDED.zeit")


def test_upsert_ohne_uebrige_spalten_tut_nichts():
    """Bestehen alle Spalten aus dem Schlüssel, gäbe es nichts zu setzen —
    ein leeres `SET` wäre ein Syntaxfehler."""
    assert db.upsert("t", ("a", "b"), ("a", "b"), "postgres").endswith("DO NOTHING")


def test_upsert_weist_eine_fremde_konfliktspalte_ab():
    with pytest.raises(ValueError):
        db.upsert("t", ("a", "b"), ("c",), "postgres")


def test_upsert_der_drei_stellen_nennt_jede_spalte():
    """Der Unterschied zwischen REPLACE und ON CONFLICT DO UPDATE fällt nur
    dann nicht auf, wenn jede Spalte der Tabelle genannt wird — sonst
    verlöre die eine Fassung Werte, die die andere behielte."""
    for tabelle, spalten in (("lesestatus", ("un", "dokument", "zeit")),
                             ("einstellungen", ("un", "schluessel", "wert")),
                             ("abschluss_status", ("un", "jahr", "json", "zeit"))):
        assert set(spalten) == _spalten_der_migration(tabelle), tabelle


def _spalten_der_migration(tabelle: str) -> set[str]:
    conn = sqlite3.connect(":memory:")
    db.schema_anwenden(conn, "sqlite")
    zeilen = conn.execute(f"PRAGMA table_info({tabelle})").fetchall()
    conn.close()
    return {z[1] for z in zeilen}


def test_fuer_sqlite_uebersetzt_identity_und_double():
    sql = db._fuer_sqlite(
        "CREATE TABLE t (id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
        "p DOUBLE PRECISION, z TIMESTAMPTZ, j JSONB)")
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" in sql
    assert "IDENTITY" not in sql
    assert "REAL" in sql and "DOUBLE" not in sql
    assert "TIMESTAMPTZ" not in sql and "JSONB" not in sql


def test_anweisungen_trennt_nicht_in_zeichenketten():
    sql = "CREATE TABLE a (x TEXT DEFAULT 'ein;zwei'); CREATE TABLE b (y TEXT)"
    assert len(list(db._anweisungen(sql))) == 2


def test_anweisungen_ueberspringt_kommentare():
    sql = "-- ein Kommentar; mit Semikolon\nCREATE TABLE a (x TEXT);"
    stuecke = list(db._anweisungen(sql))
    assert len(stuecke) == 1
    assert stuecke[0].startswith("CREATE TABLE a")


# ---------------------------------------------------------------------------
# 2. Migrations-Runner und Schema-Gleichheit
# ---------------------------------------------------------------------------

def test_runner_faehrt_einmal_und_dann_nicht_mehr():
    conn = sqlite3.connect(":memory:")
    erst = db.schema_anwenden(conn, "sqlite")
    assert "0001_initial.sql" in erst
    assert db.schema_anwenden(conn, "sqlite") == [], "zweiter Lauf muss leer sein"
    stand = conn.execute("SELECT nummer, datei FROM schema_version").fetchall()
    assert stand == [(1, "0001_initial.sql"), (2, "0002_kanzlei_mandant_audit.sql"), (3, "0003_kanzlei_ohne_nutzer_fk.sql")]
    conn.close()


def test_runner_zaehlt_nur_nummerierte_dateien(tmp_path):
    (tmp_path / "0001_eins.sql").write_text("CREATE TABLE a (x TEXT);")
    (tmp_path / "0002_zwei.sql").write_text("CREATE TABLE b (x TEXT);")
    (tmp_path / "notizen.sql").write_text("CREATE TABLE c (x TEXT);")
    (tmp_path / "0003_drei.txt").write_text("CREATE TABLE d (x TEXT);")
    conn = sqlite3.connect(":memory:")
    assert db.schema_anwenden(conn, "sqlite", tmp_path) == ["0001_eins.sql",
                                                            "0002_zwei.sql"]
    tabellen = {z[0] for z in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"a", "b"} <= tabellen
    assert "c" not in tabellen and "d" not in tabellen
    conn.close()


def test_runner_holt_eine_nachgereichte_migration_nach(tmp_path):
    (tmp_path / "0001_eins.sql").write_text("CREATE TABLE a (x TEXT);")
    conn = sqlite3.connect(":memory:")
    db.schema_anwenden(conn, "sqlite", tmp_path)
    (tmp_path / "0002_zwei.sql").write_text("CREATE TABLE b (x TEXT);")
    assert db.schema_anwenden(conn, "sqlite", tmp_path) == ["0002_zwei.sql"]
    conn.close()


def _schema_aus_inline(pfad: Path) -> dict[str, set[str]]:
    """Alles, was der Code im Betrieb von selbst anlegt.

    Das sind zwei Stellen: die 23 Tabellen aus `babu_web._sqlite_schema()`
    (18 eigene plus audit/passwort_reset/kanzlei/mandant/kanzlei_mitglied)
    und `meldung_puffer`, das `gitlab_meldungen` beim ersten Puffern
    nachzieht. Ausdrücklich mit `"sqlite"` geöffnet und nicht über
    `babu_web._db()`: dieser Vergleich gilt dem SQLite-Weg, auch wenn die
    Suite gerade gegen Postgres läuft.
    """
    import babu_web  # noqa: PLC0415
    import gitlab_meldungen  # noqa: PLC0415
    with db.oeffnen(pfad, "sqlite") as conn:
        babu_web._sqlite_schema(conn)
        gitlab_meldungen._puffer_tabelle(conn)
    return _tabellen(sqlite3.connect(pfad))


def _tabellen(conn) -> dict[str, set[str]]:
    namen = [z[0] for z in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name <> 'schema_version'")]
    ergebnis = {n: {z[1] for z in conn.execute(f"PRAGMA table_info({n})")}
                for n in namen}
    conn.close()
    return ergebnis


def test_migration_bildet_die_inline_tabellen_ab(tmp_path):
    """Die eigentliche Absicherung: beide Wege, ein Schema.

    Solange die SQLite-Seite ihre Inline-Statements behält und Postgres aus
    `migrations/` kommt, könnten die beiden auseinanderlaufen. Hier laufen
    sie nebeneinander und werden Spalte für Spalte verglichen.
    """
    inline = _schema_aus_inline(tmp_path / "inline.db")
    gewandert = sqlite3.connect(tmp_path / "migriert.db")
    db.schema_anwenden(gewandert, "sqlite")
    migriert = _tabellen(gewandert)

    assert set(inline) == set(migriert), (
        f"nur inline: {set(inline) - set(migriert)}; "
        f"nur Migration: {set(migriert) - set(inline)}")
    assert len(inline) == 24, f"24 Tabellen erwartet, {len(inline)} gefunden"
    for tabelle in sorted(inline):
        assert inline[tabelle] == migriert[tabelle], tabelle


def test_id_tabellen_sind_die_mit_einer_id(tmp_path):
    """`db.ID_TABELLEN` steuert, wo Postgres `RETURNING id` anhängt.

    Vergisst jemand eine neue Tabelle darin, liefert `lastrowid` dort still
    None — und der Code baut eine Antwort mit einer Nummer, die es nicht
    gibt. Deshalb wird die Menge gegen das Schema geprüft.
    """
    conn = sqlite3.connect(tmp_path / "s.db")
    db.schema_anwenden(conn, "sqlite")
    mit_id = set()
    for name in _tabellen(sqlite3.connect(tmp_path / "s.db")):
        spalten = conn.execute(f"PRAGMA table_info({name})").fetchall()
        # z = (cid, name, typ, notnull, default, pk)
        if any(z[1] == "id" and z[5] for z in spalten):
            mit_id.add(name)
    conn.close()
    assert mit_id == set(db.ID_TABELLEN)


# ---------------------------------------------------------------------------
# 3. Gegen ein echtes Postgres
# ---------------------------------------------------------------------------

@pytest.fixture()
def pg(pg_url, pg_schema):
    """Eine Verbindung in ein frisches Schema, Migrationen schon gefahren."""
    import psycopg  # noqa: PLC0415
    conn = psycopg.connect(pg_url)
    conn.execute(f'SET search_path TO "{pg_schema}"')
    conn.commit()
    db.schema_anwenden(conn, "postgres")
    try:
        yield db.Verbindung(conn, "postgres")
    finally:
        conn.close()


@pytest.mark.pg
def test_pg_schema_steht_und_traegt_alle_tabellen(pg, pg_schema):
    zeilen = pg.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=?",
        (pg_schema,)).fetchall()
    namen = {z[0] for z in zeilen}
    assert "schema_version" in namen
    assert len(namen - {"schema_version"}) == 24


@pytest.mark.pg
def test_pg_lastrowid_kommt_aus_returning(pg):
    zeiger = pg.execute(
        "INSERT INTO kundin (un, name, angelegt) VALUES (?,?,?)",
        ("nina", "Frau Holder", "2026-09-02T10:00:00"))
    assert isinstance(zeiger.lastrowid, int) and zeiger.lastrowid > 0
    zweite = pg.execute("INSERT INTO kundin (un, name, angelegt) VALUES (?,?,?)",
                        ("nina", "Frau Bosch", "2026-09-02T10:01:00"))
    assert zweite.lastrowid == zeiger.lastrowid + 1


@pytest.mark.pg
def test_pg_ohne_id_spalte_kein_returning(pg):
    """`app_schluessel` hat keine `id` — dort darf nichts angehängt werden,
    sonst bräche jedes Einfügen mit einem Syntaxfehler."""
    zeiger = pg.execute("INSERT INTO app_schluessel VALUES (?,?,?,?,?)",
                        ("abc", "nina", "iPhone", "2026-09-02", None))
    assert zeiger.lastrowid is None


@pytest.mark.pg
def test_pg_upsert_ueberschreibt(pg):
    sql = db.upsert("einstellungen", ("un", "schluessel", "wert"),
                    ("un", "schluessel"), "postgres")
    pg.execute(sql, ("nina", "rahmen", "SKR03"))
    pg.execute(sql, ("nina", "rahmen", "SKR04"))
    zeilen = pg.execute("SELECT wert FROM einstellungen WHERE un=?",
                        ("nina",)).fetchall()
    assert zeilen == [("SKR04",)]


@pytest.mark.pg
def test_pg_zeilen_kommen_als_tupel(pg):
    """Der ganze Code liest `z[0]` — Tupel sind also die Vorgabe, nicht
    Wörterbücher, auch wenn psycopg beides kann."""
    pg.execute("INSERT INTO leistung (un, name, preis, minuten) VALUES (?,?,?,?)",
               ("nina", "Waschen", 25.0, 30))
    zeile = pg.execute("SELECT name, preis FROM leistung").fetchone()
    assert zeile == ("Waschen", 25.0)


@pytest.mark.pg
def test_pg_row_factory_liefert_namen(pg):
    pg.execute("INSERT INTO anlagegut (un, bezeichnung, angeschafft, wert_cent) "
               "VALUES (?,?,?,?)", ("nina", "Frisierstuhl", "2026-01-02", 120000))
    pg.row_factory = db.ZEILEN_MIT_NAMEN
    zeile = pg.execute("SELECT * FROM anlagegut").fetchone()
    assert zeile["bezeichnung"] == "Frisierstuhl"
    assert zeile["wert_cent"] == 120000


@pytest.mark.pg
def test_pg_migration_ist_idempotent(pg_url, pg_schema):
    import psycopg  # noqa: PLC0415
    conn = psycopg.connect(pg_url)
    conn.execute(f'SET search_path TO "{pg_schema}"')
    conn.commit()
    assert db.schema_anwenden(conn, "postgres") == ["0001_initial.sql", "0002_kanzlei_mandant_audit.sql", "0003_kanzlei_ohne_nutzer_fk.sql"]
    assert db.schema_anwenden(conn, "postgres") == []
    conn.close()


@pytest.mark.pg
def test_pg_double_precision_verliert_keine_cents(pg):
    """Postgres' REAL wäre 4 Byte — deshalb steht DOUBLE PRECISION im
    Schema. Der Test hält fest, warum."""
    pg.execute("INSERT INTO leistung (un, name, preis, minuten) VALUES (?,?,?,?)",
               ("nina", "Balayage", 189.95, 120))
    assert pg.execute("SELECT preis FROM leistung").fetchone()[0] == 189.95


def test_eine_nur_postgres_migration_wird_in_sqlite_uebersprungen_aber_gemerkt(tmp_path):
    """`-- nur: postgres` (0003 nimmt einen Fremdschlüssel weg, das kann SQLite
    nicht): SQLite fährt nichts, trägt die Nummer aber ein — beide Seiten
    zeigen dieselbe Versionsliste."""
    (tmp_path / "0001_a.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);")
    (tmp_path / "0002_b.sql").write_text("-- nur: postgres\nALTER TABLE a DROP CONSTRAINT IF EXISTS gibt_es_nicht;")
    conn = sqlite3.connect(tmp_path / "s.db")
    assert db.schema_anwenden(conn, "sqlite", tmp_path) == ["0001_a.sql", "0002_b.sql"]
    assert db.schema_anwenden(conn, "sqlite", tmp_path) == []
