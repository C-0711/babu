#!/bin/sh
# UIKit-freie Logik-Harnesse (macOS, swiftc) — Muster wie in HANDOVER §4.
set -e
cd "$(dirname "$0")"
ZIEL="${TMPDIR:-/tmp}/beleg-harness"
mkdir -p "$ZIEL"

echo "— EXTF-Harness —"
swiftc -o "$ZIEL/extf" ../Beleg/Beleg/Models.swift ../Beleg/Beleg/ExtfWriter.swift extf/main.swift
"$ZIEL/extf"

echo "— Rechnungs-Harness —"
swiftc -o "$ZIEL/rechnung" ../Beleg/Beleg/Models.swift ../Beleg/Beleg/Rechnungsmodelle.swift rechnung/main.swift
"$ZIEL/rechnung"

echo "— Karten-Harness —"
# ProximityReader ist ein iOS-Framework; für den Mac-Harness bauen wir
# gegen das iOS-Simulator-SDK, aber ohne UIKit — reine Logik.
swiftc -target arm64-apple-ios17.0-simulator \
  -sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" \
  -o "$ZIEL/karte" ../Beleg/Beleg/Kartenzahlung.swift \
  ../Beleg/Beleg/KartenTerminal.swift karte/main.swift
xcrun simctl spawn --standalone "$(xcrun simctl list devices available -j \
  | python3 -c "import json,sys
d=json.load(sys.stdin)['devices']
print([g[0]['udid'] for k,g in d.items() if g and 'iOS' in k][0])")" "$ZIEL/karte"

echo "— Kassen-Harness —"
swiftc -o "$ZIEL/kasse" ../Beleg/Beleg/Models.swift ../Beleg/Beleg/Kassenbuch.swift \
       ../Beleg/Beleg/TeamModelle.swift kasse/main.swift
"$ZIEL/kasse"

echo "— Protokoll-Harness —"
swiftc -o "$ZIEL/protokoll" ../Beleg/Beleg/Protokollsatz.swift protokoll/main.swift
"$ZIEL/protokoll"

echo "— Einrichtungs-Harness —"
# Seit die Karte nur noch den Anfang zeigt, filtert Einrichtungsschritte
# nicht mehr nach Ausbaustufe — die Datei steht wieder fuer sich allein.
swiftc -o "$ZIEL/einrichtung" \
       ../Beleg/Beleg/Einrichtungsschritte.swift einrichtung/main.swift
"$ZIEL/einrichtung"

echo "— Zuschnitt-Harness (schmaler Bau) —"
# Zwei Apps aus einem Ordner: welche Reiter und welche Menuezeilen in welchem
# Bau erscheinen. Dieselbe Quelle zweimal uebersetzt, einmal mit BABU_PRO.
swiftc -o "$ZIEL/zuschnitt-schmal" ../Beleg/Beleg/Ausbaustufe.swift \
       ../Beleg/Beleg/Einrichtungsschritte.swift zuschnitt/main.swift
"$ZIEL/zuschnitt-schmal"

echo "— Zuschnitt-Harness (babu Pro) —"
swiftc -DBABU_PRO -o "$ZIEL/zuschnitt-voll" ../Beleg/Beleg/Ausbaustufe.swift \
       ../Beleg/Beleg/Einrichtungsschritte.swift zuschnitt/main.swift
"$ZIEL/zuschnitt-voll"

echo "— Chattexte-Harness —"
swiftc -o "$ZIEL/chat" ../Beleg/Beleg/Chattexte.swift chat/main.swift
"$ZIEL/chat"

echo "— Parser-Harness —"
swiftc -o "$ZIEL/parser" ../Beleg/Beleg/Models.swift ../Beleg/Beleg/FeldParser.swift parser/main.swift
"$ZIEL/parser"

echo "— Bündel-Harness —"
# Mehrseitige Belege: PDF-Bau braucht UIKit/PDFKit — wie der Karten-Harness
# gegen das iOS-Simulator-SDK gebaut und im Simulator ausgeführt.
swiftc -target arm64-apple-ios17.0-simulator \
  -sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" \
  -o "$ZIEL/buendel" ../Beleg/Beleg/Models.swift \
  ../Beleg/Beleg/BelegBuendelPDF.swift buendel/main.swift
