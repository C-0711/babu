# HANDOVER — babu / Beleg-App mit Salon-Portal

Für einen frischen Agenten oder Entwickler. Stand: 27.08.2026.
Sprache in UI und Commits: Deutsch.

## 1. Mission & Stand

Beleg-App für einen **Beauty-Salon** (Zielnutzerin: Nina, Inhaberin, erfasst
Belege zwischen zwei Terminen). Seit 26.08.2026 gilt das **Zielbild: EINE
Lesung, keine Zweitspur** — die komplette Kette läuft produktiv:

```
Kamera (eigener Sucher, Auto-Auslösung mit Plausibilitäts-Gates, Entzerrung)
  → Apple Vision liest auf dem iPhone ({text, conf, box} — Geometrie in % vom Blatt)
  → POST /api/buchung/einschaetzung: Server reichert an (Profil, ungedeckte
    Abbuchungen des Monats, Verträge/Personal, Kontenkatalog) → Gemma (vLLM,
    Text) antwortet strict JSON mit Pflichtfeld dokumentklasse
  → Fragen ↔ Antworten (max. eine Runde Rückfragen) → Buchung
  → DANACH Upload: multipart /api/aufnahme (Foto + Text + Ergebnis-JSON);
    Server sortiert nach Gemmas Klasse ein, schreibt review/<stamm>.json
    (engine "Vision (Gerät) + Gemma"), meldet Doppelgänger
  → Die Belegbox ist reines Archiv. Das Bild fasst kein System mehr an
    (nur die Portal-Vorschau rendert es zur Ansicht).
```

**Was es NICHT mehr gibt** (gelöscht 27.08., nicht wieder einbauen):
`review_watcher.py` (pm2 `belegreview`), `belegdeutung.py`,
`leseprotokoll.py`, `doc_classify.py`, der App-FeldParser im Buchungsweg,
das Kontierung-Enum, `POST /review/<stamm>/neu-lesen` und
`POST /review/<stamm>/buchungsfragen`. Paddle-OCR (:7833) ruft babu gar
nicht mehr (seit 27.08. liest auch die Abschluss-Lane Scans über Gemma) —
der Dienst gehört ctax.

**UI-Sprachregel (verbindlich):** Kein Technik-Vokabular, keine Systemnamen,
keine Geräte-/Server-Behauptungen, kein „Erst-/Zweitlesung"-Vokabular.
Vertrauen = **ein grüner Haken**. Kein Hex-Hash in der Oberfläche.

## 2. ⚠️ Betrieb: dieser Branch ist die Quelle

Produktiv auf der H200V ist `main`. **babu-web läuft seit 27.08.2026 als
Docker-Container** (Quelle `server/docker/`: host network, User 1001:1000,
Volumes `~/babu-web` rw + `~/inspektor-store` ro + PAT ro + Gemini-Env ro;
Build-Kopie `~/babu-docker/`). Deploy-Ritual: Golden vorher (`/api/belege` +
`/api/abgleich/<monat>`) → `rsync server/ h200v:~/babu-docker/` →
`docker compose build && up -d` → Golden nachher byte-diffen →
Live-Rauchtest. In pm2 bleiben `babu-eingang` und `babu-tunnel`; der
pm2-Eintrag `babu-web` ist gestoppt und dient nur als Rückweg
(`docker compose down` + `pm2 start babu-web`). **Nie anfassen:** `insp-app`
(Belegbox-Gateway :7808) und `belege-review` (ANDERES Projekt).

