# Übergabe DATEV-Sitzung, 02.09.2026

Die Sitzung brach um 18:28 mitten im Planungsmodus ab. Dieser Ordner hält fest,
was aus dem Transkript gerettet wurde, damit die Planung ohne Neuanfang weitergeht.

## Was bereits auf main liegt (deployt, Suite 1608 grün)

- `ac0bf64` 19:45 — Buchungsstapel trägt beide Seiten (Kassenblätter als
  Tageseinnahmen, Geldtransit 1460, Kleinunternehmerin 4184); 183 Automatikkonten
  aus dem SKR04-PDF (`skr04_automatik.py`), kein BU-Schlüssel auf AV/AM-Konten.
- `39b14c6` 19:55 — Einlesen netto statt brutto, alte Historie-Stände werden aus
  den Originalen nachgelesen. Erster Fremdtest: Ninas Kanzlei-Stapel April 2026.
- `d163ac6` 20:11 — ganzer SKR04 2026 als `skr04_konten.py` (1.516 Konten) plus
  Test `test_skr04_konten.py`.

## Der offene Auftrag (18:15, `00-auftrag.md`)

1. SKR04-Konten komplett auslesen und als Embeddings im Kontext verfügbar machen.
2. Alle DATEV-Themen im Frontend und Backend hochladen, sortiert, in den Kontext
   (Chat und Buchungs-Prompt).
3. Pro-Zugang für Steuerberater, die im Backend hunderte Mandanten verwalten.
   Nachgeschoben: Postgres deployen falls nötig, alles in Docker.
4. 26 Portal-Befunde, Reihenfolge laut Auftrag: 1+2+3, dann 4, dann 6, dann 5,
   dann der Rest.

## Stand der Planung

- Drei Erkundungen sind fertig (`01`–`03`): Kompendium-Format samt harter
  Invariante (Zeilen in `atome.jsonl` == Zeilen in `vektoren.npy`, sonst schweigt
  das Kompendium), alle Ein-Box-Annahmen im Rollenmodell, Code-Stellen hinter den
  P0/P1-Befunden.
- Drei Planaufträge (`10`–`12`) waren gestartet, als die Sitzung abbrach. Sie
  wurden am Abend erneut ausgeführt (Sonnet), Ergebnisse in `20`–`22`.
- `30-gesamtplan.md` ordnet die drei Pläne in eine Reihenfolge und listet die
  Entscheidungen, die vor dem Bauen beim Auftraggeber liegen.

Die Erkundungen sind Agenten-Ausgaben mit Zeilennummern vom Stand `d163ac6`.

## Umsetzungsstand (Branch `claude/session-context-210439`)

Welle 1, 02.09. abends, fünf Agenten parallel, alles auf dem Branch, Suite 1680 grün:

- Rollen-Fallback fail-closed (Plan 21, Phase 0).
- P0-1, P0-2, P0-3 (Plan 22, Runde 1): eine Kategorie und eine Ausgaben-Zahl
  überall, gedruckte Steuerzeilen gewinnen (Server, Prompt, iOS), Export-Summe.
- Wissensschicht Phasen 2–6 (Plan 20): Modul `datev_wissen.py`, Fach „Wissen",
  `POST /api/wissen`, Suche in Chat und Buchung, Portal-Upload.
- Wissensschicht Phasen 1 und 7: Host-Skript `werkzeuge/kompendium/skr04_atome_bauen.py`
  (noch NICHT auf der H200V gelaufen) und `werkzeuge/wissen-import/datev_ordner_hochladen.py`.
- P1-7, P1-8, P2 9–16 und 19–20 (Plan 22, Runden 5 und 6). Offen: 17, 18.

Welle 2 läuft: P0-4 „Wird gelesen" + P3-26, Runde 3 (Kassenbuch, Rechnung,
Termine-Woche, Salon-Check-Korrektur). Danach Runde 4 (Desktop-Layout).

