#!/usr/bin/env bash
# Sichert alles, was babu ausmacht und nur einmal existiert — täglich per Cron
# auf der H200V, seit 14.09.2026 aus dem Repo (vorher ~/babu-sichern.sh, das
# beim Umräumen des Home am 12.09. vom Cron-Pfad getrennt wurde: zwei Tage
# ohne Sicherung, und niemand hat es gemerkt).
#
#   17 3 * * * ~/babu-docker/docker/sichern.sh
#
# Was gesichert wird, nach ~/backups/babu/:
#   1. die Belegboxen — als Spiegel (babu-box.git, wie bisher) UND als
#      git-Bundle je Box (eine Datei, offsite-tauglich: git clone <bundle>)
#   2. Postgres (pg_dump, custom format) — Konten, Mandanten, Einstellungen,
#      Team, Audit; dazu portal.db, solange sie als Rückweg liegt
#   3. Bilder, die bewusst nicht in Git liegen (Logos, Team-Fotos, Ausweise)
#   4. die Geheimnisse — verschlüsselt mit age für den Schlüssel des Mac
#      (privater Schlüssel liegt NUR dort). Alle vier sind neu ausstellbar;
#      die Sicherung spart nach einem Serververlust Zeit, keine Daten.
#
# Außer Haus holt der Mac (server/docker/sicherung-holen.sh, launchd). Diese
# Datei schreibt am Ende ~/backups/babu/stand.txt — daran misst der Mac, ob
# die Kopie frisch ist.
#
# `--trocken` zählt nur durch, ohne zu schreiben. 14 Stände rollierend.
set -u
TROCKEN=0; [ "${1:-}" = "--trocken" ] && TROCKEN=1

ZIEL="${BABU_SICHERUNG:-$HOME/backups/babu}"
# Seit dem GitChain-Standard (27.09.2026) liest babu aus eigenen Lesespiegeln
# (`~/babu-web/lesen/<ref>.git`, je Box ein `git clone --mirror` vom Dienst).
# Gesichert wird von dort — nie aus dem Speicher von GitChain.
LESE_WURZEL="${BABU_LESE_WURZEL_HOST:-$HOME/babu-web/lesen}"
DEFAULT_REF="${BABU_REF:-babu/babu/belege}"
LOG="$ZIEL/sichern.log"
STEMPEL=$(date +%Y%m%d)
# Öffentlicher age-Schlüssel des Mac (~/.config/babu/sicherung.key dort).
# Nur damit lässt sich das Geheimnis-Archiv wieder öffnen.
AGE_EMPFAENGER="${BABU_AGE_EMPFAENGER:-age1kkz5rvjmm39wqllftgldek5epsecr5qrxykmkdqc4nl3krfyj38sq9r80q}"
AGE_BIN="${AGE_BIN:-$HOME/.local/bin/age}"
BEHALTEN=14
# Bundles sind je 300 MB und jedes Mal vollständig — sieben reichen, der
# Spiegel daneben hat ohnehin die ganze Historie.
BEHALTEN_BUNDLE=7

mkdir -p "$ZIEL"
sage() { echo "$(date +%Y-%m-%dT%H:%M:%S) $*" | tee -a "$LOG"; }
tue() { if [ "$TROCKEN" = 1 ]; then echo "  (trocken) $*"; else "$@"; fi; }

sage "start$([ "$TROCKEN" = 1 ] && echo " (trocken)")"

# ── 1. Belegboxen ───────────────────────────────────────────────────────────
# Welche Boxen gehören babu? Die Default-Box und alles, was in der
# Mandantentabelle als box_ref steht (volle Verweise babu/<betrieb>/belege).
# Name der Sicherung: `babu-box` für die Default-Box (wie bisher), sonst
# `box-<betrieb>`.
refs="$DEFAULT_REF"
if docker ps --format "{{.Names}}" | grep -qx babu-postgres; then
  weitere=$(docker exec babu-postgres psql -U babu -d babu -tAc \
    "select box_ref from mandant where box_ref is not null and box_ref <> ''" 2>/dev/null \
    | sed -E 's#\.git$##; s#^/+##; s#/+$##' | grep -E '^[a-z0-9._/-]+$' | sort -u)
  refs=$(printf "%s\n%s\n" "$refs" "$weitere" | grep -v '^$' | sort -u)
