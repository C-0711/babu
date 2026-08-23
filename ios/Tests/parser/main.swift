import Foundation

// Parser-Harness: die Randfälle, die im Salon-Alltag echtes Geld kosten.
// Läuft als swiftc-Binary auf macOS: ios/Tests/run.sh

var fehler = 0
func pruefe(_ b: Bool, _ n: String) { print("\(b ? "✓" : "✗") \(n)"); if !b { fehler += 1 } }
func gleich(_ a: Double?, _ b: Double) -> Bool { a.map { abs($0 - b) < 0.005 } ?? false }
func parse(_ zeilen: [String]) -> Felder {
    FeldParser.parse(zeilen: zeilen.map { ($0, 0.95) })
}

// 1. Betrag ≥ 1.000 € OHNE Tausenderpunkt (viele Kassen drucken so)
let f1 = parse(["Friseurbedarf Groß GmbH", "Rechnungs-Nr.: 4711",
                "Rechnungsdatum: 05.08.2026",
                "Netto 1037,45", "USt 19% 197,11", "Gesamt 1234,56"])
pruefe(gleich(f1.brutto, 1234.56), "1234,56 ohne Punkt wird gelesen")
pruefe(f1.summenprobeOK, "Summenprobe über die Steuertabelle hält")
pruefe(f1.datumText == "05.08.2026", "Datum von der Datums-Zeile")
pruefe(f1.belegNr == "4711", "Beleg-Nr. über Label")

// 2. Barbon mit Gegeben/Rückgeld: 44,50 + 5,50 = 50,00 darf NICHT bestehen
let f2 = parse(["Gasthaus Sonne", "SUMME 44,50", "GEGEBEN 50,00", "RÜCKGELD 5,50"])
pruefe(gleich(f2.brutto, 44.50), "Brutto ist die Summe, nicht das Gegeben")
pruefe(f2.bewirtungsSignal, "Gasthaus erkannt")
pruefe(f2.ustSatz == 0 && gleich(f2.ust, 0),
       "ohne Steuerausweis keine erfundenen 19 %")

// 3. §19-Kleinunternehmer: keine Vorsteuer erfinden
let f3 = parse(["Kosmetikstudio Elke", "Gemäß §19 UStG keine Umsatzsteuer ausgewiesen",
                "Gesamt 25,00"])
pruefe(f3.ustSatz == 0, "§19 → Satz 0")
pruefe(gleich(f3.ust, 0), "keine erfundene Steuer")
pruefe(gleich(f3.netto, 25.00), "Netto = Brutto ohne Steuerausweis")

// 4. Unplausibles Datum wird übersprungen
let f4 = parse(["Shop", "Kd 32.13.2026", "gekauft am 05.08.2026", "9,99"])
pruefe(f4.datumText == "05.08.2026", "32.13. verworfen, gültiges Datum gewinnt")

// 5. Mehrsatz-Bon (7 % + 19 %): Positionen bleiben getrennt erhalten
let f5 = parse(["REWE Markt", "A 19% 15,97 3,03 19,00", "B 7% 79,81 5,59 85,40",
                "SUMME 104,40"])
pruefe(f5.steuerPositionen.count == 2, "zwei Steuer-Positionen erkannt")
pruefe(gleich(f5.brutto, 104.40), "Brutto = Summe beider Sätze")
pruefe(f5.steuerPositionen.contains { $0.satz == 7 && abs($0.brutto - 85.40) < 0.005 },
       "7-%-Zeile einzeln erhalten (85,40-Regression)")

// 6. Über den Satz-Token gesplittete Tabelle (Geräte-OCR-Muster)
let f6 = parse(["Weingärtle", "79,81 85,40", "7% 5,59"])
pruefe(gleich(f6.brutto, 85.40), "gesplittete 7-%-Zeile aufgelöst")

// 7. Gutschrift/Storno: erkennen und nie automatisch siegeln
let f7 = parse(["Friseurbedarf Groß GmbH", "GUTSCHRIFT", "Betrag -25,00"])
pruefe(f7.gutschriftSignal, "Gutschrift erkannt")
pruefe(Kontierung.vorschlag(felder: f7).confidence <= 70,
       "Gutschrift bleibt unter der Auto-Siegel-Schwelle")

// 8. Normalfall bleibt normal (keine Regression)
let f8 = parse(["Blumen Riedle", "Bon 5512", "03.08.2026", "19% MwSt", "12,61", "2,39", "15,00"])
pruefe(gleich(f8.brutto, 15.00), "einfacher Bon: Brutto 15,00")
pruefe(!f8.gutschriftSignal, "kein falsches Gutschrift-Signal")

// 9. Gegeben minus Rückgeld muss der Betrag sein — sonst ist eine der drei
//    Zahlen falsch gelesen. Genau so fällt ein verlesener Endbetrag auf.
let f9 = parse(["Kiosk Meier", "SUMME 54,50", "Netto 45,80", "MwSt 19% 8,70",
                "GEGEBEN 50,00", "RÜCKGELD 5,50"])
pruefe(!f9.summenprobeOK, "Bargeld geht nicht auf: 50,00 − 5,50 ≠ 54,50")

// 10. Mehr gegeben als nötig ist Trinkgeld, kein Lesefehler
let f10 = parse(["Gasthaus Sonne", "SUMME 44,50", "GEGEBEN 50,00", "RÜCKGELD 3,00"])
pruefe(gleich(f10.brutto, 44.50), "Trinkgeld ändert den Rechnungsbetrag nicht")

// 11. Beleg ohne jeden Steuerausweis (Porto, Versicherung, Beitrag): 0 %.
//     19 % anzunehmen wäre Vorsteuer, die auf keinem Beleg stand.
let f11 = parse(["Deutsche Post Filiale", "Porto Briefmarken", "Summe 8,50"])
pruefe(f11.ustSatz == 0, "kein Steuerausweis → Satz 0")
pruefe(gleich(f11.netto, 8.50) && gleich(f11.ust, 0), "netto gleich brutto")

// 12. 7 % steht auch neben 19 % noch da (Zeitschrift im Wartezimmer)
let f12 = parse(["Presse Müller", "Zeitschrift 7,00 %", "Netto 4,67",
                 "MwSt 0,33", "Summe 5,00"])
pruefe(f12.ustSatz == 7, "7,00 % wird als 7 gelesen")

print(fehler == 0 ? "\nAlle Prüfungen bestanden." : "\n\(fehler) Prüfung(en) fehlgeschlagen.")
exit(fehler == 0 ? 0 : 1)
