# Apple-Freigabe, iPad/Duo, Kaufweg, Messung — Umsetzungsplan (Build 15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 15 besteht Apples Prüfung (2.1(a) Chat-Anhänge auf dem iPad, 2.1(b) Kaufweg), babu wird Universal-App mit Arbeitsplatz-Layout auf iPad und iPhone Duo, der Kaufweg ist an jeder Stelle robust, und die Paywall wird serverseitig gemessen.

**Architecture:** Die App bleibt ein Ordner mit zwei Zielen; jede breite Variante ist ein zusätzlicher Zweig hinter `horizontalSizeClass == .regular`, nie ein Umbau des iPhone-Pfads. Der Kaufweg trennt den Menü-Schalter (lokaler `@State` in `PlatzView`) vom Wurzel-Schalter (`store.zeigePlatz`) und lädt Preise mit sichtbarem Zustand. Der Server bekommt ein kleines Kern-Modul `kern_platz.py` für Ereignisse und den Trichter.

**Tech Stack:** SwiftUI (Deployment Target iOS 17, Xcode 26.3, Ziel Xcode 27.1), StoreKit 2, FastAPI + Postgres/SQLite (`db.py`-Dialekt), pytest, `ios/Tests/run.sh`-Harnesse (swiftc, UIKit-frei), App Store Connect API (`werkzeuge/asc_*.py`).

**Spec:** `docs/superpowers/specs/2026-10-24-apple-freigabe-ipad-kaufweg-design.md`

## Global Constraints

- Zwei Ziele aus einem Ordner: Unterschied nur in `ios/Beleg/Beleg/Ausbaustufe.swift` (Flag `BABU_PRO`); jeder neue Reiter steht dort und in `ios/Tests/zuschnitt/main.swift`.
- Neue Felder in `Store.Zustand` sind optional (`var x: T?`), alte `zustand.json` müssen laden.
- UI-Sprachregel: kein Technik-Vokabular in Nutzertexten (kein StoreKit, Sandbox, Server, Token).
- iPhone (compact) ändert sich nirgends; am Chat auf dem iPhone ändert sich nichts (Auftraggeber 24.10.).
- Größenklasse entscheidet, nie das Gerätemodell; `UIScreen.main.bounds` wird nirgends benutzt.
- Server: jede Schemaänderung zweimal (inline `schema()` + `migrations/0020_platz_ereignis.sql`); neue Tabelle mit `mandant_id` in `kern_konto.NACH_MANDANT`; neue Route hinter `_box_wache`.
- Preise/Stufen/Ebenen bleiben: `paket.STUFEN`, `Support/babu.storekit`, `tests/test_apple_produkte.py` unverändert.
- An Apple nur Statuswerte, nie „no storefront restrictions"; Einreichen nur nach OK des Auftraggebers.
- Commits auf Deutsch, Suite vor dem Deploy, kein Force-Push, kein `git stash`.
- Messwerte (Logs, Screenshots der Nachstellung) unter `~/.beleglex/messungen/20261024-build15/`.

## Review Focus

1. **Kaufseite ohne Netz / ohne Produkte:** „Platz buchen" darf nie in „nicht zu haben" enden; es gibt einen sichtbaren Zustand mit „Nochmal" — Test `preisLadung` (Task 3) + Nachstellung mit Flugmodus (Task 3, Schritt 9).
2. **Mitarbeiterin oder Kanzlei auf breit:** `reiter(fuer: rechte, breit: true)` darf nur dann zusammenlegen, wenn Dokumente UND Fragen da sind — Harness `zuschnitt` (Task 5).
3. **Portal-Konto meldet ein Platz-Ereignis:** Route antwortet 409 mit Weg, nie 500, nichts wird gespeichert — Test (Task 9).
4. **Alter Zustand lädt:** Build 15 über Build 14 installiert, `zustand-<hash>.json` ohne `stufenZuletzt`/`breitErzwingen` lädt und zeigt die Belege — Nachstellung (Task 4, Schritt 6).
5. **Drehen des iPad bei offenem Kaufblatt / offenem Anhang-Blatt:** kein Absturz, kein hängender Schalter — Nachstellung (Task 8, Schritt 8).

---

### Task 1: Simulatoren und Negativkontrolle (vor jeder Änderung)

**Files:**
- Create: `~/.beleglex/messungen/20261024-build15/LIESMICH.txt`, `…/ipad-vorher.log`

**Interfaces:**
- Produces: die UDID des iPad-Simulators `babu-ipad` (in `LIESMICH.txt`), die Log-Zeilen `Attempt to present … while a presentation is in progress` als Beleg des Fehlers vor der Änderung.

- [ ] **Step 1: Prüfen, welche Laufzeiten da sind**

Run: `xcrun simctl list runtimes | grep iOS; xcrun simctl list devicetypes | grep -E "iPad Air 11-inch \(M3\)|iPhone Duo"`
Expected: iOS 26.3 vorhanden; „iPhone Duo" nur, wenn Xcode 27.1 installiert ist. Beides in `LIESMICH.txt` notieren (Datum, Xcode-Version aus `xcodebuild -version`).

- [ ] **Step 2: iPad-Simulator anlegen und starten**

Run: `U=$(xcrun simctl create babu-ipad "iPad Air 11-inch (M3)"); xcrun simctl boot $U; xcrun simctl status_bar $U override --time 9:41 --wifiBars 3 --cellularBars 4 --batteryLevel 100`
Expected: UDID ausgegeben; in `LIESMICH.txt` eintragen. Gibt es Xcode 27.1, zusätzlich `xcrun simctl create babu-duo "iPhone Duo"`.

- [ ] **Step 3: Build 14 (Stand `63bd4f2`, unverändert) auf das iPad bauen und starten**

Run: `cd ~/babu && xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination "platform=iOS Simulator,id=$U" -derivedDataPath /tmp/bsim-ipad build -quiet && xcrun simctl install $U /tmp/bsim-ipad/Build/Products/Debug-iphonesimulator/Beleg.app && xcrun simctl launch $U io.0711.beleg`
Expected: App startet im iPhone-Kompatibilitätsfenster auf dem iPad.

- [ ] **Step 4: Beide Fehler nachstellen und das Log sichern**

