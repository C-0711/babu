// Kartenzahlung: die Teile, die ohne Gerät und ohne Anbieter prüfbar sind.
//
// Das Lesen der Karte gehört Apple und dem Zahlungsdienstleister. Was babu
// gehört, ist alles davor und danach: Was fehlt noch? Stimmt der Betrag?
// Und vor allem — wird nichts gebucht, was nicht angekommen ist.
import Foundation

var fehler = 0

func pruefe(_ was: String, _ bedingung: Bool) {
    print(bedingung ? "✓ \(was)" : "✗ \(was)")
    if !bedingung { fehler += 1 }
}

// ————— Was fehlt noch? Immer nur die nächste Hürde zeigen —————

pruefe("alles da → bereit",
       Kartenpruefung.lage(geraet: .erfuellt, freigabe: .erfuellt,
                           anbieter: .erfuellt) == .bereit)

pruefe("altes Gerät schlägt alles andere",
       Kartenpruefung.lage(geraet: .offen, freigabe: .offen,
                           anbieter: .offen) == .geraetKannNicht)

pruefe("Gerät ok, Apple fehlt",
       Kartenpruefung.lage(geraet: .erfuellt, freigabe: .offen,
                           anbieter: .erfuellt) == .freigabeFehlt)

pruefe("Gerät und Apple ok, Anbieter fehlt",
       Kartenpruefung.lage(geraet: .erfuellt, freigabe: .erfuellt,
                           anbieter: .offen) == .anbieterFehlt)

// Die Reihenfolge ist der Punkt: Nina soll nicht drei Hürden auf einmal
// lesen, sondern die, die als Nächstes dran ist.
pruefe("bei zwei offenen Punkten zuerst die Freigabe",
       Kartenpruefung.lage(geraet: .erfuellt, freigabe: .offen,
                           anbieter: .offen) == .freigabeFehlt)

// ————— „Weiß nicht" wird nie zu „ja" —————
//
// Der erste Durchlauf im Simulator meldete „Apples Freigabe ist erteilt".
// Sie war es nicht — es ließ sich nur nicht feststellen, und der Code hat
// daraus einen grünen Haken gemacht. Damit schickt man jemanden mit
// falscher Sicherheit zur Kundin.

pruefe("unbekanntes Gerät ist nicht bereit",
       Kartenpruefung.lage(geraet: .unbekannt, freigabe: .erfuellt,
                           anbieter: .erfuellt) == .unklar)

pruefe("unbekannte Freigabe ist nicht bereit",
       Kartenpruefung.lage(geraet: .erfuellt, freigabe: .unbekannt,
                           anbieter: .erfuellt) == .unklar)

pruefe("unbekannter Anbieter ist nicht bereit",
       Kartenpruefung.lage(geraet: .erfuellt, freigabe: .erfuellt,
                           anbieter: .unbekannt) == .anbieterFehlt)

pruefe("bereit gibt es NUR, wenn alles dreifach feststeht",
       [Huerdenstand.erfuellt, .offen, .unbekannt].allSatisfy { a in
           [Huerdenstand.erfuellt, .offen, .unbekannt].allSatisfy { b in
               [Huerdenstand.erfuellt, .offen, .unbekannt].allSatisfy { c in
                   (Kartenpruefung.lage(geraet: a, freigabe: b, anbieter: c)
                        == .bereit)
                   == (a == .erfuellt && b == .erfuellt && c == .erfuellt)
               }
           }
       })

pruefe("ein feststehendes Nein schlägt ein Weiß-nicht",
       Kartenpruefung.lage(geraet: .offen, freigabe: .unbekannt,
                           anbieter: .unbekannt) == .geraetKannNicht)

pruefe("jede Lage erklärt sich auf Deutsch",
       [Kartenlage.bereit, .geraetKannNicht, .freigabeFehlt, .anbieterFehlt,
        .unklar].allSatisfy { $0.satz.count > 20 })

pruefe("nur die fertige Lage hat keinen nächsten Schritt",
       Kartenlage.bereit.naechstes == nil
       && Kartenlage.freigabeFehlt.naechstes != nil)

// ————— Beträge: in Cent, nie in Fließkomma —————

pruefe("42,00 sind 4200 Cent", Kartenbetrag(euro: "42,00")?.cent == 4200)
pruefe("Punkt statt Komma geht auch", Kartenbetrag(euro: "42.00")?.cent == 4200)
pruefe("mit Eurozeichen", Kartenbetrag(euro: "42,00 €")?.cent == 4200)
pruefe("Tausenderpunkt", Kartenbetrag(euro: "1.250,00")?.cent == 125_000)
pruefe("krummer Betrag", Kartenbetrag(euro: "12,50")?.cent == 1250)

// Der Fehler, der bei Geld am teuersten ist: 0,1 + 0,2 ergibt in Double
// nicht 0,3. In Cent gerechnet stimmt die Summe.
let summe = (Kartenbetrag(euro: "0,10")!.cent + Kartenbetrag(euro: "0,20")!.cent)
pruefe("0,10 + 0,20 sind genau 0,30", summe == 30)
pruefe("und lesen sich auch so", Kartenbetrag(cent: summe).text == "0,30 €")

