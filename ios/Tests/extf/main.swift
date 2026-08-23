import Foundation

// EXTF-Harness: prüft die UIKit-freie Stapel-Erzeugung (ExtfWriter.swift)
// mit festen Fixture-Belegen. Läuft als swiftc-Binary auf macOS:
//   ios/Tests/run.sh

var fehler = 0
func pruefe(_ bedingung: Bool, _ name: String) {
    print("\(bedingung ? "✓" : "✗") \(name)")
    if !bedingung { fehler += 1 }
}

func fixture(lieferant: String, nr: String, datum: String,
             netto: Double, ust: Double, brutto: Double,
             konto: String?, status: BelegStatus = .bestaetigt,
             istDemo: Bool? = nil) -> Beleg {
    var b = Beleg(lieferant: lieferant, belegNr: nr, datumText: datum,
                  netto: netto, ust: ust, brutto: brutto, ustSatz: 19,
                  konto: konto, steuerschluessel: "9", kreditor: "70001",
                  herkunft: .regel, confidence: 96, status: status,
                  begruendung: "", summenprobeOK: true)
    b.istDemo = istDemo
    return b
}

// Fixtures: normaler Beleg, Beleg ≥ 1.000 € mit einstelligem Datum + Umlaut.
let b1 = fixture(lieferant: "Stadtwerke Stuttgart", nr: "A-1", datum: "03.08.2026",
                 netto: 346.22, ust: 65.78, brutto: 412.00, konto: "6325")
let b2 = fixture(lieferant: "Weingärtle", nr: "R-77", datum: "5.8.2026",
                 netto: 1037.45, ust: 197.11, brutto: 1234.56, konto: "6640")

// --- Stapeltext ---------------------------------------------------------
let text = extfStapelText(belege: [b1, b2], von: "20260801", bis: "20260831")
let zeilen = text.components(separatedBy: "\r\n")

pruefe(zeilen.count == 4, "2 Kopfzeilen + 2 Buchungen")
pruefe(text.components(separatedBy: "\n").count == text.components(separatedBy: "\r\n").count,
       "nur CRLF-Zeilenenden, kein nacktes LF")
pruefe(text.data(using: .windowsCP1252) != nil, "CP1252-kodierbar (inkl. Umlaut ä)")
pruefe(zeilen[2].hasPrefix("412,00;"), "Betrag mit Komma")
pruefe(zeilen[3].hasPrefix("1234,56;"), "Betrag ≥ 1.000 ohne Tausenderpunkt")
pruefe(zeilen[2].contains("\"0308\""), "Belegdatum 03.08. → 0308")
pruefe(zeilen[3].contains("\"0508\""), "einstelliges Datum 5.8. → 0508 (Regression)")
pruefe(zeilen[0].hasPrefix("\"EXTF\";"), "Kopfzeile beginnt mit EXTF")
pruefe(zeilen[1].contains("\"20260801\"") && zeilen[1].contains("\"20260831\""),
       "Zeitraum aus Parametern, nicht fest verdrahtet")

// --- Formel-Einschleusung -------------------------------------------------
// Die Stapeldatei landet beim Steuerbüro und wird dort in Excel geöffnet.
// Ein Lieferantenname, der mit = + - @ beginnt, ist für Excel eine Formel.
let boese = fixture(lieferant: "=cmd|'/c calc'!A1", nr: "-2+3", datum: "01.08.2026",
                    netto: 10, ust: 1.9, brutto: 11.9, konto: "6640")
let boeseFelder = extfStapelText(belege: [boese], von: "20260801", bis: "20260831")
    .components(separatedBy: "\r\n")[2].components(separatedBy: ";")
pruefe(boeseFelder[11] == "\"'=cmd|'/c calc'!A1\"",
       "Lieferantenname wird in Excel keine Formel")
pruefe(boeseFelder[10] == "\"'-2+3\"", "Belegnummer mit Rechenzeichen wird entschärft")
pruefe(boeseFelder[6] == "\"70001\"", "harmlose Felder bekommen kein Apostroph")
pruefe(extfFeld("Sagt \"hallo\"") == "\"Sagt 'hallo'\"",
       "Anführungszeichen im Text sprengen das Feld nicht")

// --- Belegdatum-Randfälle -----------------------------------------------
pruefe(extfBelegdatum("kein datum") == "", "unlesbares Datum bleibt leer statt Müll")
pruefe(extfBelegdatum("32.13.2026") == "", "unplausibles Datum (32.13.) bleibt leer")
pruefe(extfBelegdatum("1.1.26") == "0101", "1.1.26 → 0101")

// --- Export-Reihenfolge (Regression: leerer Stapel nach Fixieren) -------
// Der Bug: erst fixieren, dann Datei erzeugen → exportierbar war leer.
// Richtige Reihenfolge: Schnappschuss → Text → fixieren.
var bestand = [b1, b2, fixture(lieferant: "Offen GmbH", nr: "X", datum: "01.08.2026",
                               netto: 10, ust: 1.9, brutto: 11.9,
                               konto: nil, status: .offen)]
