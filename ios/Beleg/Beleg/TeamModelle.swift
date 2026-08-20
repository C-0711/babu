import Foundation

/// Eine Mitarbeiterin — bewusst wenige Felder. Steuerklasse und
/// Sozialversicherung bleiben beim Lohnbüro; babu braucht die Kosten.
struct TeamPerson: Identifiable, Equatable {
    var id: Int = 0
    var name: String
    var email: String?
    var lohnArt: String = "fest"          // "fest" oder "stunden"
    var betrag: Double?
    var stundenlohn: Double?
    var stunden: Double?
    var aktiv: Bool = true
    var fotoPfad: String?

    var kostenMonat: Double {
        lohnArt == "stunden" ? (stundenlohn ?? 0) * (stunden ?? 0) : (betrag ?? 0)
    }

    var kostenText: String {
        guard kostenMonat > 0 else { return "kein Betrag hinterlegt" }
        if lohnArt == "stunden" {
            return "\(fmtEur(stundenlohn ?? 0)) × \(Int(stunden ?? 0)) Std = \(fmtEur(kostenMonat))"
        }
        return "\(fmtEur(kostenMonat)) im Monat"
    }

    init(id: Int = 0, name: String, email: String? = nil, lohnArt: String = "fest",
         betrag: Double? = nil, stundenlohn: Double? = nil, stunden: Double? = nil,
         aktiv: Bool = true, fotoPfad: String? = nil) {
        self.id = id; self.name = name; self.email = email; self.lohnArt = lohnArt
        self.betrag = betrag; self.stundenlohn = stundenlohn; self.stunden = stunden
        self.aktiv = aktiv; self.fotoPfad = fotoPfad
    }

    init?(json: [String: Any]) {
        guard let id = json["id"] as? Int, let name = json["name"] as? String
        else { return nil }
        self.init(id: id, name: name, email: json["email"] as? String,
                  lohnArt: json["lohn_art"] as? String ?? "fest",
                  betrag: json["betrag"] as? Double,
                  stundenlohn: json["stundenlohn"] as? Double,
                  stunden: json["stunden"] as? Double,
                  aktiv: json["aktiv"] as? Bool ?? true,
                  fotoPfad: json["foto"] as? String)
    }
}

/// Monatsabschluss: was reinkam, was rausging — und die Umsatzsteuer.
struct Monatsabschluss {
    struct Gruppe: Identifiable {
        var id: String { schluessel }
        let schluessel: String
        let name: String
        let netto: Double
        let anteil: Double?
        let ausVertrag: String?
        let geschaetzt: Bool
    }
    struct SteuerZeile: Identifiable {
        var id: String { kz }
        let kz: String
        let name: String
        let wert: Double
    }
    struct OffenerPunkt: Identifiable {
        var id: String { stamm }
        let stamm: String
        let lieferant: String
        let hinweis: String
    }

    let monat: String
    let umsatzNetto: Double
    let kostenNetto: Double
    let ergebnis: Double
    let ergebnisAnteil: Double?
    let gruppen: [Gruppe]
    let fehlt: [String]
    let tageErfasst: Int

    let steuerStand: String            // "entwurf" | "keine"
    let steuerSatz: String
    let steuerHinweis: String
    let steuerZeilen: [SteuerZeile]
    let zahllast: Double
    let offenePunkte: [OffenerPunkt]

    init?(json: [String: Any]) {
        guard let bwa = json["bwa"] as? [String: Any],
              let ustva = json["ustva"] as? [String: Any] else { return nil }
        monat = json["monat"] as? String ?? ""
        umsatzNetto = bwa["umsatz_netto"] as? Double ?? 0
        kostenNetto = bwa["kosten_netto"] as? Double ?? 0
        ergebnis = bwa["ergebnis"] as? Double ?? 0
        ergebnisAnteil = bwa["ergebnis_anteil"] as? Double
        fehlt = bwa["fehlt"] as? [String] ?? []
        tageErfasst = bwa["tage_erfasst"] as? Int
            ?? (json["erloese"] as? [String: Any])?["tage"] as? Int ?? 0
        gruppen = ((bwa["gruppen"] as? [[String: Any]]) ?? []).compactMap { g in
            guard let s = g["schluessel"] as? String, let n = g["name"] as? String
            else { return nil }
            return Gruppe(schluessel: s, name: n, netto: g["netto"] as? Double ?? 0,
                          anteil: g["anteil"] as? Double,
                          ausVertrag: g["aus_vertrag"] as? String,
                          geschaetzt: g["geschaetzt"] as? Bool ?? false)
        }
        steuerStand = ustva["stand"] as? String ?? "keine"
        steuerSatz = ustva["satz"] as? String ?? ""
        steuerHinweis = ustva["hinweis"] as? String ?? ""
        zahllast = ustva["zahllast"] as? Double ?? 0
        steuerZeilen = ((ustva["zeilen"] as? [[String: Any]]) ?? []).compactMap { z in
            guard let kz = z["kz"] as? String, let n = z["name"] as? String
            else { return nil }
            let netto = z["netto"] as? Double
            return SteuerZeile(kz: kz, name: n, wert: netto ?? (z["steuer"] as? Double ?? 0))
        }
        offenePunkte = ((ustva["pruefliste"] as? [[String: Any]]) ?? []).compactMap { p in
            guard let stamm = p["stamm"] as? String else { return nil }
            return OffenerPunkt(stamm: stamm,
                                lieferant: p["lieferant"] as? String ?? "Beleg",
                                hinweis: p["hinweis"] as? String ?? "")
        }
    }
}