**Deployt 02.09. 21:50** (main `c6a2ed6`, Freigabe des Auftraggebers): Golden vorher/nachher
unter `~/golden/` auf der H200V, `/api/abgleich/*` byte-identisch, `/api/belege` weicht
in 392 Zeilen ab, alle `belegart` (vorher null, jetzt Kategorie — der P0-1-Fix).
Sicherung `~/backups/babu-docker-vor-deploy-20260902-2148.tgz`. Live geprüft:
`/api/ich` (`hat_passwort`), `/api/monat` (`export`), `/api/monatsabschluss`
(`aus_vertrag`), `/api/wissen/status`, `/portal` (neue Funktionen im Bundle),
Container-Log ohne Fehler.

**Kompendium-Rebuild 02.09. 21:57** auf dem Host gelaufen: Skript liegt unter
`~/babu-werkzeuge/werkzeuge/kompendium/` (Symlink `~/babu-werkzeuge/server -> ~/babu-docker`
stellt die Repo-Struktur nach). 89.760 → 91.459 Atome (1.699 SKR04), Invariante geprüft,
Sicherungen `~/kompendium/*.bak-20260902-215704`, Kontenübersicht (27 Kategorien) in
`kontierung-grundwissen.md`, Container neu gestartet, Laden im Container verifiziert.

**Produktiv-Vorfall und Fix, 02.09. 22:15** (Commit `87624ec`): der erste
DATEV-Upload-Versuch hat den Container abstürzen lassen — `pypdfium2` ist
zwischen Threads nicht threadsicher, und seit `_wissen_job` PDFs im
Hintergrund liest, überlappte das mit anderen Anfragen. Docker startete
den Prozess automatisch neu, acht von zehn Uploads blieben aus. Fix:
`PDFIUM_LOCK` in `abschluss_lesen.py`, geteilt mit `kontoauszug.py` und
drei Inline-Stellen in `babu_web.py`. `tests/test_pdfium_lock.py` beweist
es: ohne Schloss crasht der dritte parallele Testlauf zuverlässig
(`Fatal Python error: Aborted`), mit Schloss fünf von fünf grün. Deployt,
Golden byte-identisch, alle zehn DATEV-Dokumente danach erfolgreich
hochgeladen und eingelesen (zwei hängende aus dem Absturz per Hand über
die bestehende `_wissen_job`-Funktion nachgeholt, kein neuer Code dafür).

Noch nicht: der iOS-Build auf Ninas iPhone (P0-2-Anteil in `Store.swift`) — auf
Wunsch des Auftraggebers später. Der Getränkemarkt-Beleg wurde nicht nachgestellt
(Rohdaten nur lokal).

**Welle 3, 02./03.09. nachts** (Branch `claude/belege-table-rendering-db4f82`,
lokal, nicht gepusht, nicht deployt) — Runde 4 und der Pro-Zugang, Plan 21,
mit Subagenten in zwei Wellen, jede Übernahme per Cherry-Pick, Suite danach
in BEIDEN Dialekten:

- Runde 4 (P1-5, `2cc05ee`): Belege ab 1180px als sortierbare Tabelle,
  `.spalten`-Raster mit zwei festen Spalten (auto-fit kollabierte nichts —
  gemessen 433px-Karten, korrigiert), Einzelkarten volle Breite.
- Seitenleiste (`cb6e611`): Konto-Dropdown wird ab 821px eine einklappbare
  linke Leiste (Prototyp `~/Downloads/seitennav.html`, fünf gemessene
  Fehler behoben: Login-Sperre, Mobil-Dropdown, `[hidden]`, Name/Rolle,
  Header-Höhe); Zugänge-Ansicht mit Belegbox-freigeben-Knopf, Rolle
  Mitarbeit, Suche und Pager à 25; `.spalten` per Container-Query.
- Plan 21 §7 (`ebf12e7`): `audit.py` (Tabelle `audit_log`, `GET /api/audit`
  nur admin), `passwort_reset.py` — Reset-Link statt Klartext über
  Betriebsgrenzen, Rate-Limits, Portal-Formular `#reset/<token>`.
- DATEV-Seite (`70fbf81`, verlinkt `06e67f5`): eigene Seite `/datev`
  (nur admin/kanzlei, serverseitig gated), Modul `datev_seite.py`
  (`/api/datev/*`): Stapel für Monat/Zeitraum mit Prüfbefund und
  Zeilenvorschau, Kontenbeschriftungen und Kreditoren als CSV, EXTF-Import
  mit Abgleich (fehlt bei uns / fehlt bei DATEV / Betrag weicht ab), liest nur.
