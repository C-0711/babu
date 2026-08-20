import Foundation

/// Ein Tages-Kassenbericht — bewusst NUR Tagessummen, exakt wie das
/// Papier-Formular der offenen Ladenkasse (Bestand Vortag, Einnahmen,
/// Ausgaben, gezählter Bestand). Es werden KEINE einzelnen Zahlvorgänge
/// erfasst und keine Zahlung abgewickelt — die App bleibt damit
/// Kassenbuch-Unterstützung und wird kein elektronisches
/// Aufzeichnungssystem mit Kassenfunktion (KassenSichV/§146a-AO-Grenze).
struct Kassenbericht: Codable, Identifiable, Equatable {
    var id = UUID()
    var datum: String              // "2026-08-17" — genau ein Bericht pro Tag
    var bestandVortag = 0.0
    var einnahmenBar = 0.0
    var privateinlagen = 0.0
    var barabhebungBank = 0.0
    var ecZahlungen = 0.0
    // Eingelöste Gutscheine: KEINE neue Einnahme — das Geld kam schon beim
    // Verkauf des Gutscheins in die Kasse. Wird nur für den Tagesumsatz
    // ausgewiesen, nicht in den Kassenbestand gerechnet.
    var gutscheineEingeloest = 0.0
    var trinkgeldTeamEC = 0.0
    var sonstigeAusgaben = 0.0
    var privatentnahmen = 0.0
    var einzahlungBank = 0.0
    var gezaehltSchluss = 0.0
    var erstellt = Date()
    // Optional, damit ältere zustand.json weiter dekodiert (Migration).
    var differenzGrund: String?    // z. B. „10 € Wechselgeld verzählt"
    var sonstigeNotiz: String?     // wofür die sonstige Ausgabe war
    var uebermittelt: Date?        // Tagesblatt liegt in der Belegbox

    var summeEinnahmen: Double { bestandVortag + einnahmenBar + privateinlagen + barabhebungBank }
    var summeAusgaben: Double { trinkgeldTeamEC + sonstigeAusgaben + privatentnahmen + einzahlungBank }
    var rechnerischerBestand: Double { summeEinnahmen - summeAusgaben }
    var differenz: Double { gezaehltSchluss - rechnerischerBestand }
    var tagesumsatz: Double { einnahmenBar + ecZahlungen }
    var kasseStimmt: Bool { abs(differenz) < 0.01 }
}

/// Tag-Schlüssel fürs Kassenbuch: sortierbar und zeitzonenfest.
enum KassenTag {
    static let kalender: Calendar = {
        var k = Calendar(identifier: .gregorian)
        k.locale = Locale(identifier: "de_DE")
        k.firstWeekday = 2   // Montag
        return k
    }()

    private static let schluesselFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = kalender
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static let anzeigeFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = kalender
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "EEEE, d. MMMM"
        return f
    }()

    static func schluessel(_ datum: Date) -> String {
        schluesselFormat.string(from: datum)
    }

    static func datum(_ schluessel: String) -> Date? {
        schluesselFormat.date(from: schluessel)
    }

    /// „Sonntag, 17. August" — für Überschriften.
    static func anzeige(_ schluessel: String) -> String {
        datum(schluessel).map { anzeigeFormat.string(from: $0) } ?? schluessel
    }
}
