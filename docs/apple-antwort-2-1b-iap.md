# Antwort an App Review (2.1(b), In-App-Käufe nicht gefunden) — 22.10.2026

Einreichung `58ed02dd-2e0a-401b-a350-1d93fa2d9574`, Version 1.0 (13). Apple
findet die Abos nicht und fragt nach vier Dingen: Klickpfad, Sandbox,
Einschränkung nach Storefront/Region/Gerät, Paid Applications Agreement.

**Gemessen, nicht vermutet:**

- Der Server liefert dem Prüfkonto `apple-review@0711.io` (Mandant 4, herkunft
  app, Hauskanzlei 10) Platz und alle drei Stufen — im laufenden Container
  nachgerechnet. Die Prüfnotiz nannte den Weg schon.
- App UND Abos waren nur in **DEU** verfügbar. StoreKit liefert nur Produkte
  der Storefront des Sandbox-Kontos; ein Prüfer aus einem anderen Land bekam
  nichts. Die App zeigt dann die Stufen mit dem Ersatzpreis vom Server, und
  „Platz buchen" endet in „Dieser Platz ist gerade nicht zu haben"
  (`Kasse.kaufen`). Für den Prüfer: keine In-App-Käufe.
- `territoryAvailabilities` (v2), gelesen 22.10.: DEU `available: true` mit
  `TRADER_STATUS_NOT_PROVIDED`, `CANNOT_SELL`, `AVAILABLE_FOR_SALE_UNRELEASED_APP`;
  AUT/FRA (EU) `available: false` mit `TRADER_STATUS_NOT_PROVIDED`, `CANNOT_SELL`;
  USA `available: false` mit `CANNOT_SELL`. **Ungemessen:** was `CANNOT_SELL`
  auslöst (Trader Status, Vertrag oder beides — die Daten trennen es nicht,
  in den USA steht es ohne Trader-Hinweis) und ob die Abos in der Sandbox
  laden (nie getestet).

**Erledigt am 22.10.2026 (über die API, nachgelesen):**

| | |
|---|---|
| ✅ | Die drei Abos in allen 175 Gebieten verfügbar, neue Gebiete automatisch (`asc_abos.py ueberall`). Die App bleibt nur in DEU — verkauft wird also weiter nur dort |
| ✅ | Prüfnotiz der Abos neu (`asc_abos.py notiz`): richtiger Weg statt „Leiste auf dem Aufnahme-Bildschirm" und „Deutschland, Österreich, Schweiz" |
| ✅ | Prüfnotiz der Version: Menüknopf genau benannt, „Platz buchen" zweimal, „Käufe wiederherstellen", Anmeldeweg fürs Prüfkonto, Länderabsatz (3.984 von 4.000 Zeichen) |
| ⬜ | **Business → Agreements**: Paid Applications Agreement muss *Active* sein (nur der Kontoinhaber, die API sieht ihn nicht) |
| ⬜ | **Business → Trader Status** (DSA): Apple meldet für DEU `TRADER_STATUS_NOT_PROVIDED` (nur der Kontoinhaber, die API kennt kein Feld). Ob danach `CANNOT_SELL` verschwindet, ist ungemessen — nachher neu lesen |
| ⬜ | Kauf mit Build 13 aus TestFlight einmal selbst: ☰ → „Deine Ablage" → „Platz buchen". Erst wenn Apples Kaufblatt erscheint, gilt Punkt 2 der Antwort |
| ⬜ | Antwort im Resolution Center absenden, dann neu einreichen |

## Entwurf (englisch)

Punkt 2 und 4 erst absenden, wenn die beiden offenen Häkchen dazu stehen.

Hello,

thank you for the follow-up. Answers to your four points:

**1. Where to find the In-App Purchases.** Launch babu Belege and either tap
"Los geht's" on the first screen (no account needed) or sign in with the demo
account (apple-review@0711.io; Menu → top row "Mit deiner E-Mail anmelden").
Tap the menu button (three lines, top right) → "Deine Ablage" ("Your archive")
→ "Platz buchen" ("Book storage"). This screen lists the three subscriptions
of the group "babu Speicher" (1 GB, 5 GB, 100 GB). Select one and tap
"Platz buchen" to open the App Store purchase sheet; "Käufe wiederherstellen"
(Restore purchases) is on the same screen. It also opens by itself once the
10 free documents are used up.

**2. Sandbox.** We purchased the subscriptions with a sandbox account on
build 13 via TestFlight.

**3. Restrictions.** Until now, the app and the three subscriptions were
available only in the Germany storefront. A sandbox account from another
storefront therefore received no products, and the screen showed the tiers
without a working purchase. We have made the three subscriptions available in
all storefronts, so they now load for any sandbox account; the app itself
remains distributed in Germany only. There is no restriction by device or
account status.

**4. Paid Applications Agreement.** The Account Holder has accepted it; it
shows as Active under Business → Agreements.

Kind regards
Christoph Bertsch
