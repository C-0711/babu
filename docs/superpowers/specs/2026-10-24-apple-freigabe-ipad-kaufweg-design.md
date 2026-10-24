# Apple-Freigabe, iPad als Zielgerät, Kaufweg und Conversion — Design

> Entwurf 24.10.2026 nach der zweiten Ablehnung von Build 14 und dem Entscheid
> des Auftraggebers „babu geht auch auf iPad". Befunde am Stand `main 170ad66`,
> App Store Connect per API und Resolution Center gelesen, Fehler im Simulator
> nachgestellt und im Log belegt. Kein Code geändert — das ist die Grundlage
> für den Umsetzungsplan.

## 1. Warum jetzt

Apple hat Version 1.0 (Build 14) am 24.10.2026 um 13:54 abgelehnt, geprüft auf
einem **iPad Air 11″ (M3), iPadOS 27.0**:

- **2.1(a)** „multiple attachment options in the chat feature were
  unresponsive" — die Anhang-Optionen im Reiter „Fragen".
- **2.1(b)** „we cannot locate the In-App Purchases … within the app" — die drei
  Speicherstufen wurden nicht gefunden.

Beides hat eine gemessene Ursache im Code, keine im App-Store-Setup:

1. **Der Kaufweg aus dem Menü tut nichts.** `store.zeigePlatz` hängt an zwei
   `.sheet`-Modifiern: an der Wurzel (`BelegApp.swift:86`, 10.10.) und im
   Menüblatt (`PlatzView.swift:47`, 11.10.). Beim Tippen auf „Platz buchen" im
   Menü meldet UIKit „Attempt to present … while a presentation is in
   progress" und danach „whose view is not in the window hierarchy"
   (Simulator-Log 24.10., 18:41:32–33). Das Menü klappt zu, kein Kaufblatt.
   Der Schalter bleibt danach `true`; weil `angebotNachErstemBelegPruefen`
   mit `!zeigePlatz` abbricht, kommt auch das automatische Angebot nicht mehr
   bis zum Neustart. Genau diesen Weg nennt die Prüfnotiz dem Prüfer.
2. **Die Anhang-Optionen im Chat sind ein `Menu` mit `PhotosPicker` darin und
   Knöpfen, die `fileImporter` setzen** (`FragenTab.swift:477–505`). Auf dem
   iPad läuft ein `Menu` als Popover; Picker aus einem schließenden Popover
   heraus zu präsentieren ist dieselbe Fehlerklasse wie Punkt 1. Hypothese,
   noch nicht auf dem iPad nachgestellt — der erste Schritt des Plans.
3. Die App ist `TARGETED_DEVICE_FAMILY = 1` (nur iPhone). Apple prüft
   iPhone-Apps trotzdem auf dem iPad und verlangt, dass sie dort laufen;
   iPad-Unterstützung zu entfernen hilft nachweislich nicht (Forum-Fälle
   802147, 781735). Der Auftraggeber hat am 24.10. entschieden: **babu wird
   eine richtige iPad-App.**

Dazu kommt, was heute außerhalb des Codes offen ist (gemessen 24.10. mit
`asc_pruefung.py`): `CANNOT_SELL` in allen 175 Gebieten,
`TRADER_STATUS_NOT_PROVIDED` in 27 EU-Gebieten (Trader Status „In Review" seit
24.09.), Paid Apps Agreement aktiv seit 13.10., Abos dreimal READY_TO_SUBMIT in
175 Gebieten, der Einreichung beigelegt.

## 2. Ziele

1. **Build 15 besteht die Prüfung.** Beide Punkte behoben, nachgestellt auf
   iPad und iPhone, mit einem Klickpfad in der Prüfnotiz, der nachweislich
   funktioniert (Screenshots vom iPad-Simulator als Anhang).
2. **iPad ist ein vollwertiges Gerät.** Universal-App, eigenes Layout bei
   breiter Größenklasse, alle Orientierungen, Store-Screenshots für 13″.
