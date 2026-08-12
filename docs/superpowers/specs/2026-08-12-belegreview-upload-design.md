# BelegReview Stufe 1a — App-Upload in die GitChain-Belegbox

Datum: 2026-08-12 · Status: entworfen, vom Nutzer freigegeben (Reihenfolge: App-Upload zuerst)

## Kontext

Die Beleg-App (iOS, bisher 100 % on-device) soll Belege an **BelegReview** in
Unlimited-OCR übergeben: Server-Verifikation samt steuerlicher Einschätzung
(Dual-Lane aus `docs/build-plan.md`), und die Belege sollen immer in der
Cloud-Belegbox aktuell sein. Der Aufnahme-Kanal existiert bereits (Parallel-Session):

- **GitChain-Ablage auf der H200V**: `POST http://192.168.145.10:7843/ablage`,
  Multipart-Feld `file`, Header `Authorization: Bearer <PAT>`.
- Jeder Upload wird ein Commit `aufnahme: <name>` im Container
  `ws-christoph0711.io/babu.git` unter `docs/JJJJ-MM/JJJJMMTT-HHMMSS-<hex>-<name>`;
  Autor `christoph0711.io <aufnahme@gitchain.local>`.
- Abwehr verifiziert: ohne Token 401, Fake-Token 401, txt-Datei 400 (nur Bilder/PDF).
- **Grenzen v1 (bewusst geerbt):** LAN-only, HTTP ohne TLS; Dienst nicht
  reboot-fest (pm2 save absichtlich weggelassen). Gateway/pm2 werden hier NICHT angefasst.

Gesamtbild (Stufen): **1a App-Upload (dieses Dokument)** → 1b BelegReview-Watcher
auf der H200V (PaddleOCR aus `~/OCR` + `doc_classify` + ctax_belegbox-Mapping,
Review-Commit zurück ins Repo) → 2 Rückkanal in die App (Reconciliation
Gerät ↔ Server + steuerliche Einschätzung im Provenance-Panel).

## Ziel Stufe 1a

Nach dem Siegeln überträgt die App das entzerrte Beleg-JPEG selbst in die
Ablage — nativ statt Kurzbefehl, mit Offline-Queue und sichtbarem Status.
**Opt-in:** ohne konfigurierten Server + PAT bleibt die App vollständig
on-device (bisheriges Verhalten, unverändert).

## Komponenten

### 1. `AblageService.swift` (neu)
- Baut den Multipart-POST (`file` = JPEG, Dateiname
  `beleg_<datum>_<lieferant-slug>_<uuid8>.jpg` — der Server prefixt ohnehin
  Zeitstempel + Hex).
- `URLSession` mit kurzem Timeout (LAN); Ergebnis: `.uebertragen` (2xx),
  `.tokenFehler` (401), `.abgelehnt` (4xx), `.nichtErreichbar` (Netzfehler).
- **Verbindungstest ohne Commit:** Mini-`verbindungstest.txt` senden — txt
  wird vom Server IMMER abgelehnt: gültiger Token ⇒ 400 (Dateityp), falscher
  Token ⇒ 401, kein Netz ⇒ Fehler. (Empirisch geklärt: ein leerer POST liefert
  422 VOR der Token-Prüfung und taugt daher nicht als Token-Test.)

### 2. Keychain-Ablage (`KeychainHelfer` in AblageService.swift)
- PAT ausschließlich in der iOS-Keychain (`kSecClassGenericPassword`,
  Service `io.0711.beleg.ablage`), nie in `zustand.json`, nie im Log.
- Der Nutzer trägt den PAT selbst im Einstellungen-Screen ein
  (aus dem `--zeigen`-Lauf auf dem Server).

### 3. AppStore-Erweiterung (Upload-Queue)
- `Beleg` bekommt optionale Felder: `ablageStatus` (`ausstehend | uebertragen |
  fehlgeschlagen`), `ablageDateiname`, `ablageZeit` — **optional**, damit
  bestehende `zustand.json` weiter dekodiert.
- Einstellungen im Store (persistiert): `ablageURL` (Default
  `http://192.168.145.10:7843`), `ablageAktiv` (Default **aus**).
- Ablauf: `routen(...)` markiert bei `ablageAktiv` den Beleg `ausstehend` und
  stößt den Upload an. Retry: beim App-Start und bei Rückkehr in den
  Vordergrund werden alle `ausstehend`/`fehlgeschlagen` erneut versucht;
  zusätzlich manueller Button im Detail.

### 4. UI
- **Einstellungen-Screen** (neu, erreichbar aus dem Export-Tab über
  Zahnrad-Symbol): Server-URL, PAT (SecureField → Keychain), Toggle
  „Belege automatisch in die Belegbox übertragen", Button „Verbindung testen"
  mit Klartext-Ergebnis. Hinweis-Text: LAN-only, kein TLS — Übertragung nur im
  eigenen Netz.
- **Provenance/Detail:** Zeile „Belegbox: übertragen ✓ <zeit>" /
  „Übertragung ausstehend" / „fehlgeschlagen — erneut versuchen".
- **Ergebnis-Karte:** kleines Status-Badge (analog BadgeView).

## Sicherheit & Datenschutz
- Opt-in; Default bleibt on-device. PAT nur Keychain. Kein Logging des Tokens.
- HTTP im LAN: iOS-ATS via `NSAllowsLocalNetworking` (Info.plist-Ergänzung);
  dazu `NSLocalNetworkUsageDescription` (iOS fragt beim ersten LAN-Zugriff).
- Projekt: kleine Info.plist-Datei zusätzlich zum generierten Plist
  (`GENERATE_INFOPLIST_FILE=YES` + `INFOPLIST_FILE` mergen), in project.yml
  und pbxproj nachgezogen.

## Verifikation (Ende-zu-Ende messbar)
1. Simulator: Build grün; ohne Konfiguration verhält sich die App exakt wie bisher.
2. Verbindungstest vom Gerät: falscher PAT → „Token ungültig", richtiger → „Verbunden".
3. Echter Beleg vom iPhone scannen → per SSH prüfen: neuer Commit
   `aufnahme: beleg_…jpg` in `babu.git` (git log + ls-tree).
4. Flugmodus-Test: scannen offline → Status „ausstehend" → WLAN an →
   Foreground-Retry überträgt → Commit da, Status ✓.
5. Regression: alte `zustand.json` (ohne neue Felder) lädt fehlerfrei.

## Explizit NICHT in Stufe 1a
Watcher/Review-Verarbeitung (1b), Rückkanal in die App (2), TLS/öffentliche
Route (Gateway v2), pm2-Persistenz auf der H200V, Mehrseitigkeit/PDF-Upload.
