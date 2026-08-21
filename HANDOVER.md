# HANDOVER — babu / Beleg-App mit BelegReview

Für einen frischen Agenten oder Entwickler. Stand: 16.08.2026, Branch
`claude/project-understanding-f6f4ff` ([PR #8](https://github.com/C-0711/babu/pull/8)).
Sprache in UI und Commits: Deutsch.

## 1. Mission & Stand

Beleg-App für einen **Beauty-Salon** (Zielnutzerin: Inhaberin, erfasst Belege
zwischen zwei Terminen). Die komplette Kette **läuft produktiv am echten iPhone**:

```
Kamera (eigener Sucher, Auto-Auslösung mit Plausibilitäts-Gates)
  → On-Device-Lesung (Vision-OCR + FeldParser: Steuertabelle je Satz, Beleg-Nr., Bewirtung)
  → Kontierung (Historie → Regeln → Bewirtungssignal → Fallback) + SHA-256-Siegel
  → Upload in die GitChain-Belegbox (babu.0711.io, TLS, PAT)
  → BelegReview auf der H200V (Salon-Portal-Session): PaddleOCR + Semantik + Gemma-Bild-Lane
  → review:-Commit zurück (oder Stub „unlesbar" nach 3 Fehlversuchen)
  → App zeigt Zweitprüfung mit ✓-Abgleich, DATEV-Boxen, ehrlichen Fehlerzuständen
```

**Am 16.08. wurden nach einer Voll-Analyse (~130 Findings, `/Users/…/plans/smooth-wiggling-gem.md`)
vier Runden umgesetzt** (Commits `b50df76`…`9100c26`):
Export-Bug behoben (Datei war nach dem Fixieren LEER), Demo-Belege aus dem
Stapel verbannt, Konto-Pflicht im Wischstapel, „Nichts erkannt"-Zustand,
ehrliche Kette (Fehlstatus statt Endlos-„läuft noch", Backoff-Polling,
Duplikatwarnung, Upload-Guard), Parser-Härtung (Beträge ≥ 1.000 ohne Punkt,
§19/0 %, Gegeben/Rückgeld, Datums-Validierung, Gutschrift-Signal),
SteuerPositionen im Modell, Feld-Editor + Kategorie-Änderung im Detail,
Siegel über ALLE Felder inkl. Bild, Kamera-Erholung nach Anruf,
Lösch-Rückfrage, Sprach-Sweep (Onboarding/Einstellungen/Fragen/Export),
helles Design festgeschrieben. Tests: `ios/Tests/run.sh` (39 Prüfungen).

**UI-Sprachregel (verbindlich):** Kein Technik-Vokabular, keine Systemnamen,
keine Geräte-/Server-Behauptungen. Vertrauen = **ein grüner Haken** (nur wenn
die Zweitprüfung wirklich OK war — `Beleg.zweitgeprueft`). Kein Hex-Hash in
der Oberfläche.

## 2. ⚠️ Wichtigste Betriebsregel: der Server gehört dem Portal-Branch

Auf der H200V läuft seit 13.08. das **Salon-Portal** — Quelle ist
**`claude/project-handover-context-7bfaa2`**, NICHT dieser Branch. Die
Kopien unter `server/belegreview/` hier sind historisch. **Nie von diesem
Branch aus auf die H200V deployen** — am 16.08. hätte genau das das Portal
überschrieben; der Golden-Diff (Memory `babu-salon-portal`) hat es verhindert.
Portal-Fakten, die die App betreffen:

- Watcher schließt unlesbare Belege nach 3 Versuchen mit einem **Stub-Review**
  ab: `engine: "BelegReview-Stub"`, `dokumentklasse: "unlesbar"`. Die App
  erkennt das (`BelegReviewDaten.fehlgeschlagen`) → kein grüner Haken,
  Hinweis „neu fotografieren". E-Rechnungs-Stubs sind normale Hinweise.
- iOS-Vertrag = Golden-Fixture `server/belegreview/tests/golden/review_weingaertle.json`
  (Portal-Branch). Vertragstest-Muster: Scratchpad-Harness dekodiert das
  Fixture mit `BelegReviewDaten` (16.08.: 7/7 grün).
- `/ablage` läuft inzwischen über babu-web/boxschreiber; nur `/health` liegt
  noch auf :7843. **EXTF-v13-Export existiert serverseitig**
  (`GET /api/export/{monat}.csv`, Rolle „kanzlei", Mehrsatz-Split,
  festschreiben=1 legt den Stapel in die Belegbox). Deshalb bekommt die App
  KEINEN eigenen v13-Writer — ihr Export-Tab ist als Vorschau beschriftet.
- Bekanntes offenes Live-Problem: `async def chat` blockiert babu-web
  serverweit während einer Antwort — Fix läuft in eigener Session
  (Task-Chip „Chat-Blockade in babu_web des Salon-Portals beheben").

## 3. iOS-App (`ios/Beleg/`, SwiftUI, iOS 17, keine Dependencies)

| Datei | Zweck |
|---|---|
| ScannerView + CameraController/DocumentDetector/AutoCaptureGate/LiveFieldsReader/CaptureOverlayView/Dewarper | eigener Sucher, 8 Gates, Live-Chips, Entzerrung; erholt sich nach Anruf (interruptionEnded/runtimeError), Abbruch storniert den Snap |
| FeldParser | Steuertabellen-Kombinatorik (auch über Satz-Token gesplittet), Beträge ohne Tausenderpunkt, §19/0 %, Gegeben/Rückgeld-Filter, Datums-Validierung, Gutschrift-Signal, Beleg-Nr.-Kette, Bewirtungssignal |
| Models | Beleg (alle neuen Felder optional!), SteuerPosition, `zweitgeprueft`, `siegelHash` über alle Felder + Bild-Hash |
| ExtfWriter | UIKit-freie Stapel-Vorschau (Betrag ohne Gruppierung, TTMM mit Nullen, Monat dynamisch) — der echte Export ist Portal-Sache |
| Store | Persistenz, `exportieren()` (Datei VOR fixieren!), Upload-Queue mit In-flight-Guard, Backoff-Polling, `felderKorrigieren`, `altBelegeNachreichen`, Fixiert-Schutz überall |
| AblageService | Upload, `ReviewAntwort` (fertig/nochNicht/zugangFehlt/serverProblem/keineVerbindung), Stub-Erkennung, Chat-SSE inkl. Fehlerframes, Keychain |
| ListeView/DetailView | grüner Haken nur bei `zweitgeprueft`, Fehlstatus-Zeilen, Feld-Editor + Kategorie ändern, Lösch-Rückfrage |
| FeldEditorSheet | Korrektur von Lieferant/Nr./Datum/Beträgen mit Live-Summenprobe |
| AufraeumenView | Wischstapel; ohne Konto → Kontierungs-Sheet statt Leerbuchung |
| CaptureTab | „Nichts erkannt"-Zustand, Duplikat-/Gutschrift-Warnung, Demo nur im Simulator |

Tests: `ios/Tests/run.sh` — EXTF-Golden + Parser-Fixtures (39 Prüfungen).
**Fixtures pflegen, nicht löschen** — jede war mal ein echter Bug.

## 4. Zugänge & Bauen

- Upload-PAT: `ssh h200v 'cd ~/gitchain-eingang && .venv/bin/python pat_minten.py --zeigen --geraet "<Name>"'`
  (laufen lassen, Code binnen 10 min auf gitchain.de/auth/device). Keychain-only.
- Bauen: `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination 'generic/platform=iOS Simulator' build`
  · iPhone: `… 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG -allowProvisioningUpdates` +
  `xcrun devicectl device install app --device DE430DAD-59C1-5D52-BBBD-2B8869DDC2C6 <Pfad>/Beleg.app`
- H200V nur über OpenVPN (`ssh h200v`).

## 5. Bekannte Fallen

1. Leerer `POST /ablage` → 422 VOR der Token-Prüfung; Token-Test mit txt-Datei.
2. Golden-Diff vor JEDEM Server-Deploy — und deployen nur vom Portal-Branch (Abschnitt 2!).
3. PaddleOCR: nur `lang="german"` + `ocr_version="PP-OCRv5"`, CPU (GPUs voll mit vLLM).
4. Simulator-Keychain ≠ iPhone-Keychain.
5. Alte zustand.json müssen laden: neue Beleg-/Zustand-Felder IMMER optional.
   (Achtung Altlast: `ocrText` ist nicht-optional mit Default — Swift-Decodable
   nutzt Defaults NICHT; sehr alte Stände vor `ocrText` würden komplett auf
   Demo-Daten zurückfallen. Bei Migrationsarbeit zuerst hier ansetzen.)
6. pm2 ist gesichert (Dump + systemd-Unit enabled, geprüft 22.08.2026) — die
   frühere Warnung „nach Reboot ist alles weg" stimmt nicht mehr. Neu:
   `~/babu-sichern.sh` spiegelt die Belegbox täglich (cron 3:17), aber auf
   dieselbe Maschine — ein Ziel außerhalb fehlt noch.
7. Nie in der Arbeitskopie des laufenden Watchers committen.

## 6. Offene Punkte (Reihenfolge = Empfehlung)

1. **Neuen Build aufs iPhone** — am 16.08. war kein Gerät angeschlossen
   (devicectl: alle „unavailable"). Beim nächsten Anstecken installieren;
   danach die migrierten Demo-Leichen prüfen (werden jetzt als BEISPIEL markiert)
   und den bestätigten 85,40-Weingärtle-Doppler löschen (Lösch-Rückfrage kommt).
2. **Chat-Blockade** — läuft als eigene Session (Portal-Branch); danach gilt
   der /chat-Golden-Mitschnitt (`tests/golden/chat_sse_mitschnitt.txt`).
3. **Bewirtung 70/30 (6640/6644)** — gehört in den Portal-EXTF-Writer, nicht
   in die App; Bewirtungsangaben aus der App in die Belegbox zurückschreiben
   (Portal hat `POST /api/bewirtung/{stamm}` — App könnte den nutzen!).
4. Datenhaltung: JPEGs raus aus der JSON (einzelne Dateien + Index) — bei
   vielen Belegen drohen Speicherdruck und lange Schreiber.
5. Kontierung „lernt" nicht wirklich (statische Historie) — echte
   Kreditor-Historie aus gebuchten Belegen aufbauen.
6. A11y: Dynamic Type (8-pt-Labels), VoiceOver im Sucher.
7. `CaptureTuning` am Gerät justieren; `pm2 save` sobald die Parallel-Session ruht.

## 7. Dokumente

- `docs/build-plan.md` — Gesamtplan · `ios/README.md` — App-Struktur
- Analyse & Runden-Plan: `~/.claude/plans/smooth-wiggling-gem.md`
- Portal: Spec + Golden-Fixtures auf `claude/project-handover-context-7bfaa2`
- Memory: `babu-salon-portal.md` (Deploy-Ritual!), `babu-testkorpus.md`
