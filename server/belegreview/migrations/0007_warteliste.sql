-- 0007_warteliste — Anmeldung nur über Einladung, davor die Warteliste.
--
-- Abbild der Inline-Anweisung aus `babu_web._sqlite_schema()`. Dieselbe Regel
-- wie in 0001–0006: Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt
-- zurück, `tests/test_db_dialekt.py` legt beide Schemata nebeneinander und
-- vergleicht Spalte für Spalte.
--
-- Wer sich anmelden will (Salon oder Kanzlei), hinterlässt E-Mail und Art.
-- Die Verwaltung entscheidet: Zugang einrichten (Startpasswort) oder
-- dankend ablehnen. Die E-Mail-Adresse ist der natürliche Schlüssel — dieselbe
-- Adresse, die schon anfragt, braucht keine zweite Zeile, sondern einen
-- Zähler und den neuesten Wunsch.
CREATE TABLE IF NOT EXISTS warteliste (
    email    TEXT PRIMARY KEY,
    art      TEXT NOT NULL DEFAULT 'salon',
    name     TEXT,
    salon    TEXT,
    telefon  TEXT,
    bemerkung TEXT,
    anfragen INTEGER NOT NULL DEFAULT 1,
    zeit     TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'wartet'
);
CREATE INDEX IF NOT EXISTS warteliste_status ON warteliste (status, zeit);
