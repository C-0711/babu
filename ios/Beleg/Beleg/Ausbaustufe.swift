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
    static var reiter: [Reiter] {
        Reiter.allCases.filter {
            (voll || !$0.nurVoll) && !$0.nurMitarbeit && !$0.nurAmbassadorin
        }
    }

    /// Die Zeilen im Menü rechts oben, in der Reihenfolge, in der sie stehen.
    static var kontomenue: [Kontomenuepunkt] {
        Kontomenuepunkt.allCases.filter { (voll || !$0.nurVoll) && !$0.nurAmbassadorin }
    }

    /// Mehr Reiter stellt das iPhone nicht nebeneinander. Ein sechster landet
    /// unter einem „Mehr", das iOS selbst baut — fremde Liste, eigener
    /// Zurück-Pfeil, doppelter Kopf (im Simulator gesehen, 08.10.2026).
    static let hoechstensReiter = 5

    /// Steht dieser Reiter in diesem Bau überhaupt zur Verfügung?
    /// Wer irgendwo „geh dorthin" sagt, fragt vorher hier nach — sonst
    /// bliebe ein Knopf stehen, der ins Leere führt.
    static func erreichbar(_ r: Reiter) -> Bool { reiter.contains(r) }

    static func erreichbar(_ p: Kontomenuepunkt) -> Bool { kontomenue.contains(p) }

    /// Was eine Mitarbeiterin darf (aus `/api/ich`, babu Expenses D1).
    /// `nil` heißt: Inhaberin oder Kanzlei — dann gilt der Zuschnitt oben.
    struct Rechte: Equatable, Codable {
        var belege: Bool
        var kasse: Bool
        var auslagen: Bool
    }

    /// Empfiehlt dieses Konto babu weiter (`GET /api/ambassador/me` sagt 200)
    /// — und hat es selbst eine Ablage? Eine Ambassadorin ohne eigenen
    /// Salon bekommt nie eine; für sie ist „Empfehlen" der Anfang.
    enum Ambassadorin: Equatable {
        case nein, mitAblage, ohneAblage
    }

    /// Die Reiter für dieses Konto — nie mehr als `hoechstensReiter`.
    /// Mitarbeiterinnen sehen nur, was sie dürfen, und nie „Empfehlen".
    ///
    /// Eine Ambassadorin mit Salon behält ihre Reiter, wie sie sind;
    /// „Empfehlen" kommt hinten dazu, wenn noch Platz ist — sonst (babu Pro)
    /// steht es im Menü (`kontomenue(fuer:ambassadorin:)`). Ohne Ablage ist
    /// „Empfehlen" ihr Anfang und steht ganz vorn; was dahinter keinen Platz
    /// mehr hat (in babu Pro „Fragen"), bräuchte eine Ablage und ginge für
    /// sie ohnehin nicht.
    static func reiter(fuer rechte: Rechte?,
                       ambassadorin: Ambassadorin = .nein) -> [Reiter] {
        guard let r = rechte else {
            switch ambassadorin {
            case .nein:
                return reiter
            case .mitAblage:
                return reiter.count < hoechstensReiter ? reiter + [.empfehlen] : reiter
            case .ohneAblage:
                return Array(([.empfehlen] + reiter).prefix(hoechstensReiter))
            }
        }
        let erlaubt = Reiter.allCases.filter { t in
            switch t {
            case .auslagen: return r.auslagen
            case .erfassen: return r.belege
            case .kasse: return r.kasse && voll
            case .dokumente, .termine, .fragen, .empfehlen: return false
            }
        }
        return Array(erlaubt.prefix(hoechstensReiter))
    }

    /// Welcher Reiter beim Start offen ist, wenn nicht der erste gemeint ist.
    /// `nil`: wie bisher (Erfassen bzw. was das Konto zuerst sieht).
    static func startreiter(fuer rechte: Rechte?,
                            ambassadorin: Ambassadorin) -> Reiter? {
        guard rechte == nil, ambassadorin == .ohneAblage else { return nil }
        return .empfehlen
    }

    /// Das Menü für dieses Konto. „Empfehlen" steht hier genau dann, wenn
    /// eine Ambassadorin es braucht und unten kein Platz mehr dafür war.
    static func kontomenue(fuer rechte: Rechte?,
                           ambassadorin: Ambassadorin = .nein) -> [Kontomenuepunkt] {
        guard rechte == nil else { return [.meldungen, .einstellungen] }
        let imMenue = ambassadorin != .nein
            && !reiter(fuer: nil, ambassadorin: ambassadorin).contains(.empfehlen)
        return Kontomenuepunkt.allCases.filter {
            (voll || !$0.nurVoll) && (!$0.nurAmbassadorin || imMenue)
        }
    }
}

