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
