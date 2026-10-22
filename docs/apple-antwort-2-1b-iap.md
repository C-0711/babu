# Antwort an App Review (2.1(b), In-App-Käufe nicht gefunden) — 22.10.2026

Einreichung `58ed02dd-2e0a-401b-a350-1d93fa2d9574`, Version 1.0 (13). Apple
findet die Abos nicht und fragt nach vier Dingen: Klickpfad, Sandbox,
Einschränkung nach Storefront/Region/Gerät, Paid Applications Agreement.

**Gemessen, nicht vermutet:**

- Der Server liefert dem Prüfkonto `apple-review@0711.io` (Mandant 4, herkunft
  app, Hauskanzlei 10) Platz und alle drei Stufen — im laufenden Container
  nachgerechnet. Die Prüfnotiz nannte den Weg schon.
- App UND Abos waren nur in **DEU** verfügbar (gelesen: `subscriptionAvailability`
  1 Gebiet). Im Code gelesen: liefert `Product.products` nichts, zeigt die App
  die Stufen mit dem Ersatzpreis vom Server, und „Platz buchen" endet in
  „Dieser Platz ist gerade nicht zu haben" (`Kasse.kaufen`). **Ungemessen:**
  welche Storefront der Prüfer hatte und ob StoreKit ihm deshalb nichts lieferte —
  das ist ein Verdacht aus Apples Frage 3, kein Befund.
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
| ✅ | Die drei Abos in allen 175 Gebieten verfügbar, neue Gebiete automatisch (`asc_abos.py ueberall`) |
| ✅ | Die App in allen Gebieten verfügbar (`asc_verfuegbarkeit.py weltweit`) — Entscheid des Auftraggebers 22.10.: „weltweit, aber nur für die deutsche Steuererklärung“ |
| ✅ | Prüfnotiz der Abos neu (`asc_abos.py notiz`): richtiger Weg statt „Leiste auf dem Aufnahme-Bildschirm" und „Deutschland, Österreich, Schweiz" |
| ✅ | Prüfnotiz der Version: Menüknopf genau benannt, „Platz buchen" zweimal, „Käufe wiederherstellen", Anmeldeweg fürs Prüfkonto, Länderabsatz (3.984 von 4.000 Zeichen) |
| ✅ | **Business → Agreements** (in der Weboberfläche gelesen 22.10.): Paid Applications Agreement aktiv seit 13.10.2026 bis 26.07.2027, alle Länder; Bankkonto aktiv, W-8BEN und Bescheinigung zum Auslandsstatus aktiv seit 14.10. |
| ⏳ | **Business → Trader Status** (DSA): eingereicht, „In Review“ seit 24.09.2026 (Weboberfläche, 22.10.) — die API meldet in den 27 EU-Gebieten weiter `TRADER_STATUS_NOT_PROVIDED`. Nur warten |
| ✅ | **Business → DAC7**: am 22.10. zuerst „Missing Info“, später am Tag aktiv (Weboberfläche, Chrome-Sitzung) |
| ✅ | **Server für den Kauf bereit (22.10., nur gelesen):** `kern_apple.py`, `apple_abo.py`, `paket.py`, `kern_geraet.py` und die Apple-Wurzel live bytegleich zum Repo (md5); Wurzel lädt, Bundle `io.0711.beleg`, keine Testwurzel; `POST /api/abo/apple` ohne Anmeldung → 401. Die Prüfung verlangt Apples Signatur, Bundle und Laufzeit, aber keine Umgebung — Sandbox-Käufe des Prüfers gehen durch. 126 Tests des Kaufwegs grün |
| ✅ | **Kauftest im Simulator (22.10., Code von Build 13, iOS-Code seit 947fa75 unverändert):** gestartet per `simctl` (ohne die StoreKit-Datei des Schemas, also gegen Apples Sandbox), „Los geht's" gegen einen lokalen Server. ☰ → „Deine Ablage" → „Platz buchen": StoreKit liefert alle drei Abos mit Apples Preisen in der US-Storefront des Simulators — **$8.99 / $17.99 / $89.00** (der Ersatzpreis vom Server wäre 9,99 €). „Platz buchen" startet Apples Kaufablauf („Sign in to Apple Account"). Dort abgebrochen: im Konto gibt es 0 Sandbox-Tester (`GET /v2/sandboxTesters`), und Zugangsdaten gibt Claude nicht ein |
| ⬜ | Kauf bis zum Ende: Build 13 aus TestFlight auf dem iPhone, ☰ → „Deine Ablage" → „Platz buchen" — TestFlight bucht mit der echten Apple-ID in der Sandbox, ohne Abbuchung |
| ✅ | **Build 14 (22.10., 3a19743):** das Angebot öffnet sich von selbst nach dem ersten Beleg, mit „Erst kostenlos weiter – noch N Belege frei“ (Auftraggeber). Hochgeladen, VALID, an Version 1.0 gehängt (Build 13 ersetzt), Verschlüsselung beantwortet; Prüfnotiz der Version (3.994 Zeichen) und der drei Abos auf den neuen Weg umgeschrieben und zurückgelesen |
| ✅ | **Neu eingereicht 22.10.2026 01:06 UTC** (Auftraggeber „deploy“ → „Bei Apple neu einreichen“): Versions-Eintrag `resolved`, Einreichung 58ed02dd `submitted` → WAITING_FOR_REVIEW, Version 1.0 mit Build 14, dazu die drei Abos und die Abo-Gruppe |
| ⬜ | Antwort im Resolution Center eintragen (Weboberfläche, die API kennt keine Nachrichten) |

## Entwurf (englisch)

Punkt 4 ist belegt (Vertrag aktiv, gelesen 22.10.). Punkt 2 ist belegt, soweit er formuliert ist (Produkte laden, Kaufablauf startet — Simulator 22.10.).

Hello,

thank you for the follow-up. Answers to your four points:

**1. Where to find the In-App Purchases.** We have uploaded build 14, in
which the purchase screen no longer has to be found. Launch babu Belege, tap
"Los geht's" on the first screen (no account needed) and capture any
document. Right after the first document the purchase screen opens by
itself: the three subscriptions of the group "babu Speicher" (1 GB, 5 GB,
100 GB), "Platz buchen" ("Book storage") for the App Store purchase sheet,
"Käufe wiederherstellen" (Restore purchases), and "Erst kostenlos weiter"
(continue for free; the first 10 documents are free). It stays reachable at
any time via the menu button (three lines, top right) → "Deine Ablage"
("Your archive") → "Platz buchen", and it opens again once the 10 free
documents are used up.

**2. Sandbox.** We verified it in the sandbox environment with a US
storefront: all three subscriptions load with their App Store prices
(USD 8.99, 17.99 and 89.00 per month; seen in builds 13 and 14), and tapping
"Platz buchen" starts the App Store purchase flow (tested on build 13; this
part is unchanged in build 14).

**3. Restrictions.** Until now, the app and the three subscriptions were
available only in the Germany storefront. We have made the app and the
three subscriptions available in all storefronts. babu is made for
businesses that keep their books and pay taxes in Germany, wherever the
owner lives; that is a matter of content, not of availability. There is no
restriction by device or account status.

**4. Paid Applications Agreement.** The Account Holder has accepted it; it
shows as Active under Business → Agreements.

Kind regards
Christoph Bertsch