/// Ein Reiter in der Leiste unten.
enum Reiter: String, CaseIterable, Hashable {
    case erfassen, dokumente, termine, kasse, fragen, empfehlen, auslagen

    /// Gibt es diesen Reiter nur im großen Bau?
    var nurVoll: Bool {
        switch self {
        case .termine, .kasse: return true
        case .erfassen, .dokumente, .fragen, .empfehlen, .auslagen: return false
        }
    }

    /// Nur für Mitarbeiterinnen (babu Expenses D1) — die Inhaberin gibt
    /// Auslagen über das Menü frei.
    var nurMitarbeit: Bool { self == .auslagen }

    /// Nur für Ambassadorinnen — in beiden Bauten, aber nur, wenn der Server
    /// das Konto als Ambassadorin kennt (`reiter(fuer:ambassadorin:)`).
    var nurAmbassadorin: Bool { self == .empfehlen }

    var titel: String {
        switch self {
        case .erfassen:  return "Erfassen"
        case .dokumente: return "Dokumente"
        case .termine:   return "Termine"
        case .kasse:     return "Kassenbuch"
        case .fragen:    return "Fragen"
        case .empfehlen: return "Empfehlen"
        case .auslagen:  return "Auslagen"
        }
    }

    var symbol: String {
        switch self {
        case .erfassen:  return "viewfinder"
        case .dokumente: return "doc.text"
        case .termine:   return "calendar"
        case .kasse:     return "banknote"
        case .fragen:    return "questionmark.bubble"
        case .empfehlen: return "gift"
        case .auslagen:  return "eurosign.circle"
        }
    }
}

/// Eine Zeile im Menü rechts oben.
enum Kontomenuepunkt: String, CaseIterable, Hashable {
    // Was die Zahlen angeht
    case aufraeumen, rechnungen, vorlagen, briefkopf, monatsabschluss, export
    case auslagen
    // Was den Salon angeht
    case betrieb, kundinnen, preise, kartenzahlung, team, vertraege
    case kontoauszug, marketing
    // Das Konto selbst
    case empfehlen, wasBabuKann, meldungen, einstellungen

    /// Nur für Ambassadorinnen, und nur, wenn „Empfehlen" unten keinen Platz
    /// mehr als Reiter hat (`Ausbaustufe.kontomenue(fuer:ambassadorin:)`).
    var nurAmbassadorin: Bool { self == .empfehlen }

    /// Gibt es diese Zeile nur im großen Bau?
    var nurVoll: Bool {
        switch self {
        case .rechnungen, .vorlagen, .briefkopf, .kundinnen, .preise,
             .kartenzahlung, .team, .marketing, .auslagen:
            return true
        // Verträge und Versicherungen bleiben im schmalen Bau (Entscheidung
        // des Auftraggebers, 08.09.2026). Ein Mietvertrag oder eine Police
        // ist ein DOKUMENT, kein Salonbetrieb — und die Kündigungsfrist, an
        // die babu erinnert, gehört zum Kern dessen, was es leisten soll.
        case .aufraeumen, .monatsabschluss, .export, .betrieb, .kontoauszug,
             .vertraege, .empfehlen, .wasBabuKann, .meldungen, .einstellungen:
            return false
        }
    }

    /// Unter welcher Überschrift die Zeile steht.
    enum Abschnitt: String { case buchhaltung, salon, konto }

    var abschnitt: Abschnitt {
        switch self {
        case .aufraeumen, .rechnungen, .vorlagen, .briefkopf,
             .monatsabschluss, .export, .auslagen:
            return .buchhaltung
        case .betrieb, .kundinnen, .preise, .kartenzahlung, .team,
             .vertraege, .kontoauszug, .marketing:
            return .salon
        case .empfehlen, .wasBabuKann, .meldungen, .einstellungen:
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
        case .auslagen:        return "Auslagen freigeben"
        case .betrieb:         return "Dein Betrieb"
        case .kundinnen:       return "Kundinnen"
        case .preise:          return "Deine Preise"
        case .kartenzahlung:   return "Kartenzahlung"
        case .team:            return "Dein Team"
        case .vertraege:       return "Deine Verträge"
        case .kontoauszug:     return "Kontoauszug"
        case .marketing:       return "Marketing"
        case .empfehlen:       return "Empfehlen"
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
        case .auslagen:        return "person.crop.circle.badge.checkmark"
        case .betrieb:         return "building.2"
        case .kundinnen:       return "person.crop.circle"
        case .preise:          return "tag"
        case .kartenzahlung:   return "creditcard"
        case .team:            return "person.2"
        case .vertraege:       return "shippingbox"
        case .kontoauszug:     return "building.columns"
        case .marketing:       return "megaphone"
        case .empfehlen:       return Reiter.empfehlen.symbol
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
