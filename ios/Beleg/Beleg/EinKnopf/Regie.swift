import Foundation

/// Die Regie entscheidet, welche EINE Seite gerade dran ist.
///
/// Reine Logik: kein SwiftUI, kein Netz, kein Store — darum im Harness
/// prüfbar (`ios/Tests/einknopf`). Die Lage kommt von außen (Belegbox oder
/// Rundgang), heraus kommt eine Seite und ihr Blatt: eine Zahl, ein Satz,
/// ein Knopf. Nichts sonst. Oberste passende Regel gewinnt.
enum Regie {

    struct Frist: Equatable {
        var datum: Date
        /// Der Tag, wie er im Satz steht — „10."
        var tagText: String
    }

    struct Frage: Equatable {
        /// Beleg-Kennung oder Schlüssel des Rundgangs — stabil, damit
        /// „später" die richtige Seite trifft.
        var kennung: String
        /// Gesetzt → die Buchhaltung fragt selbst (BuchungsfragenView).
        var belegID: UUID?
        var lieferant: String
        var betrag: Double
        var text: String
        /// Antworten fürs Halbblatt. Leer → die Buchhaltung fragt selbst.
        var optionen: [String]
    }

    struct Fehlend: Equatable {
        var schluessel: String
        var datumKurz: String      // „12.08."
        var betrag: Double
        var an: String
    }

    struct Monat: Equatable {
        var schluessel: String     // „2026-08"
        var name: String           // „August"
        var stand: String          // laeuft · wartet · bereit · freigegeben
        var zahllast: Double?      // > 0 zahlen, < 0 kommt zurück
        var ergebnis: Double?
    }

    /// Alles, was die Regie wissen darf. Was hier nicht steht, sieht sie nicht.
    struct Lage {
        var jetzt: Date
        var kleinunternehmerin = false
        var frist: Frist?
        /// Offene Belege plus ungedeckte Abbuchungen — der Grund für die Frist-Seite.
        var offeneAnzahl = 0
        var frage: Frage?
        var fehlend: Fehlend?
        var monat: Monat?
        /// Vorsteuer der gebuchten Belege dieses Monats (Kleinunternehmerin: Brutto).
        var zurueckgeholt = 0.0
        var heuteBelege = 0
        var heuteZurueck = 0.0
        /// Was vom laufenden Monat bisher bleibt (`zahlen.ergebnis`).
        var ergebnisMonat: Double?
    }

    enum Stimmung { case ruhig, mahnend, dringend, fertig }

    enum Seite: Equatable {
        case fristNaht(tage: Int)
        case frage(Frage)
        case belegFehlt(Fehlend)
        case monatFertig(Monat)
        case heim(abend: Bool)

        /// Stabil je Inhalt — Schlüssel für „später" und für den Seitenwechsel.
        var kennung: String {
            switch self {
            case .fristNaht: return "frist"
            case .frage(let f): return "frage:\(f.kennung)"
            case .belegFehlt(let f): return "fehlt:\(f.schluessel)"
            case .monatFertig(let m): return "monat:\(m.schluessel)"
            case .heim(let abend): return abend ? "heim:abend" : "heim:tag"
            }
        }
    }

    /// Das, was auf der Seite steht. Mehr gibt es nicht.
    struct Blatt: Equatable {
        var zahl: String
        var label: String?
        var satz: String
        var knopf: String
        var stimmung: Stimmung
    }

    // MARK: - Entscheiden

    static func entscheide(_ l: Lage, kalender: Calendar = .current) -> Seite {
        if let f = l.frist, l.offeneAnzahl > 0 {
            let t = tageBis(f.datum, von: l.jetzt, kalender)
            if (0...7).contains(t) { return .fristNaht(tage: t) }
        }
        if let f = l.frage { return .frage(f) }
        if let f = l.fehlend { return .belegFehlt(f) }
        if let m = l.monat, m.stand == "bereit" { return .monatFertig(m) }
        return .heim(abend: kalender.component(.hour, from: l.jetzt) >= 18)
    }

