#!/usr/bin/env bash
# Box-Umzug: eine Belegbox mit voller Historie aus dem alten Tresor in den
# neuen GitChain-Dienst übernehmen (GitChain-Standard 27.09.2026).
#
# Läuft auf dem HOST der H200v (der Tresor ist im Container nicht gemountet).
# Die Quelle wird nur gelesen: `git clone --mirror --no-local` in einen
# Arbeitsordner, keine Hardlinks, kein Schreiben im Tresor. Ziel ist
# `<dienst>/git/babu/<betrieb>/belege.git` — per Push-to-create als
# Dienstkonto (Basic <konto>:<token>, Token aus einer 0600-Datei; der Wert
# erscheint nie in argv, Log oder Ausgabe).
#
# Standard ist der TROCKENLAUF: Quelle klonen und prüfen (fsck, Commits,
# HEAD, Refs, Größe), Ziel per ls-remote ansehen — nichts wird geschrieben.
# Erst `--scharf` pusht (`git push --mirror`) und prüft danach aus einem
# frischen Klon des Ziels: Commit-Zahl, HEAD und alle Refs müssen gleich sein.
#
#   box-umzug.sh --ziel-ref babu/babu/belege                 # Trockenlauf
#   box-umzug.sh --ziel-ref babu/babu/belege --scharf        # übernehmen
#
# Optionen (Vorgaben in Klammern):
#   --quelle <pfad|url>   (~/gitchain/tresor/inspektor/ws-christoph0711.io/babu.git)
#   --ziel-ref <ref>      Pflicht, Form babu/<betrieb>/belege
#   --dienst <url>        (http://127.0.0.1:3361 — der neue Dienst, intern)
#   --konto <name>        (svc-babu)
#   --token-datei <pfad>  (~/gitchain-eingang/.pat_babu; Umgebung BABU_UMZUG_TOKEN_DATEI)
#   --arbeit <ordner>     Elternordner für den Arbeitsordner (mktemp darin; nur der
#                         eigene mktemp-Ordner wird am Ende gelöscht, außer --behalten)
#   --scharf              wirklich pushen
#   --behalten            Arbeitsordner stehen lassen
#
# Rückgabe: 0 = geprüft (Trockenlauf) bzw. übernommen und bestätigt;
#           1 = Prüfung gescheitert; 2 = falscher Aufruf; 3 = Ziel nicht leer
#           (schon übernommen und identisch → 0 mit Hinweis).
set -euo pipefail

QUELLE="$HOME/gitchain/tresor/inspektor/ws-christoph0711.io/babu.git"
ZIEL_REF=""
DIENST="http://127.0.0.1:3361"
KONTO="svc-babu"
TOKEN_DATEI="${BABU_UMZUG_TOKEN_DATEI:-$HOME/gitchain-eingang/.pat_babu}"
ARBEIT=""
SCHARF=0
BEHALTEN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --quelle) QUELLE="$2"; shift 2 ;;
    --ziel-ref) ZIEL_REF="$2"; shift 2 ;;
    --dienst) DIENST="${2%/}"; shift 2 ;;
    --konto) KONTO="$2"; shift 2 ;;
    --token-datei) TOKEN_DATEI="$2"; shift 2 ;;
    --arbeit) ARBEIT="$2"; shift 2 ;;
    --scharf) SCHARF=1; shift ;;
    --behalten) BEHALTEN=1; shift ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    *) echo "unbekannte Option: $1" >&2; exit 2 ;;
  esac
done

sage() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
stirb() { sage "FEHLER: $1"; exit "${2:-1}"; }

[[ "$ZIEL_REF" =~ ^babu/[a-z0-9][a-z0-9._-]{0,79}/belege$ ]] && [[ "$ZIEL_REF" != *..* ]] \
  || stirb "--ziel-ref muss die Form babu/<betrieb>/belege haben (bekommen: „$ZIEL_REF“)" 2
