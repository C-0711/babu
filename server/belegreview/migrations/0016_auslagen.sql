-- 0016_auslagen — babu Expenses D1: Auslagen der Mitarbeiterinnen (seit 04.10.2026).
--
-- Abbild der Inline-Anweisungen in `babu_web._sqlite_schema()`. Dieselbe Regel
-- wie in 0001–0015: Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt zurück.
--
-- team.darf_auslagen   darf diese Person Auslagen einreichen (0/1)
-- team.iban            wohin die Erstattung geht (trägt die Mitarbeiterin selbst ein)
-- push_geraet          ein Gerät je Zeile; kein Fremdschlüssel auf nutzer(email),
--                      PAT-Konten haben keine nutzer-Zeile
ALTER TABLE team ADD COLUMN darf_auslagen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE team ADD COLUMN iban TEXT;
CREATE TABLE IF NOT EXISTS push_geraet (
    token       TEXT PRIMARY KEY,
    un          TEXT NOT NULL,
    umgebung    TEXT NOT NULL,
    thema       TEXT NOT NULL,
    angelegt_am TEXT NOT NULL,
    zuletzt_am  TEXT NOT NULL
);