fi
boxen=""
for ref in $refs; do
  if [ "$ref" = "$DEFAULT_REF" ]; then box="babu"
  else box=$(printf '%s' "$ref" | awk -F/ '{print (NF>=3 ? $(NF-1) : $NF)}'); fi
  boxen="$boxen $box"
  quelle="$LESE_WURZEL/$ref.git"
  [ -d "$quelle" ] || { sage "HINWEIS: Box $ref hat noch keinen Lesespiegel ($quelle)"; continue; }
  # Alarm bei eingefrorenem Spiegel: babu-web zieht ihn bei jedem Lesen nach
  # (FETCH_HEAD). Ist er älter als SPIEGEL_MAX_STUNDEN, sichert diese Datei
  # einen alten Stand — dann FEHLER, damit stand.txt es dem Mac meldet.
  # (Box ohne Leser über Nacht ist bei der Default-Box nicht zu erwarten.)
  if [ "$ref" = "$DEFAULT_REF" ]; then
    geholt=$(stat -c %Y "$quelle/FETCH_HEAD" 2>/dev/null || stat -c %Y "$quelle/HEAD")
    alter_h=$(( ( $(date +%s) - geholt ) / 3600 ))
    [ "$alter_h" -le "${SPIEGEL_MAX_STUNDEN:-26}" ] \
      || sage "FEHLER: Lesespiegel $ref seit ${alter_h} h nicht nachgezogen — Sicherung wäre veraltet (babu-web gestoppt oder Rückweg aktiv?)"
  fi
  spiegel="$ZIEL/$([ "$box" = babu ] && echo babu-box || echo "box-$box").git"
  if [ -d "$spiegel" ]; then
    # Bestehende Sicherung auf die neue Quelle umhängen (vorher: alter Tresor).
    tue git -C "$spiegel" remote set-url origin "$quelle"
    tue git -C "$spiegel" remote update --prune >/dev/null 2>&1 \
      && sage "Box $ref nachgezogen ($(git -C "$spiegel" rev-list --count --all 2>/dev/null) Commits)" \
      || sage "FEHLER: Box $ref liess sich nicht nachziehen"
  else
    tue git clone --mirror "$quelle" "$spiegel" >/dev/null 2>&1 \
      && sage "Box $ref erstmals gespiegelt" || sage "FEHLER: Box $ref spiegeln gescheitert"
  fi
  # Das Bundle ist die Datei, die außer Haus geht: eine Datei je Box und Tag.
  if [ -d "$spiegel" ]; then
    tue git -C "$spiegel" bundle create "$ZIEL/box-$box-$STEMPEL.bundle" --all >/dev/null 2>&1 \
      && sage "Bundle box-$box-$STEMPEL ($(stat -c %s "$ZIEL/box-$box-$STEMPEL.bundle" 2>/dev/null || echo 0) Bytes)" \
      || sage "FEHLER: Bundle $box gescheitert"
  fi
done

# ── 2. Datenbank ────────────────────────────────────────────────────────────
if docker ps --format "{{.Names}}" | grep -qx babu-postgres; then
  if [ "$TROCKEN" = 1 ]; then echo "  (trocken) pg_dump -> pg-$STEMPEL.dump"
  elif docker exec babu-postgres pg_dump -U babu -d babu -Fc > "$ZIEL/pg-$STEMPEL.dump" 2>>"$LOG"; then
    sage "Postgres gesichert ($(stat -c %s "$ZIEL/pg-$STEMPEL.dump") Bytes)"
  else
    sage "FEHLER: pg_dump gescheitert"
  fi
