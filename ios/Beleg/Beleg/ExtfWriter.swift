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

/// Derselbe Zeitraum, aber nach den BELEGEN statt nach dem Kalender.
///
/// Die Vorschau nannte immer den laufenden Monat. Ein Bon vom 5. August, im
/// Oktober fotografiert, stand damit in einem Stapel „01.10.–31.10.", und
/// babu musste danebenschreiben, dass ein Beleg nicht hineingehört
/// (gefunden beim Durchlauf am 11.10.2026). Der Monat eines Belegs ist der
/// seines DATUMS — dieselbe Regel wie in der Dokumentenliste, im
/// Kassenbuch und auf dem Server. Jetzt nennt der Kopf die Monate, die
/// wirklich drinstehen; liegen mehrere drin, nennt er die Spanne.
///
/// Ohne lesbares Datum gibt es nichts zu folgen — dann bleibt der laufende
/// Monat, damit der Stapel überhaupt einen Kopf hat.
func extfZeitraum(fuer belege: [Beleg], heute: Date = Date())
    -> (von: String, bis: String, dateiname: String, titel: String) {
    let monate = belege.compactMap { belegMonatSchluessel($0.datumText) }.sorted()
    guard let erster = monate.first, let letzter = monate.last else {
        return extfMonat(fuer: heute)
    }
    let von = extfMonat(fuer: monatsDatum(erster) ?? heute)
    let bis = extfMonat(fuer: monatsDatum(letzter) ?? heute)
    if erster == letzter { return von }
    return (von: von.von, bis: bis.bis,
            dateiname: "EXTF_Buchungsstapel_\(erster)_bis_\(letzter).csv",
            titel: von.titel + " – " + bis.titel
                .replacingOccurrences(of: "Buchungsstapel ", with: ""))
}

/// „2026-08" → der 1. August 2026.
func monatsDatum(_ schluessel: String) -> Date? {
    let t = schluessel.split(separator: "-")
    guard t.count == 2, let jahr = Int(t[0]), let monat = Int(t[1]) else { return nil }
    var komp = DateComponents()
    komp.year = jahr; komp.month = monat; komp.day = 1
    return Calendar(identifier: .gregorian).date(from: komp)
}
