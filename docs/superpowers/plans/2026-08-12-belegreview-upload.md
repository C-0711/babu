# BelegReview Stufe 1a — App-Upload: Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Die Beleg-App lädt gesiegelte Belege nativ in die GitChain-Ablage
(`POST http://192.168.145.10:7843/ablage`, Bearer-PAT) hoch — Opt-in, Keychain,
Offline-Queue, Status im UI.

**Architecture:** Neuer `AblageService` (Multipart-Upload + Keychain) wird vom
`AppStore` orchestriert (Queue über optionale `Beleg`-Felder, Retry bei
Foreground); Einstellungen-Screen konfiguriert URL/PAT/Toggle; ATS-Ausnahme
über gemergtes Info.plist. Spec: `docs/superpowers/specs/2026-08-12-belegreview-upload-design.md`.

**Tech Stack:** Swift/SwiftUI, URLSession (async), Security.framework
(Keychain), XcodeGen/pbxproj (INFOPLIST_FILE-Merge). Tests: swiftc-Harness auf
macOS (wie parser-tests), Gerätetest per devicectl + SSH-Nachweis in babu.git.

## Global Constraints

- iOS 17, keine Fremd-Dependencies, deutsche UI-Texte ohne Sie-Form.
- Default = Opt-out: ohne `ablageAktiv` + PAT verhält sich die App exakt wie bisher.
- PAT nur in der Keychain (`io.0711.beleg.ablage`), nie in zustand.json/Logs.
- Bestehende `zustand.json` (ohne neue Felder) muss weiter dekodieren → alle
  neuen Codable-Felder optional.
- H200V-Seite (Gateway, pm2, Watcher) wird NICHT angefasst.

---

### Task 1: Modell + Dateiname (testgetrieben)

**Files:**
- Modify: `ios/Beleg/Beleg/Models.swift` (Beleg + AblageStatus + ablageDateiname())
- Test: Scratchpad-Harness `ablage-tests/main.swift` (kompiliert Models.swift)

**Interfaces (Produces):**
```swift
enum AblageStatus: String, Codable { case ausstehend, uebertragen, fehlgeschlagen }
// Beleg: var ablageStatus: AblageStatus?; var ablageDateiname: String?; var ablageZeit: Date?
func ablageDateiname(fuer beleg: Beleg) -> String  // "beleg_2026-07-21_rotenberger-weingaertle_a1b2c3d4.jpg"
```

- [ ] **Step 1 (RED):** Harness: (a) echten Geräte-Store `geraet-zustand.json`
  (Alt-Format) als `[Beleg]`-tragende Struktur dekodieren → muss laden;
  (b) Roundtrip mit gesetzten Ablage-Feldern; (c) `ablageDateiname` slugt
  Umlaute/Sonderzeichen (`"WEINGÄRTE" → "weingaerte"`), Datum `dd.MM.yyyy → yyyy-MM-dd`,
  endet auf 8-hex + `.jpg`. Laufen lassen → (a) darf schon grün sein
  (Regression), (b)/(c) FAIL (Symbole fehlen).
- [ ] **Step 2 (GREEN):** Felder + Funktion implementieren; Harness grün.
- [ ] **Step 3:** Commit.

### Task 2: AblageService + Keychain

**Files:**
- Create: `ios/Beleg/Beleg/AblageService.swift`

**Interfaces (Produces):**
```swift
enum AblageErgebnis: Equatable { case uebertragen, tokenFehler, abgelehnt(Int), nichtErreichbar }
enum KeychainHelfer {
    static func speicherePAT(_ pat: String); static func ladePAT() -> String?; static func loeschePAT()
}
enum AblageService {
    static func lade(bildJpeg: Data, dateiname: String, basis: URL, pat: String) async -> AblageErgebnis
    static func verbindungstest(basis: URL, pat: String) async -> AblageErgebnis
    // verbindungstest: POST /ablage OHNE file → 400 = .uebertragen(„verbunden"), 401 = .tokenFehler
}
```

- [ ] **Step 1:** Implementieren: Multipart-Body (`file`, image/jpeg, CRLF-Boundary),
  `URLRequest` mit `Authorization: Bearer <pat>`, Timeout 15 s; Statuscode-Mapping:
  2xx → `.uebertragen`, 401 → `.tokenFehler`, sonst-4xx/5xx → `.abgelehnt(code)`,
  URLError → `.nichtErreichbar`. Verbindungstest = leerer POST, Mapping:
  400 → `.uebertragen`, 401 → `.tokenFehler`. Keychain via SecItem CRUD.
- [ ] **Step 2:** Harness-Check: Multipart-Body-Bau (Boundary, Content-Disposition,
  Bytes enthalten) als reine Funktion `multipartBody(...) -> (Data, contentType)`
  im Harness prüfen. Simulator-Build grün.
- [ ] **Step 3:** Commit.

### Task 3: Store-Queue + Retry

