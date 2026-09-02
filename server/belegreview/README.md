# BelegReview — Serverseite (H200V)

Läuft auf der H200V. **`babu-web` ist seit 27.08.2026 ein Docker-Container**
(Quelle `../docker/`, Build-Kopie `~/babu-docker/` auf dem Server): host
network, User 1001:1000, `restart: unless-stopped`. Volumes: `~/babu-web`
(rw — portal.db, Box-Klon, Session-Geheimnis, Logos), `~/inspektor-store`
(ro), der Push-PAT und die Gemini-Env (beide ro). Deploy = `rsync server/
h200v:~/babu-docker/` + `docker compose build && up -d` — mit Golden-Diff
davor und danach.

| Dienst | Wo | Zweck |
|---|---|---|
| `babu-web` | **Docker** | der ganze Dienst: Upload-Seite, **Salon-Portal** (`/portal` + `/api/*`, Session-Cookie), App-API (`/api/aufnahme`, `/api/buchung/einschaetzung`, `GET /review/<stamm>`, `/chat`) |
| `babu-eingang` | pm2 | GitChain-Gateway (Push in den Bare-Store) |
| `babu-tunnel` | pm2 | Cloudflare-Tunnel `babu-0711` → babu.0711.io (`~/.cloudflared/babu-0711.yml`) |
| `insp-app` | pm2 | Belegbox-Gateway :7808 — **nie anfassen**, ohne ihn kommt nichts in die Box |

Der gestoppte pm2-Eintrag `babu-web` ist der Rückweg: `docker compose down`
(in `~/babu-docker/docker`) + `pm2 start babu-web`. Das alte `~/belegreview/`
auf dem Server ist nur noch die letzte Vor-Docker-Kopie.

**Es gibt keine zweite Lesung mehr.** Seit dem Zielbild (26.08.2026) liest
Apple Vision auf dem iPhone, Gemma bucht über `/api/buchung/einschaetzung`,
und `/api/aufnahme` archiviert Foto + Ergebnis. Der frühere Watcher
(`review_watcher.py`, pm2 `belegreview`) ist gelöscht — **nicht neu starten,
nicht neu erfinden**. Der Paddle-OCR-Dienst :7833 gehört vollständig ctax;
babu ruft ihn nirgends mehr (Scan-Blätter der Salonprüfung liest Gemma).

Nach einem H200V-Reboot startet alles von selbst: der Container über Docker
(`restart: unless-stopped`, dockerd ist enabled), pm2 über seine
systemd-Unit. Falls doch einmal von Hand:

```bash
cd ~/babu-docker/docker && docker compose up -d
pm2 start ~/gitchain-eingang/babu_eingang.py --name babu-eingang --interpreter ~/gitchain-eingang/.venv/bin/python
pm2 start /usr/bin/cloudflared --name babu-tunnel -- tunnel --config ~/.cloudflared/babu-0711.yml run babu-0711
```

## Portal-Deploy (Stufe 1)

Zu `babu-web` gehören seit dem Salon-Portal vier Dateien in `~/belegreview/`:
`babu_web.py`, `portal.html`, `portal.manifest.json`, `portal.sw.js` — plus die
Upload-Seite `~/babu-web/index.html`. Deploy = Dateien kopieren,
`pm2 restart babu-web`, danach Golden-Check (siehe `tests/golden/README.md`):
`/review/<stamm>` muss byte-gleich bleiben, `/chat`-SSE die Form
`data: {"d": …}` + `data: [DONE]` behalten. Session-Geheimnis liegt in
`~/babu-web/.session_geheimnis` (wird beim ersten Start erzeugt, 0600).

## Wer in die Belegbox darf

Auf diesem Server liegt EINE Belegbox. Ein Konto allein ist deshalb noch kein
Zugang zu ihren Belegen — sonst läse jede Selbstregistrierung die Buchhaltung
des Salons mit. In die Box kommt (`box_mitglied` in `babu_web.py`):

- wer in `BABU_ERLAUBT` steht (der PAT-Weg: App-Upload, `/review`, `/ablage`),
- wer ein Konto mit gesetztem `box`-Merker hat,
- das Team dieses Kontos (`gehoert_zu`) — mit den Rechten, die die Inhaberin
  vergeben hat (`darf_belege`, `darf_kasse`),
- die Kanzlei (Rolle `kanzlei`/`admin`).

Alles andere — Konto, Einstellungen, Team, Fristen — bleibt jedem eigenen
Zugang offen; das sind seine eigenen Daten.

**Beim Deploy wichtig:** die Spalte `nutzer.box` wird beim Start angelegt und
steht für bestehende Zeilen auf 1 — vorhandene Zugänge arbeiten unverändert
weiter. Neu ist nur, dass `POST /api/signup` ein Konto **ohne** Box anlegt.
Freischalten geht über `POST /api/nutzer-aktion`
(`{"email": …, "aktion": "box_freigeben"}`, Rolle kanzlei/admin) — oder direkt:

```bash
sqlite3 ~/babu-web/portal.db "UPDATE nutzer SET box=1 WHERE email='…';"
```

Nach dem Deploy einmal prüfen, dass die echten Zugänge noch hineinkommen:
`GET /api/ich` muss `"box": true` liefern.

## Löschen