    static func blatt(_ s: Seite, _ l: Lage, kalender: Calendar = .current) -> Blatt {
        switch s {
        case .fristNaht(let tage):
            let tag = l.frist?.tagText ?? "10."
            return Blatt(zahl: tageText(tage), label: nil,
                         satz: "Bis zum \(tag) muss die Umsatzsteuer raus. "
                               + belegeText(l.offeneAnzahl),
                         knopf: "Loslegen",
                         stimmung: tage <= 3 ? .dringend : .mahnend)

        case .frage(let f):
            return Blatt(zahl: f.betrag > 0 ? fmtEur(f.betrag) : "1",
                         label: f.betrag > 0 ? f.lieferant : "Beleg wartet",
                         satz: f.text, knopf: "Antworten", stimmung: .ruhig)

        case .belegFehlt(let f):
            return Blatt(zahl: fmtEur(f.betrag), label: "vom Konto abgegangen",
                         satz: "Am \(f.datumKurz) gingen \(fmtEur(f.betrag)) an \(f.an) "
                               + "vom Konto. Dazu fehlt der Beleg.",
                         knopf: "Beleg reinwerfen", stimmung: .ruhig)

        case .monatFertig(let m):
            let satz = "Dein \(m.name) ist gerechnet."
            if l.kleinunternehmerin {
                return Blatt(zahl: fmtEur(m.ergebnis ?? 0), label: "bleibt dir",
                             satz: satz, knopf: "Monat abschließen", stimmung: .fertig)
            }
            let z = m.zahllast ?? 0
            return Blatt(zahl: fmtEur(abs(z)),
                         label: z < 0 ? "bekommst du zurück" : "zahlst du",
                         satz: satz, knopf: "Ans Finanzamt schicken", stimmung: .fertig)

        case .heim(let abend):
            let monat = monatsname(jetzt: l.jetzt, kalender)
            let zaehlerLabel = l.kleinunternehmerin ? "erfasst im \(monat)"
                                                    : "zurückgeholt im \(monat)"
            guard abend else {
                return Blatt(zahl: fmtEur(l.zurueckgeholt), label: zaehlerLabel,
                             satz: "Wirf alles rein — Bons, Rechnungen, Post vom Amt. "
                                   + "babu sortiert.",
                             knopf: "Reinwerfen", stimmung: .ruhig)
            }
            var satz: String
            if l.heuteBelege == 0 {
                satz = "Heute nichts reingeworfen — auch gut."
            } else {
                let belege = l.heuteBelege == 1 ? "1 Beleg" : "\(l.heuteBelege) Belege"
                satz = l.kleinunternehmerin
                    ? "Heute \(belege) reingeworfen."
                    : "Heute \(belege) reingeworfen, \(fmtEur(l.heuteZurueck)) zurückgeholt."
            }
            if let e = l.ergebnisMonat {
                satz += " Im \(monat) bleiben dir bisher \(fmtEur(e))."
                return Blatt(zahl: fmtEur(e), label: "Bleibt dir", satz: satz,
                             knopf: "Reinwerfen", stimmung: .ruhig)
            }
            return Blatt(zahl: fmtEur(l.zurueckgeholt), label: zaehlerLabel, satz: satz,
                         knopf: "Reinwerfen", stimmung: .ruhig)
        }
    }

    // MARK: - Der Zähler

    static let gebucht: Set<BelegStatus> = [.automatisch, .bestaetigt, .korrigiert, .fixiert]

    /// Was dieser Monat schon zurückgeholt hat — die Vorsteuer der gebuchten
    /// Belege. Kleinunternehmerin: es gibt keine, dann zählt das Brutto als
    /// „erfasst". Demo-Belege zählen nie.
    static func zaehler(belege: [Beleg], monat: String, jetzt: Date,
                        kleinunternehmerin: Bool, kalender: Calendar = .current)
            -> (betrag: Double, label: String, heuteBelege: Int, heuteZurueck: Double) {
        let echt = belege.filter { gebucht.contains($0.status) && $0.istDemo != true }
        let imMonat = echt.filter { belegMonatSchluessel($0.datumText) == monat }
        let heute = echt.filter {
            guard let z = $0.siegelZeit else { return false }
            return kalender.isDate(z, inSameDayAs: jetzt)
        }
        let name = monatsname(schluessel: monat)
        if kleinunternehmerin {
            return (imMonat.reduce(0) { $0 + $1.brutto }, "erfasst im \(name)",
                    heute.count, 0)
        }
        return (imMonat.reduce(0) { $0 + $1.ust }, "zurückgeholt im \(name)",
                heute.count, heute.reduce(0) { $0 + $1.ust })
    }

    // MARK: - Kleine Helfer

    static func tageBis(_ ziel: Date, von: Date, _ k: Calendar) -> Int {
        k.dateComponents([.day], from: k.startOfDay(for: von),
                         to: k.startOfDay(for: ziel)).day ?? 0
    }

    static func tageText(_ t: Int) -> String {
        t <= 0 ? "Heute" : (t == 1 ? "1 Tag" : "\(t) Tage")
    }

    static func belegeText(_ n: Int) -> String {
        n == 1 ? "1 Beleg fehlt noch." : "\(n) Belege fehlen noch."
    }

    /// „2026-08" → „August"
    static func monatsname(schluessel: String) -> String {
        String(belegMonatTitel(schluessel).prefix { $0 != " " })
    }

    static func monatsname(jetzt: Date, _ k: Calendar) -> String {
        let c = k.dateComponents([.year, .month], from: jetzt)
        return monatsname(schluessel: String(format: "%04d-%02d", c.year ?? 2000, c.month ?? 1))
    }

    /// „12.08.2026" → „12.08." (die Abbuchung im Satz)
    static func datumKurz(_ datum: String) -> String {
        let t = datum.split(separator: ".")
        guard t.count >= 2 else { return datum }
        return "\(t[0]).\(t[1])."
    }
}
