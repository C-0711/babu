#!/usr/bin/env bash
# Box-Anleger: legt für jeden Mandanten im Zustand „box_ausstehend" die
# Belegbox an — dasselbe, was das Runbook (docs/betrieb-golive.md, §1) bis
# 15.09.2026 dem Betreiber von Hand vorschrieb.
#
# Läuft auf dem HOST (nicht im Container) im Cron jede Minute:
#   * * * * *  ~/babu-docker/docker/box-anleger.sh >> ~/logs/box-anleger.log 2>&1
#
# Warum auf dem Host: der Tresor ist im babu-web-Container bewusst nur lesbar
# gemountet, und das Gateway insp-app wird nicht ferngesteuert. Ein leeres
# Repo im Workspace ist alles, was das Gateway braucht — genau das legt
# dieses Skript an, mit den Rechten des Betreibers, und meldet danach die Box
# über `betrieb_anlegen.py --nur-box` im Container, das den Mandanten prüft
# und auf `aktiv` setzt. Jeder Schritt steht im Log; nichts wird gelöscht.
#
#   box-anleger.sh          # anlegen, was ansteht
#   box-anleger.sh --probe  # nur zeigen, was es täte
set -euo pipefail

WORKSPACE="${BABU_WORKSPACE:-$HOME/gitchain/tresor/inspektor/ws-christoph0711.io}"
BOX_PRAEFIX="${BABU_BOX_PRAEFIX:-inspektor/ws-christoph0711.io}"
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
  repo="$WORKSPACE/$kurz.git"
  ref="$BOX_PRAEFIX/$kurz"
  if [ "$PROBE" = 1 ]; then
    echo "$(stempel) PROBE Mandant $id „$name“ ($besitzer) → $repo"
    continue
  fi
  if [ ! -d "$repo" ]; then
    if git init --bare --initial-branch=main -q "$repo"; then
      echo "$(stempel) Box angelegt: $repo (Mandant $id „$name“)"
    else
      echo "$(stempel) FEHLER: git init für $repo schlug fehl (Mandant $id)"
      continue
    fi
  fi
  # Der Container prüft, ob die Box am erwarteten Pfad liegt, verknüpft sie
  # und setzt den Mandanten auf aktiv. Rückgabe 0 = alles da, 1 = verknüpft, aber eine Prüfung mahnt (meist
  # fehlende DATEV-Nummern — die trägt die Kanzlei nach), 3 = Box nicht am
  # erwarteten Pfad. Entscheidend ist der Stand des Mandanten danach.
  docker exec "$CONTAINER" python werkzeuge/betrieb_anlegen.py --nur-box \
       --email "$besitzer" --box-ref "$ref" >/dev/null 2>&1 || true
  stand=$(docker exec "$PG" psql -U babu -d babu -tA -c \
    "SELECT status || ' ' || COALESCE(box_ref,'') FROM mandant WHERE id=$id")
  case "$stand" in
    "aktiv $ref") echo "$(stempel) Box verknüpft: Mandant $id „$name“ → $ref" ;;
    *) echo "$(stempel) FEHLER: Mandant $id ($besitzer) steht nach --nur-box auf „$stand“ — nächster Versuch in einer Minute" ;;
  esac
done <<< "$offen"
