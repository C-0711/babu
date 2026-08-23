import Foundation

/// Was beim Einrichten noch aussteht — reine Logik, ohne SwiftUI, damit der
/// swiftc-Harness unter ios/Tests sie ohne App-Target prüfen kann.
///
/// Der Stand wird nirgends gespeichert, sondern aus dem abgeleitet, was
/// wirklich da ist: die Anmeldung, die Angaben im babu-Konto, die Belege auf
/// dem Gerät und die Kassenberichte. Eine Karte, die „erledigt" behauptet,
/// weil jemand einmal einen Haken gesetzt hat, wäre schlimmer als keine.

/// Wohin eine Zeile der Einrichtungskarte führt.
enum Einrichtungsziel: String, Equatable {
    case konto, betrieb, ersterBeleg, kassenbuch, steuernummer
}

/// Ein Schritt beim Einrichten: Titel, Stand und wohin es weitergeht.
struct Einrichtungsschritt: Identifiable, Equatable {
    enum Stand: Equatable {
        case erledigt
        case offen
        /// Angefangen, aber nicht fertig — „3 von 7".
        case teilweise(fertig: Int, gesamt: Int)
        /// Ohne Verbindung lässt sich nichts über die Angaben im Konto sagen.
        /// „offen" wäre hier geraten, und Geratenes gehört nicht in die Karte.
        case unbekannt
    }

    let ziel: Einrichtungsziel
    let titel: String
    let stand: Stand

    var id: String { ziel.rawValue }
    var istErledigt: Bool { stand == .erledigt }

    /// Was rechts neben dem Titel steht — kurz genug für eine Spalte.
    var standText: String {
        switch stand {
        case .erledigt: return "✓"
        case .offen: return "offen"
        case .teilweise(let fertig, let gesamt): return "\(fertig) von \(gesamt)"
        case .unbekannt: return "—"
        }
    }
}

enum Einrichtung {
    /// Die Angaben zum Betrieb, die babu für Rechnungen und Meldungen braucht.
    /// Reihenfolge und Namen sind dieselben wie im Formular — was in der Karte
    /// als „3 von 7" steht, muss sich dort abzählen lassen.
    static let betriebsfelder: [(schluessel: String, name: String)] = [
        ("betrieb_name", "Name des Salons"),
        ("anschrift", "Anschrift"),
        ("rechtsform", "Wie du angemeldet bist"),
        ("finanzamt", "Dein Finanzamt"),
        ("telefon", "Telefon"),
        ("email", "E-Mail"),
        ("kleinunternehmer", "Umsatzsteuer ja oder nein"),
    ]

    /// Leerzeichen sind kein Inhalt — der Server nimmt sie trotzdem an.
    static func gefuellt(_ angaben: [String: String], _ schluessel: String) -> Bool {
        !(angaben[schluessel] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Welche Betriebsangaben noch fehlen — für den Satz unter der Zeile.
    static func fehlendeBetriebsfelder(_ angaben: [String: String]) -> [String] {
        betriebsfelder.filter { !gefuellt(angaben, $0.schluessel) }.map(\.name)
    }

    /// Die Steuernummer gilt als hinterlegt, wenn eine Steuernummer ODER eine
    /// USt-IdNr. da ist — auf der Rechnung reicht eines von beiden (§ 14 UStG).
    static func steuernummerDa(_ angaben: [String: String]) -> Bool {
        gefuellt(angaben, "steuernummer") || gefuellt(angaben, "ust_id")
    }

    /// Der Stand aller fünf Schritte.
    ///
    /// - Parameter angaben: die Einstellungen aus dem babu-Konto, oder `nil`,
    ///   solange niemand sie abrufen konnte (nicht verbunden, kein Netz).
    static func schritte(kontoVerbunden: Bool,
                         angaben: [String: String]?,
                         ersterBeleg: Bool,
                         kassenbuchBegonnen: Bool) -> [Einrichtungsschritt] {
        let betrieb: Einrichtungsschritt.Stand
        let steuer: Einrichtungsschritt.Stand
        if let angaben {
            let fertig = betriebsfelder.count - fehlendeBetriebsfelder(angaben).count
            betrieb = fertig == betriebsfelder.count
                ? .erledigt
                : .teilweise(fertig: fertig, gesamt: betriebsfelder.count)
            steuer = steuernummerDa(angaben) ? .erledigt : .offen
        } else {
            betrieb = .unbekannt
            steuer = .unbekannt
        }
        return [
            Einrichtungsschritt(ziel: .konto, titel: "Konto verbunden",
                                stand: kontoVerbunden ? .erledigt : .offen),
            Einrichtungsschritt(ziel: .betrieb, titel: "Betriebsangaben vollständig",
                                stand: betrieb),
            Einrichtungsschritt(ziel: .ersterBeleg, titel: "Ersten Beleg fotografiert",
                                stand: ersterBeleg ? .erledigt : .offen),
            Einrichtungsschritt(ziel: .kassenbuch, titel: "Kassenbuch begonnen",
                                stand: kassenbuchBegonnen ? .erledigt : .offen),
            Einrichtungsschritt(ziel: .steuernummer, titel: "Steuernummer hinterlegt",
                                stand: steuer),
        ]
    }

    /// Alles erledigt heißt: die Karte darf verschwinden und bleibt weg.
    static func alleErledigt(_ schritte: [Einrichtungsschritt]) -> Bool {
        !schritte.isEmpty && schritte.allSatisfy(\.istErledigt)
    }
}
