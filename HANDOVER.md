# HANDOVER — babu / Beleg-App mit BelegReview

Für einen frischen Agenten oder Entwickler. Stand: 13.08.2026, Branch
`claude/project-understanding-f6f4ff` ([PR #8](https://github.com/C-0711/babu/pull/8)).
Sprache in UI und Commits: Deutsch.

## 1. Mission & Stand

Beleg-App für einen **Beauty-Salon** (Zielnutzerin: Inhaberin, erfasst Belege
zwischen zwei Terminen). Die komplette Kette **läuft produktiv am echten iPhone**:

```
Kamera (eigener Sucher, Auto-Auslösung mit Plausibilitäts-Gates)
  → On-Device-Lesung (Vision-OCR + FeldParser: Steuertabelle, Beleg-Nr., Bewirtung)
  → Kontierung (Historie → Regeln → Bewirtungssignal → Fallback) + SHA-256-Siegel
  → Upload in die GitChain-Belegbox (babu.0711.io, TLS, PAT)
  → BelegReview auf der H200V: PaddleOCR + embeddinggemma-Semantik + Gemma-4-Bild-Lane
  → review:-Commit zurück ins Repo (Felder, Einordnung, DATEV-Satz, Embedding)
  → App zeigt Zweitprüfung mit ✓-Abgleich, DATEV-Boxen, sprechendem Buchungstext
```

Dazu: **Aufräumen** (Tinder-Wischstapel für offene Belege), **Fragen-Chat**
(Gemma 4, SSE, antwortet nur aus den eigenen Reviews), **Bewirtungs-Nachfrage**
(§4 Abs. 5: Anlass + Personen beim Buchen), Löschen per Wischgeste, Persistenz.

**UI-Sprachregel (verbindlich, vom Nutzer gesetzt):** Kein Technik-Vokabular,
keine Systemnamen, keine Geräte-/Server-Behauptungen. Vertrauen = **ein grüner
Haken**. Sektionen heißen „ZWEITPRÜFUNG", „AUS DEM FOTO", „DAS GEHT AN DATEV".
Nachfragen menschlich formuliert („Mit wem warst du essen?"), Paragraf klein.

## 2. Komponenten

### iOS-App (`ios/Beleg/`, SwiftUI, iOS 17, keine Dependencies)
| Datei | Zweck |
|---|---|
| ScannerView + CameraController/DocumentDetector/AutoCaptureGate/LiveFieldsReader/CaptureOverlayView/Dewarper | eigener Sucher: Segmentierung, 8 Gates (kein Auto-Fire auf Bildschirme), Live-Chips, Entzerrung. Konstanten in `CaptureTuning` (am Gerät justierbar) |
| FeldParser | Steuertabellen-Kombinatorik (auch über Satz-Token gesplittete Zeilen), Beleg-Nr.-Kette, Bewirtungssignal; Kontierung 6640 etc. |
| Store | Persistenz als JSON (Application Support), Upload-Queue, Audit-Nachladen, Bewirtungsangaben, Löschen |
| AblageService | Upload (Multipart, Server-Dateiname aus Antwort = Review-Schlüssel), Verbindungstest (txt-Ablehnung: 400=Token ok, 401=falsch — leerer POST gibt 422 VOR der Auth!), Review-Abruf, Chat (SSE + Fallback), Keychain-PAT |
| ListeView/DetailView | grüner Haken, Zweitprüfungs-✓-Abgleich, DATEV-Boxen, Aufräumen-Einstieg |
| AufraeumenView | Wischstapel: rechts=buchen, links=später, Bewirtungs-Intercept, Abschluss mit Tagessumme |
| FragenTab | Chat, Streaming, Beispielfragen |
| EinstellungenView | Server-URL (Default `https://babu.0711.io`), PAT→Keychain, Toggle (Opt-in!), Verbindungstest |

### Server H200V (`ssh h200v`, Nutzer christoph.bertsch) — Code-Kopien in `server/belegreview/`
| pm2-Prozess | Was |
|---|---|
| `babu-eingang` | :7843, POST /ablage → Commit `aufnahme:` in babu.git via Gateway :7808 (**Parallel-Session — nicht anfassen**, gehört zu ~/gitchain-eingang) |
| `babu-web` | :7844 FastAPI: Upload-Webseite, GET /review/<stamm> (whoami-Auth, Suffix-Match, reichert **audit** + **buchungssatz** an), POST /chat (Gemma 4, SSE bei `"stream":true`) |
| `belegreview` | Watcher (Takt 15 s): neue Belege → PaddleOCR PP-OCRv5 `german` **CPU** (GPUs sind von vLLM belegt!) → Felder → embeddinggemma (:11436) Semantik gegen babu-SKR04-Katalog + Embedding-Datei → Gemma 4 (:11435) liest das Bild inkl. Buchungstext → `review:`-Commit. Venv: `~/paddle-ocr-env` |
| `babu-tunnel` | Cloudflare-Tunnel `babu-0711` → **babu.0711.io** (expliziter CNAME sticht \*.0711.io-Wildcard). Ingress: /ablage,/health→7843, Rest→7844 |

**⚠️ Nichts davon ist reboot-fest** (pm2 bewusst ohne `save`, Parallel-Session-Regel).
Neustart-Befehle: `server/belegreview/README.md`. `pm2 save` nachholen, sobald
die Parallel-Session ruht (vorher `~/.pm2/dump.pm2` sichern).

### Belegbox (GitChain)
`~/inspektor-store/inspektor/ws-christoph0711.io/babu.git` — Commits
`aufnahme: <datei>` (Autor = Hochladender) und `review: <datei>` (Autor
belegreview). Unter `review/`: `<stamm>.json`, `.md`, `.embedding.json`
(embeddinggemma, 768-dim — Ähnlichkeits-Historie ab dem zweiten Beleg).
**Nie in der Arbeitskopie des laufenden Watchers committen** (`~/belegreview/babu`
— sein reset --hard frisst lokale Commits): Watcher stoppen oder eigenen Clone.

## 3. Zugänge

- **Upload-PAT**: `ssh h200v 'cd ~/gitchain-eingang && .venv/bin/python pat_minten.py --zeigen --geraet "<Name>"'`
  — Befehl **laufen lassen**, Code binnen 10 min auf gitchain.de/auth/device
  bestätigen, PAT wird einmalig gezeigt. Kein Formatzwang (gcpat-Präfix wird
  NICHT geprüft — gefixter Bug). Widerruf: gitchain.de/auth/device.
- App speichert den PAT nur in der **Keychain** (pro Gerät/Simulator getrennt!).
- Auth serverseitig: `GET gitchain.de/auth/whoami` + Allowlist `BABU_ERLAUBT`
  (Default christoph0711.io). Push-PAT des Dienstes: `~/gitchain-eingang/.pat_babu`
  (Rotation ohne Neustart; beim Shell-Gebrauch `tr -d '[:space:]'`, sonst 401).
- H200V vom Mac: nur über **OpenVPN** (`ssh h200v`, 192.168.145.10:443).
  Das iPhone nutzt die öffentliche Route babu.0711.io.

## 4. Bauen & Deployen

```bash
# Simulator (UDID iPhone 17 Pro: BB64BA87-9F6E-4EF5-919B-CD37BE9D1C3B)
xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg \
  -destination 'generic/platform=iOS Simulator' build
# iPhone (UDID DE430DAD-59C1-5D52-BBBD-2B8869DDC2C6, Team 8L87Z2GRSG)
xcodebuild ... -destination 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG \
  -allowProvisioningUpdates build
xcrun devicectl device install app --device <UDID> <Pfad>/Beleg.app
xcrun devicectl device process launch --device <UDID> io.0711.beleg
```
Info.plist wird generiert **und** mit `ios/Beleg/Support/Info.plist` gemergt
(ATS-LAN-Ausnahme). Tests: UIKit-freie Logik (AutoCaptureGate, FeldParser,
Modelle) läuft als swiftc-Harness auf macOS — Muster: Gate-Szenarien,
Parser-Fixtures **mit echtem Geräte-OCR-Text** (Fixtures unbedingt behalten:
Steuertabelle spaltenweise UND über Satz-Token gesplittet). Store vom Gerät
ziehen: `devicectl device copy from … appDataContainer io.0711.beleg`.

## 5. Bekannte Fallen

1. Leerer `POST /ablage` → **422 vor der Token-Prüfung** (FastAPI-Validierung).
   Token-Tests immer mit txt-Datei (400 = gültig, 401 = ungültig).
2. `git fetch` ohne Auth funktioniert am Gateway, Push nicht — PAT-Header per
   `GIT_CONFIG_*`, Wert ohne Newline.
3. Beide H200-GPUs sind dauerhaft voll (vLLM) — PaddleOCR läuft auf CPU (~7 s/Beleg, reicht).
4. PaddleOCR 3.7: nur `lang="german"` + `ocr_version="PP-OCRv5"` existiert.
5. Simulator-Keychain ≠ iPhone-Keychain; Mac-Clipboard einfügbar mit ⌘V.
6. `route dns` von cloudflared nutzte die falsche Tunnel-ID → immer mit
   expliziter ID + `--overwrite-dns` arbeiten.
7. Alte zustand.json müssen laden: neue Beleg-/Zustand-Felder **immer optional**.

## 6. Offene Punkte (Reihenfolge = Empfehlung)

1. **EXTF-v13-Writer** (Bauplan Phase 5): importierbar, CP1252/CRLF, Golden-File-
   Tests gegen echte DATEV-Instanz; Mehrsatz-Aufteilung (7 %+19 % in einer
   Buchung — aktuell vereinfacht ein Satz). Der Export-Tab nutzt noch die Vorschau.
2. **Demo-Leichen auf dem iPhone löschen** (Wischgeste): v. a. den bestätigten
   85,40-Weingärtle — sonst doppelt im nächsten Stapel!
3. `CaptureTuning` am Gerät justieren (False-Positive-Suite aus dem Plan).
4. Watcher: PDF/HEIC-Reviews; Bewirtungsangaben aus der App in die Belegbox
   zurückschreiben; Semantik-Konfidenz kalibrieren (Cosine ≠ Wahrscheinlichkeit).
5. pm2 save + Reboot-Test H200V; optional Cloudflare Access vor babu.0711.io.
6. Design: Claude-Design-Systemprojekt existiert („Beleg — Unlimited-OCR Design
   System" + Salon-Brief); generierte Screens wurden verworfen — **native
   Umsetzung ist der gesetzte Weg**, Design-Referenz bleibt `design/unlimited-ocr/`.

## 7. Dokumente

- `docs/build-plan.md` — Gesamtplan (Phasen, Architektur)
- `docs/superpowers/specs/2026-08-12-belegreview-upload-design.md` — Belegbox-Spec + Nachtrag öffentliche Route
- `docs/superpowers/plans/2026-08-12-belegreview-upload.md` — Umsetzungsplan Stufe 1a
- `server/belegreview/README.md` — Serverbetrieb + Reboot
- `ios/README.md` — App-Struktur
