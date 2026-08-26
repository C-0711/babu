# babu — Projektanweisungen für Claude

Salon-Buchhaltung: iOS-App „Beleg" (SwiftUI) + FastAPI-Server auf der H200V
(babu.0711.io). Nutzerin: Nina (Salon-Inhaberin). Sprache in UI, Commits und
Antworten: **Deutsch**. Einstieg und Details: `HANDOVER.md`.

## Verbindlich: das Zielbild (seit 26.08.2026)

**EINE Lesung, keine zweite.** Apple Vision liest auf dem iPhone
(`{text, conf, box}`), `POST /api/buchung/einschaetzung` reichert an
(Profil, ungedeckte Abbuchungen, Verträge/Personal), Gemma bucht strict JSON
mit Pflichtfeld `dokumentklasse`, **erst danach** archiviert
`POST /api/aufnahme` Foto + Ergebnis. Die Belegbox ist reines Archiv; das
Bild fasst kein System mehr an.

**Nicht wieder einbauen** (gelöscht 27.08., main `d5f0d5f`):
review_watcher, belegdeutung, leseprotokoll, doc_classify, die Routen
`neu-lesen`/`buchungsfragen`, der App-FeldParser im Buchungsweg, das
Kontierung-Enum. **Paddle-OCR (:7833) ruft babu gar nicht mehr** — der
Dienst gehört ctax; Scan-Blätter der Salonprüfung liest Gemma (multimodal).

**UI-Sprachregel:** kein Technik-Vokabular, keine Systemnamen, kein
„Erst-/Zweitlesung". Vertrauen = ein grüner Haken. Kein Hex-Hash.

## Betrieb H200V — Finger weg / Ritual

- **babu-web läuft seit 27.08.2026 als Docker-Container** (host network,
  `restart: unless-stopped`; Quelle `server/docker/`, Build-Kopie auf der
  H200V unter `~/babu-docker/`). In pm2 bleiben nur `babu-eingang` und
  `babu-tunnel`; der pm2-Eintrag `babu-web` ist gestoppt und NUR Rückweg
  (`docker compose down` + `pm2 start babu-web`). **Nie anfassen:**
  `insp-app` (Belegbox-Gateway :7808) und `belege-review` (ANDERES Projekt).
- Deploy-Ritual (immer vollständig): Golden vorher (`/api/belege` +
  `/api/abgleich/<monat>` als `python3 -m json.tool --sort-keys`) →
  `rsync server/ h200v:~/babu-docker/` → `cd ~/babu-docker/docker &&
  docker compose build && docker compose up -d` → Golden nachher
  byte-diffen → geänderte Routen live durchrufen. Golden-Diff allein
  genügt nicht.
- H200V nur über OpenVPN (`ssh h200v`). Kein sqlite3-CLI auf dem Server.
- Vor schreibenden Rauchtests erst den Ist-Wert lesen — oder Testkonto.

## Sicherheit

- Nie Passwörter oder Token-Werte entgegennehmen, eintippen oder ausgeben
  (nur Länge/Status). Keychain-only für den Upload-PAT.
- Neue Routen immer über `_box_wache`/`box_mitglied` absichern, nie über
  `ERLAUBT`.

## Bauen & Testen

- Server-Suite: aus `server/belegreview/` heraus mit
  `/tmp/babu-venv/bin/python -m pytest tests/` (Python 3.12; fastapi, httpx,
  pytest, requests, python-multipart, pypdfium2, pillow-heif, pillow).
- iOS-Simulator: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg
  -destination 'platform=iOS Simulator,name=iPhone 16e' -derivedDataPath /tmp/bsim build`
- Ninas iPhone (UDID `00008130-001411E00146001C`):
  `… 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG CODE_SIGN_STYLE=Automatic
  -allowProvisioningUpdates -derivedDataPath /tmp/bbuild` + `xcrun devicectl
  device install app` (WLAN wackelig: zweiter Versuch hilft, Kabel sofort).
- App-Logik-Harnesse: `ios/Tests/run.sh` — Fixtures pflegen, nie löschen.

## Git

- Arbeiten im Worktree, mergen per ff: im Worktree `git fetch && git rebase
  origin/main`, dann im Haupt-Checkout `git reset --hard origin/main &&
  git merge --ff-only <branch> && git push`. **Nie force-pushen** — der
  autonome Fixlauf (Meldeschleife, launchd 30 min) pusht parallel.
- iOS-Merge-Falle: im Haupt-Checkout gebaut ≠ im Worktree committet — vor
  dem Merge diffen.

## Bekannte Fallen

- Alte `zustand.json` müssen laden: neue Beleg-/Zustand-Felder IMMER
  optional (`ocrText`-Altlast: Decodable nutzt Defaults nicht).
- Simulator-Keychain ≠ iPhone-Keychain; App-Neuinstallation verliert die
  Keychain → Nina muss sich neu verbinden.
- Testdaten (echte Salon-/Bankdaten) liegen in `~/Downloads` und bleiben
  lokal — nie committen, nie hochladen.

Die `~/CLAUDE.md` im Home beschreibt die Mac-OCR-Werkzeugkette
(`~/bin/vision-ocr/`) — anderes Projekt, dort gelten eigene verbindliche
Vorgaben.
