#!/usr/bin/env bash
# Die Wache: startet babu-web neu, wenn der Healthcheck ihn für tot erklärt.
#
# Docker selbst tut das nicht — `restart: unless-stopped` greift nur, wenn der
# Prozess ENDET, nicht wenn er hängt. Ein Sidecar (autoheal) bräuchte den
# Docker-Socket im Container, also Root-Rechte auf dem Host; deshalb ein
# Zweizeiler im Cron des Benutzers, alle zwei Minuten:
#
#   */2 * * * * ~/babu-docker/docker/wache.sh >> ~/logs/wache.log 2>&1
#
# Kein Watcher im Sinne von CLAUDE.md: kein Prozess, kein Zugriff auf Belege.
set -euo pipefail

CONTAINER="${1:-babu-web}"
zustand=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unbekannt")

if [ "$zustand" = "unhealthy" ]; then
  echo "$(date '+%F %T') $CONTAINER unhealthy — starte neu"
  docker restart "$CONTAINER" >/dev/null
  # Kein zweiter Neustart innerhalb der start_period: der Healthcheck braucht
  # nach dem Start bis zu 90 s, bevor er wieder urteilt.
  sleep 5
  echo "$(date '+%F %T') $CONTAINER neu gestartet"
fi
