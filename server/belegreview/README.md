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
