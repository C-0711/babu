#!/usr/bin/env bash
# Verfügbarkeits-Check von AUSSEN (seit 03.10.2026): der Mac fragt alle 5 min
# https://mybabu.io/healthz — über das Internet und Cloudflare, also genau den
# Weg der Salons. `wache.sh` auf der H200V startet einen kranken Container neu,
# sieht aber nicht, wenn Tunnel, DNS oder der ganze Rechner weg sind. Das hier
# schon.
#
# Meldet sich per macOS-Mitteilung:
#   * ausgefallen   nach ZWEI Fehlschlägen in Folge (ein Wackler ist kein Ausfall)
#   * eingeschränkt einmal, wenn `stand` = degraded (z. B. Gemma weg)
#   * wieder da     sobald es nach einer Meldung wieder `stand: ok` heißt
# Zustand in ~/.babu/verfuegbarkeit.zustand, Verlauf in
# ~/Library/Logs/babu-verfuegbarkeit.log (nur Wechsel und Fehlschläge).
#
# Einrichten (einmalig):
#   mkdir -p ~/.babu && cp server/docker/verfuegbarkeit.sh ~/.babu/
#   cp server/docker/io.0711.babu-verfuegbarkeit.plist ~/Library/LaunchAgents/
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.0711.babu-verfuegbarkeit.plist
# Einmal sofort: launchctl kickstart gui/$(id -u)/io.0711.babu-verfuegbarkeit
# Abschalten:    launchctl bootout gui/$(id -u)/io.0711.babu-verfuegbarkeit
set -u

ADRESSE="${BABU_HEALTHZ:-https://mybabu.io/healthz}"
ORDNER="$HOME/.babu"
ZUSTAND="$ORDNER/verfuegbarkeit.zustand"
LOG="$HOME/Library/Logs/babu-verfuegbarkeit.log"
mkdir -p "$ORDNER" "$(dirname "$LOG")"

stempel() { date +"%Y-%m-%d %H:%M:%S"; }
melden() {
  osascript -e "display notification \"$2\" with title \"babu: $1\" sound name \"Basso\"" \
    >/dev/null 2>&1 || true
  echo "$(stempel) MELDUNG $1 — $2" >> "$LOG"
}

# Zustand: <letzter Stand> <Fehlschläge in Folge> <gemeldet 0/1>
ALT=ok; FEHLER=0; GEMELDET=0
[ -f "$ZUSTAND" ] && read -r ALT FEHLER GEMELDET < "$ZUSTAND"

ANTWORT=$(curl -s -m 20 -w '\n%{http_code}' "$ADRESSE" 2>/dev/null)
CODE=$(printf '%s' "$ANTWORT" | tail -1)
RUMPF=$(printf '%s' "$ANTWORT" | sed '$d')
STAND=$(printf '%s' "$RUMPF" | sed -n 's/.*"stand" *: *"\([a-z]*\)".*/\1/p')

if [ "$CODE" = "200" ] && [ "$STAND" = "ok" ]; then
  if [ "$GEMELDET" = "1" ]; then
    melden "wieder da" "mybabu.io antwortet wieder normal."
  fi
  echo "ok 0 0" > "$ZUSTAND"
  exit 0
fi

if [ "$CODE" = "200" ] && [ "$STAND" = "degraded" ]; then
  if [ "$ALT" != "degraded" ]; then
    melden "eingeschränkt" "mybabu.io läuft, aber ein Teil fehlt (healthz: degraded). Belege werden später gelesen."
  fi
  echo "degraded 0 1" > "$ZUSTAND"
  exit 0
fi

FEHLER=$((FEHLER + 1))
echo "$(stempel) fehlschlag $FEHLER: http=$CODE stand=${STAND:-—}" >> "$LOG"
if [ "$FEHLER" -ge 2 ] && [ "$GEMELDET" != "1" ]; then
  melden "ausgefallen" "mybabu.io antwortet nicht (http $CODE). wache.sh, Tunnel und docker ps prüfen."
  GEMELDET=1
fi
echo "weg $FEHLER $GEMELDET" > "$ZUSTAND"