[ -r "$TOKEN_DATEI" ] || stirb "Token-Datei $TOKEN_DATEI nicht lesbar" 2
rechte=$(stat -c %a "$TOKEN_DATEI" 2>/dev/null || stat -f %Lp "$TOKEN_DATEI")
[ "$rechte" = "600" ] || [ "$rechte" = "400" ] || stirb "Token-Datei $TOKEN_DATEI hat Rechte $rechte, erwartet 600" 2
ZIEL_URL="$DIENST/git/$ZIEL_REF.git"

# Auth nur über die Umgebung dieses Prozesses (nicht argv). Vorhandene
# GIT_CONFIG_*-Listen und Schlüsselbünde bleiben außen vor.
for v in $(env | sed -n 's/^\(GIT_CONFIG_[A-Z_0-9]*\)=.*/\1/p'); do unset "$v"; done
TOKEN=$(tr -d '\r\n' < "$TOKEN_DATEI")
[[ "$TOKEN" == gcpat-* ]] || stirb "Token-Datei enthält kein gcpat-Token" 2
export GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=2 \
  GIT_CONFIG_KEY_0=http.extraHeader \
  GIT_CONFIG_VALUE_0="Authorization: Basic $(printf '%s:%s' "$KONTO" "$TOKEN" | base64 | tr -d '\n')" \
  GIT_CONFIG_KEY_1=credential.helper GIT_CONFIG_VALUE_1=
unset TOKEN
# Große Packs (Belegfotos): nicht in 1-MB-Häppchen, keine Zeitgrenze durch Trägheit.
export GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=120

# Gelöscht wird am Ende NUR ein Ordner, den dieses Skript selbst per mktemp
# angelegt hat. Ein per --arbeit übergebener Ordner bekommt einen eigenen
# mktemp-Unterordner; nur der wird aufgeräumt, der Ordner selbst nie.
if [ -z "$ARBEIT" ]; then
  ARBEIT=$(mktemp -d "${TMPDIR:-/tmp}/babu-umzug.XXXXXX")
else
  mkdir -p "$ARBEIT"
  ARBEIT=$(mktemp -d "$ARBEIT/babu-umzug.XXXXXX")
fi
aufraeumen() {
  [ "$BEHALTEN" = 1 ] && return
  case "$(basename "$ARBEIT")" in babu-umzug.??????) rm -rf -- "$ARBEIT" ;; esac
}
trap aufraeumen EXIT

sage "Umzug $([ "$SCHARF" = 1 ] && echo SCHARF || echo TROCKENLAUF): $QUELLE → $ZIEL_URL (Konto $KONTO)"

# ── 1. Quelle lesen (nur lesen) ─────────────────────────────────────────────
Q="$ARBEIT/quelle.git"
rm -rf "$Q"
# Die Quelle ist lokal und gehört niemandem sonst: keine Anmeldung nötig.
env -u GIT_CONFIG_COUNT git clone -q --mirror --no-local "$QUELLE" "$Q" \
  || stirb "Quelle $QUELLE lässt sich nicht klonen"
git -C "$Q" fsck --no-progress --connectivity-only >/dev/null 2>&1 || stirb "fsck der Quelle meldet Fehler"
q_commits=$(git -C "$Q" rev-list --count --all)
q_head=$(git -C "$Q" rev-parse --verify -q HEAD || echo "-")
q_headref=$(git -C "$Q" symbolic-ref -q HEAD || echo "-")
q_refs=$(git -C "$Q" for-each-ref --format='%(objectname) %(refname)' | sort)
q_nrefs=$(printf '%s\n' "$q_refs" | grep -c . || true)
q_groesse=$(du -sk "$Q" | cut -f1)
sage "Quelle: $q_commits Commits, HEAD $q_head ($q_headref), $q_nrefs Refs, $((q_groesse / 1024)) MiB (gepackt)"
[ "$q_head" != "-" ] || stirb "Quelle hat keinen HEAD — nichts zu übernehmen (leere Box neu anlegen statt umziehen)"
[ "$q_headref" = "refs/heads/main" ] || sage "HINWEIS: HEAD der Quelle ist $q_headref, nicht refs/heads/main"

