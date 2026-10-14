-- 0019_konto_loeschen — was von einem gelöschten Konto bleibt (14.10.2026).
--
-- Abbild der Inline-Anweisung in `kern_konto.schema()`. Dieselbe Regel wie
-- in 0001–0018: Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt zurück,
-- `tests/test_db_dialekt.py` legt beide Schemata nebeneinander.
--
-- Apple verlangt, dass ein Konto in der App gelöscht werden kann (5.1.1(v)).
-- Gelöscht wird dabei alles, was babu über den Zugang führt — diese Zeile
-- ist das Einzige, was übrig bleibt, und sie nennt niemanden:
--
-- mandant_id   die Nummer des Betriebs, der es war
-- box_ref      der Verweis auf die Belegbox. babu leert sie in einem Commit;
--              das Repo selbst samt Historie löscht nur der Betreiber, denn
--              der GitChain-Dienst kennt dafür keinen Weg (box.py spricht
--              ausschliesslich Git über HTTP). Deshalb IST diese Tabelle die
--              Arbeitsliste des Betreibers.
-- dateien      wie viele Dateien aus der Box genommen wurden
-- box_leer     ob das Leeren geklappt hat (0 = da liegt noch etwas)
-- zeit         wann gelöscht wurde
--
-- KEIN Fremdschlüssel auf mandant(id): die Zeile überlebt den Mandanten.
CREATE TABLE IF NOT EXISTS geloescht
    (mandant_id INTEGER PRIMARY KEY,
     box_ref TEXT,
     dateien INTEGER NOT NULL DEFAULT 0,
     box_leer INTEGER NOT NULL DEFAULT 0,
     zeit TEXT NOT NULL);
