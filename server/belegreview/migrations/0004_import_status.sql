-- 0004_import_status — der Stand eines Massenimports je Mandant.
--
-- Abbild der Inline-Anweisung aus `babu_web._sqlite_schema()`. Dieselbe
-- Regel wie in 0001–0003: Postgres-Dialekt hier, `db._fuer_sqlite()`
-- übersetzt zurück, `tests/test_db_dialekt.py` legt beide Schemata
-- nebeneinander und vergleicht Spalte für Spalte.
--
-- Warum eine Tabelle und nicht nur der Speicher: der Lauf läuft in einem
-- Faden im Prozess. Startet der Prozess neu, ist das Register leer — und
-- ohne diese Zeile wüsste niemand mehr, dass für einen Mandanten gerade
-- 200 Belege unterwegs waren. Genau eine Zeile je Mandant: was zählt, ist
-- der letzte Lauf.
--
-- `mandant_id` steht als TEXT und ohne Fremdschlüssel — wie
-- `audit_log.mandant_id`. Ein gelöschter Mandant soll den Stand nicht
-- mitreißen, und die Tabelle hat keine `id`-Spalte (also nichts für
-- `db.ID_TABELLEN`).
CREATE TABLE IF NOT EXISTS import_status (
    mandant_id TEXT PRIMARY KEY,
    lauf       TEXT,
    json       TEXT NOT NULL,
    zeit       TEXT NOT NULL
);
