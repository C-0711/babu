-- 0018_paket — die Stufen: Platz statt Funktionen (seit 10.10.2026).
--
-- Abbild der Inline-Anweisungen in `mandanten.schema()`. Dieselbe Regel wie
-- in 0001–0017: Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt zurück,
-- `tests/test_db_dialekt.py` legt beide Schemata nebeneinander.
--
-- herkunft        woher der Betrieb kam. "app" = über den App Store, ohne
--                 Anmeldung, mit Gerätekonto. NULL = über das Portal, wie
--                 jeder Betrieb bis heute — für die ändert sich nichts.
-- apple_abo       die originalTransactionId des Apple-Abos (eindeutig: ein
--                 Abo gehört genau einem Betrieb, sonst zahlt einer für zwei)
-- apple_produkt   die gekaufte Produkt-Kennung; paket.stufe_fuer_produkt()
--                 macht daraus die Stufe
-- speicher_bytes  was belegt ist, zuletzt gezählt
-- belege_gesamt   wie viele Belege je abgelegt wurden — zählt nur aufwärts,
--                 damit Löschen das Freikontingent nicht zurücksetzt
ALTER TABLE mandant ADD COLUMN herkunft TEXT;
ALTER TABLE mandant ADD COLUMN apple_abo TEXT;
ALTER TABLE mandant ADD COLUMN apple_produkt TEXT;
ALTER TABLE mandant ADD COLUMN speicher_bytes BIGINT NOT NULL DEFAULT 0;
ALTER TABLE mandant ADD COLUMN belege_gesamt INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS mandant_apple_abo ON mandant (apple_abo);