- Plan 21 Phase 2 (`28bc3ac`): `box.py` (Box-Objekt, Registry LRU 50),
  `mandanten.py` (kanzlei/mandant/kanzlei_mitglied), `_AKTIVE_BOX`-
  ContextVar, `boxschreiber` mit Box-Argument, Alt-Pfad bit-identisch
  (1725 Bestandstests unverändert grün).
- Plan 21 Phase 1 (`7908198` + `49169da` + `6cb0479`): `db.py` (zwei
  Dialekte, `?`→`%s`, `RETURNING id`, `REAL`→`DOUBLE PRECISION`),
  `migrations/0001` (19 Tabellen) und `0002` (Audit, Reset, Kanzlei,
  Mandant), Migrationsskript `werkzeug/migrate_sqlite_to_pg.py`,
  compose.yml mit Postgres-16-Dienst (127.0.0.1:55432, Passwortdatei),
  `BABU_DB_URL` bewusst auskommentiert — Umschalten ist ein zweiter
  Handgriff nach dem Migrationslauf, Reihenfolge im Server-README.
- Belegdatum (`2b281ed`, `76dd7d9`): der Zielbild-Weg schreibt ISO-Daten,
  extf/Portal/Bankabgleich lasen nur TT.MM.JJJJ — jeder seit 27.08.
  gebuchte Beleg ging OHNE Belegdatum in den DATEV-Stapel. Behoben über
  `extf._datum_teile`. Dazu: Mischsatz-Belege (19 %+7 %) werden im Stapel
  wieder gesplittet (`felder.steuertabelle` wird jetzt geschrieben).
- Race (`c9966a1`): Auswertungs-Job setzte „fertig" vor der Mail; unter
  Last fielen wechselnde Tests. Postausgang schreibt atomar.

Stand vor Welle-2-Übernahme (c9966a1): SQLite 1837 grün + 8 pg-Tests
übersprungen, Postgres 16 volle Suite 1845 grün.

**Welle 2 (03.09. früh), beide Agenten wurden gestoppt und von Hand zu Ende
gebracht:**

