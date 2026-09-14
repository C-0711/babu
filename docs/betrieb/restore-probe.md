# Restore-Probe — die Sicherung, die zurückkommt

Eine Sicherung, die nie zurückgespielt wurde, ist eine Vermutung. Dieses Protokoll hält
jede Probe fest: was gesichert war, was zurückkam, und ob die Zahlen stimmen. Einmal vor
dem Go-Live, danach am Monatsersten.

## Das Ritual (auf dem Mac, ~10 Minuten)

Voraussetzungen: `brew install age postgresql@16`, der private Schlüssel unter
`~/.config/babu/sicherung.key` (nur auf diesem Mac), die Kopie unter `~/Backups/babu/`
(holt `server/docker/sicherung-holen.sh` nächtlich per launchd).

```bash
export LC_ALL=C   # sonst „postmaster became multithreaded" auf macOS
PG=/opt/homebrew/opt/postgresql@16/bin; P=/tmp/babu-probe; rm -rf $P; mkdir -p $P
D=$(ls -t ~/Backups/babu/pg-*.dump | head -1)
$PG/initdb -D $P/pg --locale=C -E UTF8 -U probe >/dev/null
$PG/pg_ctl -D $P/pg -o "-p 55433 -k $P -c listen_addresses=''" -l $P/pg.log start; sleep 2
$PG/createdb -h $P -p 55433 -U probe babu_probe
$PG/pg_restore -h $P -p 55433 -U probe -d babu_probe --no-owner --no-privileges "$D"
$PG/psql -h $P -p 55433 -U probe -d babu_probe -tAc \
  "select 'nutzer',count(*) from nutzer union all select 'mandant',count(*) from mandant \
   union all select 'einstellungen',count(*) from einstellungen \
   union all select 'app_schluessel',count(*) from app_schluessel order by 1"
$PG/pg_ctl -D $P/pg stop; rm -rf $P
```

Dieselben Zahlen auf dem Server: `ssh h200v docker exec babu-postgres psql -U babu -d babu -tAc "…"`.

```bash
B=$(ls -t ~/Backups/babu/box-babu-*.bundle | head -1)
git clone -q "$B" /tmp/babu-box-probe && git -C /tmp/babu-box-probe log -1 --oneline
ssh h200v git -C '~/gitchain/tresor/inspektor/ws-christoph0711.io/babu.git' log -1 --oneline
rm -rf /tmp/babu-box-probe

G=$(ls -t ~/Backups/babu/geheimnisse-*.tar.gz.age | head -1)
age -d -i ~/.config/babu/sicherung.key "$G" | tar tzf -     # nur die Liste, nie den Inhalt
```

Bestanden heißt: `pg_restore` ohne Fehlermeldung, Zeilenzahlen gleich, Bundle-HEAD gleich
dem Server, Geheimnis-Archiv entschlüsselbar mit allen vier Dateien.

## Protokoll

### 2026-09-14 — erste Probe, bestanden

Anlass: Woche 4 des Go-Live-Plans (`docs/golive-babu-2026-09-14.md`, B7). Vorgeschichte:
das alte `~/babu-sichern.sh` war beim Umräumen des Home am 12.09. vom Cron-Pfad getrennt
worden (nach `~/Ablage/gitchain/`); vom 13.09. bis 14.09. lief keine Sicherung, und am 12.09.
war der Box-Spiegel bereits gescheitert (`~/inspektor-store` fehlte). Seit heute läuft
`server/docker/sichern.sh` aus dem Repo, Cron `17 3 * * *`, Kopie per launchd auf den Mac.

| Stück | Sicherung | zurückgespielt | Ergebnis |
|---|---|---|---|
| Postgres | `pg-20260914.dump` (52 KB) | Wegwerf-Cluster auf dem Mac, `pg_restore` Exit 0, 0 Meldungen | 27 Tabellen, `schema_version` 5 |
| Zeilenzahlen | Server | Mac | nutzer 8 = 8 · mandant 2 = 2 · einstellungen 33 = 33 · app_schluessel 2 = 2 · kundin 4 = 4 · termin 0 = 0 |
| Belegbox | `box-babu-20260914.bundle` (307 MB, 1280 Commits) | `git clone` | HEAD `fd196e3` = Server-HEAD, 1274 Dateien |
| Geheimnisse | `geheimnisse-20260914.tar.gz.age` (650 B) | `age -d` | `.session_geheimnis`, `.pg_passwort`, `.gitlab_token`, `.pat_babu` — alle vier |
| Bilder | `bilder-20260914.tgz` (121 MB) | nicht zurückgespielt (tar, keine Fremdlogik) | — |
| Kopie außer Haus | `~/Backups/babu/` auf dem Mac | `sicherung-holen.sh`: „ok: Stand 2026-09-14T10:29:09, 14 Dumps, 435M" | frisch |

Offen: Time Machine sichert `~/Backups` mit (dritte Kopie), sobald der Mac es das nächste Mal
tut — nicht geprüft.