**Files:**
- Modify: `ios/Beleg/Beleg/Store.swift` (Zustand + ablageURL/ablageAktiv, ablagePlanen/uebertrage/ablageRetry, Aufruf in routen)
- Modify: `ios/Beleg/Beleg/BelegApp.swift` (scenePhase .active → ablageRetry)

**Interfaces (Produces):**
```swift
// AppStore: @Published var ablageURL: String (Default "http://192.168.145.10:7843")
// @Published var ablageAktiv: Bool (Default false) — beide persistiert (Zustand: optionale Felder!)
// func ablageRetry()  — alle ausstehend/fehlgeschlagen erneut senden
// func uebertrage(_ id: UUID) async — Status-Updates am Beleg
```

- [ ] **Step 1:** Zustand-Struct: `var ablageURL: String?`, `var ablageAktiv: Bool?`
  (optional → Alt-JSON lädt); init mapped mit `?? Default`. `routen()`: bei
  aktiv → `beleg.ablageStatus = .ausstehend` + `Task { await uebertrage(id) }`.
  `uebertrage`: guard aktiv/URL/PAT/bildJpeg → Dateiname aus Task 1 (einmal
  erzeugen, am Beleg merken) → Service → Status setzen. `ablageRetry()` über
  alle offenen. BelegApp: bei `.active` → `store.ablageRetry()`.
- [ ] **Step 2:** Simulator-Build grün; Harness aus Task 1 nochmal (Regression).
- [ ] **Step 3:** Commit.

### Task 4: Einstellungen-UI + Status-Anzeige

**Files:**
- Create: `ios/Beleg/Beleg/EinstellungenView.swift`
- Modify: `ios/Beleg/Beleg/ExportView.swift` (Toolbar-Zahnrad → Sheet)
- Modify: `ios/Beleg/Beleg/ListeView.swift` (DetailView: Provenance-Zeile „Belegbox" + Retry-Button)

**Interfaces (Consumes):** AppStore-Properties aus Task 3, KeychainHelfer/AblageService aus Task 2.

- [ ] **Step 1:** EinstellungenView (Form): TextField Server-URL, SecureField PAT
  (Platzhalter „gespeichert ✓" wenn vorhanden; leeres Feld beim Speichern = PAT
  löschen), Toggle „Belege automatisch in die Belegbox übertragen", Button
  „Verbindung testen" → Ergebnistext („Verbunden ✓" / „Token ungültig" /
  „Server nicht erreichbar (nur im eigenen WLAN)" / „Server meldet <code>").
  Fußnote: LAN-only, kein TLS. ExportView: `.toolbar` Zahnrad → `.sheet`.
- [ ] **Step 2:** DetailView-Provenance: `provZeile("Belegbox", …)` je Status;
  bei fehlgeschlagen/ausstehend Button „Jetzt übertragen".
- [ ] **Step 3:** Simulator-Build grün, Commit.

### Task 5: ATS/Info.plist + Projekt

**Files:**
- Create: `ios/Beleg/Support/Info.plist` (NSAppTransportSecurity→NSAllowsLocalNetworking, NSLocalNetworkUsageDescription)
- Modify: `ios/Beleg/project.yml` (+`INFOPLIST_FILE: Support/Info.plist`)
- Modify: `ios/Beleg/Beleg.xcodeproj/project.pbxproj` (beide buildSettings-Blöcke, Zeilen ~198/226: `INFOPLIST_FILE = Support/Info.plist;`)

- [ ] **Step 1:** Dateien schreiben (Support/ liegt AUSSERHALB des synchronisierten
  Beleg/-Ordners → kein Doppel-Resource-Konflikt). GENERATE_INFOPLIST_FILE bleibt
  YES (Xcode mergt; Datei-Keys gewinnen).
- [ ] **Step 2:** Simulator-Build grün; generiertes Info.plist im Produkt prüfen
  (`plutil -p …/Beleg.app/Info.plist | grep -A2 Transport`).
- [ ] **Step 3:** Commit.

### Task 6: Ende-zu-Ende-Verifikation

- [ ] **Step 1:** Reachability-Smoke vom Mac: `curl -X POST :7843/ablage` ohne
  Token → 401 (Server da, Auth aktiv). KEIN Test mit echtem PAT vom Mac.
- [ ] **Step 2:** Device-Build signiert + `devicectl install/launch`.
- [ ] **Step 3:** Nutzer: PAT in Einstellungen eintragen (aus `--zeigen`-Lauf),
  Verbindungstest → „Verbunden ✓", Beleg scannen.
- [ ] **Step 4:** Nachweis per SSH: `git log --oneline | head` +
  `git ls-tree -r --name-only HEAD | tail` in
  `~/inspektor-store/inspektor/ws-christoph0711.io/babu.git` → neuer Commit
  `aufnahme: beleg_…jpg`.
- [ ] **Step 5:** Flugmodus-Test (Nutzer): offline scannen → „ausstehend" →
  WLAN an, App in Vordergrund → Commit da, Status ✓.
- [ ] **Step 6:** Commit + Push (PR #8 aktualisiert sich).
