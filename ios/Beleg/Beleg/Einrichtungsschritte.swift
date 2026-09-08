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
    /// Alles, was im Profil über den Betrieb steht — mit der Unterlage, aus
    /// der babu es lernen kann. Die ersten sieben stehen zugleich im Formular
    /// „Dein Betrieb"; was in der Karte als „3 von 7" steht, muss sich dort
    /// abzählen lassen.
    static let profilfelder: [Profilfeld] = [
        Profilfeld("betrieb_name", "Name des Salons",
                   "den Namen deines Salons", .nurSelbst, imFormular: true),
        Profilfeld("anschrift", "Anschrift",
                   "deine Anschrift", .nurSelbst, imFormular: true),
        // Der Name im Formular bleibt die einfache Frage („Wie du angemeldet
        // bist"); mitten in einer Aufzählung braucht es ein Substantiv,
        // sonst kippt der Satz.
        Profilfeld("rechtsform", "Wie du angemeldet bist",
                   "deine Rechtsform", .gewinnrechnung, imFormular: true),
        Profilfeld("finanzamt", "Dein Finanzamt",
                   "dein Finanzamt", .amt, imFormular: true),
        Profilfeld("telefon", "Telefon",
                   "deine Telefonnummer", .nurSelbst, imFormular: true),
        Profilfeld("email", "E-Mail",
                   "deine E-Mail-Adresse", .nurSelbst, imFormular: true),
        Profilfeld("kleinunternehmer", "Umsatzsteuer ja oder nein",
                   "deine Umsatzsteuer-Regelung", .amt, imFormular: true),
        // Diese beiden stehen nicht im Formular, aber im Profil — und sie
        // sind genau die, die babu am zuverlässigsten selbst liest.
        Profilfeld("steuernummer", "Steuernummer",
                   "deine Steuernummer", .amt, imFormular: false,
                   ersatz: "ust_id"),
        Profilfeld("iban", "Bankverbindung",
                   "deine Bankverbindung", .kontoauszug, imFormular: false),
    ]

    /// Die Angaben zum Betrieb, die babu für Rechnungen und Meldungen braucht.
    /// Reihenfolge und Namen sind dieselben wie im Formular.
    static var betriebsfelder: [(schluessel: String, name: String)] {
        profilfelder.filter(\.imFormular).map { ($0.schluessel, $0.name) }
    }

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

    /// Die zwei Schritte, ohne die babu gar nicht anfangen kann.
    ///
    /// Bis zum 08.09.2026 zeigte die Karte auf der Startseite alle fünf Zeilen
    /// und blieb stehen, bis jede abgehakt war. Sie maß damit den Menschen an
    /// dem, was ihm fehlt, und verlangte Arbeit, die niemand von Hand tun muss:
    /// Betriebsangaben, Steuernummer und Kassenbuch wachsen aus den Unterlagen
    /// nach. Übrig bleibt, was wirklich nur am Anfang hilft — sich verbinden
    /// und einmal auslösen. Danach gehört der Erfassen-Reiter der Kamera, und
    /// was noch fehlt, steht im Profil.
    static let anfangsziele: [Einrichtungsziel] = [.konto, .ersterBeleg]

    /// Der Anfang, wie die Karte ihn zeigt.
    ///
    /// Beide Zeilen hängen weder an den Angaben aus dem babu-Konto noch am
    /// Kassenbuch — deshalb stehen dort unten `nil` und `false`: sie fließen
    /// nur in die drei Zeilen, die diese Ansicht gar nicht mehr zeigt. Das
    /// Kassenbuch war zugleich der Grund für den früheren Bau-Filter; im
    /// schmalen Bau führte seine Zeile ins Leere. Jetzt steht sie nirgends
    /// mehr, und beide Bauten zeigen dieselben zwei Schritte.
    static func anfangsschritte(kontoVerbunden: Bool,
                                ersterBeleg: Bool) -> [Einrichtungsschritt] {
        schritte(kontoVerbunden: kontoVerbunden, angaben: nil,
                 ersterBeleg: ersterBeleg, kassenbuchBegonnen: false)
            .filter { anfangsziele.contains($0.ziel) }
    }

    /// Ist der Anfang geschafft? Dann verschwindet die Karte — endgültig.
    static func anfangGeschafft(kontoVerbunden: Bool, ersterBeleg: Bool) -> Bool {
        alleErledigt(anfangsschritte(kontoVerbunden: kontoVerbunden,
                                     ersterBeleg: ersterBeleg))
    }

    /// Alles erledigt heißt: die Karte darf verschwinden und bleibt weg.
    static func alleErledigt(_ schritte: [Einrichtungsschritt]) -> Bool {
        !schritte.isEmpty && schritte.allSatisfy(\.istErledigt)
    }

    // MARK: - Wie das Profil wächst

    /// Steht diese Angabe schon im Profil? Bei der Steuernummer zählt auch
    /// die Umsatzsteuer-ID — auf der Rechnung reicht eines von beiden.
    static func steht(_ feld: Profilfeld, in angaben: [String: String]) -> Bool {
        if gefuellt(angaben, feld.schluessel) { return true }
        if let ersatz = feld.ersatz { return gefuellt(angaben, ersatz) }
        return false
    }

    /// Was babu über den Betrieb schon weiß — in der Reihenfolge des Profils.
    static func bekannteFelder(_ angaben: [String: String])
            -> [(feld: Profilfeld, wert: String)] {
        profilfelder.compactMap { feld in
            for schluessel in [feld.schluessel, feld.ersatz].compactMap({ $0 }) {
                let wert = (angaben[schluessel] ?? "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !wert.isEmpty { return (feld, wert) }
            }
            return nil
        }
    }

    /// Was als Nächstes dazukäme — gebündelt nach der Unterlage, die es
    /// mitbringt. Ein Kontoauszug bringt die Bankverbindung, ein Brief vom
    /// Amt gleich mehrere Angaben auf einmal; deshalb steht jede Unterlage
    /// nur einmal da und nennt alles, was sie beantwortet.
    static func naechstes(_ angaben: [String: String])
            -> [(quelle: Lernquelle, satz: String)] {
        let offen = profilfelder.filter { !steht($0, in: angaben) }
        return Lernquelle.allCases.compactMap { quelle in
            let dazu = offen.filter { $0.lernquelle == quelle }
            guard !dazu.isEmpty else { return nil }
            return (quelle, quelle.satz(fuer: dazu.map(\.satzname)))
        }
    }
}