Mit dem Simulator-Panel: „Los geht's" (nutzt den Schlüssel aus der Keychain, sonst entsteht ein Test-Betrieb — in `LIESMICH.txt` notieren), ☰ → „Deine Ablage" → „Platz buchen"; danach Reiter „Fragen" → Büroklammer → jede der vier Optionen.
Run: `xcrun simctl spawn $U log show --last 10m --predicate 'process == "Beleg" AND category == "Presentation"' --style compact > ~/.beleglex/messungen/20261024-build15/ipad-vorher.log; grep -c "Attempt to present" ~/.beleglex/messungen/20261024-build15/ipad-vorher.log`
Expected: Zahl > 0 für den Kaufweg; für die Anhang-Optionen festhalten, welche nichts öffnen (Screenshot je Option). Ist der Anhang-Fehler auf iOS 26.3 NICHT nachstellbar, in `LIESMICH.txt` schreiben: „nur auf iPadOS 27 geprüft von Apple — Haltepunkt: Xcode 27.1 nötig" und mit Task 2 weitermachen.

- [ ] **Step 5: Commit der Messnotiz-Referenz**

Nichts im Repo zu committen; `LIESMICH.txt` enthält Datum, Xcode, UDIDs, Befund je Fehler.

---

### Task 2: Kaufweg aus dem Menü — eigener Schalter, kein hängender Zustand

**Files:**
- Modify: `ios/Beleg/Beleg/PlatzView.swift:25,47,126-127`
- Modify: `ios/Beleg/Beleg/BelegApp.swift:86-88`
- Modify: `ios/Beleg/Beleg/Store.swift:592-611`

**Interfaces:**
- Consumes: `PlatzSheet()` (unverändert), `store.zeigePlatz`.
- Produces: `PlatzView` besitzt `@State private var zeigePlatzHier = false`; Wurzel-`.sheet` in `BelegApp` hat `onDismiss: { store.zeigePlatz = false }`; `AppStore.angebotNachErstemBelegPruefen()` prüft nicht mehr `!zeigePlatz`, sondern setzt es.

- [ ] **Step 1: `PlatzView` auf lokalen Schalter umstellen**

In `PlatzView.swift`: `@State private var zeigePlatzHier = false`; Zeile 47 wird `.sheet(isPresented: $zeigePlatzHier) { PlatzSheet(quelle: .menue) }` (Parameter `quelle` kommt in Task 10 — bis dahin `PlatzSheet()`); Zeile 127 wird `zeigePlatzHier = true`.

- [ ] **Step 2: Wurzel-Schalter beim Schließen zurücksetzen**

In `BelegApp.swift:86`: `.sheet(isPresented: $store.zeigePlatz, onDismiss: { store.zeigePlatz = false }) { PlatzSheet() }`.

- [ ] **Step 3: Angebot darf nicht an einem alten Schalter hängen**

In `Store.swift:596`: `!zeigePlatz` aus dem `guard` entfernen; `angebotNachErstemBelegPruefen` setzt `zeigePlatz = true` nur, wenn das Angebot laut `PlatzStand.angebotNachErstemBeleg` fällig ist. `platzIstVoll()` (Zeile 610) ebenso: `guard` auf `!zeigePlatz` entfernen.

- [ ] **Step 4: Beide Ziele bauen**

Run: `cd ~/babu && for s in Beleg BelegPro; do xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme $s -destination "platform=iOS Simulator,id=$U" -derivedDataPath /tmp/bsim-ipad build -quiet || exit 1; done; echo ok`
Expected: `ok`.

- [ ] **Step 5: Nachstellen wie Task 1, Schritt 4 (Kaufweg)**

Run: `xcrun simctl install $U /tmp/bsim-ipad/Build/Products/Debug-iphonesimulator/Beleg.app; xcrun simctl launch $U io.0711.beleg` — dann ☰ → Deine Ablage → Platz buchen (iPad), dasselbe auf dem iPhone-16e-Simulator.
Expected: Kaufblatt erscheint auf beiden; `log show … category == "Presentation"` seit dem Start ohne `Attempt to present`. Log als `ipad-nachher-kaufweg.log` sichern.

- [ ] **Step 6: Commit**

```bash
git add ios/Beleg/Beleg/PlatzView.swift ios/Beleg/Beleg/BelegApp.swift ios/Beleg/Beleg/Store.swift
git commit -m "Kaufweg aus dem Menü: eigenes Blatt in Deine Ablage, Wurzel-Schalter setzt sich zurück"
```

---

### Task 3: Preise mit sichtbarem Zustand, Stufen gemerkt, „Nochmal"

