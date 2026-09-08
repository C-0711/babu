-- 0005_post_adresse — die Empfangsadresse eines Betriebs für echte Post.
--
-- Abbild der Inline-Anweisung aus `postadresse.schema()`, die
-- `babu_web._sqlite_schema()` am Ende ruft. Dieselbe Regel wie in 0001–0004:
-- Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt zurück,
-- `tests/test_db_dialekt.py` legt beide Schemata nebeneinander und
-- vergleicht Spalte für Spalte.
--
-- Warum `lokal` der Schlüssel ist und nicht eine laufende `id`: die Adresse
-- ist von Natur aus eindeutig, jedes Nachschlagen geht über sie, und eine
-- Tabelle ohne `id`-Spalte braucht keinen Eintrag in `db.ID_TABELLEN`.
--
-- Der Fremdschlüssel zeigt auf `mandant(id)` — deshalb erst nach 0002. Er
-- steht hier bewusst (anders als bei `import_status`, wo `mandant_id` ohne
-- Schlüssel als TEXT liegt): eine Empfangsadresse ohne Betrieb dahinter
-- wäre eine offene Tür, durch die Post ins Nichts fällt.
--
-- `aktiv` statt Löschen: steht die Adresse einmal auf einem Briefkopf,
-- kommt Post noch Monate später. Eine stillgelegte Zeile weist sie ab und
-- verhindert zugleich, dass derselbe Zufallswert je neu vergeben wird.
CREATE TABLE IF NOT EXISTS post_adresse (
    lokal      TEXT PRIMARY KEY,
    mandant_id INTEGER NOT NULL REFERENCES mandant(id),
    angelegt   TEXT NOT NULL,
    aktiv      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS post_adresse_mandant ON post_adresse (mandant_id, aktiv);
