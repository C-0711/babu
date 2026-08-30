import Foundation

/// Ein Monat mit den Dokumenten, die zu ihm gehören.
///
/// Die Liste war eine einzige Kette: der Beleg von gestern über dem von
/// März, ohne Schnitt dazwischen. Buchhaltung passiert aber in Monaten —
/// abgerechnet, abgeschlossen und abgegeben wird je Monat. Also wird auch
/// so gezeigt: eine Überschrift je Monat, darunter das Papier dieses
/// Monats, mit Anzahl und Summe im Kopf.
struct Belegmonat: Identifiable {
    /// „2026-08"; leer heißt: auf dem Papier stand kein lesbares Datum.
    let schluessel: String
    let dokumente: [Beleg]

    var id: String { schluessel }
    var titel: String { Monatsgruppen.titel(schluessel) }
    var kurz: String { Monatsgruppen.kurz(schluessel) }
    var summe: Double { dokumente.reduce(0) { $0 + $1.brutto } }
}

enum Monatsgruppen {
    static let monatsnamen = ["Januar", "Februar", "März", "April", "Mai",
                              "Juni", "Juli", "August", "September",
                              "Oktober", "November", "Dezember"]
    static let monatskurz = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                             "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

    /// „05.08.2026" → „2026-08-05". Unlesbares Datum → leer.
    ///
    /// Zweistellige Jahre kommen von Bons, die nur „26" drucken; das ist
    /// dasselbe Zugeständnis, das `ablageDateiname` schon macht.
    static func tagesschluessel(_ datumText: String) -> String {
        let teile = datumText.split(separator: ".")
        guard teile.count == 3,
              let tag = Int(teile[0]), let monat = Int(teile[1]),
              let jahrRoh = Int(teile[2]),
              (1...31).contains(tag), (1...12).contains(monat) else { return "" }
        let jahr = teile[2].count == 2 ? 2000 + jahrRoh : jahrRoh
        guard (2000...2100).contains(jahr) else { return "" }
        return String(format: "%04d-%02d-%02d", jahr, monat, tag)
    }

    /// „05.08.2026" → „2026-08". Unlesbares Datum → leer.
    static func schluessel(_ datumText: String) -> String {
        let tag = tagesschluessel(datumText)
        return tag.isEmpty ? "" : String(tag.prefix(7))
    }

    /// Der Zeitstempel der Server-Ablage („2026-08-05T09:12:00") → „2026-08".
    static func schluesselAusAblagezeit(_ zeit: String?) -> String {
        guard let zeit, zeit.count >= 7 else { return "" }
        let kopf = String(zeit.prefix(7))
        let teile = kopf.split(separator: "-")
        guard teile.count == 2, let jahr = Int(teile[0]), let monat = Int(teile[1]),
              (2000...2100).contains(jahr), (1...12).contains(monat) else { return "" }
        return String(format: "%04d-%02d", jahr, monat)
    }

    /// Der Monat aus einem Ablage-Dateinamen („beleg_2026-08-05_dm_….jpg").
    static func schluesselAusName(_ name: String) -> String {
        guard let treffer = name.range(of: #"\d{4}-\d{2}-\d{2}"#,
                                       options: .regularExpression) else { return "" }
        let teile = name[treffer].split(separator: "-")
        guard let jahr = Int(teile[0]), let monat = Int(teile[1]),
              (2000...2100).contains(jahr), (1...12).contains(monat)
        else { return "" }   // „0000-00-00" heißt: Datum unbekannt
        return String(format: "%04d-%02d", jahr, monat)
    }

    /// Der Monat eines Stücks aus der Ablage. Das Datum im Namen wiegt
    /// schwerer als die Uhrzeit des Uploads — hochgeladen wird oft Wochen
    /// später, und der Beleg gehört in den Monat, in dem er entstand.
    static func schluesselFuerAblage(name: String, zeit: String?) -> String {
        let ausName = schluesselAusName(name)
        return ausName.isEmpty ? schluesselAusAblagezeit(zeit) : ausName
    }

    /// „2026-08" → „August 2026".
    static func titel(_ schluessel: String) -> String {
        let teile = schluessel.split(separator: "-")
        guard teile.count == 2, let monat = Int(teile[1]), (1...12).contains(monat)
        else { return "Ohne Datum" }
        return "\(monatsnamen[monat - 1]) \(teile[0])"
    }

    /// „2026-08" → „Aug 26" — die Kurzform für die Monatsleiste.
    static func kurz(_ schluessel: String) -> String {
        let teile = schluessel.split(separator: "-")
        guard teile.count == 2, let monat = Int(teile[1]), (1...12).contains(monat)
        else { return "Ohne Datum" }
        return "\(monatskurz[monat - 1]) \(teile[0].suffix(2))"
    }

    /// Ein Dokument mit seinem Tag und seinem Platz in der Liste.
    private struct Platziert {
        let platz: Int
        let tag: String
        let beleg: Beleg
    }

    /// Dokumente nach Monat gruppieren: jüngster Monat zuerst, innerhalb des
    /// Monats der jüngste Tag zuerst. Belege ohne lesbares Datum fallen nicht
    /// hinten runter — sie bekommen ihre eigene Gruppe ganz unten, sonst
    /// wäre ein falsch gelesenes Datum gleichbedeutend mit „verschwunden".
    static func gruppieren(_ dokumente: [Beleg]) -> [Belegmonat] {
        // Die Reihenfolge der Liste (zuletzt aufgenommen zuerst) entscheidet
        // bei gleichem Tag — sort ist in Swift nicht stabil, deshalb reist
        // der Platz in der Liste als zweiter Schlüssel mit.
        let mitPlatz = dokumente.enumerated().map { eintrag in
            Platziert(platz: eintrag.offset,
                      tag: tagesschluessel(eintrag.element.datumText),
                      beleg: eintrag.element)
        }
        let gruppen = Dictionary(grouping: mitPlatz) { String($0.tag.prefix(7)) }
        let reihenfolge = gruppen.keys.sorted { links, rechts in
            // Ohne Datum ganz nach unten, sonst absteigend nach Monat.
            if links.isEmpty { return false }
            if rechts.isEmpty { return true }
            return links > rechts
        }
        return reihenfolge.map { monat in
            let sortiert = (gruppen[monat] ?? []).sorted {
                $0.tag == $1.tag ? $0.platz < $1.platz : $0.tag > $1.tag
            }
            return Belegmonat(schluessel: monat, dokumente: sortiert.map(\.beleg))
        }
    }
}