else
  sage "FEHLER: babu-postgres laeuft nicht, kein pg_dump"
fi
# portal.db — der Rückweg, solange er liegt. Über die SQLite-Sicherung, nicht
# per cp: eine Dateikopie einer beschriebenen Datenbank wäre womöglich zerrissen.
if [ -f "$HOME/babu-web/portal.db" ] && [ "$TROCKEN" = 0 ]; then
  python3 - "$HOME/babu-web/portal.db" "$ZIEL/portal-$STEMPEL.db" <<'PY' >>"$LOG" 2>&1 \
    && sage "portal.db gesichert" || sage "FEHLER: portal.db-Sicherung gescheitert"
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as a, sqlite3.connect(sys.argv[2]) as b:
    a.backup(b)
PY
fi

# ── 3. Bilder und Postausgang ───────────────────────────────────────────────
teile=""
for d in babu-web/logos babu-web/team-fotos babu-web/ausweise babu-web/bilder babu-web/postausgang; do
  [ -d "$HOME/$d" ] && teile="$teile $d"
done
if [ -n "$teile" ]; then
  # shellcheck disable=SC2086
  tue tar czf "$ZIEL/bilder-$STEMPEL.tgz" -C "$HOME" $teile 2>/dev/null \
    && sage "Bilder gesichert ($teile )" || sage "FEHLER: Bilder-Archiv gescheitert"
else
  sage "Bilder: nichts zu sichern"
fi

# ── 4. Geheimnisse, verschlüsselt ───────────────────────────────────────────
geheim=""
for f in babu-web/.session_geheimnis babu-web/.pg_passwort babu-web/.gitlab_token \
         gitchain-eingang/.pat_babu babu-docker/docker/.env; do
  [ -f "$HOME/$f" ] && geheim="$geheim $f"
done
if [ -x "$AGE_BIN" ] && [ -n "$geheim" ]; then
  if [ "$TROCKEN" = 1 ]; then echo "  (trocken) age <-$geheim"
  # shellcheck disable=SC2086
  elif tar czf - -C "$HOME" $geheim 2>/dev/null | "$AGE_BIN" -r "$AGE_EMPFAENGER" -o "$ZIEL/geheimnisse-$STEMPEL.tar.gz.age"; then
    chmod 600 "$ZIEL/geheimnisse-$STEMPEL.tar.gz.age"
    sage "Geheimnisse gesichert ($geheim ) — nur der Mac kann sie oeffnen"
  else
    sage "FEHLER: Geheimnisse verschluesseln gescheitert"
  fi
else
  sage "FEHLER: age fehlt ($AGE_BIN) oder keine Geheimnisdateien"
fi

# ── Aufräumen: die letzten 14 Stände genügen ────────────────────────────────
if [ "$TROCKEN" = 0 ]; then
  for muster in "pg-*.dump" "portal-*.db" "bilder-*.tgz" "geheimnisse-*.tar.gz.age"; do
    ls -1t "$ZIEL"/$muster 2>/dev/null | tail -n +$((BEHALTEN + 1)) | xargs -r rm --
  done
  # Bundles je Box getrennt zählen, sonst verdrängt eine große Box die kleine.
  for box in $boxen; do
    ls -1t "$ZIEL"/box-"$box"-*.bundle 2>/dev/null | tail -n +$((BEHALTEN_BUNDLE + 1)) | xargs -r rm --
  done
fi

fehler=$(grep -c "FEHLER" <<<"$(tail -n 30 "$LOG" | sed -n "/ start/,\$p")")
if [ "$TROCKEN" = 0 ]; then
  echo "$(date +%Y-%m-%dT%H:%M:%S) $STEMPEL fehler=$fehler" > "$ZIEL/stand.txt"
fi
sage "fertig (Fehler: $fehler)"
