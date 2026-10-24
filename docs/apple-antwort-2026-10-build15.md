# Antwort an App Review zu Build 14 (2.1(a) Anhänge, 2.1(b) Abos) — Build 16, 24.10.2026

*Build 15 (20:45 hochgeladen) enthält die Review-Fixes noch nicht; eingereicht wird Build 16.*

Einreichung `58ed02dd-2e0a-401b-a350-1d93fa2d9574`, Version 1.0. Apple lehnte Build 14 am
24.10.2026 13:54 auf einem iPad Air 11" (M3), iPadOS 27.0 ab:

1. **2.1(a)** „multiple attachment options in the chat feature were unresponsive“
2. **2.1(b)** die drei Speicherstufen in der App nicht gefunden; Hinweis auf Sandbox und
   Paid Apps Agreement.

## Gemessen, nicht vermutet (`~/.beleglex/messungen/20261024-build15/`)

| Punkt | Ursache (im Code gefunden, im Simulator nachgestellt) | Fix in Build 15 |
|---|---|---|
| 2.1(a) Fotos | Die Büroklammer ist ein `Menu` mit einem `PhotosPicker` darin. Im iPhone-Kompatibilitätsfenster auf dem iPad schließt sich das Menü, der Picker erscheint nie (Negativkontrolle `ipad-vorher-anhang-fotos-nach-tipp.png`). | Auf dem iPad (auch im Kompat-Fenster: dort meldet `userInterfaceIdiom` `.phone`, nur `model` sagt „iPad“) öffnet die Büroklammer ein eigenes Blatt; der Picker kommt erst, wenn das Blatt zu ist. Auf dem iPhone bleibt das Menü. |
| 2.1(a) Fotos, iPhone | `PhotosPicker` als Menüeintrag öffnet auf iOS 26.3 nichts — auch in Build 14 (`iphone-b14-anhang-fotos.png`). Damit waren in Build 14 auf dem iPhone drei von vier Optionen tot. | Die zwei Foto-Einträge sind Knöpfe, die den `.photosPicker(isPresented:)` am Reiter schalten. |
| 2.1(a) Dateien | Zwei `.fileImporter` am selben View — SwiftUI bedient nur den zweiten. „Aus Dateien (PDF)“ für den Brief öffnete nie, auf iPhone **und** iPad (`iphone-nachher-anhang-dateien.png` vor dem Fix). | Ein Dateidialog mit Zielschalter (Brief/Vertrag). |
| 2.1(b) | `store.zeigePlatz` hing an zwei `.sheet`-Modifiern (Wurzel + „Deine Ablage“). UIKit brach das zweite Zeigen ab („Attempt to present … while a presentation is in progress“, 2 Fehler im Log), das Flag blieb wahr und sperrte das Angebot nach dem ersten Beleg. Dazu: fehlten die StoreKit-Preise, stand stumm der Ersatzpreis vom Server da. | Eigenes Blatt in „Deine Ablage“, Wurzel-Schalter setzt sich beim Schließen zurück. Preise: drei Versuche, sichtbarer Zustand (lädt / geladen / „Preise gerade nicht erreichbar“ + „Nochmal“), gekauft nur bei vollständigen Preisen; Stufen vom letzten Server-Stand bleiben gemerkt. |

Nachgestellt mit Build 15 (iPad Air 11" M3 Simulator, iPhone-Kompat-Fenster, iPadOS 26.3 — iPadOS 27
gibt es in Xcode 26.3 nicht): alle vier Anhang-Optionen öffnen Fotos- bzw. Dateidialog
(`ipad-nachher-anhang-*.png`), Presentation-Log 0 Fehler; ☰ → „Deine Ablage“ → „Platz buchen“ zeigt die
drei Stufen mit StoreKit-Preisen (`ipad-nachher-kaufblatt-preise.png`, US-Sandbox des Simulators: $8.99 /
$17.99 / $89.00). iPhone 17 Pro Max: Kaufblatt und Dateidialog ebenso. Pixelvergleich Build 14 ↔ 15 auf dem
iPhone: 5/5 Bildschirme gleich (`iphone-vergleich.txt`).

Nach dem Abschluss-Review zusätzlich (Build 16): Wurzel-Blatt wird nur über `platzZeigen()` angefordert (ein
hängender Schalter wird erkannt und neu gesetzt; das einmalige Angebot zählt erst als gezeigt, wenn das Blatt da
ist); Stufen vom letzten Server-Stand gelten auch ohne Serverantwort; ein Ladelauf für die Preise, kein Rückfall
eines vollständigen Stands; Kaufblatt zeigt „–“ statt Euro-Ersatzpreis. iPhone 17 Pro Max: alle vier
Anhang-Optionen öffnen ihren Picker (`iphone-nachher-anhang-*.png`); iPad: Angebot nach dem Demo-Beleg
(`ipad-fix-angebot-nach-demo.png`).

**Statuswerte (API, 24.10.):** App und die drei Abos in allen 175 Gebieten; `CANNOT_SELL` überall,
`TRADER_STATUS_NOT_PROVIDED` in 27 EU-Gebieten; Paid Applications Agreement aktiv seit 13.10.2026 (Business →
Agreements, gelesen 22.10.); Trader Status „In Review“ seit 24.09. Was `CANNOT_SELL` auslöst, ist ungemessen —
in der Antwort stehen nur die Werte.

