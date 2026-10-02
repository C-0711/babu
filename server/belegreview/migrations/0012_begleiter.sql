-- 0012_begleiter — der Begleiter der Ambassadorin (seit 03.10.2026).
--
-- Abbild der Inline-Nachrüstung in `babu_web._sqlite_schema()`. Dieselbe
-- Regel wie in 0001–0011: Postgres-Dialekt hier, `db._fuer_sqlite()`
-- übersetzt zurück, `tests/test_db_dialekt.py` legt beide Schemata nebeneinander.
--
-- Jede Einladung trägt jetzt, wen sie eingeladen hat (Vorname) und die
-- Handynummer (nur Ziffern, international). babu schlägt daraus Nachrichten
-- vor (begleiter.py); was sie davon verschickt hat, steht in erinnert_am /
-- erinnerungen / erinnert_art (Grenze: alle drei Tage, je Lage höchstens
-- drei). weiter_am: sie hat gemeldet, dass der Salon weitermachen will.
ALTER TABLE ambassador_einladung ADD COLUMN person TEXT;
ALTER TABLE ambassador_einladung ADD COLUMN telefon TEXT;
ALTER TABLE ambassador_einladung ADD COLUMN erinnert_am TEXT;
ALTER TABLE ambassador_einladung ADD COLUMN erinnerungen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ambassador_einladung ADD COLUMN erinnert_art TEXT;
ALTER TABLE ambassador_einladung ADD COLUMN weiter_am TEXT;