- Plan 21 Phase 3 (`dae28ec`): Kopf `X-Mandant: <id>`, geprüft in
  `_api_wache` gegen `kanzlei_mitglied`, `_box_wache` macht daraus die Box;
  ohne Kopf Alt-Verhalten (Golden-Diff), mit Kopf entscheidet allein die
  Mitgliedschaft (403 ohne, 409 „Belegbox wird eingerichtet"). `salon_von_
  aktiv` an allen Stellen inkl. der Team-Routen, Wächter-Test hält es.
  Verwaltung gescoped (`_reichweite`, `_kanzlei_wache`), Audit mit
  `mandant_id`, Export mit Berater-/Mandantennummer aus der Mandantenzeile.
- Plan 21 Phase 4 (`99f7add`, `2638ef9`): Modul `kanzlei_routen.py`
  (`/api/kanzlei/mandanten` Liste/Anlegen/Detail/Status, `box-verknuepfen`
  nur admin, `warteschlange` mit Zeitbudget je Box). Portal: Ansicht
  „Mandanten" (Tabelle, Pager, Detailkarte, Formular, Reiter „Was
  ansteht"), Umschalter `aktiverMandant` (Sitzungsspeicher, Chip im Kopf,
  Hinweis in der Seitenleiste, `X-Mandant` an jedem `api()`-Aufruf). In
  der Vorschau mit Betreiber-Rolle durchgespielt.

Endstand `20fa9a5` (03.09. früh): volle Suite **1900 grün gegen SQLite und
1900 grün gegen Postgres 16**. Unterwegs durch Postgres aufgedeckt, was
SQLite verdeckte: `mandant.besitzer_un` als echter Fremdschlüssel (Route
legte den Mandanten vor dem Konto an), `executemany` im Verbindungs-
Wrapper, zwei Tests, die `sqlite_master` bzw. die Datei direkt lasen.

Bewusst offen: Plan 21 Phase 5 (Lasttest 50 Boxen, Backup-Cron auf dem
Host, Rate-Limits auf den neuen Routen sind drin, `docker compose build`
wurde auf diesem Mac nicht gefahren — kein Docker), das „Box wird
eingerichtet"-Blatt in Heute beim Acting-as auf einen Mandanten ohne Box
(die UI bietet den Umschalter nur bei aktiver Box an, per URL/Konsole
erzwungen zeigt Heute leere Karten mit 409 im Netz).

**Deployt 03.09. 01:30** (main `9f3809d`, Freigabe des Auftraggebers: „deploy",
„mit Postgres auf h200v"): Golden vorher → rsync → build → Postgres hoch →
Probelauf und Umzug (103 Zeilen) → `BABU_DB_URL` scharf → up → Golden nachher.
`/api/abgleich/*` byte-identisch; `/api/belege` weicht nur in den 195
Buchungstexten (Datumspräfix, gewollt) und vier Status `erfasst → unlesbar`
(P0-4) ab. Live geprüft: `/api/ich`, `/api/nutzer` (5 Zugänge, Alt-Verhalten
ohne Kanzlei-Zeilen), `/api/kanzlei/mandanten` und `/warteschlange`, `/datev`
und `/api/datev/uebersicht`, `/api/audit` 403 für Kanzlei, `/portal` trägt
Mandanten-Ansicht, Seitenleiste und Belege-Tabelle, Export-Vorschau 200,
Container-Log ohne Fehler. Postgres nachweislich in Benutzung: Audit-Zeile des
Export-Aufrufs liegt dort, `schema_version` 0001+0002. Unterwegs gefixt:
das Umzugsskript kannte die Passwortdatei nicht (`9f3809d`).

**Welle 4, 03.09. früh** (nach dem Postgres-Deploy): die Reste des Auftrags plus
die Steuerberater-Sicht.

- Portal-Befunde P2-17 (Salon-Check unter Auswertung), P2-18 (ein Menüpunkt
  „Dein Team" mit zwei Unterreitern, Datenmodelle unverändert), P3-23 (62
  Felder mit Beschriftung), P3-24 (nur tote Breakpoint-Regeln entfernt, drei
  Zusammenlegungen bewusst gelassen — Begründung im Commit), P3-25 (Fußzeile
  Impressum/Datenschutz mit Platzhalter „Text folgt", auch ohne Anmeldung).
- Plan 21 Phase 5: Lasttest der Box-Registry (50 Boxen, LRU, TTL, 8 Threads;
  `box_von` ~0,4 ms warm wie kalt, weil `mandant_holen` je Aufruf gegen die
  DB geht), Rate-Limits auf `/api/datev/lesen` und `box-verknuepfen`
  nachgezogen, P3-26 als Test festgeschrieben, Backup-Cron auf dem Host um
  `pg_dump` ergänzt (`~/babu-sichern.sh`, 14 Stände).
- Kanzlei-Cockpit: `GET /api/kanzlei/mandanten/{id}/monate` und
  `GET /api/kanzlei/uebersicht` (Matrix, Zeitbudget je Box); im Portal der
  Reiter „Überblick" und „Die letzten Monate" in der Detailkarte. Dabei
  gefunden und behoben: die DATEV-Seite las beim Acting-as die eigene Box der
  Kanzlei (`_verwalter_box_wache`), `_kleinunternehmerin` nahm das Umsatz-
  profil der Kanzlei; `?mandant=` zählt jetzt wie der Kopf (Downloads).

Suite: 1939 grün gegen SQLite und Postgres 16 (vor dem Cockpit-Portalteil,
der nur portal.html ändert).

**Deployt 03.09. 02:15** (main `1a10e49`): Golden vorher/nachher `~/golden/{vorher4,
nachher4}-*` byte-identisch für `/api/belege` und beide `/api/abgleich`; live geprüft
`/api/ich`, `/api/kanzlei/uebersicht`, `/warteschlange`, `/datev`, Portal trägt
Überblick, Fußzeile und Team-Unterreiter; Container-Log ohne Fehler. Sicherungen
`~/backups/babu-docker-vor-deploy-20260903-0213.tgz` und `~/backups/babu/pg-vor-deploy-20260903-0213.dump`.

