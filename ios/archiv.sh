#!/usr/bin/env bash
# Archiv bauen und zu TestFlight hochladen — ein Aufruf, ein Ziel.
#
#   ios/archiv.sh                 # Ziel „Beleg" (babu) archivieren und hochladen
#   ios/archiv.sh BelegPro        # dito für babu Pro
#   ios/archiv.sh Beleg --nur-ipa # nur die .ipa unter /tmp/babu-archiv/ ablegen
#
# Voraussetzungen, die nur der Mensch schaffen kann: das Apple-Team
# 8L87Z2GRSG in Xcode angemeldet (Xcode → Settings → Accounts) ODER ein
# App-Store-Connect-API-Schlüssel in den drei Variablen
#   ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PFAD   (die .p8-Datei)
# — dann läuft der Upload ohne Anmeldedialog, z. B. im Cron.
#
# Build-Nummer: CURRENT_PROJECT_VERSION in ios/Beleg/project.yml UND
# project.pbxproj — beide gleich, ios/Tests/run.sh prüft es. App Store
# Connect nimmt dieselbe Build-Nummer kein zweites Mal an; vor jedem Upload
# hochzählen (in BEIDEN Dateien).
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
SCHEMA="${1:-Beleg}"
MODUS="${2:-upload}"
ARCHIV_DIR="/tmp/babu-archiv"
ARCHIV="$ARCHIV_DIR/$SCHEMA.xcarchive"
EXPORT="$ARCHIV_DIR/$SCHEMA-export"
OPTIONEN="$HIER/Beleg/ExportOptions.plist"

case "$SCHEMA" in
  Beleg|BelegPro) ;;
  *) echo "Unbekanntes Ziel: $SCHEMA (Beleg oder BelegPro)"; exit 2 ;;
esac

# Die Prüfungen aus run.sh, bevor Zeit ins Archiv geht.
VERSION=$(sed -nE 's/^ *MARKETING_VERSION: *(.*)$/\1/p' "$HIER/Beleg/project.yml")
BUILD=$(sed -nE 's/^ *CURRENT_PROJECT_VERSION: *(.*)$/\1/p' "$HIER/Beleg/project.yml")
if [ "$(grep -c "CURRENT_PROJECT_VERSION = $BUILD;" "$HIER/Beleg/Beleg.xcodeproj/project.pbxproj")" != "4" ]; then
  echo "Build-Nummer $BUILD aus project.yml steht nicht in allen vier Konfigurationen von project.pbxproj."; exit 3
fi
[ -f "$HIER/Beleg/Beleg/PrivacyInfo.xcprivacy" ] || { echo "PrivacyInfo.xcprivacy fehlt — Apple nimmt das Archiv nicht an."; exit 3; }
# Rechtstexte: Platzhalter sind für interne Tester in Ordnung, für die Beta
# App Review (externe Einladung) nicht — Apple liest die Datenschutz-Seite.
if ! (cd "$HIER/../server/belegreview" && python3 -c "import recht, sys; sys.exit(0 if recht.fertig() else 1)" 2>/dev/null); then
  echo "HINWEIS: Impressum/Datenschutz/AGB sind noch Platzhalter (server/belegreview/recht.py) — dieser Build taugt nur für interne Tester."
fi

# Bash 3.2 (macOS) verträgt ein leeres Array unter `set -u` nicht — deshalb ein
# String, der leer bleiben darf, und unten ungequotet eingesetzt wird.
AUTH=""
if [ -n "${ASC_KEY_ID:-}" ]; then
  AUTH="-authenticationKeyID $ASC_KEY_ID -authenticationKeyIssuerID $ASC_ISSUER_ID -authenticationKeyPath $ASC_KEY_PFAD"
fi

echo "── $SCHEMA $VERSION ($BUILD): Archiv ──"
rm -rf "$ARCHIV" "$EXPORT"
xcodebuild -project "$HIER/Beleg/Beleg.xcodeproj" -scheme "$SCHEMA" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIV" \
  -allowProvisioningUpdates $AUTH archive 2>&1 | grep -E 'error:|warning: .*Beleg/|ARCHIVE (SUCCEEDED|FAILED)|\*\*' || true
[ -d "$ARCHIV" ] || { echo "Kein Archiv entstanden."; exit 1; }

if [ "$MODUS" = "--nur-ipa" ]; then
  # Export auf die Platte statt Upload: dieselben Optionen, nur das Ziel anders.
  TMP=$(mktemp "$ARCHIV_DIR/optionen.XXXXXX.plist")
  sed 's#<string>upload</string>#<string>export</string>#' "$OPTIONEN" > "$TMP"
  OPTIONEN="$TMP"
  echo "── Export nach $EXPORT ──"
else
  echo "── Upload zu App Store Connect ──"
fi
LOG="$ARCHIV_DIR/$SCHEMA-export.log"
xcodebuild -exportArchive -archivePath "$ARCHIV" -exportOptionsPlist "$OPTIONEN" \
  -exportPath "$EXPORT" -allowProvisioningUpdates $AUTH > "$LOG" 2>&1 || true
grep -E 'error:|EXPORT (SUCCEEDED|FAILED)|Upload' "$LOG" || true
if ! grep -q 'EXPORT SUCCEEDED' "$LOG"; then
  echo "Export fehlgeschlagen — Einzelheiten in $LOG:"
  grep -iE 'error|reason|description' "$LOG" | grep -v '^error: exportArchive' | head -8
  exit 1
fi
if [ "$MODUS" = "--nur-ipa" ]; then
  ls -la "$EXPORT"/*.ipa
else
  echo "Fertig: $SCHEMA $VERSION ($BUILD) liegt bei App Store Connect. Bis TestFlight ihn zeigt, dauert es ein paar Minuten."
fi
