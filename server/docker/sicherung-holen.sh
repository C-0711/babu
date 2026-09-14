#!/usr/bin/env bash
# Die Kopie außer Haus: der Mac holt nachts ~/backups/babu/ von der H200V.
#
# Läuft auf dem MAC (nicht auf dem Server) per launchd, siehe
# server/docker/io.0711.babu-sicherung.plist — täglich 04:30; ist der Mac da
# gerade zu, holt launchd es beim nächsten Aufwachen nach. Braucht die
# OpenVPN-Verbindung zur H200V (ssh h200v).
#
# Danach die Frage, die zählt: ist die jüngste Sicherung frisch? Älter als
# 48 h heißt: auf dem Server läuft etwas nicht — und der Mac sagt es mit
# einer Mitteilung, statt still weiter Altes zu kopieren.
#
# Time Machine sichert ~/Backups mit — das ist die dritte Kopie, gratis.
set -u
QUELLE="${BABU_SICHERUNG_QUELLE:-h200v:backups/babu/}"
ZIEL="${BABU_SICHERUNG_ZIEL:-$HOME/Backups/babu}"
LOG="$ZIEL/holen.log"
mkdir -p "$ZIEL"
sage() { echo "$(date +%Y-%m-%dT%H:%M:%S) $*" >> "$LOG"; }
melden() {
  # Eine macOS-Mitteilung — läuft nur, wenn jemand angemeldet ist; sonst
  # bleibt es beim Log.
  osascript -e "display notification \"$1\" with title \"babu-Sicherung\"" >/dev/null 2>&1 || true
}

# Nur zusammenhängende Sicherungen holen, keine Spiegel-Repos: die Bundles
# enthalten dieselbe Historie als eine Datei. `--delete` NICHT: was der
# Server aufräumt, darf hier ruhig liegen bleiben (Time Machine ohnehin).
if rsync -az --timeout=120 \
     --include='*.dump' --include='*.bundle' --include='*.tgz' --include='*.age' \
     --include='*.db' --include='stand.txt' --include='sichern.log' --exclude='*' \
     "$QUELLE" "$ZIEL/" >>"$LOG" 2>&1; then
  sage "geholt"
else
  sage "FEHLER: rsync von $QUELLE gescheitert (VPN? Server?)"
  melden "Kopie von der H200V nicht geholt — VPN oder Server prüfen."
  exit 1
fi

# Frische prüfen: der Server schreibt stand.txt am Ende jedes Laufs.
if [ -f "$ZIEL/stand.txt" ]; then
  stand=$(cut -d' ' -f1 "$ZIEL/stand.txt")
  fehler=$(sed -nE 's/.*fehler=([0-9]+).*/\1/p' "$ZIEL/stand.txt")
  alter=$(( ( $(date +%s) - $(date -j -f "%Y-%m-%dT%H:%M:%S" "$stand" +%s 2>/dev/null || echo 0) ) / 3600 ))
  if [ "$alter" -gt 48 ]; then
    sage "WARNUNG: juengste Sicherung ist $alter h alt"
    melden "Die letzte Sicherung auf der H200V ist $alter Stunden alt."
  elif [ "${fehler:-0}" != "0" ]; then
    sage "WARNUNG: Sicherung vom $stand meldet $fehler Fehler"
    melden "Die Sicherung vom $stand meldet $fehler Fehler — sichern.log ansehen."
  else
    sage "ok: Stand $stand, $(ls "$ZIEL"/pg-*.dump 2>/dev/null | wc -l | tr -d ' ') Dumps, $(du -sh "$ZIEL" | cut -f1)"
  fi
else
  sage "WARNUNG: kein stand.txt — laeuft sichern.sh auf dem Server?"
  melden "Auf der H200V fehlt stand.txt — läuft die Sicherung dort?"
fi
