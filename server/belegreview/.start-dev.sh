#!/bin/sh
# Nur zum Ansehen der Oberfläche. Eigene Datenbank in einem Wegwerf-Ordner,
# damit weder die echte Belegbox noch portal.db angefasst werden.
#
#   PYTHON=/pfad/zum/venv/bin/python ./.start-dev.sh
#
# Nicht für den Betrieb — dort läuft babu_web.py direkt unter pm2.
set -e
cd "$(dirname "$0")"
D="${TMPDIR:-/tmp}/babu-dev"
mkdir -p "$D"
if [ ! -d "$D/babu.git" ]; then
  git init -q -b main "$D/arbeit"
  git -C "$D/arbeit" config user.name entwicklung
  git -C "$D/arbeit" config user.email dev@local
  echo box > "$D/arbeit/README.md"
  git -C "$D/arbeit" add -A
  git -C "$D/arbeit" commit -q -m start
  git clone -q --bare "$D/arbeit" "$D/babu.git"
fi
export BABU_STORE="$D/babu.git" BABU_PORTAL_DB="$D/portal.db" \
       BABU_SESSION_GEHEIMNIS="$D/.geheimnis" BABU_INDEX_TTL=0
exec "${PYTHON:-python3}" -c "
import uvicorn, babu_web
uvicorn.run(babu_web.app, host='127.0.0.1', port=${PORT:-8791}, log_level='warning')"
