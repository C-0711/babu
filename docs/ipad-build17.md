# Build 17/18 — babu auf dem iPad (und aufgeklapptem iPhone Duo), 27./28.10.2026

Umsetzung der Tasks 4–10 aus `docs/superpowers/plans/2026-10-24-apple-freigabe-ipad-kaufweg.md`
(Spezifikation `docs/superpowers/specs/2026-10-24-apple-freigabe-ipad-kaufweg-design.md`), Branch
`claude/ipad-build17` ab main 82cba92. Messungen unter `~/.beleglex/messungen/20261028-build17/`
(LIESMICH.txt, Screenshots, `iphone-vergleich.txt`). Build 16 steht seit 25.10. bei Apple in
„Waiting for Review“ — Build 17 wird deshalb NICHT an die Version gehängt, bis Apple entschieden hat.

## Was sich ändert

| Bereich | Vorher | Build 17 |
|---|---|---|
| Gerätefamilie | nur iPhone (auf dem iPad im Kompatibilitätsfenster) | Universal (`TARGETED_DEVICE_FAMILY = "1,2"`, beide Ziele); iPad alle Orientierungen, iPhone weiter Hochformat |
| Breite Größenklasse (`horizontalSizeClass == .regular`: iPad-Vollbild, aufgeklapptes Duo) | iPhone-Layout | **Arbeitsplatz**: Dokumente + Fragen werden EIN Reiter — links die Belegliste (45 %), rechts Chat oder der aufgeschlagene Beleg groß (Umschalter „Fragen \| Beleg“) |
| Erfassen auf breit | volle Breite | mittig, Höchstbreite 640 pt |
| Menü / Kaufblatt auf breit | bildschirmfüllend | Formblatt (`presentationSizing(.form)`, ab iOS 18) |
| Export, Monatsabschluss, Betrieb, Einstellungen auf breit | volle Breite | mittig ≤ 640 pt |
| Chat-Anhang | eigenes Blatt nur auf dem iPad | auch in jeder breiten Größenklasse (Duo, Testphase-Schalter) |
| Testphase | — | Einstellungen → Testwerkzeuge → „Breites Layout erzwingen“ (iPhone zeigt den Arbeitsplatz) |
| Paywall-Messung | keine | App meldet `gesehen/gekauft/weiter/abgebrochen/wiederhergestellt` mit Quelle `angebot/menue/streifen/voll`; Server zählt in `platz_ereignis`, Trichter in `/api/kpi/{monat}` nur für `admin` |

iPhone (compact) bleibt unverändert — gemessen, nicht angenommen: Pixelvergleich Build 16 ↔ 17 auf dem
iPhone 17 Pro Max, fünf Bildschirme (Erfassen, Dokumente, Fragen, Menü, Ablage), 5/5 gleich, nur
Rauschen ≤ 4/255 am „Fertig“-Knopf des Menü-Blatts (dasselbe Rauschen wie am 24.10.).

## Entscheidungen beim Bauen

- **Größenklasse, nie Gerätemodell.** Im iPadOS-26-Fenster ist ein schmales Fenster (560 pt) compact
  und zeigt das iPhone-Layout — gewollt. Vollbild = regular = Arbeitsplatz.
- **Empfehlen** wechselt auf breit nicht den Platz: babu Pro behält es im Menü (dort war unten kein
  Platz, und das Menü kennt die Größenklasse nicht — sonst stünde es doppelt), babu hinten in der Leiste.
- **„Fertig“ der Großansicht** rief `dismiss()`; in der Spalte ist nichts zu schließen (toter Knopf).
  `BelegGrossView` bekommt einen optionalen Rückruf `fertig`; der Arbeitsplatz schaltet damit auf Fragen.
- **„Zu den Dokumenten“** und andere Stellen setzen weiter `.belege`/`.fragen`; `MainTabs` lenkt auf
  breit nach `.arbeitsplatz` um — kein Aufrufer wurde angefasst.
- **Portal-Konten** (ohne App-Betrieb) bekommen bei `POST /api/platz/ereignis` 409 „kein Platz-Modell“,
  es wird nichts gespeichert. Unbekannte Werte 400, ohne Schlüssel 401.
- **Neue Tabelle** `platz_ereignis` steht in `kern_konto.NACH_MANDANT` (Konto löschen nimmt sie mit)
  und in `db.ID_TABELLEN`; Migration `0020_platz_ereignis.sql` + Inline-Schema, Tabellenzahl 41.

## Fix-Pass nach dem Review (28.10.2026)

- **Nur-Lesen-Sperre ließ die Messung nicht durch:** bei vollem Platz (zehn freie Belege verbraucht) gab
  `POST /api/platz/ereignis` 403 — die Quelle `voll` wäre immer leer geblieben. `/api/platz/` steht jetzt
  in `abo.FREIE_PFADE`; Tests `test_voller_platz_meldet_trotzdem`, `test_der_kauf_weg_bleibt_offen…`.
- **Wechsel der Größenklasse** (Fenster schmaler, Split View, Testschalter) warf auf „Erfassen“ zurück.
  `Ausbaustufe.reiterNachWechsel(aktuell:neu:)`: Arbeitsplatz ↔ Dokumente/Fragen; Harness zuschnitt.
- **`project.yml`** führte die App weiter als reine iPhone-App (`xcodegen generate` hätte Universal still
  zurückgedreht): Gerätefamilie 1,2 + iPad-Orientierungen; `run.sh` prüft beides gegen die pbxproj.
- **Messung:** Quelle wird beim Öffnen des Kaufblatts festgehalten; „gekauft“/„wiederhergestellt“ werden
  vor dem Server-Nachfragen gemeldet, damit ein Wegwischen in dieser Sekunde nicht als „abgebrochen“ zählt.

## Builds bei App Store Connect

- Build 17 (0e4f149, 28.10. 00:30): Stand VOR dem Fix-Pass, nur TestFlight-Verarbeitung — nicht verwenden.
- Build 18 (67cd619 + Build-Nr.): Stand MIT Fix-Pass, der Kandidat für die Einreichung nach Apples Entscheid zu Build 16.

## Noch offen

- 13″-Store-Screenshots (Arbeitsplatz, Beleg im Arbeitsplatz, Kaufblatt in Euro, Erfassen, Menü):
  Euro-Preise gibt es nur mit der StoreKit-Konfiguration des Xcode-Schemas (▶ in Xcode), der
  Simulator zeigt sonst die US-Sandbox. Hochladen erst nach Apples Entscheid zu Build 16.
- iPhone Duo: kein Simulator ohne Xcode 27.1 — geprüft über den Testphase-Schalter und das iPad.
- Im Arbeitsplatz bringen beide Spalten je einen Konto-Knopf (☰) mit, und die Kopfzeilen liegen nicht
  auf einer Höhe (Review 28.10.) — vor den 13″-Store-Screenshots beheben.
- Vorschlag Build 18 (Auftraggeber 28.10.: „horizontal mehr Vorteile“): im Querformat eine dritte
  Spalte Liste | Beleg | Chat (je ~390 pt), ohne Umschalter.
