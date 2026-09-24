-- 0009_ambassador — Salon wirbt Salon: Codes, Zuordnung, Provision.
--
-- Ein Ambassador (zumeist eine Salon-Inhaberin, die babu selbst nutzt)
-- bekommt einen persönlichen Code. Damit erzeugt sie Einladungslinks; löst
-- ein Salon einen Link ein, steht seine Wartelisten-Zeile unter dem Code.
-- Zeichnet der Salon ab und bleibt 3 Monate, erhält die Ambassadorin
-- jeweils 25 % der Jahreszahlung (Vorschlag Vertriebskonzept 19.09.2026) —
-- die Anerkennung ist manuell (Verwaltung hakt ab), die Zuordnung nicht.
--
-- ambassador         die Person + ihr Code
-- ambassador_salon   ein geworbener Salon und sein Meilenstein-Stand
CREATE TABLE IF NOT EXISTS ambassador
    (code TEXT PRIMARY KEY,
     email TEXT NOT NULL,
     name TEXT NOT NULL,
     erstellt TEXT NOT NULL,
     aktiv INTEGER NOT NULL DEFAULT 1,
     verdient INTEGER NOT NULL DEFAULT 0,
     gezahlt INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ambassador_salon
    (code TEXT NOT NULL,
     email TEXT NOT NULL,
     salon TEXT,
     eingelöst TEXT NOT NULL,
     meilenstein TEXT NOT NULL DEFAULT 'testet',
     verdienst INTEGER NOT NULL DEFAULT 0,
     PRIMARY KEY (code, email),
     FOREIGN KEY (code) REFERENCES ambassador(code));
ALTER TABLE warteliste ADD COLUMN herkunft_code TEXT;