**Files:**
- Modify: `ios/Beleg/Beleg/Platz.swift` (neu: `enum PreisLadung`, `PlatzStand.preisLadung(...)`)
- Modify: `ios/Beleg/Beleg/Kasse.swift:34-45`
- Modify: `ios/Beleg/Beleg/Store.swift:72,262-286,407`
- Modify: `ios/Beleg/Beleg/PlatzSheet.swift:56-62,145-170`
- Create: `ios/Tests/platz/main.swift`
- Modify: `ios/Tests/run.sh` (neuer Harness-Block vor „Zuschnitt")

**Interfaces:**
- Produces: `enum PreisLadung: Equatable { case laedt, geladen, fehler }` in `Platz.swift`; `static func preisLadung(gefunden: Int, erwartet: Int, versucheUebrig: Int) -> PreisLadung` auf `PlatzStand`; `Kasse.ladung: PreisLadung` (`@Published private(set)`), `Kasse.preiseLaden(_:)` mit bis zu 3 Versuchen (Pause 1 s, 2 s); `AppStore.stufenZuletzt: [PlatzStufe]` persistiert (Zustand-Feld `stufenZuletzt: [PlatzStufe]?`), `AppStore.stufen` fällt bei leerer Serverantwort auf `stufenZuletzt` zurück; `PlatzSheet` zeigt drei Zustände und einen Knopf „Nochmal".

- [ ] **Step 1: Harness-Test schreiben**

`ios/Tests/platz/main.swift` nach dem Muster von `ios/Tests/zuschnitt/main.swift` (`pruefe(_:_:)`, `exit(fehler == 0 ? 0 : 1)`):

```swift
pruefe("alle gefunden → geladen", PlatzStand.preisLadung(gefunden: 3, erwartet: 3, versucheUebrig: 2) == .geladen)
pruefe("keins gefunden, Versuche übrig → lädt", PlatzStand.preisLadung(gefunden: 0, erwartet: 3, versucheUebrig: 2) == .laedt)
pruefe("keins gefunden, keine Versuche → Fehler", PlatzStand.preisLadung(gefunden: 0, erwartet: 3, versucheUebrig: 0) == .fehler)
pruefe("eins fehlt → Fehler, nie halb kaufen", PlatzStand.preisLadung(gefunden: 2, erwartet: 3, versucheUebrig: 0) == .fehler)
pruefe("nichts erwartet (Stufen fehlen) → lädt", PlatzStand.preisLadung(gefunden: 0, erwartet: 0, versucheUebrig: 3) == .laedt)
pruefe("Angebot nach erstem Beleg wie bisher", PlatzStand.angebotNachErstemBeleg(PlatzStand.beispielOhneStufe, belegeAufTelefon: 1, schonGezeigt: false, inhaberin: true))
```

`PlatzStand.beispielOhneStufe` ist ein statischer Testwert in `Platz.swift` (stufe nil, voll false) — anlegen, falls es keinen Initialisierer ohne Server gibt.

- [ ] **Step 2: Harness in `run.sh` eintragen und laufen lassen (rot)**

In `ios/Tests/run.sh` vor dem Zuschnitt-Block:
```sh
echo "— Platz-Harness —"
swiftc -o "$ZIEL/platz" ../Beleg/Beleg/Platz.swift platz/main.swift
"$ZIEL/platz"
```
Run: `ios/Tests/run.sh 2>&1 | tail -20`
Expected: Übersetzungsfehler „preisLadung" unbekannt.

- [ ] **Step 3: `PreisLadung` und `preisLadung` in `Platz.swift` implementieren**

Regel: `erwartet > 0 && gefunden == erwartet` → `.geladen`; sonst `versucheUebrig > 0` → `.laedt`; sonst `.fehler`.

- [ ] **Step 4: Harness grün**

Run: `ios/Tests/run.sh 2>&1 | grep -A8 "Platz-Harness"`
Expected: sechs ✓, kein ✗.

- [ ] **Step 5: `Kasse.preiseLaden` mit Zustand und Versuchen**

`@Published private(set) var ladung: PreisLadung = .laedt`; Schleife über 3 Versuche: `Product.products(for:)`, danach `ladung = PlatzStand.preisLadung(gefunden: geholt.count, erwartet: stufen.count, versucheUebrig: 3 - versuch)`; bei `.laedt` `try? await Task.sleep(for: .seconds(versuch))`; bei `.geladen` abbrechen. Produkt-IDs und Fehlertext per `print("[kasse] …")` (Konsole, kein Nutzertext). `kaufen` bleibt.

- [ ] **Step 6: Stufen merken**

`Store.swift`: `@Published var stufenZuletzt: [PlatzStufe] = [] { didSet { speichern() } }`; Zustand-Feld `var stufenZuletzt: [PlatzStufe]?` (optional, Kommentar „Neu ab 24.10.2026"), in `init` und `zustandWechseln` laden; in `kontoNachfragen` (Zeile 421): wenn `antwort.stufen` leer und `stufenZuletzt` nicht leer → `stufen = stufenZuletzt`, sonst `stufenZuletzt = stufen`.

- [ ] **Step 7: `PlatzSheet` zeigt die Zustände**

Unter `auswahl` (Zeile 145–170): bei `kasse.ladung == .laedt` Text „Preise werden geladen …" mit `ProgressView`; bei `.fehler` Text „Preise gerade nicht erreichbar." und Knopf „Nochmal" → `Task { await store.kontoNachfragen(); await kasse.preiseLaden(store.stufen) }`; „Platz buchen" nur bei `.geladen` aktiv (`.disabled(kasse.ladung != .geladen)`). Das bisherige „Die Stufen laden gerade …" (Zeile 149) entfällt zugunsten derselben Zustände.

- [ ] **Step 8: Beide Ziele bauen, Harness grün**

Run: wie Task 2, Schritt 4; dazu `ios/Tests/run.sh 2>&1 | grep -c "✗"` → `0`.

- [ ] **Step 9: Nachstellen ohne Netz**

iPad-Simulator: Netz aus (`xcrun simctl … ` kennt keinen Flugmodus — auf dem Mac WLAN kurz trennen), App starten, Kaufseite über Menü öffnen.
Expected: „Preise werden geladen …", nach ~3 s „Preise gerade nicht erreichbar." mit „Nochmal"; WLAN an, „Nochmal" → drei Stufen mit Preisen; „Platz buchen" vorher ausgegraut. Screenshots nach `~/.beleglex/messungen/20261024-build15/`.

- [ ] **Step 10: Commit**

```bash
git add ios/Beleg/Beleg/Platz.swift ios/Beleg/Beleg/Kasse.swift ios/Beleg/Beleg/Store.swift ios/Beleg/Beleg/PlatzSheet.swift ios/Tests/platz/main.swift ios/Tests/run.sh
git commit -m "Kaufseite: Preise mit sichtbarem Zustand und Nochmal, Stufen bleiben gemerkt"
```

---

### Task 4: Universal-App und Testphase-Schalter „Breites Layout erzwingen"

**Files:**
- Modify: `ios/Beleg/Beleg.xcodeproj/project.pbxproj:266,297,329,361` (`TARGETED_DEVICE_FAMILY = "1,2";`)
- Modify: `ios/Beleg/Beleg/Store.swift` (neu `breitErzwingen`, Zustand-Feld optional)
- Modify: `ios/Beleg/Beleg/EinstellungenView.swift:294-300`
- Modify: `ios/Beleg/Beleg/BelegApp.swift` (RootView)

**Interfaces:**
- Produces: `AppStore.breitErzwingen: Bool` (persistiert, Zustand-Feld `breitErzwingen: Bool?`); `RootView` setzt `.environment(\.horizontalSizeClass, .regular)` auf `MainTabs()`, wenn `store.breitErzwingen`; Umgebungsschlüssel bleibt der SwiftUI-eigene.

- [ ] **Step 1: Gerätefamilie in allen vier Konfigurationen auf `"1,2"`**

Run: `grep -c 'TARGETED_DEVICE_FAMILY = "1,2";' ios/Beleg/Beleg.xcodeproj/project.pbxproj`
Expected: `4`.

- [ ] **Step 2: Schalter im Store und in den Einstellungen**

`Store.swift`: `@Published var breitErzwingen = false { didSet { speichern() } }`, Zustand-Feld optional, laden wie `testmodus`. `EinstellungenView.swift` im Block `if store.testmodus` (Zeile 296): `Toggle("Breites Layout erzwingen", isOn: $store.breitErzwingen)`.

- [ ] **Step 3: RootView wendet ihn an**

In `BelegApp.swift` `RootView`: `MainTabs().environment(\.horizontalSizeClass, store.breitErzwingen ? .regular : nil)` — `nil` lässt den Systemwert stehen (SwiftUI nimmt bei `nil` den geerbten Wert; falls der Compiler das nicht annimmt, zwei Zweige mit `if`).

- [ ] **Step 4: Beide Ziele für iPad UND iPhone bauen**

Run: `for s in Beleg BelegPro; do for d in "id=$U" "name=iPhone 16e"; do xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme $s -destination "platform=iOS Simulator,$d" -derivedDataPath /tmp/bsim-ipad build -quiet || exit 1; done; done; echo ok`
Expected: `ok`. Auf dem iPad läuft die App jetzt bildschirmfüllend (noch im iPhone-Layout, das ist in diesem Schritt gewollt).

- [ ] **Step 5: Zuschnitt-Harness unverändert grün**

Run: `ios/Tests/run.sh 2>&1 | grep -c "✗"`
Expected: `0`.

- [ ] **Step 6: Alter Zustand lädt (Review Focus 4)**

Auf dem iPhone-16e-Simulator zuerst Build 14 (`git stash` verboten — Build 14 aus `/tmp/bsim-shots/…/Beleg.app` vom 24.10. oder frisch aus `git worktree add /tmp/b14 63bd4f2`) installieren, Demo-Beleg einlesen, dann Build 15 darüber installieren.
Expected: Belegliste zeigt den Beleg, Einstellungen zeigen „Breites Layout erzwingen" aus.

- [ ] **Step 7: Commit**

```bash
git add ios/Beleg/Beleg.xcodeproj/project.pbxproj ios/Beleg/Beleg/Store.swift ios/Beleg/Beleg/EinstellungenView.swift ios/Beleg/Beleg/BelegApp.swift
git commit -m "babu läuft auf dem iPad: beide Ziele Universal, Testphase-Schalter für das breite Layout"
```

---

### Task 5: Zuschnitt kennt „Arbeitsplatz" (breit = Dokumente + Fragen in einem Reiter)

**Files:**
- Modify: `ios/Beleg/Beleg/Ausbaustufe.swift` (Reiter `.arbeitsplatz`, `reiter(fuer:ambassadorin:breit:)`)
- Modify: `ios/Beleg/Beleg/Store.swift:26-27,1159-1169` (`Tab.arbeitsplatz`)
- Modify: `ios/Tests/zuschnitt/main.swift`

**Interfaces:**
- Produces: `Reiter.arbeitsplatz` (Titel „Arbeitsplatz", Symbol `rectangle.split.2x1`, `nurBreit == true`); `Ausbaustufe.reiter(fuer rechte: Rechte?, ambassadorin: Ambassadorin = .nein, breit: Bool = false) -> [Reiter]`: bei `breit` werden `.dokumente` und `.fragen` durch ein `.arbeitsplatz` an der Stelle von `.dokumente` ersetzt — nur wenn BEIDE in der Liste stehen; `Reiter.arbeitsplatz.tab == .arbeitsplatz`; `Ausbaustufe.reiter` (ohne Argumente) bleibt schmal/voll wie bisher.

- [ ] **Step 1: Harness-Erwartungen schreiben (beide Zweige)**

In `ios/Tests/zuschnitt/main.swift` nach den Reiter-Prüfungen je Zweig:
```swift
print("— Breit (iPad, Duo) —")
let breitErwartet: [Reiter] = Ausbaustufe.voll
    ? [.erfassen, .arbeitsplatz, .termine, .kasse] : [.erfassen, .arbeitsplatz]
pruefe("breit: Dokumente und Fragen werden zum Arbeitsplatz",
       Ausbaustufe.reiter(fuer: nil, breit: true) == breitErwartet)
pruefe("schmal bleibt, was es war", Ausbaustufe.reiter(fuer: nil, breit: false) == Ausbaustufe.reiter)
pruefe("Mitarbeiterin ohne Dokumente bekommt keinen Arbeitsplatz",
       !Ausbaustufe.reiter(fuer: Ausbaustufe.Rechte(belege: true, kasse: false, auslagen: true), breit: true).contains(.arbeitsplatz))
pruefe("Ambassadorin mit Ablage auf breit: Empfehlen bleibt hinten",
       Ausbaustufe.reiter(fuer: nil, ambassadorin: .mitAblage, breit: true).last == .empfehlen)
pruefe("Arbeitsplatz ist nie in der schmalen Liste", !Ausbaustufe.reiter.contains(.arbeitsplatz))
```

- [ ] **Step 2: Harness rot**

Run: `ios/Tests/run.sh 2>&1 | grep -B2 -A12 "Zuschnitt-Harness (babu)"`
Expected: Übersetzungsfehler `arbeitsplatz`/`breit:`.

- [ ] **Step 3: `Reiter.arbeitsplatz` und `breit:` implementieren**

`Reiter`: Fall `arbeitsplatz`; `nurVoll false`, `nurMitarbeit false`, `nurAmbassadorin false`, neu `var nurBreit: Bool { self == .arbeitsplatz }`; `Ausbaustufe.reiter` filtert zusätzlich `!$0.nurBreit`. `reiter(fuer:ambassadorin:breit:)`: Ergebnis der heutigen Logik berechnen, dann bei `breit` und `contains(.dokumente) && contains(.fragen)` → `.fragen` entfernen, `.dokumente` durch `.arbeitsplatz` ersetzen. `Store.Tab` bekommt `arbeitsplatz`, `Reiter.tab` bildet `.arbeitsplatz → .arbeitsplatz` ab.

- [ ] **Step 4: Harness grün (beide Läufe)**

Run: `ios/Tests/run.sh 2>&1 | grep -c "✗"`
Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add ios/Beleg/Beleg/Ausbaustufe.swift ios/Beleg/Beleg/Store.swift ios/Tests/zuschnitt/main.swift
git commit -m "Zuschnitt: auf breit werden Dokumente und Fragen zum Arbeitsplatz"
```

---

### Task 6: Der Arbeitsplatz — links Belege, rechts Chat oder Beleg

**Files:**
- Create: `ios/Beleg/Beleg/ArbeitsplatzView.swift`
- Modify: `ios/Beleg/Beleg/BelegApp.swift:107-160` (MainTabs: `breit`, `inhalt(.arbeitsplatz)`, Tab-Umlenkung)
- Modify: `ios/Beleg/Beleg/ListeView.swift:319-326` (aufgeschlagenen Beleg melden)
- Modify: `ios/Beleg/Beleg/Store.swift` (`aufgeschlagen: UUID?`, nicht persistiert)

**Interfaces:**
- Consumes: `ListeView()`, `FragenTab()`, `BelegGrossView(beleg:)`, `Ausbaustufe.reiter(fuer:ambassadorin:breit:)` (Task 5).
- Produces: `struct ArbeitsplatzView: View` mit `@State private var rechts: RechteSpalte = .fragen` (`enum RechteSpalte { case fragen, beleg }`); `AppStore.aufgeschlagen: UUID?` (`@Published`, nicht persistiert); `MainTabs` liest `@Environment(\.horizontalSizeClass)` und übergibt `breit: sizeClass == .regular`; Tab-Umlenkung: wird `store.tab` auf `.belege` oder `.fragen` gesetzt, während `breit`, wird daraus `.arbeitsplatz`.

- [ ] **Step 1: `ArbeitsplatzView` bauen**

`GeometryReader` → `HStack(spacing: 0)`: links `ListeView()` mit `.frame(width: proxy.size.width * 0.45)`, Trennlinie `Divider()`, rechts `VStack`: `Picker("", selection: $rechts) { Text("Fragen").tag(RechteSpalte.fragen); Text("Beleg").tag(RechteSpalte.beleg) }.pickerStyle(.segmented).padding()` darüber, darunter `switch rechts`: `.fragen → FragenTab()`, `.beleg → if let id = store.aufgeschlagen, let b = store.belege.first(where: { $0.id == id }) { BelegGrossView(beleg: b) } else { Text("Tipp links einen Beleg an.").foregroundStyle(GC.desc) }`. Beide Spalten bekommen `.environmentObject(store)`.

- [ ] **Step 2: Liste meldet den aufgeschlagenen Beleg**

`ListeView.swift:319` im `navigationDestination(for: UUID.self)`: `BelegGrossView(beleg: b).onAppear { store.aufgeschlagen = id }`.

- [ ] **Step 3: `MainTabs` kennt breit**

`@Environment(\.horizontalSizeClass) private var sizeClass`; `reiter` ruft `Ausbaustufe.reiter(fuer: store.rechte, ambassadorin: store.ambassadorin, breit: sizeClass == .regular)`; `inhalt(.arbeitsplatz) → ArbeitsplatzView()`; `.onChange(of: store.tab) { _, neu in if sizeClass == .regular, neu == .belege || neu == .fragen { store.tab = .arbeitsplatz } }`.

- [ ] **Step 4: Bauen und auf dem iPad prüfen**

Run: beide Ziele wie Task 4, Schritt 4; `xcrun simctl install $U …; xcrun simctl launch $U io.0711.beleg`.
Expected: Reiter „Erfassen · Arbeitsplatz" (Pro: „· Termine · Kassenbuch"); links Liste, rechts Chat; Beleg antippen → links der Beleg, Umschalter „Beleg" zeigt ihn rechts groß; Demo-Beleg einlesen → „Zu den Dokumenten" landet im Arbeitsplatz. Drehen hoch/quer ohne Sprung. Screenshots sichern.

- [ ] **Step 5: iPhone unverändert**

iPhone-16e-Simulator: drei Reiter wie vorher, Dokumente und Fragen getrennt.

- [ ] **Step 6: Commit**

```bash
git add ios/Beleg/Beleg/ArbeitsplatzView.swift ios/Beleg/Beleg/BelegApp.swift ios/Beleg/Beleg/ListeView.swift ios/Beleg/Beleg/Store.swift
git commit -m "Arbeitsplatz auf breit: links Belege oder Beleg, rechts Chat oder Beleg"
```

---

### Task 7: Breite Formulare — Erfassen 640 pt, Menü und Kaufblatt in Formulargröße

**Files:**
- Create: `ios/Beleg/Beleg/Breit.swift` (`BreiteSpalte` Modifier, `View.breiteSpalte(max:)`, `View.formblatt()`)
- Modify: `ios/Beleg/Beleg/CaptureTab.swift` (Wurzel-View), `KontoMenu.swift:238`, `BelegApp.swift:86` und `PlatzView.swift:47` (Kaufblatt), `ExportView.swift`, `AbschlussView.swift`, `BetriebsprofilView.swift`, `EinstellungenView.swift` (je Wurzel)

**Interfaces:**
- Produces: `extension View { func breiteSpalte(max: CGFloat = 640) -> some View }` — bei `horizontalSizeClass == .regular` `frame(maxWidth: max).frame(maxWidth: .infinity)`, sonst unverändert; `func formblatt() -> some View` — `if #available(iOS 18, *) { presentationSizing(.form) } else { self }`.

- [ ] **Step 1: `Breit.swift` schreiben**

Zwei Modifier wie in Interfaces; beide lesen `@Environment(\.horizontalSizeClass)`.

- [ ] **Step 2: Anwenden**

`CaptureTab` Wurzel `.breiteSpalte(max: 640)`; `KontoMenuKnopf` Zeile 238: `.sheet(isPresented: $zeigeMenu) { KontoMenuView().formblatt() }`; beide `PlatzSheet`-Präsentationen `.formblatt()`; Export, Monatsabschluss, Betrieb, Einstellungen: `.breiteSpalte()`.

- [ ] **Step 3: Bauen, iPad hoch/quer prüfen, iPhone unverändert**

Expected: Erfassen mittig, Menü und Kaufblatt als Formblatt, Formulare mittig ≤ 640 pt; iPhone pixelgleich (Vergleich in Task 11).

- [ ] **Step 4: Commit**

```bash
git add ios/Beleg/Beleg/Breit.swift ios/Beleg/Beleg/CaptureTab.swift ios/Beleg/Beleg/KontoMenu.swift ios/Beleg/Beleg/BelegApp.swift ios/Beleg/Beleg/PlatzView.swift ios/Beleg/Beleg/ExportView.swift ios/Beleg/Beleg/AbschlussView.swift ios/Beleg/Beleg/BetriebsprofilView.swift ios/Beleg/Beleg/EinstellungenView.swift
git commit -m "Breite Größenklasse: Erfassen mittig, Menü und Kaufblatt als Formblatt"
```

---

### Task 8: Chat-Anhänge auf breit — eigenes Blatt, Picker erst nach dem Schließen

**Files:**
- Create: `ios/Beleg/Beleg/AnhangBlatt.swift`
- Modify: `ios/Beleg/Beleg/FragenTab.swift:17-21,118-134,475-505`

**Interfaces:**
- Produces: `enum AnhangWahl { case briefFoto, briefDatei, vertragFoto, vertragDatei }`; `struct AnhangBlatt: View` mit `let wahl: (AnhangWahl) -> Void` (vier Knöpfe in zwei Abschnitten „Brief vom Amt" / „Vertrag", Texte wie im heutigen `Menu`); in `FragenTab`: `@State private var zeigeAnhang = false`, `@State private var anhangWahl: AnhangWahl?`, `@State private var zeigeBriefFotos = false`, `@State private var zeigeVertragFotos = false`; am Reiter-Wurzelview `.sheet(isPresented: $zeigeAnhang, onDismiss: anhangAusfuehren) { AnhangBlatt { anhangWahl = $0 } }`, `.photosPicker(isPresented: $zeigeBriefFotos, selection: $briefAuswahl, matching: .images)`, `.photosPicker(isPresented: $zeigeVertragFotos, selection: $vertragAuswahl, matching: .images)`; die vorhandenen `.fileImporter` (Zeilen 118, 127) bleiben.

- [ ] **Step 1: `AnhangBlatt` schreiben**

`NavigationStack { List { Section("Brief vom Amt") { Button … }; Section("Vertrag") { … } }.navigationTitle("Anhang") }`, jeder Knopf ruft `wahl(…)` und `dismiss()`.

- [ ] **Step 2: Verzweigung in `eingabeleiste` — genau eine Stelle**

```swift
if sizeClass == .regular {
    Button { zeigeAnhang = true } label: { /* dasselbe Label wie heute */ }.disabled(briefLaeuft)
} else {
    Menu { /* unverändert, Zeilen 477–505 */ } label: { … }
}
```
`@Environment(\.horizontalSizeClass) private var sizeClass` in `FragenTab`. Das `Menu` wird NICHT angefasst (Byte für Byte).

- [ ] **Step 3: `anhangAusfuehren()`**

```swift
private func anhangAusfuehren() {
    guard let w = anhangWahl else { return }
    anhangWahl = nil
    switch w {
    case .briefFoto: zeigeBriefFotos = true
    case .briefDatei: zeigeBriefDateien = true
    case .vertragFoto: zeigeVertragFotos = true
    case .vertragDatei: zeigeVertragDateien = true
    }
}
```
Die `onChange`-Verarbeitung von `briefAuswahl`/`vertragAuswahl` (Zeilen 136–150) bleibt gemeinsam.

- [ ] **Step 4: Bauen, iPad: alle vier Optionen**

Expected: jede Option öffnet Fotos- bzw. Dateiauswahl; `log show … category == "Presentation"` ohne `Attempt to present`. Log als `ipad-nachher-anhang.log` sichern.

- [ ] **Step 5: iPhone 16e: Negativkontrolle**

Expected: Büroklammer öffnet das heutige Menü, alle vier Optionen wie vor der Änderung.

- [ ] **Step 6: Drehen bei offenem Blatt (Review Focus 5)**

iPad: Anhang-Blatt offen → drehen → Option wählen; Kaufblatt offen → drehen → „Erst kostenlos weiter".
Expected: kein Absturz, danach Büroklammer und Kaufweg erneut bedienbar.

- [ ] **Step 7: Commit**

```bash
git add ios/Beleg/Beleg/AnhangBlatt.swift ios/Beleg/Beleg/FragenTab.swift
git commit -m "Chat-Anhänge auf iPad und Duo: eigenes Blatt, Picker erst nach dem Schließen"
```

---

### Task 9: Server — `platz_ereignis` und Trichter in `/api/kpi`

**Files:**
- Create: `server/belegreview/kern_platz.py`
- Create: `server/belegreview/migrations/0020_platz_ereignis.sql`
- Create: `server/belegreview/tests/test_platz_ereignis.py`
- Modify: `server/belegreview/babu_web.py:707,6797-6830,13544` (schema-Aufruf, `platz_trichter`, `kern_platz.setup`)
- Modify: `server/belegreview/kern_konto.py:71-76` (`NACH_MANDANT` + `"platz_ereignis"`)
- Modify: `server/belegreview/tests/test_db_dialekt.py:168,350` (0020 in beiden Listen)

**Interfaces:**
- Consumes: `bw._box_wache(request)`, `bw._aktive_mandant_id()`, `mandanten.mandant_holen(id)`, dieselbe Herkunftsprüfung wie `kern_konto.api_konto_loeschen` (`herkunft == "app"`), `bw._db()`, `db.upsert` nicht nötig (nur INSERT).
- Produces: Tabelle `platz_ereignis (id INTEGER PRIMARY KEY, mandant_id INTEGER NOT NULL, quelle TEXT NOT NULL, aktion TEXT NOT NULL, stufe TEXT, zeit TEXT NOT NULL)` (Postgres: `id BIGINT GENERATED BY DEFAULT AS IDENTITY`); `QUELLEN = ("angebot", "menue", "streifen", "voll")`, `AKTIONEN = ("gesehen", "gekauft", "weiter", "abgebrochen", "wiederhergestellt")`; `POST /api/platz/ereignis` JSON `{"quelle", "aktion", "stufe"?}` → 204; 400 bei unbekannten Werten; 409 `{"fehler": "kein Platz-Modell"}` für Konten ohne App-Betrieb; `kern_platz.trichter(monat: str) -> dict[str, dict[str, int]]` (je Quelle die fünf Aktionen, fehlende 0); `api_kpi` hängt `"platz_trichter": kern_platz.trichter(monat)` an, nur wenn die Rolle des Aufrufers `admin` ist.

- [ ] **Step 1: Tests schreiben**

`tests/test_platz_ereignis.py` mit `welt`, `_anlegen`, `_mit_schluessel` aus `test_geraet_und_apple`:
```python
def test_app_betrieb_meldet_und_zaehlt(welt):
    konto = _anlegen(_client(), name="Salon Test").json()
    c = _mit_schluessel(konto)
    assert c.post("/api/platz/ereignis", json={"quelle": "angebot", "aktion": "gesehen"}).status_code == 204
    assert c.post("/api/platz/ereignis", json={"quelle": "angebot", "aktion": "gekauft", "stufe": "mittel"}).status_code == 204
    monat = dt.date.today().strftime("%Y-%m")
    t = kern_platz.trichter(monat)
    assert t["angebot"]["gesehen"] == 1 and t["angebot"]["gekauft"] == 1 and t["angebot"]["weiter"] == 0

def test_unbekannte_werte_400(welt):
    c = _mit_schluessel(_anlegen(_client()).json())
    assert c.post("/api/platz/ereignis", json={"quelle": "mond", "aktion": "gesehen"}).status_code == 400

def test_portal_konto_409_und_nichts_gespeichert(welt):   # Review Focus 3
    client, bw = ...  # Portal-Konto wie in test_zugriff.py anmelden
    r = client.post("/api/platz/ereignis", json={"quelle": "menue", "aktion": "gesehen"})
    assert r.status_code == 409
    assert kern_platz.trichter(monat) == {}

def test_kpi_zeigt_trichter_nur_admin(welt, monkeypatch):
    # wie test_messung_und_bremse.test_kpi_zeigt_schloesser_und_zaehler, einmal mit Rolle admin, einmal salon
    ...
    assert "platz_trichter" in admin_antwort and "platz_trichter" not in salon_antwort
```
Die Rolle wird so gesetzt, wie `tests/test_zugriff.py` Admin-Konten anlegt (dort nachschlagen).

- [ ] **Step 2: Tests rot**

Run: `cd server/belegreview && ~/.venvs/babu/bin/python -m pytest tests/test_platz_ereignis.py -q -p no:cacheprovider`
Expected: ImportError `kern_platz`.

- [ ] **Step 3: `kern_platz.py`, Migration, Verdrahtung**

Modul nach dem Muster `kern_konto.py`: `schema(c)`, `setup(app, bw_modul)` registriert `app.post("/api/platz/ereignis")(api_platz_ereignis)`; `api_platz_ereignis(request)`: `_box_wache` → Mandant → Herkunftsprüfung → Validierung → INSERT mit `zeit = datetime.now(timezone.utc).isoformat()`; `trichter(monat)`: `SELECT quelle, aktion, COUNT(*) … WHERE zeit LIKE ? GROUP BY` mit `monat + "%"`. `babu_web.py:707` `kern_platz.schema(conn)`, Zeile 13544 `kern_platz.setup(app, sys.modules[__name__])`, `api_kpi` ergänzt `platz_trichter` hinter der Rollenprüfung (Helfer: wie `_betreiber_wache` die Rolle liest). Migration `0020_platz_ereignis.sql` mit Kopfkommentar wie 0019; `test_db_dialekt.py` beide Listen um `(20, "0020_platz_ereignis.sql")` bzw. `"0020_platz_ereignis.sql"` ergänzen; `kern_konto.NACH_MANDANT` um `"platz_ereignis",  # Paywall-Ereignisse` ergänzen.

- [ ] **Step 4: Betroffene Tests grün**

Run: `cd server/belegreview && ~/.venvs/babu/bin/python -m pytest tests/test_platz_ereignis.py tests/test_konto_loeschen.py tests/test_db_dialekt.py tests/test_messung_und_bremse.py tests/test_zugriff.py -q -p no:cacheprovider`
Expected: alle grün (`test_zugriff` prüft, dass die neue Route hinter einer Wache steht — `golden/routen.txt` um `POST /api/platz/ereignis` ergänzen, wenn der Test es verlangt).

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/kern_platz.py server/belegreview/migrations/0020_platz_ereignis.sql server/belegreview/tests/test_platz_ereignis.py server/belegreview/babu_web.py server/belegreview/kern_konto.py server/belegreview/tests/test_db_dialekt.py server/belegreview/tests/golden/routen.txt
git commit -m "Paywall messen: platz_ereignis je Betrieb, Trichter in /api/kpi für Admins"
```

---

### Task 10: App meldet die Paywall-Ereignisse

**Files:**
- Modify: `ios/Beleg/Beleg/AblageService+Betrieb.swift` (neu `platzEreignis(quelle:aktion:stufe:)`)
- Modify: `ios/Beleg/Beleg/PlatzSheet.swift` (Parameter `quelle`, Meldungen), `Store.swift` (`platzQuelle`), `PlatzStreifen.swift:18`, `Store.swift:598,611`

**Interfaces:**
- Consumes: `POST /api/platz/ereignis` (Task 9).
- Produces: `enum PlatzQuelle: String { case angebot, menue, streifen, voll }` in `Platz.swift`; `AppStore.platzQuelle: PlatzQuelle = .angebot` (nicht persistiert; gesetzt von `angebotNachErstemBelegPruefen` → `.angebot`, `platzIstVoll` → `.voll`, `PlatzStreifen` → `.streifen`); `PlatzSheet(quelle: PlatzQuelle? = nil)` nimmt `quelle ?? store.platzQuelle`; `AblageService.platzEreignis(quelle: PlatzQuelle, aktion: String, stufe: String?) async` — Feuer-und-vergessen (`Task { … }`), Fehler werden verschluckt, kein Nutzertext.

- [ ] **Step 1: Meldefunktion**

In `AblageService+Betrieb.swift` nach dem Muster der vorhandenen POST-Aufrufe mit Bearer: Pfad `/api/platz/ereignis`, Rumpf `{"quelle", "aktion", "stufe"}`; Antwort ignorieren.

- [ ] **Step 2: Quellen setzen, Ereignisse melden**

`PlatzSheet`: `.onAppear` → `gesehen`; nach erfolgreichem `kasse.kaufen` → `gekauft` mit `stufe.rawValue`; Knopf „Erst kostenlos weiter" → `weiter`; `dismiss` über „Später"/Herunterziehen (`onDisappear` ohne Kauf oder Weiter) → `abgebrochen`; nach `wiederherstellen` → `wiederhergestellt`. `PlatzView` übergibt `.menue`.

- [ ] **Step 3: Bauen und live gegen den Prüfbetrieb prüfen (nach Deploy von Task 9)**

Run: Kaufblatt auf dem iPad öffnen und schließen; auf der H200V: `docker exec babu-postgres psql -U babu -d babu -At -c "select quelle, aktion, stufe, zeit from platz_ereignis order by id desc limit 5"`
Expected: `menue | gesehen`, `menue | abgebrochen`.

- [ ] **Step 4: Commit**

```bash
git add ios/Beleg/Beleg/AblageService+Betrieb.swift ios/Beleg/Beleg/PlatzSheet.swift ios/Beleg/Beleg/Platz.swift ios/Beleg/Beleg/Store.swift ios/Beleg/Beleg/PlatzStreifen.swift ios/Beleg/Beleg/PlatzView.swift
git commit -m "Kaufseite meldet, woher sie kam und was danach geschah"
```

---

### Task 11: Deploy, Screenshots, iPhone-Vergleich

**Files:**
- Modify: `ios/Beleg/Beleg.xcodeproj/project.pbxproj` (`CURRENT_PROJECT_VERSION = 15` an 4 Stellen)
- Create: `~/.beleglex/messungen/20261024-build15/iphone-vergleich.txt`, Screenshot-Sätze unter `…/screenshots-ipad13/`, `…/screenshots-iphone/`

**Interfaces:**
- Consumes: `werkzeuge/asc_screenshots.py` (Aufruf laut Dateikopf lesen), Simulator `babu-ipad13` (iPad Pro 13″, `xcrun simctl create`), Xcode-Run mit `Support/babu.storekit` (Euro).

- [ ] **Step 1: Server-Suite voll und Deploy (Task 9)**

Run: `cd server/belegreview && ~/.venvs/babu/bin/python -m pytest tests/ -q -p no:cacheprovider` (Timeout 900 s)
Expected: alles grün. Dann Deploy-Ritual aus `CLAUDE.md` (rsync `server/` und `werkzeuge/` mit `--exclude=.env`, `compose build && up -d`, `/healthz` `stand: ok` und `spiegel: ok`, `schema_version` = 20 nach dem ersten Request).

- [ ] **Step 2: Build-Nummer 15**

Run: `grep -c "CURRENT_PROJECT_VERSION = 15;" ios/Beleg/Beleg.xcodeproj/project.pbxproj` → `4`.

- [ ] **Step 3: iPhone-Vergleich (Anti-Ziel)**

Mit Build 15 auf dem iPhone-16e-Simulator dieselben fünf Bildschirme wie am 29.09. aufnehmen (Beleg, Buchung, Belegliste, Fragen, Export; Demodaten über `zustand.json` ohne Anmeldung). Pixelvergleich gegen den Satz vom 29.09. (`PIL.ImageChops.difference`, Zählung ≠ 0 außerhalb der Statusleiste).
Expected: Unterschiede nur in Uhrzeit/Daten; sonst in `iphone-vergleich.txt` erklären — jeder andere Unterschied ist ein Fehler, der vor Task 12 behoben wird.

- [ ] **Step 4: iPad-13″-Screenshots aus Xcode (Euro)**

Xcode: Schema `Beleg`, Ziel `babu-ipad13`, ▶ (StoreKit-Konfiguration DEU greift nur so). Fünf Bilder: Arbeitsplatz (Liste + Chat), Beleg im Arbeitsplatz, Kaufblatt mit Euro-Preisen, Erfassen, Menü. Hochladen mit `asc_screenshots.py` in den 13″-Satz (`APP_IPAD_PRO_3GEN_129`), Zustand `COMPLETE` abwarten.

- [ ] **Step 5: Archiv und Upload**

Run: `ios/archiv.sh Beleg` (mit `ASC_KEY_ID`/`ASC_ISSUER_ID`/`ASC_KEY_PFAD` wie in der Memory); danach `python3 werkzeuge/asc_pruefung.py`.
Expected: Build 15 `VALID`; Prüfung ohne rotes Kreuz außer Trader/CANNOT_SELL.

- [ ] **Step 6: Commit**

```bash
git add ios/Beleg/Beleg.xcodeproj/project.pbxproj
git commit -m "Build 15 für die Prüfung: Universal, Arbeitsplatz, Kaufweg, Messung"
```

---

### Task 12: Prüfnotiz, Antwort an Apple, Einreichung (Haltepunkt: OK des Auftraggebers)

**Files:**
- Create: `docs/apple-antwort-2026-10-build15.md` (Notes-Text und Antwort, Englisch; Klickpfad mit Screenshot-Verweisen)
- Modify: ASC per API (`asc_api.api("PATCH", "/v1/appStoreReviewDetails/b5741848-0d7c-44d1-8b8d-7598807a6c64", …)` für `notes`; Build 15 an Version `86907b2b-8b40-4ebd-a55d-2682e5b0ce15` hängen; Antwort im Resolution Center mit Anhängen über Chrome)

**Interfaces:**
- Consumes: Screenshots vom iPad-Air-Simulator je Klickschritt (Task 11), Statuswerte aus `asc_pruefung.py`.
- Produces: Einreichung `58ed02dd-…` mit Item `resolved: true`, dann `submitted: true` — **nur nach ausdrücklichem OK des Auftraggebers.**

- [ ] **Step 1: Text schreiben**

Notes: Zweck (wie bisher), ACCOUNTS, HOW TO TEST mit Schritt 1–5 zum Kauf (Menü ☰ → „Deine Ablage" → „Platz buchen" → Stufe → App-Store-Blatt; Alternativweg nach dem ersten Beleg), Satz zur Sandbox: „configured for the sandbox; available in all 175 territories; Paid Apps Agreement active since 13 Oct 2026" (Statuswerte, keine Ursachen), Hinweis „attachment options in Fragen rebuilt and verified on iPad Air 11″ (M3)". Antwort: dieselben Punkte plus „fixed in build 15", Anhänge = Screenshots je Schritt.

- [ ] **Step 2: Notes per API setzen, Build anhängen**

Run: Skript mit `asc_api.api` (PATCH notes; PATCH `appStoreVersions/<id>/relationships/build` auf Build 15); danach `python3 werkzeuge/asc_pruefung.py`.
Expected: Build 15 an der Version, Notes gleich dem Text.

- [ ] **Step 3: Haltepunkt**

Dem Auftraggeber den Text, die Screenshots und den Prüfbericht zeigen. Erst nach OK: Antwort im Resolution Center absenden (Chrome), dann per API Item `resolved: true` und Einreichung `submitted: true`.

- [ ] **Step 4: Commit**

```bash
git add docs/apple-antwort-2026-10-build15.md
git commit -m "Antwort an App Review für Build 15: Klickpfad mit Belegen, Statuswerte ohne Schlüsse"
```

---

### Haltepunkte für den Auftraggeber (parallel, nicht im Code)

- Xcode 27.1 installieren (für iPadOS-27- und Duo-Simulator; Build 15 wird damit gebaut — Abschnitt 5.1 der Spezifikation). Fehlt es bis Task 11, wird mit Xcode 26.3 gebaut und das in `LIESMICH.txt` vermerkt.
- Apple Developer Support: Telefon-Rückruf zum Trader Status anfordern, Case-Nummer notieren; DAC7 in Business prüfen. Erfolg nur mit `asc_pruefung.py` messen.
- Freigabe der Antwort an Apple (Task 12, Schritt 3).
