#!/usr/bin/env bash
# Box-Anleger: legt für jeden Mandanten im Zustand „box_ausstehend" die
# Belegbox an — dasselbe, was das Runbook (docs/betrieb-golive.md, §1) bis
# 15.09.2026 dem Betreiber von Hand vorschrieb.
#
# Läuft auf dem HOST (nicht im Container) im Cron jede Minute:
#   * * * * *  ~/babu-docker/docker/box-anleger.sh >> ~/logs/box-anleger.log 2>&1
#
# Seit dem GitChain-Standard (27.09.2026): KEIN `git init --bare` mehr im
# Speicher von GitChain. Die Box entsteht per Push-to-create beim Dienst —
# als Dienstkonto `svc-babu` in `babu/<kurzname>/belege`. Das erledigt
# `betrieb_anlegen.py --nur-box --box-anlegen` IM Container: nur dort liegt
# das Token (.pat_babu, read-only gemountet), dieses Skript fasst es nie an.
# Der Container legt die Box an, prüft sie per `git ls-remote`, verknüpft
# sie und setzt den Mandanten auf aktiv. Jeder Schritt steht im Log; nichts
# wird gelöscht. Scheitert das Anlegen (Dienst weg, Token falsch), bleibt der
# Mandant auf box_ausstehend und der nächste Lauf versucht es wieder.
#
#   box-anleger.sh          # anlegen, was ansteht
#   box-anleger.sh --probe  # nur zeigen, was es täte
set -euo pipefail

# babu/<kurzname>/belege — Typ und Kennung nach dem Standard.
BOX_PRAEFIX="${BABU_BOX_PRAEFIX:-babu}"
BOX_KENNUNG="${BABU_BOX_KENNUNG:-belege}"
CONTAINER="${BABU_CONTAINER:-babu-web}"
PG="${BABU_PG:-babu-postgres}"
PROBE=0
[ "${1:-}" = "--probe" ] && PROBE=1

stempel() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# Nie zwei gleichzeitig — der Cron kann schneller sein als ein Lauf.
exec 9>"${TMPDIR:-/tmp}/box-anleger.lock"
if ! flock -n 9; then exit 0; fi

# Kurzname aus dem Betriebsnamen: klein, ASCII, Bindestriche, plus die
# Mandanten-Nummer, damit zwei „Salon Schmidt" nie dieselbe Box bekommen.
kurzname() {
  local name="$1" id="$2"
  local k
  k=$(printf '%s' "$name" \
      | sed 's/ä/ae/g; s/ö/oe/g; s/ü/ue/g; s/Ä/ae/g; s/Ö/oe/g; s/Ü/ue/g; s/ß/ss/g' \
      | tr '[:upper:]' '[:lower:]' \
      | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
      | cut -c1-40 | sed -E 's/-+$//')
  [ -z "$k" ] && k="betrieb"
  printf '%s-%s' "$k" "$id"
}

# Was ansteht: Mandanten ohne Box. Tab-getrennt, damit Namen mit Leerzeichen
# und Kommas heil ankommen.
offen=$(docker exec "$PG" psql -U babu -d babu -tA -F $'\t' -c \
  "SELECT id, name, besitzer_un FROM mandant WHERE status='box_ausstehend' AND COALESCE(box_ref,'')='' ORDER BY id")
[ -z "$offen" ] && exit 0

while IFS=$'\t' read -r id name besitzer; do
  [ -z "$id" ] && continue
  kurz=$(kurzname "$name" "$id")
  ref="$BOX_PRAEFIX/$kurz/$BOX_KENNUNG"
  if [ "$PROBE" = 1 ]; then
    echo "$(stempel) PROBE Mandant $id „$name“ ($besitzer) → $ref (Push-to-create)"
    continue
  fi
  # Rückgabe 0 = alles da, 1 = verknüpft, aber eine Prüfung mahnt (meist
  # fehlende DATEV-Nummern — die trägt die Kanzlei nach), 3 = Box beim Dienst
  # nicht erreichbar. Entscheidend ist der Stand des Mandanten danach; der
  # Grund eines Fehlschlags steht auf stderr und landet hier im Log (ohne
  # Token — der wird nirgends ausgegeben).
  docker exec "$CONTAINER" python werkzeuge/betrieb_anlegen.py --nur-box --box-anlegen \
       --email "$besitzer" --box-ref "$ref" >/dev/null 2>"${TMPDIR:-/tmp}/box-anleger.err" || true
  sed "s/^/$(stempel) container: /" "${TMPDIR:-/tmp}/box-anleger.err" 2>/dev/null || true
  stand=$(docker exec "$PG" psql -U babu -d babu -tA -c \
    "SELECT status || ' ' || COALESCE(box_ref,'') FROM mandant WHERE id=$id")
  case "$stand" in
    "aktiv $ref") echo "$(stempel) Box verknüpft: Mandant $id „$name“ → $ref" ;;
    *) echo "$(stempel) FEHLER: Mandant $id ($besitzer) steht nach --nur-box auf „$stand“ — nächster Versuch in einer Minute" ;;
  esac
done <<< "$offen"
