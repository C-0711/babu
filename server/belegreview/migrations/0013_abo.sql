-- 0013_abo — Abo per Stripe und die Provision, die sich selbst bucht (seit 03.10.2026).
--
-- Abbild der Inline-Anweisungen in `babu_web._sqlite_schema()` und
-- `mandanten.schema()`. Dieselbe Regel wie in 0001–0012: Postgres-Dialekt
-- hier, `db._fuer_sqlite()` übersetzt zurück, `tests/test_db_dialekt.py`
-- legt beide Schemata nebeneinander. Go-live-Plan Phase 2 und 4.
--
-- mandant              das Abo des Betriebs (abo.py: wer voll arbeitet, wer
--                      nur ansieht); alle Spalten NULL = kein Abo, wie bisher
-- ambassador_buchung   woher die Provision kam (Stripe-Rechnung oder Hand)
--                      und EIN Eintrag je Salon und Meilenstein — der
--                      eindeutige Index ist der Schutz gegen doppelte Provision
-- stripe_ereignis      jedes angenommene Stripe-Ereignis einmal (Wiederholung
--                      und Nachholen durch den täglichen Lauf ändern nichts)
-- abo_rechnung         jede Rechnung eines Abos; zählt die bezahlten Monate
-- tageslauf            was der tägliche Lauf heute schon erledigt hat
-- ambassador.heute_mail  ob sie die Mail „Heute für dich" bekommt
ALTER TABLE mandant ADD COLUMN paket TEXT;
ALTER TABLE mandant ADD COLUMN abo_status TEXT;
ALTER TABLE mandant ADD COLUMN stripe_kunde TEXT;
ALTER TABLE mandant ADD COLUMN stripe_abo TEXT;
ALTER TABLE mandant ADD COLUMN abo_seit TEXT;
ALTER TABLE mandant ADD COLUMN bezahlt_bis TEXT;
ALTER TABLE mandant ADD COLUMN abo_ende TEXT;
ALTER TABLE mandant ADD COLUMN zahlungsfehler_seit TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS mandant_stripe_abo ON mandant (stripe_abo);
ALTER TABLE ambassador_buchung ADD COLUMN stripe_rechnung TEXT;
ALTER TABLE ambassador_buchung ADD COLUMN quelle TEXT;
ALTER TABLE ambassador_buchung ADD COLUMN paket TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ambassador_buchung_einmal
    ON ambassador_buchung (code, email, meilenstein);
ALTER TABLE ambassador ADD COLUMN heute_mail INTEGER NOT NULL DEFAULT 1;
CREATE TABLE IF NOT EXISTS stripe_ereignis
    (ereignis TEXT PRIMARY KEY,
     typ TEXT NOT NULL,
     objekt TEXT,
     erstellt TEXT,
     empfangen TEXT NOT NULL,
     verarbeitet TEXT,
     fehler TEXT);
CREATE TABLE IF NOT EXISTS abo_rechnung
    (rechnung TEXT PRIMARY KEY,
     mandant_id INTEGER NOT NULL,
     abo TEXT,
     grund TEXT,
     paket TEXT,
     netto_cent INTEGER NOT NULL DEFAULT 0,
     brutto_cent INTEGER NOT NULL DEFAULT 0,
     status TEXT NOT NULL,
     monat_nr INTEGER,
     bezahlt_am TEXT,
     zeit TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS abo_rechnung_mandant ON abo_rechnung (mandant_id, status);
CREATE TABLE IF NOT EXISTS tageslauf
    (tag TEXT NOT NULL,
     aufgabe TEXT NOT NULL,
     erledigt TEXT NOT NULL,
     ergebnis TEXT,
     PRIMARY KEY (tag, aufgabe));
