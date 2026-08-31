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

// 7. Gutschrift/Storno: erkennen (Buchungsentscheidung liegt beim Server)
let f7 = parse(["Friseurbedarf Groß GmbH", "GUTSCHRIFT", "Betrag -25,00"])
pruefe(f7.gutschriftSignal, "Gutschrift erkannt")

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

// 13. Summe und Gegeben auf EINER Zeile (OCR-Lesefehler): nur Summe zählt
let f13 = parse(["Kiosk Weber", "Summe 66,70 / bar gegeben 70,00"])
pruefe(gleich(f13.brutto, 66.70), "Summe 66,70 trotz Gegeben auf derselben Zeile")

// 20. Fremdwährung: AED-Beleg wird NICHT als Euro gelesen
// (stand bis 31.08.2026 NACH dem exit() und lief deshalb nie)
let f20 = parse(["Uber 13:30", "Gesamtsumme 55,74 AED", "Fahrpreis 45,74 AED",
                "Trinkgeld 5,00 AED"])
pruefe(f20.waehrung == "AED", "AED als Fremdwährung erkannt")
let f20b = parse(["EDEKA", "SUMME € 16,08", "EC-Cash 16,08"])
pruefe(f20b.waehrung == nil, "Euro-Beleg bleibt ohne Fremdwährung")
let f20c = parse(["Hotel Praha", "Total 799,00 CZK", "Karte 799,00"])
pruefe(f20c.waehrung == "CZK", "CZK erkannt")

// 21. Monats-Einteilung der Dokumentenliste: der Monat des BELEGdatums
pruefe(belegMonatSchluessel("03.08.2026") == "2026-08", "03.08.2026 → 2026-08")
pruefe(belegMonatSchluessel("31.12.2025") == "2025-12", "Jahreswechsel bleibt im alten Jahr")
pruefe(belegMonatSchluessel("05.08.26") == "2026-08", "zweistelliges Jahr wird 20xx")
pruefe(belegMonatSchluessel("kein Datum") == nil, "Unlesbares wird nil, nicht geraten")
pruefe(belegMonatSchluessel("01.13.2026") == nil, "Monat 13 gibt es nicht")
pruefe(belegMonatTitel("2026-08") == "August 2026", "Überschrift ist deutsch")
pruefe(belegMonatTitel("2025-03") == "März 2025", "Umlaut-Monat stimmt")

// 22. Ohne Betrag wird nicht gebucht: 0,00 € heißt „die Lesung fehlt noch",
// nicht „kostenloser Beleg". Die Rückfrage hängt an dieser einen Regel.
func huelle(brutto: Double) -> Beleg {
    Beleg(lieferant: "Test", belegNr: "ohne Nr.", datumText: "",
          netto: 0, ust: 0, brutto: brutto, ustSatz: 0, konto: nil,
          steuerschluessel: "0", kreditor: "70000", herkunft: .ki,
          confidence: 0, status: .offen, begruendung: "", summenprobeOK: false)
}
pruefe(huelle(brutto: 0).brauchtBetrag, "0,00 € heißt: Betrag fehlt noch")
pruefe(huelle(brutto: -0.004).brauchtBetrag, "Rundungsnull zählt als fehlend")
pruefe(!huelle(brutto: 119.0).brauchtBetrag, "119,00 € ist buchbar")
pruefe(!huelle(brutto: -50).brauchtBetrag, "Gutschrift (negativ) ist buchbar")

// 23. Das Etikett lügt nicht: ein ungelesener Beleg trägt kein „geprüft".
var offenBeleg = huelle(brutto: 0)
pruefe(offenBeleg.herkunftEtikett == "wird gelesen",
       "Ungelesener Beleg heißt ‚wird gelesen', nicht ‚geprüft'")
offenBeleg.confidence = 87
offenBeleg.status = .bestaetigt
pruefe(offenBeleg.herkunftEtikett == "geprüft",
       "Nach der Lesung darf ‚geprüft' stehen")
offenBeleg.herkunft = .mensch
pruefe(offenBeleg.herkunftEtikett == "Manuell",
       "Von Hand bleibt ‚Manuell'")

// 24. Die Summenprobe segnet keine leeren Belege ab: 0+0=0 ist kein Erfolg.
pruefe(summenprobe(netto: 0, ust: 0, brutto: 0) == .leer,
       "0+0=0 ist leer, nicht bestanden")
pruefe(summenprobe(netto: 100, ust: 19, brutto: 119) == .passt,
       "100+19=119 passt")
pruefe(summenprobe(netto: 0, ust: 0, brutto: 119) == .passtNicht,
       "0+0≠119 fällt durch")
pruefe(summenprobe(netto: 5, ust: 0, brutto: 0) == .passtNicht,
       "Netto ohne Brutto fällt durch")
pruefe(summenprobe(netto: 100, ust: 19, brutto: 119.005) == .passt,
       "Halber Cent ist Rundung, kein Fehler")

// 25. „Bleibt unverändert" nur, wenn es stimmt: bis zur Fixierung ist
// eine Korrektur möglich — und wird neu festgehalten.
var gesiegelt = huelle(brutto: 119)
gesiegelt.status = .bestaetigt
pruefe(gesiegelt.siegelZusatz == "eine Korrektur wird neu festgehalten",
       "Vor der Fixierung verspricht das Siegel keine Unveränderlichkeit")
gesiegelt.status = .fixiert
pruefe(gesiegelt.siegelZusatz == "bleibt unverändert",
       "Fixiert heißt wirklich unveränderlich")

print(fehler == 0 ? "\nAlle Prüfungen bestanden." : "\n\(fehler) Prüfung(en) fehlgeschlagen.")
exit(fehler == 0 ? 0 : 1)

