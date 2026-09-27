#!/usr/bin/env bash
# Box-Rückholen: der Rückweg des GitChain-Standards (27.09.2026).
#
# Holt Commits, die nach dem Umzug beim neuen Dienst entstanden sind, per
# Fast-Forward zurück in die alte Box im Tresor — BEVOR das alte babu-web
# wieder startet (sonst schreibt der alte Weg dazwischen und ein
# Fast-Forward ist nicht mehr möglich).
#
# Läuft auf dem HOST der H200v. Anmeldung beim Dienst als Dienstkonto mit
# einer EIGENEN Token-Datei (Standard ~/gitchain-eingang/.pat_babu.svc):
# beim Rückweg liegt in .pat_babu schon wieder das alte Token. Der Wert geht
# nur über die Umgebung dieses Prozesses, nie in argv, Log oder Ausgabe.
#
# Nur Fast-Forward: steht in der Zielbox ein Commit, den der Dienst nicht
# hat, bricht das Skript ab (Exit 3) und schreibt nichts. Eine leere
# Zielbox (die drei leeren Boxen der Mandanten 1/3/4) bekommt den Stand des
# Dienstes. Standard ist der TROCKENLAUF; erst --scharf schreibt, danach wird
# HEAD von Dienst und Ziel verglichen.
#
#   box-rueckholen.sh --liste paare.tsv              # Trockenlauf
#   box-rueckholen.sh --liste paare.tsv --scharf
#   box-rueckholen.sh --ref babu/babu/belege --ziel <tresor>/babu.git [--scharf]
#
# paare.tsv: je Zeile  <ref beim Dienst><TAB><Pfad der alten Box im Tresor>
#
# Optionen: --dienst (http://127.0.0.1:3361), --konto (svc-babu),
#           --token-datei (~/gitchain-eingang/.pat_babu.svc),
#           --anlegen  fehlende Zielbox (Betrieb erst nach dem Go-live angelegt)
#                      leer per git init --bare anlegen, dann zurückholen
# Rückgabe: 0 = alles geprüft bzw. zurückgeholt, 1 = Fehler, 2 = Aufruf,
#           3 = mindestens eine Box nicht per Fast-Forward holbar.
set -euo pipefail

DIENST="http://127.0.0.1:3361"
KONTO="svc-babu"
TOKEN_DATEI="${BABU_RUECK_TOKEN_DATEI:-$HOME/gitchain-eingang/.pat_babu.svc}"
LISTE=""; REF=""; ZIEL=""; SCHARF=0; ANLEGEN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --liste) LISTE="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --ziel) ZIEL="$2"; shift 2 ;;
    --dienst) DIENST="${2%/}"; shift 2 ;;
    --konto) KONTO="$2"; shift 2 ;;
    --token-datei) TOKEN_DATEI="$2"; shift 2 ;;
    --scharf) SCHARF=1; shift ;;
    --anlegen) ANLEGEN=1; shift ;;
    -h|--help) sed -n '2,31p' "$0"; exit 0 ;;
    *) echo "unbekannte Option: $1" >&2; exit 2 ;;
  esac
done

sage() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
stirb() { sage "FEHLER: $1"; exit "${2:-1}"; }

[ -r "$TOKEN_DATEI" ] || stirb "Token-Datei $TOKEN_DATEI nicht lesbar" 2
rechte=$(stat -c %a "$TOKEN_DATEI" 2>/dev/null || stat -f %Lp "$TOKEN_DATEI")
[ "$rechte" = "600" ] || [ "$rechte" = "400" ] || stirb "Token-Datei hat Rechte $rechte, erwartet 600" 2

PAARE=$(mktemp "${TMPDIR:-/tmp}/babu-rueck.XXXXXX")
trap 'rm -f -- "$PAARE"' EXIT
if [ -n "$LISTE" ]; then grep -v '^\s*#' "$LISTE" | grep -v '^\s*$' > "$PAARE"
elif [ -n "$REF" ] && [ -n "$ZIEL" ]; then printf '%s\t%s\n' "$REF" "$ZIEL" > "$PAARE"
else stirb "--liste oder --ref + --ziel angeben" 2; fi

for v in $(env | sed -n 's/^\(GIT_CONFIG_[A-Z_0-9]*\)=.*/\1/p'); do unset "$v"; done
TOKEN=$(tr -d '\r\n' < "$TOKEN_DATEI")
[[ "$TOKEN" == gcpat-* ]] || stirb "Token-Datei enthält kein gcpat-Token" 2
export GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=2 \
  GIT_CONFIG_KEY_0=http.extraHeader \
  GIT_CONFIG_VALUE_0="Authorization: Basic $(printf '%s:%s' "$KONTO" "$TOKEN" | base64 | tr -d '\n')" \
  GIT_CONFIG_KEY_1=credential.helper GIT_CONFIG_VALUE_1=
unset TOKEN
export GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=60