3. **Der Kaufweg ist an jeder Stelle robust:** Menü, Angebot nach dem ersten
   Beleg, Streifen bei knappem Platz. Preise werden vor dem Anzeigen geladen;
   ohne Preise gibt es einen sichtbaren Zustand mit „Nochmal", nie einen Knopf,
   der in „nicht zu haben" endet.
4. **Die Paywall wird gemessen.** Wie oft gesehen, woher, was danach. Ohne
   Zahl kein Umbau der Conversion.
5. **Conversion-Verbesserungen sind vorbereitet, nicht eingebaut** (Build 16,
   eigener Entwurf): Testphase statt Zähler, Streifen, Texte am Aha-Moment.

## 3. Nicht-Ziele und Anti-Ziele

Nicht-Ziele:
- Abos ins Web verlegen oder die App ohne IAP ausliefern. 3.1.3(b) greift nur,
  wenn dieselben Leistungen auch als IAP angeboten werden; B2B-Apps ohne IAP
  werden nach 3.1.1 abgelehnt (Forum 811018, 825551). Das Speicher-Modell vom
  10.10. bleibt.
- Preise, Stufen, Ebenen ändern. `babu.storekit`, ASC und
  `tests/test_apple_produkte.py` bleiben, wie sie sind.
- ERiC, Kanzlei-Seite, Portal, Buchungsweg.
- Ein Umbau der Kamera-Erfassung. Sie bekommt auf dem iPad nur Platz und
  Orientierung, keine neue Logik.

Anti-Ziele (Erfolg wäre trotzdem ein Fehlschlag, wenn …):
- … das iPhone-Layout sich irgendwo ändert. Beide Ziele (`Beleg`, `BelegPro`)
  bauen, `ios/Tests/zuschnitt` bleibt grün, die bestehenden Screenshots vom
  29.09. müssen auf dem iPhone weiter so aussehen.
- … ein Schalter hängen bleiben kann. Jeder Präsentationsweg setzt seinen
  Zustand bei Erfolg UND Misserfolg zurück.
- … Konten ohne Platz-Modell (Portal-Betriebe, Kanzlei, Mitarbeiterinnen) eine
  Paywall sehen. `store.platz == nil` heißt weiter: kein Streifen, kein
  Angebot.
