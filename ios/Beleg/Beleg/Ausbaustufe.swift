import Foundation

/// Der Zuschnitt: eine Quelle, zwei Apps.
///
/// Aus demselben Ordner entstehen zwei Programme. Das schmale babu kann vier
/// Dinge: alles fotografieren, es lesen und erklären, daraus das Bild deines
/// Betriebs bauen und den Stapel ans Steuerbüro geben. babu Pro kann dasselbe
/// und dazu den ganzen Betrieb — Termine, Kasse, Kundinnen, Rechnungen, Preise,
/// Team, Verträge, Marketing.
///
/// Der Unterschied steht NUR hier. Keine Datei wird weggelassen, keine Ansicht
/// gelöscht — die Listen unten sagen, was zu sehen ist. Wer eine Ansicht
/// hinzufügt, trägt sie hier ein; wer sie hier vergisst, sieht sie nirgends.
/// Absichtlich ohne SwiftUI, damit der Harness unter `ios/Tests/zuschnitt`
/// beide Fassungen ohne App-Ziel prüfen kann.
enum Ausbaustufe {

    /// Wahr im großen Bau. Gesetzt wird das am Ziel („BelegPro"), nicht im Code.
    static let voll: Bool = {
        #if BABU_PRO
        return true
        #else
        return false
        #endif
    }()

    /// Wie die App heißt, wenn sie sich selbst nennt.
    static var name: String { voll ? "babu Pro" : "babu" }

    /// Die Reiter unten, in der Reihenfolge, in der sie stehen.
    static var reiter: [Reiter] { Reiter.allCases.filter { voll || !$0.nurVoll } }

    /// Die Zeilen im Menü rechts oben, in der Reihenfolge, in der sie stehen.
    static var kontomenue: [Kontomenuepunkt] {
        Kontomenuepunkt.allCases.filter { voll || !$0.nurVoll }
    }

    /// Steht dieser Reiter in diesem Bau überhaupt zur Verfügung?
    /// Wer irgendwo „geh dorthin" sagt, fragt vorher hier nach — sonst
    /// bliebe ein Knopf stehen, der ins Leere führt.
    static func erreichbar(_ r: Reiter) -> Bool { reiter.contains(r) }

    static func erreichbar(_ p: Kontomenuepunkt) -> Bool { kontomenue.contains(p) }
}

/// Ein Reiter in der Leiste unten.
enum Reiter: String, CaseIterable, Hashable {
    case erfassen, dokumente, termine, kasse, fragen

    /// Gibt es diesen Reiter nur im großen Bau?
    var nurVoll: Bool {
        switch self {
        case .termine, .kasse: return true
        case .erfassen, .dokumente, .fragen: return false
        }
    }

    var titel: String {
        switch self {
        case .erfassen:  return "Erfassen"
        case .dokumente: return "Dokumente"
        case .termine:   return "Termine"
        case .kasse:     return "Kassenbuch"
        case .fragen:    return "Fragen"
        }
    }

    var symbol: String {
        switch self {
        case .erfassen:  return "viewfinder"
        case .dokumente: return "doc.text"
        case .termine:   return "calendar"
        case .kasse:     return "banknote"
        case .fragen:    return "questionmark.bubble"
        }
    }
}

/// Eine Zeile im Menü rechts oben.
enum Kontomenuepunkt: String, CaseIterable, Hashable {
    // Was die Zahlen angeht
    case aufraeumen, rechnungen, vorlagen, briefkopf, monatsabschluss, export
    // Was den Salon angeht
    case betrieb, kundinnen, preise, kartenzahlung, team, vertraege
    case kontoauszug, marketing
    // Das Konto selbst
    case wasBabuKann, meldungen, einstellungen

    /// Gibt es diese Zeile nur im großen Bau?
    var nurVoll: Bool {
        switch self {
        case .rechnungen, .vorlagen, .briefkopf, .kundinnen, .preise,
             .kartenzahlung, .team, .marketing:
            return true
        // Verträge und Versicherungen bleiben im schmalen Bau (Entscheidung
        // des Auftraggebers, 08.09.2026). Ein Mietvertrag oder eine Police
        // ist ein DOKUMENT, kein Salonbetrieb — und die Kündigungsfrist, an
        // die babu erinnert, gehört zum Kern dessen, was es leisten soll.
        case .aufraeumen, .monatsabschluss, .export, .betrieb, .kontoauszug,
             .vertraege, .wasBabuKann, .meldungen, .einstellungen:
            return false
        }
    }

    /// Unter welcher Überschrift die Zeile steht.
    enum Abschnitt: String { case buchhaltung, salon, konto }

    var abschnitt: Abschnitt {
        switch self {
        case .aufraeumen, .rechnungen, .vorlagen, .briefkopf,
             .monatsabschluss, .export:
            return .buchhaltung
        case .betrieb, .kundinnen, .preise, .kartenzahlung, .team,
             .vertraege, .kontoauszug, .marketing:
            return .salon
        case .wasBabuKann, .meldungen, .einstellungen:
            return .konto
        }
    }

    var titel: String {
        switch self {
        case .aufraeumen:      return "Belege aufräumen"
        case .rechnungen:      return "Rechnungen"
        case .vorlagen:        return "Vorlagen"
        case .briefkopf:       return "Dein Briefkopf"
        case .monatsabschluss: return "Monatsabschluss"
        case .export:          return "Export für die Buchhaltung"
        case .betrieb:         return "Dein Betrieb"
        case .kundinnen:       return "Kundinnen"
        case .preise:          return "Deine Preise"
        case .kartenzahlung:   return "Kartenzahlung"
        case .team:            return "Dein Team"
        case .vertraege:       return "Deine Verträge"
        case .kontoauszug:     return "Kontoauszug"
        case .marketing:       return "Marketing"
        case .wasBabuKann:     return "Was babu alles kann"
        case .meldungen:       return "Meine Meldungen"
        case .einstellungen:   return "Einstellungen"
        }
    }

    var symbol: String {
        switch self {
        case .aufraeumen:      return "rectangle.stack"
        case .rechnungen:      return "eurosign.circle"
        case .vorlagen:        return "doc.on.doc"
        case .briefkopf:       return "paintpalette"
        case .monatsabschluss: return "chart.bar.doc.horizontal"
        case .export:          return "square.and.arrow.up"
        case .betrieb:         return "building.2"
        case .kundinnen:       return "person.crop.circle"
        case .preise:          return "tag"
        case .kartenzahlung:   return "creditcard"
        case .team:            return "person.2"
        case .vertraege:       return "shippingbox"
        case .kontoauszug:     return "building.columns"
        case .marketing:       return "megaphone"
        case .wasBabuKann:     return "list.bullet.rectangle"
        case .meldungen:       return "exclamationmark.bubble"
        case .einstellungen:   return "gearshape"
        }
    }

    /// Zeilen, die ein eigenes Blatt aufschlagen statt weiterzuschieben —
    /// sie bringen ihren eigenen Fertig-Knopf mit.
    var alsBlatt: Bool {
        switch self {
        case .aufraeumen, .vorlagen, .briefkopf: return true
        default: return false
        }
    }
}

extension Kontomenuepunkt.Abschnitt {
    /// Die Überschrift über dem Abschnitt. Der letzte trägt keine.
    var titel: String? {
        switch self {
        case .buchhaltung: return "Buchhaltung"
        case .salon:       return "Dein Salon"
        case .konto:       return nil
        }
    }
}