sage "Rückholen $([ "$SCHARF" = 1 ] && echo SCHARF || echo TROCKENLAUF) von $DIENST (Konto $KONTO)"
fehler=0; kein_ff=0
while IFS=$'\t' read -r ref ziel; do
  [[ "$ref" =~ ^babu/[a-z0-9][a-z0-9._-]{0,79}/belege$ ]] || { sage "FEHLER: $ref ist kein babu-Verweis"; fehler=1; continue; }
  if [ ! -e "$ziel" ] && [ "$ANLEGEN" = 1 ]; then
    # Betrieb, der erst nach dem Go-live entstand: im alten Tresor gibt es
    # seine Box nicht. Mit --anlegen entsteht sie leer (git init --bare) —
    # nur als <name>.git in einem schon vorhandenen Ordner, im Trockenlauf gar nicht.
    case "$ziel" in *.git) ;; *) sage "FEHLER: $ziel endet nicht auf .git"; fehler=1; continue ;; esac
    [ -d "$(dirname "$ziel")" ] || { sage "FEHLER: Ordner $(dirname "$ziel") fehlt"; fehler=1; continue; }
    if [ "$SCHARF" = 1 ]; then
      git init -q --bare -b main "$ziel" && sage "$ref: leere Box $ziel angelegt"
    else
      sage "TROCKEN $ref: würde leere Box $ziel anlegen und dann alle Commits des Dienstes holen"
      continue
    fi
  fi
  [ -d "$ziel" ] && git -C "$ziel" rev-parse --is-bare-repository >/dev/null 2>&1 \
    || { sage "FEHLER: $ziel ist keine Git-Box (fehlt sie? dann --anlegen)"; fehler=1; continue; }
  url="$DIENST/git/$ref.git"
  set +e
  d_head=$(git ls-remote "$url" refs/heads/main 2>/dev/null | awk '{print $1}'); rc=$?
  set -e
  [ $rc -eq 0 ] || { sage "FEHLER: $ref beim Dienst nicht lesbar"; fehler=1; continue; }
  z_head=$(git -C "$ziel" rev-parse --verify -q refs/heads/main || true)
  if [ -z "$d_head" ]; then sage "$ref: beim Dienst leer — nichts zu holen"; continue; fi
  if [ "$d_head" = "$z_head" ]; then sage "$ref → $ziel: schon gleich ($d_head)"; continue; fi
  # Objekte in einen eigenen Ref holen (schreibt nur Objekte, keinen Branch).
  if [ "$SCHARF" = 1 ]; then
    git -C "$ziel" fetch -q "$url" "+refs/heads/main:refs/rueckholen/main" \
      || { sage "FEHLER: fetch $ref gescheitert"; fehler=1; continue; }
  else
    # Trockenlauf: in ein Wegwerf-Repo mit der Zielbox als Alternates-Quelle.
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/babu-rueck-trocken.XXXXXX")
    git init -q --bare "$tmp"
    echo "$(cd "$ziel" && pwd)/objects" > "$tmp/objects/info/alternates"
    [ -n "$z_head" ] && git -C "$tmp" update-ref refs/heads/alt "$z_head"
    git -C "$tmp" fetch -q "$url" "+refs/heads/main:refs/rueckholen/main" \
      || { sage "FEHLER: fetch $ref gescheitert"; rm -rf -- "$tmp"; fehler=1; continue; }
  fi
  pruef=$([ "$SCHARF" = 1 ] && echo "$ziel" || echo "$tmp")
  if [ -n "$z_head" ] && ! git -C "$pruef" merge-base --is-ancestor "$z_head" "$d_head"; then
    sage "ABBRUCH $ref: Zielbox hat Commits, die der Dienst nicht hat (Ziel $z_head) — kein Fast-Forward"
    kein_ff=1
    [ "$SCHARF" = 1 ] && git -C "$ziel" update-ref -d refs/rueckholen/main
    [ "$SCHARF" = 0 ] && rm -rf -- "$tmp"
    continue
  fi
  neu=$(git -C "$pruef" rev-list --count "${z_head:+$z_head..}$d_head")
  if [ "$SCHARF" = 0 ]; then
    sage "TROCKEN $ref → $ziel: würde main ${z_head:-(leer)} → $d_head vorspulen ($neu neue Commits)"
    rm -rf -- "$tmp"
    continue
  fi
  git -C "$ziel" update-ref refs/heads/main "$d_head" ${z_head:+"$z_head"}
  git -C "$ziel" update-ref -d refs/rueckholen/main
  [ "$(git -C "$ziel" rev-parse refs/heads/main)" = "$d_head" ] \
    || { sage "FEHLER: $ref Ziel-HEAD nach dem Vorspulen falsch"; fehler=1; continue; }
  sage "ZURÜCK $ref → $ziel: main ${z_head:-(leer)} → $d_head ($neu Commits), HEAD gleich Dienst"
done < "$PAARE"

[ "$fehler" = 0 ] || exit 1
[ "$kein_ff" = 0 ] || exit 3
exit 0
