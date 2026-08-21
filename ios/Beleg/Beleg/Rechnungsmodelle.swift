import Foundation

/// Eine Position auf der Rechnung — Text, Menge, Einzelpreis, Steuersatz.
struct RechnungPosition: Identifiable, Codable, Equatable {
    var id = UUID()
    var text: String = ""
    var menge: Double = 1
    var einzelpreis: Double = 0
    var ustSatz: Int = 19

    var gesamt: Double { (einzelpreis * menge).aufCent }

    enum CodingKeys: String, CodingKey {
        case id, text, menge, einzelpreis
        case ustSatz = "ust_satz"
    }
}

/// Wer die Rechnung bekommt. Gespeicherte Empfänger sind die halbe Vorlage.
struct Empfaenger: Identifiable, Codable, Equatable, Hashable {
    var id = UUID()
    var name: String = ""
    var anschrift: String = ""
    var ustId: String = ""

    enum CodingKeys: String, CodingKey {
        case id, name, anschrift
        case ustId = "ust_id"
    }
}

/// Eine Vorlage: Empfängerin plus die Positionen, die sich wiederholen.
/// Damit ist eine neue Rechnung zwei Handgriffe statt Abtippen.
struct Rechnungsvorlage: Identifiable, Codable, Equatable {
    var id = UUID()
    var name: String = ""
    var empfaenger: Empfaenger = Empfaenger()
    var positionen: [RechnungPosition] = []

    var kurz: String {
        let summe = positionen.reduce(0) { $0 + $1.gesamt }
        return summe > 0 ? "\(empfaenger.name) · \(fmtEur(summe))" : empfaenger.name
    }
}

/// Eine gestellte Rechnung, so wie der Server sie führt.
struct Rechnung: Identifiable, Equatable {
    var nummer: String
    var datum: String
    var empfaengerName: String
    var netto: Double
    var ust: Double
    var brutto: Double
    var bezahltAm: String?
    var stand: String            // offen · bezahlt · storniert
    var storniert: String?       // Nummer der stornierten Rechnung

    var id: String { nummer }

    var istOffen: Bool { stand == "offen" }

    /// Was in der Liste steht — ohne Technik-Vokabular.
    var standText: String {
        switch stand {
        case "bezahlt": return "bezahlt" + (bezahltAm.map { " am " + tagKurz($0) } ?? "")
        case "storniert": return "storniert"
        default: return "offen"
        }
    }

    init?(json: [String: Any]) {
        guard let nummer = json["nummer"] as? String else { return nil }
        self.nummer = nummer
        datum = json["datum"] as? String ?? ""
        let empf = json["empfaenger"] as? [String: Any]
        empfaengerName = (empf?["name"] as? String) ?? "—"
        netto = json["netto"] as? Double ?? 0
        ust = json["ust"] as? Double ?? 0
        brutto = json["brutto"] as? Double ?? 0
        bezahltAm = json["bezahlt_am"] as? String
        stand = json["stand"] as? String ?? "offen"
        storniert = json["storniert"] as? String
    }

    init(nummer: String, datum: String, empfaengerName: String, netto: Double,
         ust: Double, brutto: Double, bezahltAm: String? = nil,
         stand: String = "offen", storniert: String? = nil) {
        self.nummer = nummer; self.datum = datum; self.empfaengerName = empfaengerName
        self.netto = netto; self.ust = ust; self.brutto = brutto
        self.bezahltAm = bezahltAm; self.stand = stand; self.storniert = storniert
    }
}

/// Was der Entwurf zusammenrechnet, während getippt wird. Dieselbe Logik wie
/// auf dem Server — der Server bleibt die Wahrheit, die App zeigt sie sofort.
struct RechnungsSumme: Equatable {
    var netto: Double = 0
    var ust: Double = 0
    var brutto: Double = 0
    var jeSatz: [(satz: Int, netto: Double, ust: Double)] = []

    static func == (a: RechnungsSumme, b: RechnungsSumme) -> Bool {
        a.netto == b.netto && a.ust == b.ust && a.brutto == b.brutto
            && a.jeSatz.map(\.satz) == b.jeSatz.map(\.satz)
            && a.jeSatz.map(\.netto) == b.jeSatz.map(\.netto)
    }
}

enum Rechnungsrechnung {
    /// Summen einer Rechnung. `kleinunternehmer` heißt: kein Steuerausweis.
    static func summe(_ positionen: [RechnungPosition],
                      kleinunternehmer: Bool) -> RechnungsSumme {
        var s = RechnungsSumme()
        s.netto = positionen.reduce(0) { $0 + $1.gesamt }.aufCent
        guard !kleinunternehmer else {
            s.brutto = s.netto
            return s
        }
        var jeSatz: [Int: Double] = [:]
        for p in positionen where p.ustSatz > 0 {
            jeSatz[p.ustSatz, default: 0] += p.gesamt
        }
        s.jeSatz = jeSatz.keys.sorted().map { satz in
            let netto = (jeSatz[satz] ?? 0).aufCent
            return (satz: satz, netto: netto,
                    ust: (netto * Double(satz) / 100).aufCent)
        }
        s.ust = s.jeSatz.reduce(0) { $0 + $1.ust }.aufCent
        s.brutto = (s.netto + s.ust).aufCent
        return s
    }