xcrun simctl spawn --standalone "$(xcrun simctl list devices available -j \
  | python3 -c "import json,sys
d=json.load(sys.stdin)['devices']
print([g[0]['udid'] for k,g in d.items() if g and 'iOS' in k][0])")" "$ZIEL/buendel"

echo "— Store-Harness —"
# gemmaBuchungAnwenden hängt an AppStore (@MainActor, Foundation-Persistenz)
# und über AblageService/BelegBuendelPDF an praktisch der ganzen App inkl.
# UIKit — deshalb hier ALLE Quellen außer dem @main-Einstieg (BelegApp.swift,
# der mit unserem eigenen main.swift kollidieren würde), gegen das
# iOS-Simulator-SDK wie Karten- und Bündel-Harness.
STORE_DATEIEN=""
for f in ../Beleg/Beleg/*.swift; do
  case "$f" in
    */BelegApp.swift) continue ;;
  esac
  STORE_DATEIEN="$STORE_DATEIEN $f"
done
swiftc -target arm64-apple-ios17.0-simulator \
  -sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" \
  -o "$ZIEL/store" $STORE_DATEIEN store/main.swift
xcrun simctl spawn --standalone "$(xcrun simctl list devices available -j \
  | python3 -c "import json,sys
d=json.load(sys.stdin)['devices']
print([g[0]['udid'] for k,g in d.items() if g and 'iOS' in k][0])")" "$ZIEL/store"

# Bis hierher gekommen heißt: kein Harness ist abgebrochen (set -e oben) und
# keiner hat mit != 0 geendet. Ohne diese Zeile sah ein Übersetzungsfehler
# aus wie „keine Fehlschläge" — wer nur ✗ zählt, zählt bei einem gar nicht
# gelaufenen Harness null.
echo "Alle Harnesse durchgelaufen."

echo "— Verteilungs-Harness (TestFlight) —"
# Was Apple beim Upload prueft, hier vorher: Team gesetzt, Build-Nummer in
# project.yml und in allen vier Konfigurationen der pbxproj gleich, das
# Datenschutz-Manifest im Quellordner (die synchronisierte Gruppe packt es in
# beide Ziele), keine ATS-Ausnahme mehr, Export-Optionen vorhanden.
P=../Beleg
TEAM=$(sed -nE 's/^ *DEVELOPMENT_TEAM: *(.*)$/\1/p' $P/project.yml)
BUILD=$(sed -nE 's/^ *CURRENT_PROJECT_VERSION: *(.*)$/\1/p' $P/project.yml)
v() { if [ "$2" = "1" ]; then echo "  ✓ $1"; else echo "  ✗ $1"; exit 1; fi; }
v "Team in project.yml: $TEAM" "$([ -n "$TEAM" ] && echo 1)"
v "Team in allen vier Konfigurationen" "$([ "$(grep -c "DEVELOPMENT_TEAM = $TEAM;" $P/Beleg.xcodeproj/project.pbxproj)" = 4 ] && echo 1)"
v "Build-Nummer $BUILD in allen vier Konfigurationen" "$([ "$(grep -c "CURRENT_PROJECT_VERSION = $BUILD;" $P/Beleg.xcodeproj/project.pbxproj)" = 4 ] && echo 1)"
v "Build-Nummer ist nicht mehr die verbrauchte 1" "$([ "$BUILD" != "1" ] && echo 1)"
v "PrivacyInfo.xcprivacy liegt im Quellordner" "$([ -f $P/Beleg/PrivacyInfo.xcprivacy ] && echo 1)"
v "Privacy-Manifest ist gueltiges plist" "$(plutil -lint -s $P/Beleg/PrivacyInfo.xcprivacy >/dev/null 2>&1 && echo 1)"
v "keine ATS-Ausnahme in Info.plist" "$(! grep -q NSAllowsLocalNetworking $P/Support/Info.plist && echo 1)"
v "Export-Compliance beantwortet" "$(grep -q ITSAppUsesNonExemptEncryption $P/Support/Info.plist && echo 1)"
v "ExportOptions.plist vorhanden und gueltig" "$(plutil -lint -s $P/ExportOptions.plist >/dev/null 2>&1 && echo 1)"
v "archiv.sh ausfuehrbar" "$([ -x ../archiv.sh ] && echo 1)"
