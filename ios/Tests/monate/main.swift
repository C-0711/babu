import Foundation

// Monats-Harness: die Dokumentenliste ordnet nach Monaten. Was hier schief
// geht, sieht Nina als Beleg im falschen Monat — oder als gar keinen.
// Läuft als swiftc-Binary auf macOS: ios/Tests/run.sh

var fehler = 0
func pruefe(_ b: Bool, _ n: String) { print("\(b ? "✓" : "✗") \(n)"); if !b { fehler += 1 } }

func beleg(_ lieferant: String, _ datum: String, _ brutto: Double = 10) -> Beleg {
    Beleg(lieferant: lieferant, belegNr: "1", datumText: datum,
          netto: brutto, ust: 0, brutto: brutto, ustSatz: 0,
          konto: "6300", steuerschluessel: "0", kreditor: "70001",
          herkunft: .regel, confidence: 90, status: .automatisch,
          begruendung: "", summenprobeOK: true)
}

// 1. Der Schlüssel aus dem Belegdatum
pruefe(Monatsgruppen.schluessel("05.08.2026") == "2026-08", "05.08.2026 → 2026-08")
pruefe(Monatsgruppen.schluessel("01.12.2025") == "2025-12", "einstelliger Tag, Dezember")
pruefe(Monatsgruppen.schluessel("05.08.26") == "2026-08", "zweistelliges Jahr vom Bon")
pruefe(Monatsgruppen.schluessel("32.13.2026") == "", "unmögliches Datum zählt nicht")
pruefe(Monatsgruppen.schluessel("") == "", "leeres Datum zählt nicht")
pruefe(Monatsgruppen.schluessel("2026-08-05") == "", "ISO ist kein Belegdatum")

// 2. Die Beschriftung — deutsch, ohne Technik
pruefe(Monatsgruppen.titel("2026-08") == "August 2026", "Überschrift „August 2026“")
pruefe(Monatsgruppen.titel("") == "Ohne Datum", "ohne Datum bekommt eine Überschrift")
pruefe(Monatsgruppen.kurz("2026-08") == "Aug 26", "Kurzform für die Monatsleiste")
pruefe(Monatsgruppen.kurz("2025-03") == "Mär 25", "Umlaut-Monat kurz")

// 3. Gruppieren: jüngster Monat oben, ohne Datum ganz unten
let gruppen = Monatsgruppen.gruppieren([
    beleg("dm", "12.07.2026", 20),
    beleg("Unlesbar", "", 5),
    beleg("Hetzner", "01.08.2026", 238),
    beleg("Stadtwerke", "03.08.2026", 412),
])
pruefe(gruppen.map(\.schluessel) == ["2026-08", "2026-07", ""],
       "August vor Juli, ohne Datum zuletzt")
pruefe(gruppen[0].dokumente.map(\.lieferant) == ["Stadtwerke", "Hetzner"],
       "im Monat der jüngste Tag zuerst")
pruefe(gruppen[0].titel == "August 2026", "Monatskopf trägt den Namen")
pruefe(abs(gruppen[0].summe - 650.00) < 0.005, "Summe des Monats stimmt")
pruefe(gruppen[2].dokumente.count == 1, "der undatierte Beleg verschwindet nicht")

// 4. Kein Beleg geht beim Gruppieren verloren
let viele = (1...31).map { beleg("Bon \($0)", String(format: "%02d.09.2026", $0)) }
let g4 = Monatsgruppen.gruppieren(viele)
pruefe(g4.count == 1 && g4[0].dokumente.count == 31, "alle 31 Tage in einem Monat")
pruefe(g4[0].dokumente.first?.lieferant == "Bon 31", "der 31. steht oben")

// 5. Gleicher Tag: die Reihenfolge der Liste entscheidet (zuletzt aufgenommen
//    zuerst — die Liste stellt neue Aufnahmen nach vorn)
let g5 = Monatsgruppen.gruppieren([beleg("Zuletzt", "04.08.2026"),
                                   beleg("Davor", "04.08.2026")])
pruefe(g5[0].dokumente.map(\.lieferant) == ["Zuletzt", "Davor"],
       "gleicher Tag behält die Reihenfolge der Liste")

// 6. Die Ablage auf dem Server: das Datum im Namen schlägt die Uploadzeit
pruefe(Monatsgruppen.schluesselAusName("beleg_2026-08-05_dm_ab12cd34.jpg") == "2026-08",
       "Monat aus dem Ablagenamen")
pruefe(Monatsgruppen.schluesselAusName("beleg_0000-00-00_dm_ab12cd34.jpg") == "",
       "Platzhalterdatum zählt nicht")
pruefe(Monatsgruppen.schluesselFuerAblage(name: "beleg_2026-08-05_dm.jpg",
                                          zeit: "2026-09-30T10:00:00") == "2026-08",
       "später hochgeladen, trotzdem Augustbeleg")
pruefe(Monatsgruppen.schluesselFuerAblage(name: "kontoauszug.pdf",
                                          zeit: "2026-09-30T10:00:00") == "2026-09",
       "ohne Datum im Namen zählt die Ablagezeit")
pruefe(Monatsgruppen.schluesselFuerAblage(name: "post.pdf", zeit: nil) == "",
       "ohne alles: ohne Datum")

print(fehler == 0 ? "Alles grün." : "\(fehler) Fehlschläge")
exit(fehler == 0 ? 0 : 1)