## Prüfnotiz (ASC `notes`, ≤ 4.000 Zeichen) — Änderungen gegenüber Build 14

Absatz „HOW TO TRY IT“, Schritt 3 ergänzt um den Menüweg mit Fotos; neuer Absatz „SANDBOX AND iPAD“:

> SANDBOX AND iPAD (build 16)
> The subscriptions load from the App Store sandbox (verified: three tiers with sandbox prices on iPad Air
> 11-inch and iPhone 17 Pro Max simulators, build 16). If prices cannot be loaded, the screen now says so and
> offers "Nochmal" (retry). App and subscriptions are available in all 175 territories; the Paid Applications
> Agreement is active (since 13 Oct 2026). The attachment options in "Fragen" (paper clip) were rebuilt for
> iPad and verified on iPad Air 11-inch (M3): each of the four options opens the Photos or Files picker.

## Antwort im Resolution Center (englisch) — abgesendet 25.10.2026 00:25 (OK des Auftraggebers „machen“)

Hello,

thank you for the detailed review on the iPad Air. Both points were real defects on our side; both are fixed
in build 16, which is attached to version 1.0.

**1. Attachment options in "Fragen" (2.1(a)).** Three causes, all reproduced in the simulator: (a) in the
iPhone-compatibility window on iPad the attachment menu closed without opening the Photos picker; (b) the
Photos entries inside the menu did not open the picker on iPhone either; (c) one of the two "from Files"
options never opened on any device. In build 16 the paper clip on iPad opens its own sheet with the four
options, and each option opens the Photos or Files picker only after the sheet is closed; on iPhone the menu
entries now open the pickers attached to the tab. Verified on iPad Air 11-inch (M3) and iPhone 17 Pro Max:
all four options open their picker (screenshots of both devices attached).

**2. In-App Purchases (2.1(b)).** The purchase screen could fail to appear when opened from the menu, because
the same presentation flag was bound twice; build 16 fixes that, and a flag left behind by an interrupted
presentation is now detected and reset. Where to find it: launch the app, tap
"Los geht's" (no account needed), then menu button (three lines, top right) → "Deine Ablage" (Your archive)
→ "Platz buchen" (Book storage). The screen lists the three monthly subscriptions of the group "babu
Speicher" (babu.speicher.1gb / 5gb / 100gb) with the App Store price, "Platz buchen" opens the App Store
purchase sheet, "Käufe wiederherstellen" restores purchases. The same screen also opens by itself right
after the first captured document. If the prices cannot be loaded, the screen now says so and offers a
retry instead of showing the tiers without prices.

Sandbox: verified with build 16 — the three products load from the sandbox with their storefront prices on
iPad Air 11-inch and iPhone 17 Pro Max (screenshot attached). Availability: app and all three subscriptions
are available in all 175 territories. Paid Applications Agreement: active since 13 October 2026 (Business →
Agreements). Trader status: submitted 24 September 2026, currently "In Review".

Attachments: 1 purchase screen with the three tiers (iPad Air 11-inch), 2 the same screen opening after the
first document, 3–6 the four attachment options on iPad Air 11-inch with their picker open, 7–8 Photos picker
from the menu on iPhone 17 Pro Max.

Kind regards
Christoph Bertsch, nullsiebenelf GmbH

## Anhänge (Dateien für das Resolution Center)

- `ipad-nachher-kaufblatt-preise.png` — Kaufblatt mit drei Stufen und Preisen
- `ipad-nachher-anhang-fotos.png`, `ipad-nachher-anhang-dateien.png`, `ipad-nachher-anhang-vertragfotos.png`,
  `ipad-nachher-anhang-vertragdateien.png` — die vier Anhang-Optionen mit geöffnetem Picker
- `ipad-fix-angebot-nach-demo.png` — Angebot nach dem ersten Beleg (Wurzel-Blatt)
- `iphone-nachher-anhang-fotos.png`, `iphone-nachher-anhang-vertragfotos.png` — Fotos-Picker aus dem iPhone-Menü
- `iphone-nachher-kaufweg.png` — Kaufblatt iPhone 17 Pro Max

## Eingereicht (25.10.2026, 00:26 MESZ)

- Antwort mit den acht nummerierten Anhängen (01–08, Reihenfolge wie im Text) im Resolution Center abgesendet
  (Chrome-Sitzung des Auftraggebers); die Nachricht steht als „Christoph Bertsch, Today 12:25 AM“ unter Messages (5).
- Per API: Item der App-Version (`…fDZ8ODkxMzUxNTUy`) `resolved: true` → `READY_FOR_REVIEW`; Einreichung
  `58ed02dd` `submitted: true` → `WAITING_FOR_REVIEW`, `submittedDate 2026-10-24T22:26:28Z`; alle fünf Items
  (Version 1.0 mit Build 16, Abo-Gruppe, drei Abos) `READY_FOR_REVIEW`.
- `iphone-nachher-kaufweg.png` nicht angehängt (im Text nicht nummeriert; Kaufblatt iPhone ist durch die
  Prüfnotiz abgedeckt).