/// Eine Angabe im Profil: wie sie heißt, wie sie mitten im Satz heißt, und
/// aus welcher Unterlage babu sie lernen kann.
struct Profilfeld: Equatable {
    let schluessel: String
    let name: String
    /// Wie die Angabe mitten in einem Satz heißt — „deine Steuernummer".
    let satzname: String
    let lernquelle: Lernquelle
    /// Steht sie im Formular „Dein Betrieb"? Nur diese zählen für „3 von 7".
    let imFormular: Bool
    /// Ein zweiter Schlüssel, der genauso zählt (Steuernummer oder USt-IdNr.).
    let ersatz: String?

    init(_ schluessel: String, _ name: String, _ satzname: String,
         _ lernquelle: Lernquelle, imFormular: Bool, ersatz: String? = nil) {
        self.schluessel = schluessel
        self.name = name
        self.satzname = satzname
        self.lernquelle = lernquelle
        self.imFormular = imFormular
        self.ersatz = ersatz
    }
}

/// Aus welcher Unterlage babu eine Angabe über den Betrieb lernen kann.
///
/// **Abschrift, kein Original.** Was aus welcher Art Unterlage übernommen
/// werden darf, entscheidet der Server in `salonpruefung.ERLAUBT_JE_ART` —
/// und zwar aus gutem Grund: auf einem Steuerbescheid steht auch die
/// Bankverbindung des Finanzamts, und auf einem Mietvertrag die Telefonnummer
/// des Vermieters. Genau deshalb steht dort für die Anschrift, den Namen,
/// Telefon und E-Mail bei KEINER Art etwas — sie werden aus keiner Unterlage
/// geerntet, und `.nurSelbst` sagt das ehrlich, statt ein Foto zu versprechen,
/// aus dem nie etwas käme.
///
/// Abrufen lässt sich diese Liste heute nicht; solange das so bleibt, steht
/// sie hier zweimal. Wer sie dort ändert, ändert sie hier mit.
enum Lernquelle: String, Equatable, CaseIterable {
    /// Post vom Amt — Bescheide nennen die Steuernummer ihres Adressaten.
    case amt
    /// Die Gewinnrechnung vom Steuerbüro.
    case gewinnrechnung
    /// Ein Kontoauszug — der Kontoinhaber ist wirklich der Betrieb.
    case kontoauszug
    /// Steht auf keiner Unterlage über den Betrieb selbst.
    case nurSelbst

    /// Der Satz, der zu dieser Unterlage einlädt.
    func satz(fuer felder: [String]) -> String {
        let aufzaehlung = Lernquelle.und(felder)
        switch self {
        case .amt:
            return "Fotografier einen Brief vom Finanzamt — dann kennt babu "
                 + "auch \(aufzaehlung)."
        case .gewinnrechnung:
            return "Fotografier deine Gewinnrechnung vom Steuerbüro — dann "
                 + "kennt babu auch \(aufzaehlung)."
        case .kontoauszug:
            return "Fotografier einen Kontoauszug — dann kennt babu auch "
                 + "\(aufzaehlung)."
        case .nurSelbst:
            let stehen = felder.count == 1 ? "steht" : "stehen"
            return "\(aufzaehlung.prefix(1).uppercased())"
                 + "\(aufzaehlung.dropFirst()) \(stehen) auf keiner Unterlage "
                 + "über deinen Salon — das trägst du selbst ein."
        }
    }

    var symbol: String {
        switch self {
        case .amt: return "doc.text.viewfinder"
        case .gewinnrechnung: return "chart.bar.doc.horizontal"
        case .kontoauszug: return "building.columns"
        case .nurSelbst: return "square.and.pencil"
        }
    }

    /// „a, b und c" — eine Aufzählung, die sich vorlesen lässt.
    static func und(_ teile: [String]) -> String {
        guard let letztes = teile.last else { return "" }
        if teile.count == 1 { return letztes }
        return teile.dropLast().joined(separator: ", ") + " und " + letztes
    }
}
