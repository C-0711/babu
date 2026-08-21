# BelegReview — Serverseite (H200V)

Deployment-Kopie der Bausteine auf der H200V (`~/belegreview/`, `~/babu-web/`),
dort via pm2 (bewusst ohne `pm2 save`, siehe Spec-Nachtrag):

| pm2-Name | Datei | Zweck |
|---|---|---|
| `belegreview` | `review_watcher.py` | beobachtet babu.git, PaddleOCR (PP-OCRv5 german, CPU), Feld-Extraktion + steuerliche Einschätzung, `review:`-Commit via Gateway |
| `babu-web` | `babu_web.py` | Upload-Seite, **Salon-Portal** (`/portal` + `/api/*`, Session-Cookie) und `GET /review/<stamm>` / `POST /chat` (whoami-Auth, liest read-only aus dem Bare-Store) |
| `babu-tunnel` | — | Cloudflare-Tunnel `babu-0711` → babu.0711.io (`~/.cloudflared/babu-0711.yml`) |

Zusätzlich liegt dort `doc_classify.py` (Kopie aus `~/OCR`, standalone).
Venvs: `~/paddle-ocr-env` (PaddleOCR 3.7, CUDA-fähig — läuft auf CPU, weil
beide H200 dauerhaft von vLLM belegt sind) bzw. `~/belegreview/.venv`
(FastAPI/uvicorn/requests).

Neustart nach einem H200V-Reboot (bis `pm2 save` nachgeholt ist):

```bash
pm2 start ~/gitchain-eingang/babu_eingang.py --name babu-eingang --interpreter ~/gitchain-eingang/.venv/bin/python
pm2 start ~/belegreview/review_watcher.py --name belegreview --interpreter ~/paddle-ocr-env/bin/python
BABU_ERLAUBT="christoph0711.io,nina0711.io" BABU_ROLLEN="christoph0711.io:kanzlei" \
  pm2 start ~/belegreview/.venv/bin/python --name babu-web -- ~/belegreview/babu_web.py
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
