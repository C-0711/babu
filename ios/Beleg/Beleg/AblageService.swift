import Foundation
import Security
import UIKit

/// Ergebnis eines Ablage-Aufrufs (Upload oder Verbindungstest).
enum AblageErgebnis: Equatable {
    case uebertragen          // 2xx — bzw. beim Verbindungstest: Server + Token OK
    case tokenFehler          // 401
    case abgelehnt(Int)       // sonstiger HTTP-Status
    case nichtErreichbar      // Netzfehler (kein WLAN, falsches Netz, Timeout)
}

/// Ergebnis des Review-Abrufs — die Ursachen sind für die Nutzerin
/// grundverschieden und dürfen nicht alle wie „läuft noch" aussehen.
enum ReviewAntwort {
    case fertig(BelegReviewDaten)
    case nochNicht           // 404: Prüfung existiert (noch) nicht
    case zugangFehlt         // 401/403: Zugang ungültig oder nicht erlaubt
    case serverProblem       // 5xx oder unlesbare Antwort
    case keineVerbindung     // Netzfehler / Timeout
}

/// Antwort auf `GET /review/<stamm>/protokoll` — das Leseprotokoll als Text.
enum ProtokollAntwort {
    case fertig(String)
    case nochNicht           // 404: für diesen Beleg gibt es noch keines
    case zugangFehlt
    case serverProblem
    case keineVerbindung
}

/// Fehlermeldung aus dem Chat-Stream (SSE-Frame `{"fehler": …}`).
struct ChatFehler: Error {
    let meldung: String
}

/// Eine Zeile aus „Meine Meldungen" (`GET /api/rueckmeldungen`).
struct Meldungszeile: Identifiable, Decodable {
    let iid: Int
    let titel: String
    let status: String      // gemeldet | in-arbeit | bitte-pruefen | erledigt
    let kommentar: String?
    var id: Int { iid }
}

/// Client für die GitChain-Ablage auf der H200V:
/// `POST <basis>/ablage`, Multipart-Feld `file`, `Authorization: Bearer <PAT>`.
/// Jeder erfolgreiche Upload wird serverseitig ein Commit `aufnahme: …` in babu.git.
enum AblageService {