    /// Bis 250 € brutto genügt die Kleinbetragsrechnung (§ 33 UStDV).
    static let kleinbetragGrenze = 250.0

    static func istKleinbetrag(_ brutto: Double) -> Bool {
        abs(brutto) <= kleinbetragGrenze
    }

    /// Was fehlt, bevor die Rechnung rausgehen darf — in Klartext.
    static func fehlt(empfaenger: Empfaenger, positionen: [RechnungPosition],
                      brutto: Double) -> [String] {
        var maengel: [String] = []
        if empfaenger.name.trimmed.isEmpty { maengel.append("Wer bekommt die Rechnung?") }
        if empfaenger.anschrift.trimmed.isEmpty && !istKleinbetrag(brutto) {
            maengel.append("Für Beträge über 250 € gehört die Anschrift dazu.")
        }
        if positionen.isEmpty { maengel.append("Ohne Position ist es keine Rechnung.") }
        if positionen.contains(where: { $0.text.trimmed.isEmpty }) {
            maengel.append("Jede Zeile braucht eine Bezeichnung.")
        }
        if positionen.contains(where: { $0.einzelpreis == 0 }) {
            maengel.append("Eine Zeile hat noch keinen Betrag.")
        }
        return maengel
    }
}

/// Ein Vertrag aus der Kiste — was er monatlich kostet und wann zu handeln ist.
struct Vertrag: Identifiable, Equatable {
    var artName: String
    var partner: String
    var betragMonat: Double?
    var laufzeitBis: String?
    var kuendigungsfrist: String?
    var kuendigenBis: String?
    var kuendigenTage: Int?
    var fristSicher: Bool
    var fristHinweis: String

    var id: String { partner + artName }

    var betragText: String {
        guard let b = betragMonat else { return "kein Betrag erkannt" }
        return "\(fmtEur(b)) im Monat"
    }

    /// Der Satz, der in der Liste steht — ehrlich, wenn babu die Frist nicht las.
    var fristText: String {
        guard fristSicher, let bis = kuendigenBis else { return fristHinweis }
        guard let tage = kuendigenTage else { return "kündbar bis " + tagKurz(bis) }
        if tage < 0 { return "Frist war am " + tagKurz(bis) }
        if tage == 0 { return "Heute ist der letzte Tag zum Kündigen" }
        return "Kündigen bis \(tagKurz(bis)) — noch \(tage) Tage"
    }

    init?(json: [String: Any]) {
        artName = json["art_name"] as? String ?? "Vertrag"
        partner = json["partner"] as? String ?? "—"
        betragMonat = json["betrag_monat"] as? Double
        laufzeitBis = json["laufzeit_bis"] as? String
        kuendigungsfrist = json["kuendigungsfrist"] as? String
        let frist = json["kuendigen_bis"] as? [String: Any]
        kuendigenBis = frist?["datum"] as? String
        kuendigenTage = frist?["tage"] as? Int
        fristSicher = (frist?["sicher"] as? Bool) ?? false
        fristHinweis = (frist?["hinweis"] as? String) ?? ""
    }
}

// MARK: - Kleinkram

extension Double {
    /// Auf den Cent — Geld rundet man einmal, nicht bei jeder Zwischenrechnung.
    var aufCent: Double { (self * 100).rounded() / 100 }
}

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}

/// Betrag aus dem, was jemand tippt — deutsch mit Komma, notfalls mit Punkt.
/// Ein leeres Feld ist 0, nicht „ungültig": die Nutzerin tippt gerade erst.
func betragAusText(_ text: String) -> Double {
    var roh = text
        .replacingOccurrences(of: "€", with: "")
        .replacingOccurrences(of: " ", with: "")
        .trimmed
    // Der Punkt ist zweideutig: „1.250" meint tausend­zweihundertfünfzig,
    // „450.50" meint vierhundertfünfzig Komma fünfzig. Entschieden wird so:
    // Gibt es ein Komma, ist der Punkt Tausendertrenner. Sonst gilt ein
    // einzelner Punkt mit genau zwei Ziffern dahinter als Komma.
    if roh.contains(",") {
        roh = roh.replacingOccurrences(of: ".", with: "")
                 .replacingOccurrences(of: ",", with: ".")
    } else {
        let teile = roh.split(separator: ".", omittingEmptySubsequences: false)
        if teile.count == 2 && teile[1].count == 2 {
            roh = teile.joined(separator: ".")          // als Dezimalpunkt lesen
        } else {
            roh = roh.replacingOccurrences(of: ".", with: "")
        }
    }
    return Double(roh) ?? 0
}

/// Betrag im Eingabefeld. Null zeigt NICHTS — sonst tippt man hinter die
/// vorbelegte 0,00 und bekommt 0,00450 heraus.
func betragAlsText(_ betrag: Double) -> String {
    guard betrag != 0 else { return "" }
    return String(format: "%.2f", betrag).replacingOccurrences(of: ".", with: ",")
}

/// „2026-09-30" → „30.09.2026". Leeres bleibt leer.
func tagKurz(_ iso: String) -> String {
    let teile = iso.prefix(10).split(separator: "-")
    guard teile.count == 3 else { return iso }
    return "\(teile[2]).\(teile[1]).\(teile[0])"
}