# ── 2. Ziel ansehen ─────────────────────────────────────────────────────────
set +e
z_ls=$(git ls-remote "$ZIEL_URL" 2>"$ARBEIT/ls.err"); z_rc=$?
set -e
if [ $z_rc -ne 0 ]; then
  if grep -qiE '\b(401)\b|Authentication|could not read Username' "$ARBEIT/ls.err"; then
    stirb "Dienst lehnt die Anmeldung ab (401) — Token/Konto prüfen"
  fi
  sage "Ziel: noch nicht vorhanden (ls-remote: $(tail -n1 "$ARBEIT/ls.err" | sed 's/gcpat-[A-Za-z0-9_-]*/gcpat-***/g' | cut -c1-120))"
  z_leer=1
elif [ -z "$z_ls" ]; then
  sage "Ziel: vorhanden, aber leer"; z_leer=1
else
  z_head=$(printf '%s\n' "$z_ls" | awk '$2=="HEAD"{print $1}')
  [ "$z_head" = "$q_head" ] \
    || stirb "Ziel ist nicht leer (HEAD ${z_head:-?}) und nicht identisch — kein Überschreiben" 3
  sage "Ziel hat schon denselben HEAD $z_head — bereits übernommen, es folgt nur die Gegenprobe"
  z_leer=0
fi

if [ "$SCHARF" = 0 ] && [ "$z_leer" = 1 ]; then
  sage "TROCKENLAUF fertig: würde $q_nrefs Refs / $q_commits Commits per 'git push --mirror' nach $ZIEL_URL schieben. Nichts geschrieben."
  exit 0
fi

# ── 3. Übernehmen ───────────────────────────────────────────────────────────
if [ "$z_leer" = 1 ]; then
  t0=$(date +%s)
  git -C "$Q" -c http.postBuffer=524288000 push --mirror "$ZIEL_URL" >"$ARBEIT/push.log" 2>&1 \
    || { sed 's/gcpat-[A-Za-z0-9_-]*/gcpat-***/g' "$ARBEIT/push.log" | tail -n 5; stirb "push --mirror gescheitert"; }
  sage "gepusht in $(( $(date +%s) - t0 )) s"
fi

# ── 4. Gegenprobe aus einem frischen Klon des Ziels ─────────────────────────
# Der Dienst registriert einen per Push angelegten Container im Hintergrund
# (Eigentümer, Rechte) — bis dahin ist er für Lesende „not found". Deshalb
# bis zu 60 s warten, bevor die Gegenprobe als gescheitert gilt.
P="$ARBEIT/pruef.git"
for i in $(seq 1 30); do
  rm -rf "$P"
  git clone -q --mirror "$ZIEL_URL" "$P" 2>"$ARBEIT/pruef.err" && break
  [ "$i" = 30 ] && { tail -n1 "$ARBEIT/pruef.err"; stirb "Ziel lässt sich nach dem Push nicht klonen"; }
  sleep 2
done
p_commits=$(git -C "$P" rev-list --count --all)
p_head=$(git -C "$P" rev-parse --verify -q HEAD || echo "-")
p_refs=$(git -C "$P" for-each-ref --format='%(objectname) %(refname)' | sort)
git -C "$P" fsck --no-progress --connectivity-only >/dev/null 2>&1 || stirb "fsck des Ziels meldet Fehler"
sage "Ziel:   $p_commits Commits, HEAD $p_head"
[ "$p_commits" = "$q_commits" ] || stirb "Commit-Zahl weicht ab: Quelle $q_commits, Ziel $p_commits"
[ "$p_head" = "$q_head" ] || stirb "HEAD weicht ab: Quelle $q_head, Ziel $p_head"
[ "$p_refs" = "$q_refs" ] || stirb "Refs weichen ab"
sage "BESTÄTIGT: $q_commits Commits, HEAD $q_head, $q_nrefs Refs identisch in $ZIEL_REF"