pruefe("null wird abgelehnt", Kartenbetrag(euro: "0") == nil)
pruefe("minus wird abgelehnt", Kartenbetrag(euro: "-5,00") == nil)
pruefe("Buchstaben werden abgelehnt", Kartenbetrag(euro: "viel") == nil)
pruefe("leer wird abgelehnt", Kartenbetrag(euro: "") == nil)
pruefe("unrealistisch hoch wird abgelehnt", Kartenbetrag(euro: "999999") == nil)

pruefe("Cent-Darstellung mit führender Null",
       Kartenbetrag(cent: 705).text == "7,05 €")

// Der Punkt ist die Falle. Genau hier stand schon einmal ein Fehler im
// Server, der aus 12,50 € Trinkgeld 125 € gemacht hat — an der Kasse wäre
// derselbe Griff teurer.
pruefe("42.00 sind zweiundvierzig Euro, nicht viertausend",
       Kartenbetrag(euro: "42.00")?.cent == 4200)
pruefe("1.250 ist Tausendertrennung", Kartenbetrag(euro: "1250")?.cent == 125_000
       && Kartenbetrag(euro: "1.250")?.cent == 125_000)
pruefe("1.250,00 auch mit Komma", Kartenbetrag(euro: "1.250,00")?.cent == 125_000)
pruefe("1.250.000 bleibt Tausendertrennung",
       Kartenbetrag(euro: "1.250.000") == nil)     // über der Obergrenze
pruefe("12.50 ist zwölf fünfzig", Kartenbetrag(euro: "12.50")?.cent == 1250)
pruefe("42.5 ist kein Dezimalpunkt-Muster → 425 €",
       Kartenbetrag(euro: "42.5")?.cent == 42500)
pruefe("ganze Zahl ohne Trennung", Kartenbetrag(euro: "42")?.cent == 4200)

// ————— Der Prüfstand verhält sich wie eine echte Kasse —————

let semaphore = DispatchSemaphore(value: 0)
var ergebnisse: [String: Bool] = [:]

Task {
    let kasse = ProbeKasse(lage: .anbieterFehlt, verzoegerung: 0)
    if let beleg = try? await kasse.kassieren(Kartenbetrag(cent: 4200)) {
        ergebnisse["betrag stimmt"] = beleg.betrag.cent == 4200
        ergebnisse["als Probe gekennzeichnet"] = beleg.probe
        ergebnisse["hat eine Referenz"] = !beleg.referenz.isEmpty
    }

    // Eine abgelehnte Karte darf keinen Beleg erzeugen — sonst steht Geld
    // im Kassenbuch, das nie angekommen ist.
    let ablehnend = ProbeKasse(lage: .anbieterFehlt, verzoegerung: 0,
                               lehntAb: "Karte abgelehnt.")
    do {
        _ = try await ablehnend.kassieren(Kartenbetrag(cent: 4200))
        ergebnisse["Ablehnung wirft"] = false
    } catch {
        ergebnisse["Ablehnung wirft"] = true
        ergebnisse["Ablehnung erklärt sich"] =
            (error as? Kartenfehler)?.errorDescription?.isEmpty == false
    }

    // Zwei Belege dürfen nie dieselbe Referenz tragen.
    let a = try? await kasse.kassieren(Kartenbetrag(cent: 100))
    let b = try? await kasse.kassieren(Kartenbetrag(cent: 100))
    ergebnisse["Referenzen sind verschieden"] = a?.referenz != b?.referenz

    semaphore.signal()
}
semaphore.wait()

for (was, ok) in ergebnisse.sorted(by: { $0.key < $1.key }) {
    pruefe(was, ok)
}
pruefe("der Prüfstand wurde wirklich durchlaufen", ergebnisse.count == 6)

// ————— Die echte Kasse kassiert nicht ohne Freigabe —————

let semaphore2 = DispatchSemaphore(value: 0)
var echteKasseVerweigert = false
var grund = ""
Task {
    // Kein Anbieter hinterlegt: darf nicht einmal versuchen zu lesen.
    let terminal = KartenTerminal(tokenHolen: nil)
    do {
        _ = try await terminal.kassieren(Kartenbetrag(cent: 4200))
    } catch let f as Kartenfehler {
        echteKasseVerweigert = true
        grund = f.errorDescription ?? ""
    } catch {}
    semaphore2.signal()
}
semaphore2.wait()
pruefe("ohne Anbieter wird nicht kassiert", echteKasseVerweigert)
pruefe("und der Grund steht auf Deutsch da", grund.count > 20)

print("")
if fehler == 0 {
    print("Alle Prüfungen bestanden.")
} else {
    print("\(fehler) Prüfung(en) fehlgeschlagen.")
    exit(1)
}