    /// Aufnahme mit Einsortierung: egal was fotografiert wurde — der Server
    /// entscheidet aus dem gelesenen Text, wohin es gehört, und sagt es zurück.
    static func aufnahme(daten: Data, dateiname: String, gelesenerText: String,
                         ergebnis ergebnisJson: String? = nil,
                         basis: URL, pat: String) async
            -> (ergebnis: AblageErgebnis, serverDatei: String?,
                art: String?, wohin: String?, sicher: Bool) {
        var teile = URLComponents(
            url: basis.appendingPathComponent("api/aufnahme"),
            resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "name", value: dateiname)]
        guard let url = teile?.url else {
            return (.nichtErreichbar, nil, nil, nil, false)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        // Multipart: Foto plus Text plus (wenn vorhanden) das Ergebnis der
        // Einschätzung — Gemmas Buchung samt Dokumentklasse. Der Server legt
        // dann nach der Klasse ab und archiviert das Ergebnis als Lesung.
        let grenze = "babu-" + UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(grenze)",
                         forHTTPHeaderField: "Content-Type")
        var koerper = Data()
        func feld(_ name: String, _ wert: String) {
            let teil = "--\(grenze)\r\nContent-Disposition: form-data; "
                + "name=\"\(name)\"\r\n\r\n\(wert)\r\n"
            koerper.append(teil.data(using: .utf8)!)
        }
        feld("text", String(gelesenerText.prefix(4000)))
        if let ergebnisJson { feld("ergebnis", ergebnisJson) }
        koerper.append(("--\(grenze)\r\nContent-Disposition: form-data; "
                        + "name=\"file\"; filename=\"\(dateiname)\"\r\n"
                        + "Content-Type: "
                        + (dateiname.hasSuffix(".pdf") ? "application/pdf"
                                                       : "image/jpeg")
                        + "\r\n\r\n").data(using: .utf8)!)
        koerper.append(daten)
        koerper.append("\r\n--\(grenze)--\r\n".data(using: .utf8)!)
        request.httpBody = koerper
        let (ergebnis, antwort) = await ausfuehrenMitDaten(request)
        guard ergebnis == .uebertragen, let antwort,
              let json = try? JSONSerialization.jsonObject(with: antwort) as? [String: Any]
        else { return (ergebnis, nil, nil, nil, false) }
        let pfad = json["datei"] as? String
        return (ergebnis,
                pfad.map { ($0 as NSString).lastPathComponent },
                json["art"] as? String,
                json["wohin"] as? String,
                json["sicher"] as? Bool ?? false)
    }

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

    /// Wozu vom Konto Geld abging, ohne dass ein Beleg da ist.
    static func fehlendeBelege(basis: URL, pat: String) async
            -> (fragen: [[String: Any]], summe: Double, gruende: [[String: Any]]) {
        var request = URLRequest(url: basis.appendingPathComponent("api/fehlende-belege"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return ([], 0, []) }
        return (json["fragen"] as? [[String: Any]] ?? [],
                json["summe"] as? Double ?? 0,
                json["gruende"] as? [[String: Any]] ?? [])
    }

    static func belegFrageKlaeren(schluessel: String, grund: String, basis: URL,
                                  pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/fehlende-belege/klaeren"))
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["schluessel": schluessel, "grund": grund])
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    // MARK: - Termine

    static func termineLaden(tag: String, basis: URL, pat: String) async
            -> [String: Any]? {
        var teile = URLComponents(url: basis.appendingPathComponent("api/termine"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "von", value: tag),
                             URLQueryItem(name: "bis", value: tag)]
        guard let url = teile?.url else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let tage = json["tage"] as? [[String: Any]] else { return nil }
        return tage.first
    }

    /// Termin eintragen oder verschieben. Gibt einen Klartext-Fehler zurück,
    /// wenn sich etwas überschneidet — den soll die Nutzerin lesen.
    static func terminSpeichern(_ felder: [String: Any], basis: URL,
                                pat: String) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("api/termine"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: felder)
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if ergebnis == .uebertragen { return nil }
        if let daten, let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let fehler = json["fehler"] as? String { return fehler }
        return "Das hat gerade nicht geklappt."
    }

    /// Aus einem Satz Terminvorschläge. Gebucht wird dabei nichts.
    static func terminVorschlag(text: String, basis: URL, pat: String) async
            -> (wunsch: [String: Any]?, zeiten: [String], hinweis: String,
                fehler: String?) {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/termine/vorschlag"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text])
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        let json = daten.flatMap {
            try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
        }
        if ergebnis == .uebertragen {
            return (json?["wunsch"] as? [String: Any],
                    json?["vorschlaege"] as? [String] ?? [],
                    json?["hinweis"] as? String ?? "", nil)
        }
        return (nil, [], "", json?["fehler"] as? String ?? "Das hat nicht geklappt.")
    }

    static func terminAbsagen(id: Int, basis: URL, pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/termin/\(id)/absagen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        return await ausfuehren(request, erfolg2xx: true) == .uebertragen
    }

    // MARK: - Abrechnen und Kartei

    /// Nach der Behandlung: bar oder Karte. Daraus wird ein Vorschlag fürs
    /// Kassenbuch — gebucht wird nichts, das bestätigt sie abends selbst.
    static func terminAbrechnen(id: Int, preis: String, zahlart: String,
                                referenz: String? = nil,
                                basis: URL, pat: String) async -> String? {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/termin/\(id)/abrechnen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var felder: [String: Any] = ["preis": preis, "zahlart": zahlart]
        // Nur eine echte Zahlung bekommt eine Referenz. Ein Beleg aus dem
        // Prüfstand hat im Kassenbuch nichts verloren.
        if let referenz, !referenz.isEmpty { felder["referenz"] = referenz }
        request.httpBody = try? JSONSerialization.data(withJSONObject: felder)
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if ergebnis == .uebertragen { return nil }
        if let daten, let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let fehler = json["fehler"] as? String { return fehler }
        return "Das hat gerade nicht geklappt."
    }

    /// Die Anfrage aus WhatsApp annehmen. Erst damit steht der Termin fest —
    /// und die Kundin bekommt Bescheid.
    static func terminBestaetigen(id: Int, basis: URL, pat: String) async -> Bool {
        await schicken("api/termin/\(id)/bestaetigen", [:], basis: basis,
                       pat: pat) == nil
    }

    /// Die Einrichtungsangaben löschen, damit sie neu abgefragt werden.
    /// Belegbox, Konto und Kundendaten bleiben unberührt — das entscheidet
    /// der Server, nicht die App.
    static func einrichtungZuruecksetzen(basis: URL, pat: String) async -> Bool {
        await schicken("api/einrichtung/zuruecksetzen", [:], basis: basis,
                       pat: pat) == nil
    }

    static func kassenvorschlag(tag: String, basis: URL, pat: String) async
            -> [String: Any]? {
        await holen("api/kasse/vorschlag?datum=\(tag)", basis: basis, pat: pat)
    }

    static func leistungen(basis: URL, pat: String) async -> [[String: Any]] {
        let json = await holen("api/leistungen", basis: basis, pat: pat)
        return json?["leistungen"] as? [[String: Any]] ?? []
    }

    static func leistungSpeichern(_ felder: [String: Any], basis: URL,
                                  pat: String) async -> String? {
        await schicken("api/leistungen", felder, basis: basis, pat: pat)
    }

    static func kundinnen(suche: String, basis: URL, pat: String) async
            -> [[String: Any]] {
        let frage = suche.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed) ?? ""
        let json = await holen("api/kundinnen?suche=\(frage)", basis: basis, pat: pat)
        return json?["kundinnen"] as? [[String: Any]] ?? []
    }

    static func kundin(id: Int, basis: URL, pat: String) async -> [String: Any]? {
        await holen("api/kundin/\(id)", basis: basis, pat: pat)
    }

    static func kundinSpeichern(_ felder: [String: Any], basis: URL,
                                pat: String) async -> String? {
        await schicken("api/kundinnen", felder, basis: basis, pat: pat)
    }

    static func behandlungSpeichern(kundin: Int, _ felder: [String: Any],
                                    basis: URL, pat: String) async -> String? {
        await schicken("api/kundin/\(kundin)/behandlung", felder,
                       basis: basis, pat: pat)
    }

    static func kundinLoeschen(id: Int, basis: URL, pat: String) async -> Bool {
        await schicken("api/kundin/\(id)/loeschen", [:], basis: basis,
                       pat: pat) == nil
    }

    // MARK: - Zwei kleine Helfer, damit sich das oben nicht zehnmal wiederholt

    private static func holen(_ pfad: String, basis: URL, pat: String) async
            -> [String: Any]? {
        guard let url = URL(string: pfad, relativeTo: basis) else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode ?? 500 < 300 else { return nil }
        return try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
    }

    /// Gibt nil zurück, wenn es geklappt hat — sonst den Klartext für sie.
    private static func schicken(_ pfad: String, _ felder: [String: Any],
                                 basis: URL, pat: String) async -> String? {
        guard let url = URL(string: pfad, relativeTo: basis) else {
            return "Die Adresse stimmt nicht."
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: felder)
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if ergebnis == .uebertragen { return nil }
        if let daten, let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let fehler = json["fehler"] as? String { return fehler }
        return "Das hat gerade nicht geklappt."
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

    /// Was babu von sich aus sagen würde — höchstens drei Meldungen.
    static func meldungenLaden(basis: URL, pat: String) async -> [Meldung] {
        var request = URLRequest(url: basis.appendingPathComponent("api/meldungen"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["meldungen"] as? [[String: Any]] else { return [] }
        return liste.compactMap(Meldung.init(json:))
    }

    /// Konto-Anmeldung der App: E-Mail + Passwort → Geräteschlüssel.
    /// Der Schlüssel kommt genau einmal zurück und wandert in die Keychain —
    /// die Nutzerin sieht ihn nie.
    static func appAnmelden(email: String, passwort: String, geraet: String,
                            basis: URL) async -> (schluessel: String?, un: String?,
                                                  fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/app-anmelden"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject:
            ["email": email, "passwort": passwort, "geraet": geraet])
        do {
            let (daten, antwort) = try await URLSession.shared.data(for: request)
            let code = (antwort as? HTTPURLResponse)?.statusCode ?? 0
            let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
            if code == 200, let schluessel = json?["schluessel"] as? String {
                return (schluessel, json?["un"] as? String, nil)
            }
            return (nil, nil, json?["fehler"] as? String
                    ?? "Das hat gerade nicht geklappt — später noch einmal versuchen.")
        } catch {
            return (nil, nil, "Gerade keine Verbindung — Internet prüfen und noch einmal versuchen.")
        }
    }

    /// Ninas Rückmeldung abschicken (`POST /api/rueckmeldung`).
    ///
    /// Der Server hält sie in der Belegbox fest und reicht sie an Fixit
    /// weiter. Für Nina ist beides derselbe Vorgang: sie schreibt, es kommt
    /// an. Ob Fixit gerade erreichbar war, ist unsere Sache, nicht ihre —
    /// deshalb gilt hier schon 200 als Erfolg.
    static func rueckmeldenSenden(text: String, art: String, ansicht: String,
                                  beleg: String?, geraet: String?,
                                  fassung: String?, basis: URL,
                                  pat: String, bildB64: String? = nil) async -> (ok: Bool, fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/rueckmeldung"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var koerper: [String: Any] = ["text": text, "art": art,
                                      "quelle": "app", "ansicht": ansicht]
        if let beleg { koerper["beleg"] = beleg }
        if let geraet { koerper["geraet"] = geraet }
        if let fassung { koerper["fassung"] = fassung }
        if let bildB64 { koerper["bild"] = bildB64 }
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return (false, "Gerade keine Verbindung — gleich noch einmal.")
        }
        if http.statusCode == 200 { return (true, nil) }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        return (false, json?["fehler"] as? String
                ?? "Das hat gerade nicht geklappt.")
    }

    /// Ninas Meldungen samt Stand (`GET /api/rueckmeldungen`).
    static func meldungenHolen(basis: URL, pat: String) async -> [Meldungszeile]? {
        var request = URLRequest(url: basis.appendingPathComponent("api/rueckmeldungen"))
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        struct Antwort: Decodable { let meldungen: [Meldungszeile] }
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONDecoder().decode(Antwort.self, from: daten)
        else { return nil }
        return json.meldungen
    }

    private static func meldungPost(pfad: String, koerper: [String: Any]?,
                                     basis: URL, pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent(pfad))
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        if let koerper {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        }
        guard let (_, antwort) = try? await URLSession.shared.data(for: request)
        else { return false }
        return (antwort as? HTTPURLResponse)?.statusCode == 200
    }

    /// „Passt ✓" — schließt den Vorgang mit Ninas Freigabe.
    static func meldungFreigeben(iid: Int, basis: URL, pat: String) async -> Bool {
        await meldungPost(pfad: "api/rueckmeldungen/\(iid)/freigeben",
                           koerper: nil, basis: basis, pat: pat)
    }

    /// „Stimmt noch nicht" — mit einem Satz zurück in die Runde.
    static func meldungBeanstanden(iid: Int, text: String,
                                   basis: URL, pat: String) async -> Bool {
        await meldungPost(pfad: "api/rueckmeldungen/\(iid)/beanstanden",
                           koerper: ["text": text], basis: basis, pat: pat)
    }

    /// Wer bin ich? (`GET /api/ich`, Bearer-Geräteschlüssel)
    ///
    /// Die App merkt sich den Kontonamen beim Verbinden. Wessen Schlüssel
    /// aus einer älteren Fassung stammt, hat einen gültigen Zugang, aber
    /// keinen Namen — im Konto stand dann „verbunden" ohne zu sagen, als
    /// wer. Statt das nur bei neuen Anmeldungen zu füllen, fragt die App
    /// jetzt nach: der Server weiß es, und die Antwort heilt auch alte
    /// Installationen, ohne dass jemand sich neu verbinden muss.
    ///
    /// Nebenbei ist es die ehrlichste Prüfung, ob der Zugang noch gilt:
    /// 401 heißt abgelaufen, und das gehört im Konto auch so hin.
    static func werBinIch(basis: URL, pat: String) async
        -> (un: String?, rolle: String?, abgelaufen: Bool) {
        var request = URLRequest(url: basis.appendingPathComponent("api/ich"))
        request.timeoutInterval = 12
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else { return (nil, nil, false) }
        if http.statusCode == 401 || http.statusCode == 403 {
            return (nil, nil, true)
        }
        guard http.statusCode == 200,
              let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        else { return (nil, nil, false) }
        return (json["un"] as? String, json["rolle"] as? String, false)
    }

    /// Brief vom Amt ablegen — babu liest ihn und erklärt ihn danach
    /// in einfachen Worten (Sidecar-Erklärung, siehe `briefErklaerung`).
    static func briefAblegen(daten: Data, dateiname: String, basis: URL,
                             pat: String) async -> String? {
        var teile = URLComponents(url: basis.appendingPathComponent("api/dokumente"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "name", value: dateiname),
                             URLQueryItem(name: "titel", value: "Brief vom Amt · " + dateiname),
                             URLQueryItem(name: "art", value: "behoerde")]
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

    /// Erklärung zum abgelegten Brief holen (entsteht im Hintergrund).
    /// `hinweis` steht drin, wenn der Brief eine Beratung berührt —
    /// Einspruchsfrist, Prüfungsanordnung, Vollstreckung.
    static func briefErklaerung(pfad: String, basis: URL,
                                pat: String) async -> (einfach: String, wasTun: String?,
                                                       bisWann: String?,
                                                       hinweis: String?)? {
        var request = URLRequest(url: basis.appendingPathComponent("api/dokumente"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["dokumente"] as? [[String: Any]],
              let treffer = liste.first(where: { ($0["pfad"] as? String) == pfad }),
              let e = treffer["erklaerung"] as? [String: Any],
              let einfach = e["einfach"] as? String, !einfach.isEmpty
        else { return nil }
        return (einfach, e["was_tun"] as? String, e["bis_wann"] as? String,
                e["hinweis"] as? String)
    }

    // MARK: - Früher auf dem Server gespeicherte Gespräche (BABU-25)
    //
    // Der Server schreibt keine Chats mehr mit. Was er früher mitgeschrieben
    // hat, liegt noch da — Nina muss es sehen (Art. 15 DSGVO) und löschen
    // können (Art. 17). Diese drei Wege gab es serverseitig längst; gerufen
    // hat sie niemand.

    /// Die Fäden, die auf dem Server liegen — neueste zuerst.
    static func gespraecheLaden(basis: URL, pat: String) async -> [ServerGespraech]? {
        var request = URLRequest(url: basis.appendingPathComponent("api/gespraeche"))
        request.timeoutInterval = 20
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["gespraeche"] as? [[String: Any]] else { return nil }
        return liste.compactMap { z in
            guard let id = z["id"] as? Int else { return nil }
            return ServerGespraech(id: id,
                                   titel: (z["titel"] as? String) ?? "Ohne Titel",
                                   zuletzt: (z["zuletzt"] as? String) ?? "",
                                   nachrichten: (z["nachrichten"] as? Int) ?? 0)
        }
    }

    /// Was in einem gespeicherten Faden steht — die Auskunft selbst.
    static func gespraechNachrichten(id: Int, basis: URL, pat: String) async
            -> [(vonMir: Bool, text: String)]? {
        var request = URLRequest(url: basis.appendingPathComponent("api/gespraech/\(id)"))
        request.timeoutInterval = 20
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["nachrichten"] as? [[String: Any]] else { return nil }
        return liste.compactMap { n in
            guard let text = n["text"] as? String else { return nil }
            return (vonMir: (n["rolle"] as? String) == "user", text: text)
        }
    }

    static func gespraechLoeschen(id: Int, basis: URL, pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/gespraech/\(id)/loeschen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        let (ergebnis, _) = await ausfuehrenMitDaten(request)
        return ergebnis == .uebertragen
    }

    /// Alles auf einmal — ein Recht, das sechzehn Klicks kostet, ist zäh.
    static func gespraecheAlleLoeschen(basis: URL, pat: String) async -> Bool {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/gespraeche/loeschen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        let (ergebnis, _) = await ausfuehrenMitDaten(request)
        return ergebnis == .uebertragen
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

    /// Stammdaten des Salons — sie gehören auf jede Rechnung (§ 14 UStG).
    static func stammdatenLaden(basis: URL, pat: String) async -> [String: String]? {
        var request = URLRequest(url: basis.appendingPathComponent("api/einstellungen"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return nil }
        return json.compactMapValues { $0 as? String }
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

    // MARK: - Buchungsfragen: Gemma bucht — oder schickt EIN Fragenpaket

    struct BuchungsFrage: Identifiable, Equatable {
        let frage: String
        let optionen: [String]
        var id: String { frage }
    }

    struct GemmaBuchung {
        let lieferant: String?
        let datum: String?
        let steuersaetze: [SteuerPosition]
        let kategorieName: String
        let konto: String
        let buchungstext: String
        let betrag: Double?
        let waehrung: String
        let betragEur: Double
        let ustSatz: Int
        let begruendung: String
        /// Gemmas Antwort auf die Klassifizierungsfrage — sie bestimmt das Fach.
        let dokumentklasse: String?
        /// Die Buchung, wie sie vom Server kam — geht beim Ablegen mit ins Archiv.
        let rohJson: String?
    }

    enum BuchungsfragenErgebnis {
        case fragen([BuchungsFrage])
        case gebucht(GemmaBuchung)
        case aufgeben(String)
        case fehler(String)
    }

    /// Die Direkt-Runde: das Telefon schickt Profil und Vision-Lesung als
    /// reines Text-JSON — noch bevor das Foto im Archiv liegt. Gemma
    /// verifiziert, fragt oder bucht.
    static func einschaetzung(zeilen: [Any], profil: [String: String],
                              monat: String?,
                              antworten: [(frage: String, antwort: String)],
                              basis: URL, pat: String) async -> BuchungsfragenErgebnis {
        var request = URLRequest(
            url: basis.appendingPathComponent("api/buchung/einschaetzung"))
        request.httpMethod = "POST"
        request.timeoutInterval = 150
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var koerper: [String: Any] = [
            "zeilen": zeilen,
            "profil": profil,
            "antworten": antworten.map { ["frage": $0.frage, "antwort": $0.antwort] },
        ]
        if let monat { koerper["monat"] = monat }
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        return await buchungsRunde(request)
    }

    private static func buchungsRunde(_ request: URLRequest) async -> BuchungsfragenErgebnis {
        guard let (daten, roh) = try? await URLSession.shared.data(for: request),
              let http = roh as? HTTPURLResponse,
              let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        else { return .fehler("Keine Verbindung — später noch einmal.") }
        guard (200..<300).contains(http.statusCode) else {
            return .fehler(json["fehler"] as? String ?? "Das ging gerade nicht.")
        }
        switch json["status"] as? String {
        case "fragen":
            let fragen = (json["fragen"] as? [[String: Any]] ?? []).compactMap { f -> BuchungsFrage? in
                guard let frage = f["frage"] as? String, !frage.isEmpty else { return nil }
                return BuchungsFrage(frage: frage,
                                     optionen: f["optionen"] as? [String] ?? [])
            }
            return fragen.isEmpty ? .fehler("Das ging gerade nicht.") : .fragen(fragen)
        case "gebucht":
            guard let b = json["buchung"] as? [String: Any],
                  let konto = b["konto"] as? String else {
                return .fehler("Das ging gerade nicht.")
            }
            let tabelle: [SteuerPosition] = (b["steuersaetze"] as? [[String: Any]] ?? [])
                .compactMap { z in
                    guard let satz = z["satz"] as? Int,
                          let brutto = z["brutto"] as? Double,
                          let netto = z["netto"] as? Double,
                          let ust = z["ust"] as? Double else { return nil }
                    return SteuerPosition(satz: satz, netto: netto, ust: ust, brutto: brutto)
                }
            return .gebucht(GemmaBuchung(
                lieferant: b["lieferant"] as? String,
                datum: b["datum"] as? String,
                steuersaetze: tabelle,
                kategorieName: b["kategorie_name"] as? String ?? "",
                konto: konto,
                buchungstext: b["buchungstext"] as? String ?? "",
                betrag: b["betrag"] as? Double,
                waehrung: (b["waehrung"] as? String ?? "EUR").uppercased(),
                betragEur: b["betrag_eur"] as? Double ?? 0,
                ustSatz: b["ust_satz"] as? Int ?? 0,
                begruendung: b["begruendung"] as? String ?? "",
                dokumentklasse: b["dokumentklasse"] as? String,
                rohJson: (try? JSONSerialization.data(withJSONObject: b))
                    .flatMap { String(data: $0, encoding: .utf8) }))
        case "aufgeben":
            return .aufgeben(json["hinweis"] as? String
                             ?? "Der Beleg gehört auf den Schreibtisch.")
        default:
            return .fehler("Das ging gerade nicht.")
        }
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

    // MARK: - Dein Team
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

extension AblageService {

    static func teamLaden(basis: URL, pat: String) async -> (leute: [TeamPerson],
                                                             kosten: Double)? {
        var request = URLRequest(url: basis.appendingPathComponent("api/team"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["team"] as? [[String: Any]] else { return nil }
        let leute = liste.compactMap(TeamPerson.init(json:))
        return (leute, json["kosten_monat"] as? Double ?? 0)
    }

    static func teamSpeichern(_ person: TeamPerson, basis: URL,
                              pat: String) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("api/team"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var koerper: [String: Any] = ["name": person.name, "lohn_art": person.lohnArt]
        if person.id > 0 { koerper["id"] = person.id }
        if let e = person.email, !e.isEmpty { koerper["email"] = e }
        if let b = person.betrag { koerper["betrag"] = b }
        if let s = person.stundenlohn { koerper["stundenlohn"] = s }
        if let h = person.stunden { koerper["stunden"] = h }
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        if ergebnis == .uebertragen { return nil }
        if let daten, let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let fehler = json["fehler"] as? String { return fehler }
        return "Das hat gerade nicht geklappt."
    }

    static func teamAktion(id: Int, aktion: String, basis: URL, pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent("api/team-aktion"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject:
            ["id": id, "aktion": aktion])
        let (ergebnis, _) = await ausfuehrenMitDaten(request)
        return ergebnis == .uebertragen
    }

    /// Foto einer Mitarbeiterin — in der App aufgenommen, hier abgelegt.
    static func teamFotoSenden(_ jpeg: Data, id: Int, basis: URL,
                               pat: String) async -> Bool {
        var teile = URLComponents(url: basis.appendingPathComponent("api/team-foto"),
                                  resolvingAgainstBaseURL: false)
        teile?.queryItems = [URLQueryItem(name: "id", value: String(id))]
        guard let url = teile?.url else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.httpBody = jpeg
        let (ergebnis, _) = await ausfuehrenMitDaten(request)
        return ergebnis == .uebertragen
    }

    static func teamFotoLaden(id: Int, basis: URL, pat: String) async -> Data? {
        var request = URLRequest(url: basis.appendingPathComponent("api/team-foto/\(id)"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return daten
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
    static func kassenblattSenden(_ b: Kassenbericht, basis: URL, pat: String) async -> Bool {
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
        request.httpBody = try? JSONSerialization.data(withJSONObject: blatt)
        let (ergebnis, _) = await ausfuehrenMitDaten(request)
        return ergebnis == .uebertragen
    }

    /// Frage an den Belegbox-Assistenten — gestreamt (SSE): liefert Text-Stücke,
    /// sobald Gemma sie erzeugt. Der bisherige Gesprächsverlauf reist mit:
    /// er liegt in der App, der Server schreibt keinen mehr mit (BABU-25).
    static func fragenStream(_ frage: String, verlauf: [[String: String]] = [],
                             basis: URL,
                             pat: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                var request = URLRequest(url: basis.appendingPathComponent("chat"))
                request.httpMethod = "POST"
                request.timeoutInterval = 180
                request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try? JSONSerialization.data(
                    withJSONObject: ["frage": frage, "stream": true,
                                     "verlauf": verlauf])
                do {
                    let (bytes, antwort) = try await URLSession.shared.bytes(for: request)
                    guard (antwort as? HTTPURLResponse)?.statusCode == 200 else {
                        continuation.finish(throwing: URLError(.badServerResponse))
                        return
                    }
                    for try await zeile in bytes.lines {
                        guard zeile.hasPrefix("data: ") else { continue }
                        let roh = String(zeile.dropFirst(6))
                        if roh == "[DONE]" { break }
                        if let json = try? JSONSerialization.jsonObject(with: Data(roh.utf8)) as? [String: Any] {
                            if let stueck = json["d"] as? String {
                                continuation.yield(stueck)
                            } else if let fehler = json["fehler"] as? String {
                                // Fehlerframe nicht verschlucken — sonst wartet die
                                // Nutzerin auf eine Antwort, die nie kommt.
                                continuation.finish(throwing: ChatFehler(meldung: fehler))
                                return
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// Frage an den Belegbox-Assistenten (Gemma 4 über `POST /chat`).
    static func fragen(_ frage: String, verlauf: [[String: String]] = [],
                       basis: URL, pat: String) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("chat"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["frage": frage, "verlauf": verlauf])
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any] else {
            return nil
        }
        return json["antwort"] as? String
    }

    /// Ein Stück aus der Server-Ablage — Kontoauszüge, Verträge und Post,
    /// die übers Portal (oder von der Kanzlei) hereinkamen und deshalb
    /// nicht im lokalen Bestand liegen.
    struct AblageStueck: Identifiable {
        let pfad: String
        let titel: String
        let zeit: String?
        let seiten: Int?
        var id: String { pfad }
        /// Anzeigename ohne Zeitstempel-Präfix des Servers.
        var name: String {
            let datei = (pfad as NSString).lastPathComponent
            let kurz = datei.replacingOccurrences(
                of: #"^\d{8}-\d{6}-\w+-"#, with: "", options: .regularExpression)
            return kurz.isEmpty ? datei : kurz
        }
    }

    /// Die Server-Ablage eines Fachs (`GET /api/ablage`), neueste zuerst.
    static func ablageStuecke(art: String, basis: URL, pat: String) async -> [AblageStueck] {
        var request = URLRequest(url: basis.appendingPathComponent("api/ablage"))
        request.timeoutInterval = 12
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let jahre = json["jahre"] as? [[String: Any]] else { return [] }
        var stuecke: [AblageStueck] = []
        for jahr in jahre {
            for fach in (jahr["arten"] as? [[String: Any]]) ?? [] where (fach["art"] as? String) == art {
                for s in (fach["stuecke"] as? [[String: Any]]) ?? [] {
                    guard let pfad = s["pfad"] as? String else { continue }
                    stuecke.append(AblageStueck(pfad: pfad,
                                                titel: s["titel"] as? String ?? pfad,
                                                zeit: s["zeit"] as? String,
                                                seiten: s["seiten"] as? Int))
                }
            }
        }
        return stuecke.sorted { ($0.zeit ?? "") > ($1.zeit ?? "") }
    }

    /// Die Server-Vorschau eines Ablage-Stücks (Seite 1 als Bild).
    static func vorschauLaden(pfad: String, basis: URL, pat: String) async -> UIImage? {
        var teil = URLComponents(url: basis.appendingPathComponent("api/vorschau"),
                                 resolvingAgainstBaseURL: false)
        teil?.path += "/" + pfad
        guard let url = teil?.url else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return UIImage(data: daten)
    }

    /// BelegReview-Ergebnis abrufen (`GET /review/<stamm>`, Bearer-PAT).
    static func reviewAbrufen(stamm: String, basis: URL, pat: String) async -> ReviewAntwort {
        var request = URLRequest(url: basis.appendingPathComponent("review")
            .appendingPathComponent(stamm))
        request.timeoutInterval = 12
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else { return .keineVerbindung }
        switch http.statusCode {
        case 200:
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            guard let r = try? decoder.decode(BelegReviewDaten.self, from: daten) else {
                return .serverProblem
            }
            return .fertig(r)
        case 404: return .nochNicht
        case 401, 403: return .zugangFehlt
        default: return .serverProblem
        }
    }

    /// Das Leseprotokoll holen (`GET /review/<stamm>/protokoll`).
    static func protokollAbrufen(stamm: String, basis: URL,
                                 pat: String) async -> ProtokollAntwort {
        var request = URLRequest(url: basis.appendingPathComponent("review")
            .appendingPathComponent(stamm).appendingPathComponent("protokoll"))
        request.timeoutInterval = 12
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else { return .keineVerbindung }
        switch http.statusCode {
        case 200:
            guard let text = String(data: daten, encoding: .utf8), !text.isEmpty else {
                return .serverProblem
            }
            return .fertig(text)
        case 404: return .nochNicht
        case 401, 403: return .zugangFehlt
        default: return .serverProblem
        }
    }

    /// Verbindungs- und Token-Test OHNE Müll-Commit: eine Mini-txt-Datei senden.
    /// Der Server nimmt nur Bilder/PDF an — txt wird IMMER abgelehnt:
    /// gültiger Token ⇒ 400 (Dateityp) ⇒ verbunden · falscher Token ⇒ 401.
    /// (Ein leerer POST taugt nicht: FastAPI meldet 422 vor der Token-Prüfung.)
    static func verbindungstest(basis: URL, pat: String) async -> AblageErgebnis {
        let (body, contentType) = multipartBody(feld: "file", dateiname: "verbindungstest.txt",
                                                mime: "text/plain", daten: Data("x".utf8))
        var request = URLRequest(url: basis.appendingPathComponent("ablage"))
        request.httpMethod = "POST"
        request.timeoutInterval = 8
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        let ergebnis = await ausfuehren(request, erfolg2xx: false)
        if case .abgelehnt(400) = ergebnis { return .uebertragen }
        if case .uebertragen = ergebnis { return .uebertragen }   // falls Server 2xx liefert
        return ergebnis
    }

    private static func ausfuehren(_ request: URLRequest, erfolg2xx: Bool) async -> AblageErgebnis {
        await ausfuehrenMitDaten(request).0
    }

    private static func ausfuehrenMitDaten(_ request: URLRequest) async -> (AblageErgebnis, Data?) {
        do {
            let (daten, antwort) = try await URLSession.shared.data(for: request)
            guard let http = antwort as? HTTPURLResponse else { return (.nichtErreichbar, nil) }
            switch http.statusCode {
            case 200..<300: return (.uebertragen, daten)
            case 401: return (.tokenFehler, nil)
            default: return (.abgelehnt(http.statusCode), nil)
            }
        } catch {
            return (.nichtErreichbar, nil)
        }
    }

    /// Multipart-Body (ein Datei-Feld) — als reine Funktion testbar.
    static func multipartBody(feld: String, dateiname: String, mime: String,
                              daten: Data) -> (body: Data, contentType: String) {
        let boundary = "beleg-" + UUID().uuidString
        var body = Data()
        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(Data("Content-Disposition: form-data; name=\"\(feld)\"; filename=\"\(dateiname)\"\r\n".utf8))
        body.append(Data("Content-Type: \(mime)\r\n\r\n".utf8))
        body.append(daten)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return (body, "multipart/form-data; boundary=\(boundary)")
    }
}

/// Das archivierte Ergebnis aus `review/<name>.json`. Heute schreibt es
/// der Server aus Ninas eigener Buchung (Vision + Gemma); die vielen
/// optionalen Felder stammen aus älteren Reviews und bleiben dekodierbar.
struct BelegReviewDaten: Codable {
    struct Felder: Codable {
        var lieferant: String?
        var belegNr: String?
        var datum: String?
        var netto: Double?
        var ust: Double?
        var brutto: Double?
        var ustSatz: Int?
        var summenprobeOk: Bool?
        var bewirtungssignal: Bool?
        var offen: [String]?
        /// Wo jeder Wert herkommt: Feldname → Zeile, Regel, Erkennungsgüte.
        /// Das Vollständige steht im Leseprotokoll hinter dem ⓘ; hier reicht
        /// es, um am Wert selbst zu zeigen, worauf er beruht.
        var herkunft: [String: Herkunft]?
        /// Was die Gegenprobe anders gelesen hat. Leer heißt: beide einig.
        var widerspruch: [String]?
    }
    struct Herkunft: Codable {
        var regel: String?
        var zeile: Int?
        var zeilentext: String?
        var konf: Double?
    }
    struct Einschaetzung: Codable {
        var belegart: String?
        var kontoSkr04: String?
        var steuerschluessel: String?
        var hinweise: [String]?
    }
    /// Die Buchung: was die Buchhaltung entschieden hat — sie ist das,
    /// was zählt; die Einzelfelder daneben sind nur Archiv.
    struct BuchungsLage: Codable {
        var status: String?
        var buchung: BuchungsFelder?
    }
    struct BuchungsFelder: Codable {
        var lieferant: String?
        var datum: String?
        var steuersaetze: [SteuerPosition]?
        var konto: String?
        var kategorieName: String?
        var buchungstext: String?
        var betrag: Double?
        var waehrung: String?
        var betragEur: Double?
        var ustSatz: Int?
        var begruendung: String?
    }

    /// Bild-Lane: Gemma 4 liest das Beleg-Foto (Lane B).
    struct Vlm: Codable {
        var lieferant: String?
        var belegNr: String?
        var datum: String?
        var brutto: Double?
        var netto: Double?
        var ust: Double?
        var trinkgeld: Double?
        var zahlungsart: String?
        var bewirtung: Bool?
        var positionenAnzahl: Int?
    }
    /// Audit-Stempel: echte GitChain-Commits von Aufnahme und Review.
    struct Audit: Codable {
        struct Eintrag: Codable {
            var commit: String?
            var zeit: String?
            var autor: String?
        }
        var aufnahme: Eintrag?
        var review: Eintrag?
    }
    /// Buchungszeile in DATEV-Feldlogik (Vorstufe zum EXTF-v13-Writer).
    struct Buchungssatz: Codable {
        var umsatz: String?
        var sollHaben: String?
        var konto: String?
        var gegenkonto: String?
        var buSchluessel: String?
        var belegdatum: String?
        var belegfeld1: String?
        var buchungstext: String?
    }
    var engine: String?
    var zeilen: Int?
    var ocrKonfidenz: Double?
    var dokumentklasse: String?
    var status: String?
    var felder: Felder?
    var einschaetzung: Einschaetzung?
    var buchung: BuchungsLage?
    var vlm: Vlm?
    /// Der Satz zum grünen Haken: worum es auf diesem Beleg geht, in einer
    /// Zeile. Kommt vom Bildmodell — es entscheidet keine Zahl mehr, aber es
    /// kann sagen, was man da vor sich hat.
    var zusammenfassung: String?
    var audit: Audit?
    var buchungssatz: Buchungssatz?

    /// Lesung gescheitert? Der Watcher schließt so einen Beleg mit einem
    /// Stub-Review ab (engine "BelegReview-Stub", Dokumentklasse "unlesbar") —
    /// das ist der Live-Vertrag des Salon-Portals; `status` bleibt als
    /// zusätzliche, zukunftssichere Kennung verstanden.
    var fehlgeschlagen: Bool {
        status == "fehlgeschlagen"
            || (engine == "BelegReview-Stub" && dokumentklasse?.lowercased() == "unlesbar")
    }
}

/// PAT-Ablage ausschließlich in der iOS-Keychain — nie im JSON-Store, nie im Log.
enum KeychainHelfer {
    private static let service = "io.0711.beleg.ablage"
    private static let konto = "upload-pat"

    private static var basisQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: konto]
    }

    static func speicherePAT(_ pat: String) {
        loeschePAT()
        guard !pat.isEmpty else { return }
        var query = basisQuery
        query[kSecValueData as String] = Data(pat.utf8)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(query as CFDictionary, nil)
    }

    static func ladePAT() -> String? {
        var query = basisQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var ergebnis: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &ergebnis) == errSecSuccess,
              let daten = ergebnis as? Data,
              let pat = String(data: daten, encoding: .utf8), !pat.isEmpty else { return nil }
        return pat
    }

    static func loeschePAT() {
        SecItemDelete(basisQuery as CFDictionary)
    }
}
