import Foundation

/// EXTF-Stapel-Erzeugung als freie, UIKit-freie Funktionen — der
/// swiftc-Harness unter ios/Tests prüft sie ohne App-Target.
/// Weiterhin die vereinfachte Vorschau; der vollständige v13-Writer
/// ist Phase 5 des Bauplans (docs/build-plan.md).

/// Was in den Stapel darf: gebuchte Belege, niemals Beispiel-Belege.
func exportierbareBelege(_ belege: [Beleg]) -> [Beleg] {
    belege.filter {
        [.automatisch, .bestaetigt, .korrigiert].contains($0.status) && $0.istDemo != true
    }
}

/// Ein Textfeld des Stapels: in Anführungszeichen — und niemals eine Formel.
///
/// Die fertige Datei geht ans Steuerbüro und wird dort in Excel geöffnet.
/// Beginnt ein Feld mit `=`, `+`, `-` oder `@`, führt Excel es als Formel
/// aus; ein Lieferantenname wie `=cmd|…` wäre damit ein Angriff auf den
/// Rechner der Kanzlei. Das führende Apostroph ist Excels eigene
/// „das ist Text"-Markierung und wird beim Anzeigen nicht mitgedruckt.
func extfFeld(_ wert: String) -> String {
    var text = wert.replacingOccurrences(of: "\"", with: "'")
    if let erstes = text.first, "=+-@\t\r\n".contains(erstes) {
        text = "'" + text
    }
    return "\"" + text + "\""
}

/// Stapeltext für eine feste Belegmenge und einen Zeitraum (jjjjmmtt).
func extfStapelText(belege: [Beleg], von: String, bis: String) -> String {
    var zeilen = ["\"EXTF\";700;21;\"Buchungsstapel\";13;;;",
                  ";\"RE\";\"DE\";;\"\(von)\";\"\(bis)\";"]
    for b in belege {
        zeilen.append("\(extfBetrag(b.brutto));\"S\";\"EUR\";;;;\(extfFeld(b.kreditor));\(extfFeld(b.konto ?? ""));\(b.steuerschluessel);\(extfFeld(extfBelegdatum(b.datumText)));\(extfFeld(b.belegNr));\(extfFeld(b.lieferant))")
    }
    return zeilen.joined(separator: "\r\n")
}

/// Betrag im DATEV-Feldformat: Komma, zwei Stellen, kein Tausenderpunkt.
func extfBetrag(_ n: Double) -> String {
    String(format: "%.2f", n).replacingOccurrences(of: ".", with: ",")
}

/// Belegdatum TTMM — mit führenden Nullen, auch wenn der Beleg
/// einstellig druckt („5.8.2026" → „0508"). Unlesbares Datum bleibt leer.
func extfBelegdatum(_ text: String) -> String {
    let teile = text.split(separator: ".")
    guard teile.count >= 2, let tag = Int(teile[0]), let monat = Int(teile[1]),
          (1...31).contains(tag), (1...12).contains(monat) else { return "" }
    return String(format: "%02d%02d", tag, monat)
}

/// Zeitraum, Dateiname und Anzeigetitel des Stapels für den Monat von `datum`.
func extfMonat(fuer datum: Date = Date()) -> (von: String, bis: String, dateiname: String, titel: String) {
    var kal = Calendar(identifier: .gregorian)
    kal.locale = Locale(identifier: "de_DE")
    let komp = kal.dateComponents([.year, .month], from: datum)
    let jahr = komp.year ?? 2000
    let monat = komp.month ?? 1
    let erster = kal.date(from: komp) ?? datum
    let tage = kal.range(of: .day, in: .month, for: erster)?.count ?? 28
    let mf = DateFormatter()
    mf.locale = Locale(identifier: "de_DE")
    mf.dateFormat = "LLLL yyyy"
    return (von: String(format: "%04d%02d01", jahr, monat),
            bis: String(format: "%04d%02d%02d", jahr, monat, tage),
            dateiname: String(format: "EXTF_Buchungsstapel_%04d-%02d.csv", jahr, monat),
            titel: "Buchungsstapel " + mf.string(from: erster))
}