- Unlesbar entscheidet die App selbst (zu wenig Vision-Text → „bitte neu
  fotografieren"); es gibt keinen Server-Stub mehr für neue Belege.
- **EXTF-v13-Export existiert serverseitig** (`GET /api/export/{monat}.csv`,
  Rolle „kanzlei"). Die App bekommt KEINEN eigenen v13-Writer.
- Dublettenwache: byte-gleicher Upload wird abgewiesen; gleicher Beleg neu
  fotografiert → Doppelgänger-Hinweis in der App.
- Kontoauszüge (PDF) laufen weiter übers Portal; der Monat wird aus dem
  Auszug selbst bestimmt (`kontoauszug.py`), Belegabgleich je Monat mit
  Checkliste in App und Portal.

## 3. Meldeschleife (Nina → GitLab → autonomer Fix)

App-Rückmeldeknopf (+Screenshot) → Issue in **gitlab.0711.io, Projekt
`0711/babu`** (Label `von-nina`) → launchd-Fixlauf auf dem Mac alle 30 min
(`werkzeuge/fixlauf/`, Leitplanke deterministisch) → Deploy → Label
`zur-abnahme` → Nina gibt in der App unter „Meine Meldungen" frei.
Details: Memory `babu-meldeschleife`.

## 4. iOS-App (`ios/Beleg/`, SwiftUI, iOS 17, keine Dependencies)

| Datei | Zweck |
|---|---|
| ScannerView + CameraController/DocumentDetector/AutoCaptureGate/LiveFieldsReader/CaptureOverlayView/Dewarper | eigener Sucher, Gates, Live-Chips, Entzerrung; erholt sich nach Anruf |
| OCRService | Vision-Lesung inkl. Geometrie (`geoZeilen`/`geoJson`: {text, conf, box}) |
| FeldParser | nur noch Anzeige-Helfer für Live-Chips/Feld-Editor (`parse`, `parseBetrag`, `datumPlausibel`) — KEINE Kontierung mehr |
| Store | Persistenz, Hüllen-Beleg nach Aufnahme, Upload erst nach Buchung/Aufgabe, `ablageErgebnisSetzen`, Audit-Stempel |
| AblageService | `einschaetzung` (zeilen+profil+monat), `aufnahme` (multipart mit ergebnis), Review-Abruf, Chat-SSE, Keychain |
| BuchungsfragenView | Fragen ↔ Antworten mit Gemma, löst danach den Upload aus |
| ListeView/DetailView | grüner Haken, Feld-Editor, Lösch-Rückfrage; Review wird angezeigt, überschreibt nie lokale Buchungen |
| RueckmeldungView | Meldeknopf + „Meine Meldungen" (Meldeschleife) |

Tests: `ios/Tests/run.sh` (swiftc-Harnesse) — **Fixtures pflegen, nicht
löschen**. Server-Suite: `/tmp/babu-venv/bin/python -m pytest tests/` aus
`server/belegreview/` heraus (Python 3.12; Memory `babu-testumgebung`).

## 5. Zugänge & Bauen

- Upload-PAT: `ssh h200v 'cd ~/gitchain-eingang && .venv/bin/python pat_minten.py --zeigen --geraet "<Name>"'`
  (Code binnen 10 min auf gitchain.de/auth/device). Keychain-only.
- Simulator: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination 'platform=iOS Simulator,name=iPhone 16e' -derivedDataPath /tmp/bsim build`
- Ninas iPhone: `… 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG CODE_SIGN_STYLE=Automatic -allowProvisioningUpdates -derivedDataPath /tmp/bbuild` +
  `xcrun devicectl device install app --device 00008130-001411E00146001C <Pfad>/Beleg.app` (WLAN wackelig — zweiter Versuch hilft, Kabel sofort; Memory `babu-app-auf-ninas-iphone`).
- H200V nur über OpenVPN (`ssh h200v`).

## 6. Bekannte Fallen

1. Golden-Diff vor JEDEM Server-Deploy (Abschnitt 2).
2. Simulator-Keychain ≠ iPhone-Keychain; App-Neuinstallation verliert die
   Keychain → Nina muss sich neu verbinden.
3. Alte zustand.json müssen laden: neue Beleg-/Zustand-Felder IMMER optional
   (Achtung Altlast: `ocrText` nicht-optional mit Default — Decodable nutzt
   Defaults NICHT).
4. pm2 ist gesichert (Dump + systemd-Unit). `~/babu-sichern.sh` spiegelt die
   Belegbox täglich (cron 3:17), aber auf dieselbe Maschine — ein Ziel
   außerhalb fehlt noch.
5. iOS-Merge-Falle: im Haupt-Checkout gebaut, im Worktree committet — vor dem
   Merge diffen (Memory `babu-ios-merge-falle`).
6. Push nie mit force: `git rebase origin/main` im Worktree, dann ff-Merge —
   der Fixlauf pusht parallel.

## 7. Dokumente

- `docs/build-plan.md` — ursprünglicher Gesamtplan (historisch, siehe Banner)
- `server/belegreview/README.md` — Serverseite, Belegbox-Zugriff, Löschen
- Zielschaubild: https://claude.ai/code/artifact/401286bc-c7a1-48a1-ae5a-c5f8c6a26c39
- Kalugahair-Protokoll (Ende-zu-Ende mit echten Daten): https://claude.ai/code/artifact/86db5f96-7dfb-44ca-b917-9a5a33e8cd17
- Memory: `babu-zielbild`, `babu-salon-portal` (Deploy-Ritual!),
  `babu-meldeschleife`, `babu-testumgebung`, `babu-testkorpus`