- … in Notiz oder Antwort an Apple ein Schluss steht statt eines Messwerts
  („no storefront restrictions" ist verboten; Statuswerte ja, Ursachen nein).

## 4. Rahmen

- Zwei Ziele aus einem Ordner (`Ausbaustufe.swift`, Flag `BABU_PRO`); jede
  Reiter- oder Menüzeile dort. Keine Datei wird ausgelassen.
- Alte `zustand.json`/`zustand-<hash>.json` müssen laden: neue Felder optional.
- UI-Sprachregel: kein Technik-Vokabular. „Preise werden geladen …", nicht
  „StoreKit".
- Server-Änderungen: jede Schemaänderung zweimal (inline + Migration), neue
  Tabellen mit `un`/`mandant_id` in `kern_konto.NACH_*`.
- Deploy-Ritual, Suite vor dem Deploy, Golden-Diff bei Änderungen am
  Buchungsweg (hier nicht betroffen).
- App Store: 13″-iPad-Screenshots (2064 × 2752) werden mit Universal Pflicht;
  Hochladen per `werkzeuge/asc_screenshots.py` (Dreischritt mit MD5).
- Bearer-App-Konten dürfen keinen Kaufhinweis außerhalb des Kaufwegs sehen
  (`abo.TEXTE_APP`).

## 5. Was entschieden ist

### 5.1 Universal-App und iPad-Layout

- `TARGETED_DEVICE_FAMILY = 1,2` in beiden Zielen. Orientierungen: iPad alle
  vier (steht schon im Projekt), iPhone weiter nur Hochformat.
- **Das iPhone Duo gehört dazu (Auftraggeber 24.10., „geht mit diesem neuen
  Apple-Telefon noch besser"):** Apples faltbares iPhone zeigt aufgeklappt ein
  fast quadratisches Innendisplay im Querformat (Startbildschirm mit Dock
  rechts, Apple-Produktseite). Dort gilt dasselbe breite Layout wie auf dem
  iPad: links Beleg oder Belege, rechts Chat oder Archiv. Entschieden
  wird nach Größenklasse, nie nach Gerätemodell: `horizontalSizeClass ==
  .regular` = breit. Zugeklappt ist das Faltgerät ein iPhone und bekommt das
  iPhone-Layout. Ob der aufgeklappte Zustand in SwiftUI als `.regular` kommt
  und ob Xcode einen Simulator dafür hat, ist recherchiert (24.10., Quellen
  Dritter, Apple nennt nur Pixel): **Innendisplay 669 × 951 pt, Querformat
  nativ, Größenklasse regular/regular; Außendisplay 466 × 678 pt, compact.**
  Den Duo-Simulator gibt es **ab Xcode 27.1 (Beta)**; Xcode 26.3 auf diesem
  Mac kennt keinen Faltgeräte-Typ (`simctl list devicetypes`, 24.10.).
  Zwei Fallen aus den Berichten: `UIScreen.main.bounds` meldet auf dem
  Innendisplay weiter die Außenmaße — nie benutzen; Apple rät von festen
  Breiten und Breakpoints ab, nur Größenklassen und flexible Layouts.
- **Werkzeugkette (meine Entscheidung, Prüferfrage 2):** Der Auftraggeber
  installiert Xcode 27.1 neben Xcode 26.3 (Apple-ID, großer Download). Build 15
  wird mit Xcode 27 gebaut, weil die App nur mit dem iOS-27-SDK das
  Innendisplay des Duo bekommt und Apple auf iPadOS 27 prüft. Das Anti-Ziel
  „iPhone unverändert" wird dann nicht angenommen, sondern gemessen:
  die fünf Store-Screenshots vom 29.09. auf dem iPhone-Simulator neu
  aufnehmen und mit den alten vergleichen. Solange Xcode 27 fehlt, wird auf
  dem iPad-Air-Simulator mit iOS 26.3 nachgestellt und gebaut; der Plan hat
  dafür einen Haltepunkt.
- Die breite Größenklasse wird außerdem auf dem iPhone über einen Schalter
  „Breites Layout erzwingen" unter Einstellungen → Testphase geprüft (den
  Testphase-Mechanismus gibt es; meine Entscheidung nach Prüferfrage: kein
  neues UI-Test-Ziel, das Projekt hat keines, und `ios/Tests/run.sh` bleibt
  UIKit-frei). Der Schalter setzt die Größenklasse per
  `.environment(\.horizontalSizeClass, .regular)` an der Wurzel und liegt im
  Release-Build hinter der Testphase.
- Layout bei breiter Größenklasse — **der Arbeitsplatz: links die Belege,
  rechts der Chat** (Auftraggeber 24.10., „da ist das supergeil"):
  - **Zwei Spalten auf einer Seite, jede Seite zeigt eines von drei Dingen:**
    die Belegliste (Archiv mit Monatswechsler und Fächern, heutige
    `ListeView`-Inhalte), den einen aufgeschlagenen Beleg (groß, mit ⓘ/Alle
    Angaben als Inspector) oder den Fragen-Chat (eigene Eingabeleiste und
    Anhang-Knopf). Vorgabe beim Öffnen: links Archiv, rechts Chat. Tippt man
    links einen Beleg an, wandert die Liste nach links hinten (Navigation in
    der Spalte) und der Beleg steht links; rechts bleibt der Chat. Oben rechts
    ein kleiner Umschalter „Fragen | Beleg", mit dem die rechte Spalte
    stattdessen den aufgeschlagenen Beleg groß zeigt und links das Archiv
    bleibt (Auftraggeber: „links Beleg, rechts Chat oder Belegarchiv").
    Mehr Kombinationen gibt es in Build 15 nicht. Breitenverhältnis Vorgabe
    45/55, Spalten per `NavigationSplitView` oder `HStack` mit Teiler; der
    Umsetzende wählt.
  - **Erfassen** bleibt ein eigener Reiter: Kamera-Sucher und Ergebnis in
    einer mittigen Spalte mit Höchstbreite (Vorgabe 640 pt), Sucher folgt der
    Orientierung. Knöpfe „Beleg aus Datei …" bleiben darunter. Nach dem
    Buchen führt „Zu den Dokumenten" in den Arbeitsplatz.
  - Die Reiter „Dokumente" und „Fragen" werden auf breit zu EINEM Reiter
    „Arbeitsplatz" (Name offen, Auftraggeber); `Ausbaustufe.swift` kennt die
    Zusammenlegung, damit beide Ziele und `ios/Tests/zuschnitt` sie tragen.
    Auf dem iPhone bleiben es zwei Reiter.
  - **Dein Konto (Menü):** auf breit als Blatt in Formulargröße
    (`presentationSizing`/`.form`), nicht bildschirmfüllend; der Inhalt bleibt.
  - **Kaufseite:** als Blatt in Formulargröße; die drei Stufen bleiben
    untereinander.
  - Reiter: `TabView` bleibt; iPadOS zeigt sie oben, das ist gewollt.
- Nichts davon rührt die iPhone-Pfade an; jede breite Variante ist ein
  zusätzlicher Zweig, kein Umbau.

### 5.2 Anhang-Optionen im Chat

- **Auf dem iPhone (compact) ändert sich am Chat nichts** (Auftraggeber
  24.10.: „in der iPhone-App nichts am Chat ändern"). Das `Menu` in
  `FragenTab.eingabeleiste` bleibt dort Byte für Byte, wie es ist.
- **Bei breiter Größenklasse** (iPad, aufgeklapptes Duo) ersetzt ein eigenes
  kleines Blatt „Anhang" das `Menu` (vier Knöpfe in zwei Gruppen wie heute).
  Fotos- und Dateiauswahl werden NICHT aus dem Blatt heraus präsentiert,
  sondern über Modifier am Reiter-Wurzelview
  (`.photosPicker(isPresented:selection:)`, `.fileImporter`), ausgelöst im
  `onDismiss` des Blatts. So gibt es nie zwei Präsentationen gleichzeitig.
  Die Verzweigung ist genau eine Stelle (`if breit { AnhangKnopf } else {
  heutiges Menu }`); Verarbeitung der Auswahl bleibt gemeinsam.
- Nachgestellt wird vor und nach der Änderung auf dem iPad-Air-Simulator:
  jede der vier Optionen muss den Picker öffnen. Auf dem iPhone 16e dieselben
  vier Optionen als Negativkontrolle: unverändertes Verhalten.
- Der Chat rechts im Arbeitsplatz ist der heutige Chat, nur platziert
  (Auftraggeber 24.10.); er kennt die Belegbox über den Server wie bisher.
  Den aufgeschlagenen Beleg als Kontext in die Frage zu geben, ist Phase C.

### 5.3 Kaufweg

- `PlatzView` (Menü → Deine Ablage) bekommt einen eigenen `@State` für sein
  Blatt; der Knopf setzt den, nicht `store.zeigePlatz`. Der Wurzel-Schalter
  bleibt für Angebot nach dem ersten Beleg, „kein Platz" und `PlatzStreifen`.
- Der Wurzel-Schalter wird beim Schließen des Blatts und beim Scheitern der
  Präsentation zurückgesetzt; `angebotNachErstemBelegPruefen` darf nie an
  einem hängenden Schalter scheitern.
- `Kasse.preiseLaden` bekommt einen Zustand (`laedt`, `geladen`, `fehler`) und
  bis zu drei Versuche mit Pause; `PlatzSheet` zeigt bei `laedt` einen Hinweis
  und bei `fehler` „Preise gerade nicht erreichbar — Nochmal". „Platz buchen"
  ist nur bei `geladen` aktiv. Produkt-IDs und Fehlertext ins Log (Konsole,
  kein Nutzertext).
- **Die Stufen selbst kommen weiter nur vom Server** (`/api/ich` →
  `paket.angebot()`), keine zweite Wahrheit in der App (meine Entscheidung
  nach Prüferfrage; `tests/test_apple_produkte.py` bleibt die einzige
  Abgleichstelle). Damit eine kurze Serverstörung die Kaufseite nicht leert,
  merkt sich die App die zuletzt gelieferten Stufen in der Zustandsdatei
  (optionales Feld) und zeigt sie bis zur nächsten Antwort. „Nochmal"
  wiederholt beides: `kontoNachfragen` und `Product.products`. Der Zustand
  lebt in `Kasse` (Preise) und `AppStore` (Stufen); `PlatzSheet` zeigt ihn.
- Der Streifen `PlatzStreifen` bleibt wie heute (nur `voll`/`knapp`); in
  Build 15 keine Änderung an der Schwelle.

### 5.4 Messung der Paywall (Server + App)

- Server: Tabelle `platz_ereignis` (Migration 0020 + inline): `mandant_id`,
  `quelle` (angebot/menue/streifen/voll), `aktion` (gesehen/gekauft/weiter/
  abgebrochen/wiederhergestellt), `stufe`, `zeit`. Route
  `POST /api/platz/ereignis` hinter `_box_wache`; nur für Konten mit
  Platz-Modell. Auswertung in `/api/kpi/<monat>` als Trichter je Quelle
  **über alle App-Store-Betriebe** (Geschäftskennzahl); der Schlüssel
  `platz_trichter` steht nur in der Antwort für `rolle == admin`, alle anderen
  bekommen ihn nicht (meine Entscheidung nach Prüferfrage — je Mandant wären
  es eine Handvoll Ereignisse, dafür lohnt kein Trichter). Eintrag in
  `kern_konto.NACH_MANDANT`.
- App: `Kasse`/`PlatzSheet` melden die vier Ereignisse; Meldung ist
  Feuer-und-vergessen, nie blockierend, kein Hinweis in der UI.
- Das ist bewusst minimal (meine Entscheidung): ohne diese Zahlen lässt sich
  Phase C nicht bewerten.

### 5.5 Prüfnotiz, Antwort, Einreichung

- Prüfnotiz und Antwort im Resolution Center neu: Schritte 1–5 zum Kauf, jeder
  Schritt mit Screenshot vom iPad-Air-Simulator (Anhang), Satz zur Sandbox
  („configured for sandbox, no storefront or device restriction — available
  in all 175 territories, Paid Apps Agreement active since 13 Oct"), Hinweis,
  dass die Anhang-Optionen neu gebaut und auf iPad Air 11″ geprüft wurden.
- Einreichen per API wie am 22.10.: Eintrag `resolved: true`, Einreichung
  `submitted: true`. Vorher `asc_pruefung.py` ohne rotes Kreuz außer Trader/
  CANNOT_SELL.

### 5.6 Trader Status und EU (Auftraggeber, parallel)

- Telefon-Rückruf beim Apple Developer Support zu Geschäftszeiten anfordern,
  Case-Nummer notieren; DAC7 („Missing Info" am 22.10.) in Business prüfen.
  Erfolg wird nur mit `asc_pruefung.py` gemessen (`TRADER_STATUS_NOT_PROVIDED`
  verschwindet, `CANNOT_SELL` ändert sich oder nicht).

### 5.7 Phase C — vorbereitet, eigener Entwurf (Build 16)

Nicht Teil dieses Plans, aber aus der Recherche abgeleitet und zu entscheiden:
- Testphase statt „10 Belege frei": 14 Tage alles frei als Apple Introductory
  Offer (Free Trial) auf allen drei Stufen; RevenueCat 2026: Trials ab 17 Tagen
  konvertieren 42,5 % (Median), ≤ 4 Tage 25,5 %.
- Paywall-Text am Aha-Moment: „Dein erster Beleg ist gebucht — Konto 6815,
  119,00 €" oben auf der Kaufseite statt der Feature-Liste.
- Streifen „noch 2 frei" ab Beleg 8; Angebot beim App-Start ab Beleg 10.
- Alles über Server-Schalter steuerbar, A/B ohne neuen Build.

## 6. Wie geprüft wird

1. Simulatoren anlegen: iPad Air 11″ (M3) und iPad Pro 13″ mit iPadOS 27
   (sobald Xcode 27.1 da ist, sonst 26.3), iPhone Duo (Xcode 27.1), iPhone 16e.
   Vor jeder Änderung die beiden Ablehnungspunkte auf dem iPad nachstellen
   und das Log sichern (Negativkontrolle: der Fehler muss vorher sichtbar
   sein).
2. Nach der Änderung: alle vier Anhang-Optionen, Kaufweg aus Menü, Angebot
   nach dem ersten Beleg, Streifen — auf iPad hoch/quer, auf dem Duo offen
   und zu, und auf dem iPhone 16e; kein `Presentation`-Fehler mehr im Log.
   Auf dem iPhone 16e die fünf Store-Screenshots vom 29.09. neu aufnehmen und
   mit den alten vergleichen (Pixelvergleich, Abweichung nur in Zeit/Daten).
3. `ios/Tests/run.sh` grün, `ios/Tests/zuschnitt` zweimal grün, beide Ziele
   bauen; Server-Suite grün (nur betroffene Tests beim Ändern, voll vor dem
   Deploy).
4. `asc_pruefung.py` vor der Einreichung; 13″-Screenshots hochgeladen und
   `COMPLETE`.
5. Nach dem Deploy: `/healthz` ok, `POST /api/platz/ereignis` live mit dem
   Prüfbetrieb (Mandant 4) einmal durchgerufen, Trichter in `/api/kpi` sichtbar.

## 7. Dem Umsetzenden überlassen

- Genaue Breiten, Abstände und ob der Beleg rechts als `Inspector` oder als
  zweite Spalte erscheint.
- Welche weiteren Ansichten (Export, Monatsabschluss, Betrieb, Einstellungen)
  auf breit eine Höchstbreite bekommen; Vorgabe: alle Formulare mittig,
  Höchstbreite 640 pt.
- Ob das Anhang-Blatt ein `confirmationDialog` mit Anker oder ein eigenes
  Sheet wird — beides erlaubt, solange die Picker erst nach dem Schließen
  präsentiert werden.
- Dateinamen, Benennung der Zustände, Reihenfolge der Commits.

## 8. Entscheidungen des Auftraggebers und meine Vorgaben

Vom Auftraggeber am 24.10. entschieden: babu wird iPad- und iPhone-Duo-App;
links Beleg(e), rechts Chat oder Archiv; auf dem iPhone ändert sich am Chat
nichts; der Chat rechts ist der heutige Chat (Kopplung an den aufgeschlagenen
Beleg erst in Phase C).

Meine Vorgaben, gelten bis der Auftraggeber widerspricht:
- Name des zusammengelegten Reiters auf breit: „Arbeitsplatz".
- Höchstbreite der Erfassen-Spalte auf breit: 640 pt; der Sucher darf nicht
  die ganze Breite nutzen.
- Phase C kommt als eigener Entwurf nach der Freigabe; nichts davon in
  Build 15.
- Build 15 wird mit Xcode 27.1 gebaut (Abschnitt 5.1); Xcode 27.1 installiert
  der Auftraggeber.
