-- 0015_bank_freigabe — der Betrieb gibt seiner Kanzlei die Kontoumsätze frei (seit 04.10.2026).
--
-- Abbild der Inline-Anweisungen in `mandanten.schema()`. Dieselbe Regel wie
-- in 0001–0014: Postgres-Dialekt hier, `db._fuer_sqlite()` übersetzt zurück.
-- Plan Kanzleiansicht, Schritt B1.
--
-- mandant.bank_freigabe_am       wann der Betrieb freigegeben hat (NULL = nicht)
-- mandant.bank_freigabe_fassung  welcher Fassung des Freigabetexts (recht.fassung)
-- mandant.bank_freigabe_von      wer freigegeben hat
-- mandant.bank_widerruf_am       wann zuletzt widerrufen wurde
-- mandant.bank_anfrage_am        wann die Kanzlei zuletzt angefragt hat
--
-- Eine Zeile `mandant` ist genau eine Kanzlei und ein Betrieb — die Freigabe
-- gilt damit für genau diese Kanzlei.
ALTER TABLE mandant ADD COLUMN bank_freigabe_am TEXT;
ALTER TABLE mandant ADD COLUMN bank_freigabe_fassung TEXT;
ALTER TABLE mandant ADD COLUMN bank_freigabe_von TEXT;
ALTER TABLE mandant ADD COLUMN bank_widerruf_am TEXT;
ALTER TABLE mandant ADD COLUMN bank_anfrage_am TEXT;
