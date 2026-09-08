import Foundation

// Wo Geld im Spiel ist: Kassenbuch, Monatsabschluss und Abgleich,
// Kontoauszug und Zahlungen, gestellte Rechnungen, die Vertragskiste
// sowie Marke und Marketing (beides kostet und haengt am Briefkopf).
//
// Nicht hierher: der einzelne Beleg (`+Belege`), Termine, Team und Chat
// (`+Betrieb`), Netz-Helfer (Kern).

extension AblageService {

    // MARK: - Briefkopf und Logo

    static func markeKatalog(basis: URL, pat: String) async
            -> (farben: [[String: Any]], stile: [[String: Any]])? {
        var request = URLRequest(url: basis.appendingPathComponent("api/marke/katalog"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return nil }
        return (json["farben"] as? [[String: Any]] ?? [],
                json["stile"] as? [[String: Any]] ?? [])
    }

    static func markeFarbeWaehlen(_ schluessel: String, basis: URL,
                                  pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent("api/marke/farbe"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["farbe": schluessel])
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    /// Logo entwerfen lassen. Dauert; der Name des Salons geht dafür an einen
    /// Dienst außerhalb des Hauses — die Ansicht sagt das.
    static func logoEntwerfen(stil: String, basis: URL, pat: String) async -> String? {
        var teile = URLComponents(url: basis.appendingPathComponent("api/marke/logo/entwerfen"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "stil", value: stil)]
        guard let url = teile?.url else { return "Das hat nicht geklappt." }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 180
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if ergebnis == .uebertragen { return nil }
        if let daten, let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let fehler = json["fehler"] as? String { return fehler }
        return "Das hat gerade nicht geklappt."
    }

    static func logoSenden(_ bild: Data, basis: URL, pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent("api/marke/logo"))
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("image/png", forHTTPHeaderField: "Content-Type")
        request.httpBody = bild
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    static func logoLaden(basis: URL, pat: String) async -> Data? {
        var request = URLRequest(url: basis.appendingPathComponent("api/marke/logo"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return daten
    }

    /// Ein Knopf, zehn Zeichen. Dauert; die zehn entstehen gleichzeitig.
    static func logoVorschlaege(saat: Int, basis: URL, pat: String) async
            -> (vorschlaege: [[String: Any]], fehler: String?) {
        var teile = URLComponents(url: basis.appendingPathComponent("api/marke/vorschlaege"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "saat", value: String(saat))]
        guard let url = teile?.url else { return ([], "Das hat nicht geklappt.") }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 240
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        let json = daten.flatMap {
            try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
        }
        if ergebnis == .uebertragen, let liste = json?["vorschlaege"] as? [[String: Any]] {
            return (liste, nil)
        }
        return ([], json?["fehler"] as? String ?? "Das hat gerade nicht geklappt.")
    }

    static func logoVorschlagBild(_ nummer: Int, basis: URL, pat: String) async -> Data? {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/marke/vorschlag/\(nummer)"))
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return daten
    }

    /// Einen Vorschlag annehmen — Logo, Farbe, Schrift und Briefkopf in einem.
    static func logoWaehlen(nummer: Int, saat: Int, basis: URL,
                            pat: String) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("api/marke/waehlen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["nummer": nummer, "saat": saat])
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        guard ergebnis == .uebertragen, let daten,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return nil }
        return json["in_worten"] as? String
    }

    // MARK: - Marketing

    static func marketingStuecke(basis: URL, pat: String) async -> [[String: Any]] {
        var request = URLRequest(url: basis.appendingPathComponent("api/marketing"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return [] }
        return json["stuecke"] as? [[String: Any]] ?? []
    }

    static func marketingEntwerfen(stueck: String, text: String, basis: URL,
                                   pat: String) async -> String? {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/marketing/entwerfen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 240
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["stueck": stueck, "text": text])
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if ergebnis == .uebertragen { return nil }
        if let daten, let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let fehler = json["fehler"] as? String { return fehler }
        return "Das hat gerade nicht geklappt."
    }

    static func marketingBild(_ schluessel: String, basis: URL,
                              pat: String) async -> Data? {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/marketing/\(schluessel)"))
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return daten
    }

    static func kassenvorschlag(tag: String, basis: URL, pat: String) async
            -> [String: Any]? {
        await holen("api/kasse/vorschlag?datum=\(tag)", basis: basis, pat: pat)
    }

    /// Welcher Monat wartet — und was fehlt ihm noch?
    static func monatslauf(basis: URL, pat: String) async -> [String: Any]? {
        var request = URLRequest(url: basis.appendingPathComponent("api/monatslauf"))
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return nil }
        return json
    }

    /// Wer hat bezahlt? Vorschläge aus dem Kontoauszug.
    static func zahlungsvorschlaege(basis: URL, pat: String) async -> [[String: Any]] {
        var request = URLRequest(url: basis.appendingPathComponent("api/zahlungen"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return [] }
        return json["vorschlaege"] as? [[String: Any]] ?? []
    }

    static func zahlungUebernehmen(nummer: String, am: String, basis: URL,
                                   pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/zahlungen/uebernehmen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["nummer": nummer, "am": am])
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    /// Vertrag ablegen — babu liest, was er monatlich kostet.
    static func vertragAblegen(daten: Data, dateiname: String, basis: URL,
                               pat: String) async -> String? {
        var teile = URLComponents(url: basis.appendingPathComponent("api/dokumente"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "name", value: dateiname),
                             URLQueryItem(name: "titel", value: "Vertrag · " + dateiname),
                             URLQueryItem(name: "art", value: "vertrag")]
        guard let url = teile?.url else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.httpBody = daten
        let (ergebnis, antwort) = await ausfuehrenMitDaten(request)
        guard ergebnis == .uebertragen, let antwort,
              let json = try? JSONSerialization.jsonObject(with: antwort) as? [String: Any]
        else { return nil }
        return json["pfad"] as? String
    }

    /// Eckdaten eines gelesenen Vertrags (entstehen im Hintergrund).
    static func vertragDaten(pfad: String, basis: URL,
                             pat: String) async -> (art: String, partner: String?,
                                                    betrag: Double?, zahlweise: String,
                                                    einfach: String)? {
        var request = URLRequest(url: basis.appendingPathComponent("api/dokumente"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["dokumente"] as? [[String: Any]],
              let treffer = liste.first(where: { ($0["pfad"] as? String) == pfad }),
              let v = treffer["vertrag"] as? [String: Any],
              let einfach = v["einfach"] as? String, !einfach.isEmpty
        else { return nil }
        return (v["art_name"] as? String ?? "Vertrag", v["partner"] as? String,
                v["betrag_monat"] as? Double,
                v["zahlweise"] as? String ?? "monatlich", einfach)
    }

    // MARK: - Rechnungen stellen

    /// Alle gestellten Rechnungen samt Stand (offen/bezahlt/storniert).
    static func rechnungenLaden(basis: URL, pat: String) async
            -> (rechnungen: [Rechnung], offenSumme: Double, versteuerung: String)? {
        var request = URLRequest(url: basis.appendingPathComponent("api/rechnungen"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["rechnungen"] as? [[String: Any]] else { return nil }
        return (liste.compactMap(Rechnung.init(json:)),
                json["offen_summe"] as? Double ?? 0,
                json["versteuerung"] as? String ?? "ist")
    }

    /// Rechnung festschreiben. Der Server vergibt die Nummer — erst danach
    /// baut die App das PDF. Liefert die Nummer oder einen Klartext-Fehler.
    static func rechnungStellen(datum: String, empfaenger: Empfaenger,
                                positionen: [RechnungPosition],
                                leistungszeitpunkt: String?, hinweis: String,
                                basis: URL, pat: String) async
            -> (nummer: String?, fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/rechnungen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let zeilen = positionen.map { p -> [String: Any] in
            ["text": p.text, "menge": p.menge, "einzelpreis": p.einzelpreis,
             "ust_satz": p.ustSatz]
        }
        var koerper: [String: Any] = [
            "datum": datum, "positionen": zeilen,
            "empfaenger": ["name": empfaenger.name, "anschrift": empfaenger.anschrift,
                           "ust_id": empfaenger.ustId],
        ]
        if let l = leistungszeitpunkt, !l.isEmpty { koerper["leistungszeitpunkt"] = l }
        if !hinweis.isEmpty { koerper["hinweis"] = hinweis }
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return (nil, "Gerade keine Verbindung — die Rechnung bleibt ein Entwurf.")
        }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        if http.statusCode == 200, let nummer = json?["nummer"] as? String {
            return (nummer, nil)
        }
        return (nil, json?["fehler"] as? String ?? "Das hat gerade nicht geklappt.")
    }

    /// Das fertige PDF nachreichen — mit der Nummer, die der Server vergab.
    static func rechnungPdfSenden(_ pdf: Data, nummer: String, basis: URL,
                                  pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/rechnung/\(nummer)/pdf"))
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/pdf", forHTTPHeaderField: "Content-Type")
        request.httpBody = pdf
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    static func rechnungBezahlt(nummer: String, am: String, basis: URL,
                                pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/rechnung/\(nummer)/bezahlt"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["am": am])
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    static func rechnungStornieren(nummer: String, basis: URL,
                                   pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/rechnung/\(nummer)/storno"))
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    // MARK: - Die Vertragskiste

    static func vertraegeLaden(basis: URL, pat: String) async
            -> (vertraege: [Vertrag], monatlich: Double, anstehend: [Vertrag])? {
        var request = URLRequest(url: basis.appendingPathComponent("api/vertraege"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["vertraege"] as? [[String: Any]] else { return nil }
        let anstehend = (json["anstehend"] as? [[String: Any]] ?? [])
            .compactMap(Vertrag.init(json:))
        return (liste.compactMap(Vertrag.init(json:)),
                json["monatlich"] as? Double ?? 0, anstehend)
    }

    // MARK: - Kontoauszug

    /// Kontoauszug abgeben — der Server liest die Umsätze sofort und legt sie
    /// für den Zahlungsabgleich bereit. Nur das Original-PDF der Bank trägt
    /// einen Textlayer; ein Foto oder Scan kann der Abgleich nicht lesen.
    static func kontoauszugAbgeben(daten: Data, dateiname: String, basis: URL,
                                   pat: String) async
            -> (gelesen: (monat: String, umsaetze: Int)?, meldung: String?) {
        var teile = URLComponents(url: basis.appendingPathComponent("api/kontoauszug"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "name", value: dateiname)]
        guard let url = teile?.url else { return (nil, "Das hat gerade nicht geklappt.") }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.httpBody = daten
        guard let (koerper, roh) = try? await URLSession.shared.data(for: request),
              let http = roh as? HTTPURLResponse
        else { return (nil, "Keine Verbindung — später noch einmal.") }
        let json = (try? JSONSerialization.jsonObject(with: koerper)) as? [String: Any]
        if (200..<300).contains(http.statusCode), let monat = json?["monat"] as? String {
            return ((monat, json?["umsaetze"] as? Int ?? 0), nil)
        }
        return (nil, json?["fehler"] as? String ?? "Das hat gerade nicht geklappt.")
    }

    /// Der Abgleich eines Monats: welche Abbuchung hat ihren Beleg, welche nicht.
    static func abgleichLaden(monat: String, basis: URL, pat: String) async
            -> (auszugDa: Bool, gedeckt: Int, fehlend: Int, fehlendSumme: Double,
                bankgebuehren: Int, einnahmenSumme: Double,
                positionen: [AbgleichPosition])? {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/abgleich/\(monat)"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let da = json["auszug_da"] as? Bool else { return nil }
        let positionen = ((json["positionen"] as? [[String: Any]]) ?? [])
            .enumerated().map { AbgleichPosition(json: $1, nr: $0) }
        return (da,
                (json["gedeckt"] as? [[String: Any]])?.count ?? 0,
                (json["fehlend"] as? [[String: Any]])?.count ?? 0,
                json["fehlend_summe"] as? Double ?? 0,
                (json["bankgebuehren"] as? [[String: Any]])?.count ?? 0,
                json["einnahmen_summe"] as? Double ?? 0,
                positionen)
    }

    // MARK: - Monatsabschluss

    static func monatsabschluss(monat: String, basis: URL,
                                pat: String) async -> Monatsabschluss? {
        var request = URLRequest(url: basis.appendingPathComponent("api/monatsabschluss/\(monat)"))
        request.timeoutInterval = 60
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return nil }
        return Monatsabschluss(json: json)
    }

    /// Tagesblatt des Kassenbuchs in die Belegbox legen (POST /api/kassenbuch).
    static func kassenblattSenden(_ b: Kassenbericht, basis: URL,
                                  pat: String) async -> KassenblattAntwort {
        var request = URLRequest(url: basis.appendingPathComponent("api/kassenbuch"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var blatt: [String: Any] = [
            "datum": b.datum,
            "bestandVortag": b.bestandVortag, "einnahmenBar": b.einnahmenBar,
            "gutscheinVerkauf": b.gutscheinVerkauf,
            "privateinlagen": b.privateinlagen, "barabhebungBank": b.barabhebungBank,
            "ecZahlungen": b.ecZahlungen, "gutscheineEingeloest": b.gutscheineEingeloest,
            "trinkgeldKarte": b.trinkgeldKarte, "trinkgeldTeamEC": b.trinkgeldTeamEC,
            "sonstigeAusgaben": b.sonstigeAusgaben, "privatentnahmen": b.privatentnahmen,
            "vorschussTeam": b.vorschussTeam, "auslagenErstattet": b.auslagenErstattet,
            "einzahlungBank": b.einzahlungBank, "gezaehltSchluss": b.gezaehltSchluss,
        ]
        if let grund = b.differenzGrund, !grund.isEmpty { blatt["differenzGrund"] = grund }
        if let notiz = b.sonstigeNotiz, !notiz.isEmpty { blatt["sonstigeNotiz"] = notiz }
        if !b.trinkgeldVerteilt.isEmpty {
            blatt["trinkgeldVerteilt"] = b.trinkgeldVerteilt.map {
                ["name": $0.name, "betrag": $0.betrag]
            }
        }
        // Die Korrekturspur muss mit: die Belegbox ist der versionierte Ort,
        // an dem eine Prüfung nachlesen kann, was geändert wurde und warum.
        // Bliebe sie im Telefon, wäre sie mit dem Telefon weg.
        if let korrekturen = b.korrekturen, !korrekturen.isEmpty {
            let iso = ISO8601DateFormatter()
            blatt["korrekturen"] = korrekturen.map { k in
                [
                    "zeitpunkt": iso.string(from: k.zeitpunkt),
                    "grund": k.grund,
                    "aenderungen": k.aenderungen.map {
                        ["feld": $0.feld, "vorher": $0.vorher, "nachher": $0.nachher]
                    },
                ] as [String: Any]
            }
        }
        if let grund = b.korrekturen?.last?.grund, !grund.isEmpty {
            // Der Server verlangt für einen Tag, der schon in der Belegbox
            // liegt, eine Begründung — er liest sie sonst aus der
            // Korrekturspur. Sie hier auch als eigenes Feld zu schicken,
            // macht die Absicht eindeutig.
            blatt["grund"] = grund
        }
        request.httpBody = try? JSONSerialization.data(withJSONObject: blatt)
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if case .abgelehnt = ergebnis {
            // Eine Ablehnung ist keine Störung, die sich von selbst legt:
            // der Monat ist abgeschlossen, oder die Begründung fehlt. Der
            // Grund muss zu Nina durch, sonst versucht die App es ewig
            // weiter und niemand erfährt, warum nichts ankommt.
            let text = (try? JSONSerialization.jsonObject(with: daten ?? Data()))
                .flatMap { ($0 as? [String: Any])?["fehler"] as? String }
            return .abgelehnt(text ?? "Die Belegbox hat das Blatt nicht angenommen.")
        }
        return ergebnis == .uebertragen ? .ok : .spaeterNochmal
    }

    /// Wie es dem Tagesblatt ergangen ist. `abgelehnt` trägt den Satz, den
    /// der Server geschickt hat — er ist für Nina geschrieben.
    enum KassenblattAntwort: Equatable {
        case ok
        case spaeterNochmal
        case abgelehnt(String)
    }
}

/// Eine Position des Kontoauszugs, wie der Abgleich sie sieht — mit Haken.
struct AbgleichPosition: Identifiable {
    let id: Int
    let datum: String
    let gegenpartei: String
    let betrag: Double
    let status: String       // gedeckt | fehlt | bank | einnahme
    let stamm: String?

    init(json: [String: Any], nr: Int) {
        id = nr
        datum = json["datum"] as? String ?? ""
        gegenpartei = (json["gegenpartei"] as? String)
            ?? (json["typ"] as? String) ?? "Position"
        betrag = json["betrag"] as? Double ?? 0
        status = json["status"] as? String ?? "einnahme"
        stamm = json["stamm"] as? String
    }
}