`POST /api/beleg/{stamm}/loeschen` und `POST /api/dokument-loeschen` entfernen
über `boxschreiber.loeschen()` — ein eigener Commit, der die Datei wegnimmt.
Der aktuelle Stand zeigt sie nicht mehr, die Historie behält sie. Ein Beleg
geht immer mit seinen Beiakten (`review/<stamm>.*`), ein Dokument mit seinen
Sidecars.

Nicht löschbar, und zwar bewusst:

- Belege im Status `exportiert` — sie liegen im Stapel bei der Kanzlei (409).
- Alles außerhalb von `dokumente/`: Kassenbuch, Kontoauszüge, Buchungsstapel,
  Jahresabschluss sind aufbewahrungspflichtig (400).

Löschen darf die Inhaberin und die Kanzlei, nicht die Rolle `mitarbeit` —
einreichen ist etwas anderes als wegwerfen. `GET /api/ablage` liefert je
Eintrag `loeschbar`, damit die Oberfläche gar nicht erst einen Knopf zeigt,
der beim Drücken absagt.

## Datenbank: SQLite oder Postgres (Plan 21, Phase 1)

Der Portal-Zustand läuft seit dem 02.09.2026 durch `db.py`, das zwei
Dialekte spricht. **Ohne `BABU_DB_URL` ändert sich nichts**: SQLite,
dieselbe `~/babu-web/portal.db`, dieselben Anweisungen. Ist die Variable
gesetzt, spricht dieselbe Codebasis mit Postgres (psycopg3).

Das Schema steht in `migrations/` als nummerierte SQL-Dateien; `db.py`
führt darüber eine `schema_version`-Tabelle und wendet an, was noch fehlt.
Die SQLite-Seite legt ihre Tabellen weiter inline in `babu_web._db()` an —
dort hängen die `ALTER TABLE … ADD COLUMN`-Nachrüstungen, mit denen Ninas
Datei über Monate gewachsen ist, und daran soll Phase 1 nicht schrauben.
Dass beide Wege dasselbe Schema ergeben, prüft
`tests/test_db_dialekt.py::test_migration_bildet_die_inline_tabellen_ab`.

**Umschalten — die Reihenfolge ist der Punkt:**

1. Passwortdatei anlegen, einmalig auf der H200V:
   `umask 077 && openssl rand -base64 33 | tr -d '\n' > ~/babu-web/.pg_passwort`
2. Nur die Datenbank hochfahren: `docker compose up -d postgres`.
3. Einmal umziehen, von Hand — **nicht** in einem `CMD`, das Skript räumt
   die Zieltabellen vorher leer:

   ```bash
   BABU_DB_URL=postgresql://babu@127.0.0.1:55432/babu \
   BABU_DB_PASSWORT_DATEI=~/babu-web/.pg_passwort \
   python3 werkzeug/migrate_sqlite_to_pg.py ~/babu-web/portal.db
   ```

   `--trocken` zählt vorher durch, ohne zu schreiben.
4. In `docker/compose.yml` die Zeile `BABU_DB_URL:` einkommentieren,
   `docker compose up -d`, danach das volle Golden-Ritual aus `CLAUDE.md`.

**Rückweg:** die Zeile wieder auskommentieren, `docker compose up -d`.
`portal.db` bleibt liegen und unangetastet — der Umzug liest sie nur. Nicht
löschen, solange Postgres sich nicht bewährt hat. Der Postgres-Container
darf dabei weiterlaufen, er steht nicht im Weg.

### Sicherung

Postgres und Belegbox sind getrennte Sicherungsziele; das bestehende
`~/babu-sichern.sh` (tägliches Box-Spiegeln) bleibt, wie es ist. Dazu kommt
ein Cron **auf dem Host**, kein eigener Container — für einen Zeitplan
allein lohnt kein Dienst, und der Host hat sein Cron-Ritual schon:

```cron
# täglich 03:20, 14 Tage rollierend
20 3 * * * docker exec babu-postgres pg_dump -U babu -Fc babu > ~/backups/babu-pg-$(date +\%F).dump && find ~/backups -name 'babu-pg-*.dump' -mtime +14 -delete
```

Zurückspielen:
`docker exec -i babu-postgres pg_restore -U babu -d babu --clean --if-exists < ~/backups/babu-pg-<datum>.dump`

### Neue SQL-Zeilen schreiben

`db.platzhalter()` ersetzt für Postgres **jedes** `?` im SQL-Text durch
`%s`. Das ist sicher, solange kein SQL-Text ein Fragezeichen als Zeichen
enthält — und kein `%`, das psycopg sonst selbst als Platzhalter läse. Ein
Fragezeichen gehört in einen Parameter, nicht in den Text.
`tests/test_db_dialekt.py::test_kein_sql_literal_traegt_ein_echtes_fragezeichen`
hält das fest und bricht, sobald jemand es vergisst.

Für die Postgres-Tests braucht es kein Docker: die Fixture in
`tests/conftest.py` nimmt `BABU_TEST_DB_URL`, sonst startet sie sich mit
`initdb`/`pg_ctl` eine Wegwerf-Instanz auf Port 55433 und räumt sie
hinterher weg; findet sie keins von beidem, werden die
`@pytest.mark.pg`-Tests übersprungen. **Die übrige Suite setzt nirgends
Postgres voraus** — `pytest tests/` läuft wie bisher gegen SQLite. Die
ganze Suite gegen Postgres fährt `BABU_DB_URL=… pytest tests/`; ein
Schema-Haken in `conftest.py` gibt dabei jeder Test-`portal.db` ihr eigenes
Postgres-Schema, damit die Isolation bleibt.
