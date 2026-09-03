-- nur: postgres
-- 0003_kanzlei_ohne_nutzer_fk — die Kanzlei-Seite darf ein PAT-Konto sein.
--
-- `kanzlei.inhaber_un` und `kanzlei_mitglied.un` zeigten per Fremdschlüssel
-- auf `nutzer(email)`. Der Betreiber und Kanzlei-Zugänge kommen aber auch
-- per PAT über BABU_ERLAUBT/BABU_ROLLEN (z. B. „christoph0711.io") und haben
-- keine nutzer-Zeile — Postgres prüft den Schlüssel wirklich, SQLite nicht,
-- deshalb sah kein Test das. Erster Mandant im Betrieb: 500 (03.09.2026).
-- `mandant.besitzer_un` behält seinen Schlüssel: den Salon legt die Route
-- immer als Konto an, bevor der Mandant entsteht.
ALTER TABLE kanzlei DROP CONSTRAINT IF EXISTS kanzlei_inhaber_un_fkey;
ALTER TABLE kanzlei_mitglied DROP CONSTRAINT IF EXISTS kanzlei_mitglied_un_fkey;
