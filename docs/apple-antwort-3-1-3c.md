# Antwort an App Review (3.1.3(c)) — Entwurf, 15.10.2026

Einreichung `ea12ce78-131a-4ca4-bd94-360c72a6de17`, Prüfung 15.10.2026,
Version 1.0 (13). Noch offen ist allein der Punkt 3.1.1 / 3.1.3(c)
„Enterprise Services"; der Beschreibungstext aus der Prüfung vom 09.10.
(„ZUGANG … von deinem Steuerbüro oder über mybabu.io") steht nicht mehr in
den Store-Texten.

**Stand 15.10.2026 — was erledigt ist und was nicht:**

| | |
|---|---|
| ✅ | Prüfnotiz neu (3.724 von 4.000 Zeichen erlaubt): Abschnitt „ONE PAYMENT PATH ONLY" mit der 3.1.1/3.1.3(c)-Linie, der Kaufweg Schritt für Schritt, der Löschweg, und der Hinweis, dass der Beispiel-Beleg-Knopf nur im Simulator existiert |
| ✅ | Prüfkonto `apple-review@0711.io` ist jetzt ein Einzelbetrieb: Mandant 4 „Salon Probe" steht unter der Hauskanzlei „babu direkt" mit `herkunft = app`. Damit zeigt die App die drei Stufen, der Kauf lässt sich eintragen, und „Konto löschen" funktioniert |
| ✅ | Ein Fehler im Kaufweg behoben, der genau an diesem Konto hing (siehe unten) |
| ⬜ | **Die drei Abos der Einreichung beilegen — das muss von Hand passieren.** Die API kann es nicht: `reviewSubmissionItems` nimmt `appStoreVersion`, `appEvent`, `appCustomProductPageVersion` und `appStoreVersionExperimentV2`, aber keine Abos (`'subscription' is not a relationship on the resource 'reviewSubmissionItems'`). Weg in App Store Connect: **App → Version 1.0 → Abschnitt „In-App-Käufe und Abos" → die drei Abos auswählen → „Zur Überprüfung hinzufügen"**, dann mit der Version zusammen einreichen |
| ⬜ | **Paid Applications Agreement (W-8BEN).** Ohne ihn liefert `Product.products(for:)` eine leere Liste — der Kaufbildschirm wäre leer, auch im Sandkasten, und die nächste Ablehnung wäre dieselbe |

**Der Fehler im Kaufweg.** Zwei Routen beantworteten die Frage „zu welchem
Betrieb gehört dieser Zugang?" verschieden: `/api/ich` über
`babu_web._eigener_mandant` (Besitzer, egal unter welcher Kanzlei),
`/api/abo/apple` über `testmonat.direkt_mandant_von` (nur die Hauskanzlei).
Für jeden Betrieb aus „Los geht's" ist das dasselbe — für einen Betrieb
unter einer Kanzlei nicht: Kaufbildschirm sichtbar, Meldung des Kaufs
danach 404. Apple hätte abgebucht, und der Platz wäre nie eingetragen
worden. Genau so ein Zugang war Apples Prüfkonto. `/api/abo/apple` fragt
jetzt wie der Rest des Servers; vier Tests, einer davon Negativkontrolle.

---

## Entwurf (englisch)

Hello,

thank you for the detailed review. We would like to clarify how babu is
sold, because we believe the enterprise-services finding rests on a part of
our setup that the reviewer could not see.

**babu is not sold to organizations through the app.** The app is made for a
single owner-operated business — a hair salon, a nail studio, a one-person
workshop. The person who photographs the receipt is the owner of the
business. There is no seat licensing, no group purchase and no volume
contract anywhere in the app.

**Inside the app, In-App Purchase is the only way to pay.** After the first
10 free documents, the user picks one of three auto-renewable monthly
subscriptions, which differ only in storage space:

* `babu.speicher.1gb` — 1 GB, EUR 9.99/month
* `babu.speicher.5gb` — 5 GB, EUR 19.99/month
* `babu.speicher.100gb` — 100 GB, EUR 99.00/month

Every feature is included in all three; a higher tier unlocks nothing. The
app contains no other payment path, no price list pointing elsewhere, and no
account registration link. Starting the app requires no account at all:
"Los geht's" creates the workspace on the device.

**The separate channel for tax firms.** babu also has a web portal where a
German tax advisor manages their own clients' bookkeeping. That is a
business-to-business relationship between us and the tax firm, it is not
reachable from the app, it is not advertised in the app or in our App Store
description, and no app user can buy or extend anything there. We kept these
two worlds apart deliberately: the App Store customer pays through In-App
Purchase, and only through In-App Purchase.

**Two corrections on our side, so the next review shows what we describe.**
First, the three subscriptions are part of this submission; in the reviewed
build they were configured but not submitted. Second, the demo account we
had provided belonged to the tax-firm side and therefore had no storage
tiers at all — signed in with it, the app genuinely offered nothing to buy.
It is now an ordinary single owner-operated business with tiers, so the
purchase screen works both with that account and after tapping "Los geht's"
on first launch, which needs no account at all.

We are happy to answer any further question here.

Kind regards
Christoph Bertsch