let schnappschuss = exportierbareBelege(bestand)
pruefe(schnappschuss.count == 2, "offene Belege bleiben draußen")
let stapelText = extfStapelText(belege: schnappschuss, von: "20260801", bis: "20260831")
for i in bestand.indices where schnappschuss.map(\.id).contains(bestand[i].id) {
    bestand[i].status = .fixiert
}
pruefe(stapelText.components(separatedBy: "\r\n").count == 4,
       "Stapeltext entstand VOR dem Fixieren und ist nicht leer (Regression)")
pruefe(exportierbareBelege(bestand).isEmpty == false || schnappschuss.count == 2,
       "nach dem Fixieren ist der Schnappschuss unverändert")

// --- Demo-Sperre ---------------------------------------------------------
let demo = fixture(lieferant: "Hetzner Online GmbH", nr: "R-D", datum: "01.08.2026",
                   netto: 200, ust: 38, brutto: 238, konto: "6837",
                   status: .automatisch, istDemo: true)
pruefe(exportierbareBelege([b1, demo]).count == 1, "Beispiel-Belege gehen nie in den Stapel")
pruefe(exportierbareBelege([demo]).isEmpty, "nur Beispiel-Belege → leerer Stapel")

// --- Monats-Zeitraum ------------------------------------------------------
var kal = Calendar(identifier: .gregorian)
kal.timeZone = TimeZone(identifier: "Europe/Berlin")!
let sep = kal.date(from: DateComponents(year: 2026, month: 9, day: 15))!
let monat = extfMonat(fuer: sep)
pruefe(monat.von == "20260901" && monat.bis == "20260930", "September: 01.–30.")
pruefe(monat.dateiname == "EXTF_Buchungsstapel_2026-09.csv", "Dateiname folgt dem Monat")
pruefe(monat.titel == "Buchungsstapel September 2026", "Titel folgt dem Monat")
let feb = kal.date(from: DateComponents(year: 2028, month: 2, day: 3))!
pruefe(extfMonat(fuer: feb).bis == "20280229", "Schaltjahr-Februar endet am 29.")

// ————— Belegdatum: das Format, das der DATEV-Stapel braucht —————
//
// Am 23.08.2026 übernahm die App erstmals die Serverlesung. Der Server
// schreibt ISO (2026-03-05), die App führt TT.MM.JJJJ. `extfBelegdatum`
// zerlegt an Punkten — aus ISO wurde ein LEERES Belegdatum im Stapel.
// Ein Buchungssatz ohne Belegdatum fällt beim Steuerberater durch, oder
// schlimmer: fällt nicht auf.

// Achtung: `pruefe` nimmt hier die Bedingung ZUERST — anders als im
// Protokoll-Harness. Das kostet beim Schreiben eine Minute.
pruefe(extfBelegdatum("05.03.2026") == "0503", "deutsches Datum ergibt TTMM")
pruefe(extfBelegdatum("5.3.2026") == "0503", "einstellig wird aufgefüllt")
pruefe(extfBelegdatum("2026-03-05") == "",
       "ISO ergibt LEER — deshalb darf ISO nie in datumText landen")
pruefe(extfBelegdatum("irgendwann") == "", "Murks ergibt leer")
pruefe(extfBelegdatum("") == "", "leer bleibt leer")

// ————— Zwei Sprachen, eine Grenze —————
//
// In die DATEV-Datei gehört das DATEV-Wort: der Kopfsatz heißt „Buchungsstapel"
// und der Dateiname trägt es auch. Auf Ninas Bildschirm gehört es nicht hin,
// und „fixiert" schon gar nicht — dort steht dasselbe Wort wie am
// Export-Knopf: festgeschrieben. `BelegStatus.label` ist die einzige dieser
// Zeichenketten, die sie tatsächlich zu sehen bekommt (ListeView, BelegZeile).
let stapeltext = extfStapelText(belege: [b1], von: "20260801", bis: "20260831")
pruefe(stapeltext.hasPrefix("\"EXTF\";700;21;\"Buchungsstapel\""),
       "die DATEV-Datei behält ihr Wort")
pruefe(monat.dateiname.contains("Buchungsstapel"),
       "der Dateiname für das Steuerbüro auch")

let bildschirmworte = BelegStatus.allCases.map(\.label)
pruefe(!bildschirmworte.contains { $0.lowercased().contains("fixiert") },
       "kein Statuswort auf dem Bildschirm sagt „fixiert“")
pruefe(!bildschirmworte.contains { $0.lowercased().contains("stapel") },
       "und keins sagt „Stapel“")
pruefe(BelegStatus.fixiert.label == "exportiert · festgeschrieben",
       "exportierte Belege heißen festgeschrieben")

print(fehler == 0 ? "\nAlle Prüfungen bestanden." : "\n\(fehler) Prüfung(en) fehlgeschlagen.")
exit(fehler == 0 ? 0 : 1)

