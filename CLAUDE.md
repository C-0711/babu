# babu — Projektanweisungen für Claude

Salon-Buchhaltung: iOS-App „Beleg" (SwiftUI) + FastAPI-Server auf der H200V
(babu.0711.io). Nutzerin: Nina (Salon-Inhaberin, Mandant „SupremeStudio").
Seit 03.09.2026 dazu die Kanzlei-Seite: Steuerberater verwalten Mandanten,
arbeiten in deren Belegbox und übergeben DATEV-Stapel. Sprache in UI,
Commits und Antworten: **Deutsch**. Einstieg und Details: `HANDOVER.md`,
DATEV-Übergabe: `docs/uebergabe-datev-2026-09-02/README.md`.

## Verbindlich: das Zielbild (seit 26.08.2026)

**EINE Lesung, keine zweite.** Apple Vision liest auf dem iPhone
(`{text, conf, box}`), `POST /api/buchung/einschaetzung` reichert an
(Profil, ungedeckte Abbuchungen, Verträge/Personal), Gemma bucht strict JSON
mit Pflichtfeld `dokumentklasse`, **erst danach** archiviert
`POST /api/aufnahme` Foto + Ergebnis. Die Belegbox ist reines Archiv; das
Bild fasst kein System mehr an.

**Nicht wieder einbauen** (gelöscht 27.08., main `d5f0d5f`):
review_watcher, belegdeutung, leseprotokoll, doc_classify, die Routen
`neu-lesen`/`buchungsfragen`, der App-FeldParser im Buchungsweg, das
Kontierung-Enum. **Paddle-OCR (:7833) ruft babu gar nicht mehr** — der
Dienst gehört ctax; Scan-Blätter der Salonprüfung liest Gemma (multimodal).

**UI-Sprachregel:** kein Technik-Vokabular, keine Systemnamen, kein
„Erst-/Zweitlesung". Vertrauen = ein grüner Haken. Kein Hex-Hash.
`tests/test_sprachregel.py` prüft `portal.html` inklusive `//`-Kommentaren
(verbotene Wörter: Server, Token, Hash, Commit, Queue, Modell, KI, OCR,
Lesung) — JS-Kommentare als `/* */`. Im Portal nie Namen in
`onclick`-Attribute, nur Nummern (`MD_NAMEN`/`mdVon`).

## Verbindlich: Umsatz und Kasse (seit 03.09.2026)

- **Kasse GEGEN Konto abgleichen, nicht entweder-oder.** Die Karte im
  Kassenbuch (`ecZahlungen`) und die Auszahlungen der Kartenanbieter auf
  dem Kontoauszug (Salonkee, SumUp, Zettle … `ERLOES_QUELLEN` in
  `monatsabschluss.py`) sind dasselbe Geld. Was das Konto MEHR zeigt als
  das Kassenbuch, zählt als Umsatz mit (`aus_bank`); zeigt es weniger, ist
  das Gebühr/Zeitversatz und wird nur ausgewiesen, nie abgezogen. Ohne
  Kontoauszug kein Abgleich. Erstattungen und Rückzahlungen sind kein
  Umsatz. Alle Erlös-Aufrufer gehen über `_erloese_fuer()` in `babu_web.py`.
- Nina führt (Stand 03.09.) kein Kassenbuch; ihr Umsatz kommt aus den
  Salonkee-Auszahlungen (Mai 17.745 €, Juni 12.292 €, Juli 3.448 €).
  Kontoauszüge liegen als `auszuege/<monat>/*.umsaetze.json` in der Box.

## Rollen, Mandanten, DATEV

- Rollen `admin`/`kanzlei`/`salon`/`mitarbeit`; PAT-Konten über
  `BABU_ROLLEN` in `docker/compose.yml`. Als Mandant arbeiten geht über den
  Kopf `X-Mandant: <id>` oder `?mandant=<id>` (für Downloads) — nur für
  Mitglieder in `kanzlei_mitglied`, **Admin ist nicht automatisch Mitglied**.
- Produktivkonten: `christoph0711.io` (PAT, admin + Sachbearbeiter Kanzlei
  Afflek), `afflek@0711.io` (Kanzlei Afflek, id 7), Mandanten 1 „Jenny from
  the Block" (Box ausstehend) und 2 „SupremeStudio" = Nina (Berater 16149,
  Mandant 19364). Startpasswörter werden nie ausgegeben — der Weg ist
  „Zugänge verwalten → Neues Startpasswort".
- DATEV-Seite `/datev` (`datev_seite.py`, `extf.py`): Format nach dem
  Kanzlei-Referenzstapel (Version 12, 124 Spalten, SKR leer; babu schreibt
  cp1252, `?zeichensatz=utf8` schaltbar), Prüfbefund vor jedem Export,
  Siegel `POST /api/datev/uebergeben` nur für die Kanzlei. **Ein echter
  DATEV-Import hat noch nie stattgefunden** — Abnahme ist der Import bei
  Kanzlei Afflek mit Protokoll; #REW-Meldungen danach in den Befund
  übersetzen.

## Betrieb H200V — Finger weg / Ritual

- **babu-web läuft seit 27.08.2026 als Docker-Container** (host network,
  `restart: unless-stopped`; Quelle `server/docker/`, Build-Kopie auf der
  H200V unter `~/babu-docker/`). **Seit 03.09.2026 Postgres 16** im
  Container `babu-postgres` (127.0.0.1:55432, Passwortdatei
  `~/babu-web/.pg_passwort`, täglicher `pg_dump` in `~/babu-sichern.sh`);
  `portal.db` bleibt liegen als Rückweg (`BABU_DB_URL` auskommentieren).
  In pm2 bleiben nur `babu-eingang` und `babu-tunnel`; der pm2-Eintrag
  `babu-web` ist gestoppt und NUR Rückweg. **Nie anfassen:** `insp-app`
  (Belegbox-Gateway :7808) und `belege-review` (ANDERES Projekt).
- Deploy: **immer `rsync server/ h200v:~/babu-docker/` komplett, nie eine
  Einzeldatei** (ein gemischter Build fiel nur auf, weil ein neues
  API-Feld live fehlte) → `cd ~/babu-docker/docker && docker compose build
  && docker compose up -d` → geänderte Routen live durchrufen und ein neues
  Feld direkt abfragen. Golden-Diff (`/api/belege` + `/api/abgleich/<monat>`
  als `python3 -m json.tool --sort-keys`, Dateien unter `~/golden/`) bleibt
  das Ritual bei Änderungen am Buchungsweg; der Auftraggeber verzichtet
  ausdrücklich darauf, wenn er es sagt.
- **Seit 03.09.2026 ist die H200V Worker im Rancher-Cluster `dev-01`.** Gemma
  (:11435) und Embeddings (:11436) sind k3s-Pods mit hostPort; babu-web,
  babu-postgres, insp-app, babu-eingang, babu-tunnel und `~/inspektor-store`
  laufen AUSSERHALB des Clusters und stehen in keinem Manifest
  (`gitlab.mediacockpit.dev/0711/h200-migration-manifests`). Nach jedem
  Cluster-Eingriff aus dem Container `:11435/v1/models`, `:11436` und den
  Git-Endpunkt auf `:7808` prüfen.
- Migrationen laufen beim ersten `_db()`-Open, nicht beim Containerstart:
  `schema_version` erst nach einem Request prüfen.
- H200V nur über OpenVPN (`ssh h200v`). Kein sqlite3-CLI auf dem Server;
  Postgres per `docker exec babu-postgres psql`.
- Vor schreibenden Rauchtests erst den Ist-Wert lesen — oder Testkonto.

## Sicherheit

- Nie Passwörter oder Token-Werte entgegennehmen, eintippen oder ausgeben
  (nur Länge/Status). Keychain-only für den Upload-PAT.
- Neue Routen immer über `_box_wache`/`box_mitglied`/`_verwalter_box_wache`
  absichern, nie über `ERLAUBT`.

## Datenbank

- **Jede Schemaänderung ZWEIMAL:** inline in `_sqlite_schema()`/Modul-
  `schema()` UND als `migrations/000N_*.sql` (`-- nur: postgres`-Marker
  für dialektspezifische Zeilen).
- Postgres prüft Fremdschlüssel wirklich. **Kein FK auf `nutzer(email)`
  für Kanzlei-/Betreiber-Identitäten** — PAT-Konten haben keine
  nutzer-Zeile (erster Mandant im Betrieb war ein 500). Bei neuen Tabellen
  mit `un`-Spalte einen PAT-Fall testen.

## Bauen & Testen

- Server-Suite: **immer mit explizitem `cd server/belegreview &&`**,
  `/tmp/babu-venv/bin/python -m pytest tests/ -q -p no:cacheprovider`,
  Timeout 600 s (~4 min, 2164 grün). Python 3.12 mit fastapi, httpx,
  pytest, requests, python-multipart, pypdfium2, pillow-heif, pillow,
  psycopg. Postgres-Lauf über eine Wegwerfinstanz (`initdb --locale=C
  --encoding=UTF8`, `BABU_TEST_DB_URL`).
- **Nie generisches `pkill -f pytest`** — parallel laufende Agenten teilen
  den Rechner. Eine Suite je Worktree.
- **Nie `git stash`** — der Stash-Stapel ist mit allen Worktrees geteilt.
- iOS-Simulator: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg
  -destination 'platform=iOS Simulator,name=iPhone 16e' -derivedDataPath /tmp/bsim build`
- Ninas iPhone (UDID `00008130-001411E00146001C`):
  `… 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG CODE_SIGN_STYLE=Automatic
  -allowProvisioningUpdates -derivedDataPath /tmp/bbuild` + `xcrun devicectl
  device install app` (WLAN wackelig: zweiter Versuch hilft, Kabel sofort).
- App-Logik-Harnesse: `ios/Tests/run.sh` — Fixtures pflegen, nie löschen.
- Lokale Vorschau des Portals: Python-Änderungen brauchen einen Neustart
  des Vorschau-Servers; Mandantenboxen lokal nur mit `BABU_STORE_WURZEL=/`
  und `box_ref` ohne führenden Slash.

## Git

- Arbeiten im Worktree, mergen per ff: im Worktree `git fetch && git rebase
  origin/main`, dann im Haupt-Checkout `git reset --hard origin/main &&
  git merge --ff-only <branch> && git push`. **Nie force-pushen** — der
  autonome Fixlauf (Meldeschleife, launchd 30 min) pusht parallel.
- Subagenten: eigener Worktree, nur committen; Übernahme per cherry-pick,
  danach `git worktree remove` + Branch löschen.
- iOS-Merge-Falle: im Haupt-Checkout gebaut ≠ im Worktree committet — vor
  dem Merge diffen.

## Bekannte Fallen

- Alte `zustand.json` müssen laden: neue Beleg-/Zustand-Felder IMMER
  optional (`ocrText`-Altlast: Decodable nutzt Defaults nicht).
- Simulator-Keychain ≠ iPhone-Keychain; App-Neuinstallation verliert die
  Keychain → Nina muss sich neu verbinden.
- Testdaten (echte Salon-/Bankdaten) liegen in `~/Downloads` und bleiben
  lokal — nie committen, nie hochladen.
- pypdfium2 ist nicht threadsicher: jeder PDF-Zugriff unter `PDFIUM_LOCK`.
- Golden-Vertrag `tests/test_api.py` (Weingärtle `buchungssatz`/
  `buchungstext` byte-gleich) — wer Buchungstexte anfasst, ändert die
  Fixture bewusst mit.

Die `~/CLAUDE.md` im Home beschreibt die Mac-OCR-Werkzeugkette
(`~/bin/vision-ocr/`) — anderes Projekt, dort gelten eigene verbindliche
Vorgaben.
