# Die Dev-Lane und die Domains (Stand 2026-09-16)

## Domains

| Hostname | Weg | Ziel |
|---|---|---|
| `mybabu.io` / `www` | Cloudflare CNAME → Tunnel `babu-0711` | babu-web `:7844` (produktiv) |
| `dev.mybabu.io` | dito | babu-web-dev `:7847` (Dev-Lane) |
| `mybabu.de` / `www` | Cloudflare Page Rule: 301 → `https://mybabu.io/$1` | (kommt nie am Tunnel an) |
| `babu.0711.io` | unverändert | wie bisher, bleibt die interne Adresse |

Tunnel ist **lokal verwaltet**: Regeln stehen in `~/.cloudflared/babu-0711.yml`
(pm2 `babu-tunnel`), NICHT in der Cloudflare-Remote-Ingress-Tabelle. Eine neue
Subdomain = Zeile im yml + `pm2 restart babu-tunnel`.

Voraussetzung: Die Zonen `mybabu.io`/`mybabu.de` liegen in Cloudflare und die
Nameserver beim Registrar zeigen auf `matias.ns.cloudflare.com` /
`walk.ns.cloudflare.com` ( sonst bleibt die Zone `pending` und die Edge
antwortet nicht).

## Dev-Lane (Vorbild: ib-dev / Camp45)

* **Repo**: `gitlab.mediacockpit.dev/0711/babu` (privat). Mac-Repo `~/babu`
  hat das Additional-Remote `gitlab` — jeder Push geht an beide:
  `git push && git push gitlab main`.
* **Clone auf der H200V**: `~/babu-src` (nur lesender Deploy, Credential-Store
  `~/.git-credentials-c-0711`).
* **Container**: `babu-web-dev` aus `server/docker/compose-dev.yml`,
  Port `BABU_PORT=7847`, eigene SQLite (kein Postgres), eigene Belegbox:
  Bare-Store `~/babu-dev/dev-store/ws-dev/babu.git` (file-Remote, KEIN
  Gateway, nie `~/inspektor-store`), Klon `~/babu-dev/babu-web/box`.
  `BABU_SIGNUP=1` — Dev-Konten dürfen selbst angelegt werden.
* **Auto-Deploy**: `babu-dev-poll.timer` (30 s) → `~/babu-dev/poll-dev.sh`
  (fetch, reset --hard, compose build, up -d; `flock` gegen Überlappung;
  Log `~/babu-dev/deploy.log`).
* **Live bleibt rsync**: `rsync server/ + werkzeuge/ → ~/babu-docker` →
  `compose build && up -d` (unverändertes Ritual, siehe CLAUDE.md). Die
  Dev-Lane ist rein additiv und fasst Produktiv-Volumes nie an.

### Rückweg (alles drin, nichts kaputt)

    systemctl --user disable --now babu-dev-poll.timer
    docker rm -f babu-web-dev && docker rmi babu-web-dev
    rm -rf ~/babu-src ~/babu-dev
    # Tunnel: die drei mybabu-Zeilen aus ~/.cloudflared/babu-0711.yml streichen,
    # pm2 restart babu-tunnel  (Backup: babu-0711.yml.bak-vor-mybabu-20260916)
