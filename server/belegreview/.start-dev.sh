#!/bin/sh
# Nur zum Ansehen der Oberfläche. Eigene Datenbank in einem Wegwerf-Ordner,
# damit weder die echte Belegbox noch portal.db angefasst werden.
#
# Der Interpreter wird selbst gesucht: erst ./.venv (liegt neben diesem
# Skript und ist in .gitignore), dann PYTHON, dann python3. Vorher stand der
# Pfad in .claude/launch.json — und zwar der eines Wegwerf-Ordners aus einer
# einzelnen Sitzung. Beim nächsten Start war er weg und der Server startete
# nicht mehr. Ein bleibender Startweg darf nicht auf Wegwerfbares zeigen.
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
# Die Startseite liegt im Betrieb unter ~/babu-web/, im Arbeitsbaum aber
# neben diesem Ordner. Ohne den Hinweis endet „/" in einem Serverfehler.
export BABU_STORE="$D/babu.git" BABU_PORTAL_DB="$D/portal.db" \
       BABU_SESSION_GEHEIMNIS="$D/.geheimnis" BABU_INDEX_TTL=0 \
       BABU_SEITE="$(cd .. && pwd)/babu-web/index.html" \
       BABU_ABSCHLUSS_TMP="$D/abschluss-tmp"
if [ -z "$PYTHON" ] && [ -x "./.venv/bin/python" ]; then
  PYTHON="./.venv/bin/python"
fi
exec "${PYTHON:-python3}" -c "
import uvicorn, babu_web
uvicorn.run(babu_web.app, host='127.0.0.1', port=${PORT:-8791}, log_level='warning')"
