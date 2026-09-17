-- 0008_warteliste_appleid — die Apple-ID für die App-Einladung.
--
-- Abbild der Inline-Nachrustung in `babu_web._sqlite_schema()` (dort als
-- ALTER TABLE mit OperationalError-Fang, wie `sitzung_ab`). Dieselbe Regel
-- wie in 0001–0007: Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt
-- zurück, `tests/test_db_dialekt.py` legt beide Schemata nebeneinander.
--
-- Warum ein eigenes Feld und nicht die bemerkung: Die App-Einladung läuft
-- über TestFlight, und die geht an die Apple-ID — nicht an die babu-Adresse
-- (siehe startguide.testflight_absatz). Die Verwaltung trägt die Adresse in
-- die Wartelisten-Karte ein, sobald sie da ist; der Abgleich-Dienst
-- (werkzeuge/testflight_abgleich.py, Host-Cron) nimmt daraus von selbst die
-- Einladung vor und setzt `app_status`.
ALTER TABLE warteliste ADD COLUMN apple_id TEXT;
ALTER TABLE warteliste ADD COLUMN app_status TEXT;
