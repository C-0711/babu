// Harness für die Rechnungslogik — UIKit-frei, läuft auf macOS mit swiftc.
// Muster wie extf/ und parser/: keine Test-Bibliothek, nur Behauptungen.
import Foundation

var fehler = 0
var geprueft = 0

func pruefe(_ was: String, _ bedingung: Bool) {
    geprueft += 1
    if !bedingung {
        fehler += 1
        print("  ✗ \(was)")
    }
}

func pruefeGleich(_ was: String, _ ist: Double, _ soll: Double) {
    pruefe("\(was) (ist \(ist), soll \(soll))", abs(ist - soll) < 0.005)
}

func pos(_ text: String, _ preis: Double, _ satz: Int = 19, menge: Double = 1)
        -> RechnungPosition {
    RechnungPosition(text: text, menge: menge, einzelpreis: preis, ustSatz: satz)
}

// ————— Summen —————
let s1 = Rechnungsrechnung.summe([pos("Stuhlmiete", 450)], kleinunternehmer: false)
pruefeGleich("Netto", s1.netto, 450)
pruefeGleich("Umsatzsteuer 19 %", s1.ust, 85.50)
pruefeGleich("Brutto", s1.brutto, 535.50)
pruefe("ein Steuersatz", s1.jeSatz.count == 1 && s1.jeSatz[0].satz == 19)

// Zwei Sätze auf einer Rechnung werden getrennt ausgewiesen.
let s2 = Rechnungsrechnung.summe([pos("Dienstleistung", 100, 19),
                                  pos("Pflegeprodukt", 50, 7)],
                                 kleinunternehmer: false)
pruefeGleich("Netto zwei Sätze", s2.netto, 150)
pruefeGleich("Steuer zwei Sätze", s2.ust, 22.50)
pruefeGleich("Brutto zwei Sätze", s2.brutto, 172.50)
pruefe("Sätze aufsteigend", s2.jeSatz.map(\.satz) == [7, 19])

// Menge multipliziert, gerundet wird auf den Cent.
let s3 = Rechnungsrechnung.summe([pos("Beratung", 33.33, 19, menge: 3)],
                                 kleinunternehmer: false)
pruefeGleich("Menge × Preis", s3.netto, 99.99)
pruefeGleich("Steuer gerundet", s3.ust, 19.00)
pruefeGleich("Brutto gerundet", s3.brutto, 118.99)

// ————— Kleinunternehmerin: kein Steuerausweis —————
let s4 = Rechnungsrechnung.summe([pos("Stuhlmiete", 450)], kleinunternehmer: true)
pruefeGleich("§19 Netto", s4.netto, 450)
pruefeGleich("§19 keine Steuer", s4.ust, 0)
pruefeGleich("§19 Brutto == Netto", s4.brutto, 450)
pruefe("§19 keine Satz-Tabelle", s4.jeSatz.isEmpty)

// ————— Kleinbetrag —————
pruefe("119 € ist Kleinbetrag", Rechnungsrechnung.istKleinbetrag(119))
pruefe("535,50 € ist keiner", !Rechnungsrechnung.istKleinbetrag(535.50))
pruefe("genau 250 € zählt noch", Rechnungsrechnung.istKleinbetrag(250))

// ————— Was fehlt —————
let voll = Empfaenger(name: "Jana", anschrift: "Blumenweg 2")
pruefe("vollständig → keine Mängel",
       Rechnungsrechnung.fehlt(empfaenger: voll, positionen: [pos("Miete", 450)],
                               brutto: 535.50).isEmpty)
pruefe("ohne Namen → Mangel",
       !Rechnungsrechnung.fehlt(empfaenger: Empfaenger(name: "", anschrift: "x"),
                                positionen: [pos("Miete", 450)], brutto: 535.50).isEmpty)
pruefe("ohne Anschrift über 250 € → Mangel",
       !Rechnungsrechnung.fehlt(empfaenger: Empfaenger(name: "Jana", anschrift: ""),
                                positionen: [pos("Miete", 450)], brutto: 535.50).isEmpty)
pruefe("ohne Anschrift unter 250 € → in Ordnung",
       Rechnungsrechnung.fehlt(empfaenger: Empfaenger(name: "Jana", anschrift: ""),
                               positionen: [pos("Schnitt", 100)], brutto: 119).isEmpty)
pruefe("ohne Position → Mangel",
       !Rechnungsrechnung.fehlt(empfaenger: voll, positionen: [], brutto: 0).isEmpty)
pruefe("Zeile ohne Text → Mangel",
       !Rechnungsrechnung.fehlt(empfaenger: voll, positionen: [pos("", 450)],
                                brutto: 535.50).isEmpty)

// ————— Betrag tippen (der 0,00450-Fehler vom 22.08.) —————
pruefeGleich("450 tippen", betragAusText("450"), 450)
pruefeGleich("mit Komma", betragAusText("450,50"), 450.50)
pruefeGleich("mit Punkt", betragAusText("450.50"), 450.50)
pruefeGleich("Tausenderpunkt", betragAusText("1.250,00"), 1250)
pruefeGleich("mit Euro-Zeichen", betragAusText("450,50 €"), 450.50)
pruefeGleich("leer ist null", betragAusText(""), 0)
pruefeGleich("Quatsch ist null", betragAusText("abc"), 0)
pruefe("Null zeigt nichts an", betragAlsText(0) == "")
pruefe("Betrag deutsch", betragAlsText(450.5) == "450,50")
pruefe("Hin und zurück", betragAusText(betragAlsText(1250.99)) == 1250.99)

// ————— Anzeige —————
pruefe("Datum deutsch", tagKurz("2026-09-30") == "30.09.2026")
pruefe("kaputtes Datum bleibt stehen", tagKurz("quatsch") == "quatsch")

let offen = Rechnung(nummer: "2026-0001", datum: "2026-08-21",
                     empfaengerName: "Jana", netto: 450, ust: 85.5, brutto: 535.5)
pruefe("offen ist offen", offen.istOffen && offen.standText == "offen")
let bezahlt = Rechnung(nummer: "2026-0001", datum: "2026-08-21",
                       empfaengerName: "Jana", netto: 450, ust: 85.5, brutto: 535.5,
                       bezahltAm: "2026-09-02", stand: "bezahlt")
pruefe("bezahlt nennt den Tag", bezahlt.standText == "bezahlt am 02.09.2026")

// ————— Vertragskiste: der ehrliche Satz —————
let sicher = Vertrag(json: ["art_name": "Mietvertrag", "partner": "Sonnenberg",
                            "betrag_monat": 1250.0,
                            "kuendigen_bis": ["datum": "2026-09-30", "tage": 40,
                                              "sicher": true, "hinweis": ""]])!
pruefe("Frist mit Tagen", sicher.fristText == "Kündigen bis 30.09.2026 — noch 40 Tage")
pruefe("Betrag im Monat", sicher.betragText == "\(fmtEur(1250)) im Monat")

let unsicher = Vertrag(json: ["art_name": "Vertrag", "partner": "Unklar",
                              "kuendigen_bis": ["datum": NSNull(), "sicher": false,
                                                "hinweis": "Die Frist steht in deinem Vertrag."]])!
pruefe("Unlesbares wird nicht geraten",
       unsicher.fristText == "Die Frist steht in deinem Vertrag.")
pruefe("ohne Betrag ehrlich", unsicher.betragText == "kein Betrag erkannt")

print(fehler == 0
      ? "  \(geprueft) Prüfungen — alles grün"
      : "  \(fehler) von \(geprueft) Prüfungen gescheitert")
exit(fehler == 0 ? 0 : 1)
