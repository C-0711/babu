# Kartenzahlung mit dem Telefon

Die Kundin hält ihre Karte an die Rückseite des iPhones, fertig. Kein
Terminal, keine Miete, kein Kabel. Apple nennt es *Tap to Pay on iPhone*.

Der Code dafür steht vollständig. Was fehlt, ist nichts Technisches.

## Die drei Hürden

**1. Das Gerät** — iPhone XS oder neuer, aktuelles iOS, unterstütztes Land.
Deutschland ist dabei. Prüfen lässt sich das nur auf echter Hardware: der
Simulator meldet Bereitschaft, ohne welche zu haben, und die App sagt dort
deshalb ausdrücklich „nicht feststellbar" statt einen Haken zu setzen.

**2. Apples Freigabe** — die Berechtigung
`com.apple.developer.proximity-reader.payment.acceptance` muss dem Bundle
`io.0711.beleg` zugeteilt werden. Das geht über das Apple-Developer-Konto
auf Antrag und dauert. Die fertige Datei liegt unter
`ios/Beleg/Support/Beleg.entitlements` — **absichtlich nicht im Build**:
solange Apple nicht zugeteilt hat, scheitert jede Signierung, die sie
anfordert, und die App ließe sich nicht einmal mehr auf Ninas Telefon
installieren. Nach der Zuteilung in `project.yml` eintragen:

```
CODE_SIGN_ENTITLEMENTS: Support/Beleg.entitlements
```

**3. Ein Zahlungsdienstleister** — und das ist die eigentliche Hürde. Ohne
ihn geht gar nichts, auch kein Sandkasten: `PaymentCardReader.prepare()`
verlangt ein Sitzungs-Token, das nur ein zugelassener Anbieter ausstellt,
nachdem er den Salon geprüft hat. Wer Karten liest, ist in der
Zahlungskette drin; babu ist es nicht und soll es nicht werden.

Für einen deutschen Salon kommen unter anderem SumUp, Stripe und Adyen in
Frage. Das ist eine Geschäftsentscheidung mit Vertrag und Gebühren, keine
Programmierfrage — deshalb steht hier kein Name.

## Was heute schon geht

Der Prüfstand unter **Konto → Kartenzahlung** spielt den ganzen Ablauf
durch: Betrag eingeben, kassieren, Beleg bekommen, auch der Fall
„Karte abgelehnt". Es fließt kein Geld, und jeder Beleg daraus ist
sichtbar als Prüfstandsbeleg gekennzeichnet.

Dasselbe steckt im Abrechnen-Blatt am Termin: bei Zahlart *Karte* steht
dort „Kartenzahlung durchspielen", und sobald ein Anbieter angebunden ist,
heißt derselbe Knopf „Mit dem Telefon kassieren". Es ändert sich nichts
außer der Beschriftung.

## Wenn der Anbieter da ist

Genau eine Stelle wird angefasst: `KartenTerminal.tokenHolen` bekommt eine
Funktion, die beim Anbieter ein Sitzungs-Token holt. Alles darüber —
Betragsprüfung, Kassenbuch, Referenz — bleibt, wie es ist.

Die Referenz ist dabei kein Beiwerk: sie ist das Einzige, was Kassenbuch
und Kontoauszug später zusammenbringt. Sie wird bei jeder echten
Kartenzahlung mitgeschrieben (`termin.zahlung_ref`), bei einem
Prüfstandsbeleg ausdrücklich nicht.

## Und die Kasse?

babu bucht auch mit Karte nur einen **Vorschlag** fürs Kassenbuch, den die
Inhaberin bestätigt. Das bleibt so. Wer Umsätze selbst festschreibt, ist
eine Kasse im Sinne von § 146a AO und braucht eine zertifizierte technische
Sicherheitseinrichtung — eine ganz andere Baustelle als ein Kartenleser.
