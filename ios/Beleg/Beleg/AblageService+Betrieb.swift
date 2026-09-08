import Foundation

// Der laufende Salonbetrieb: Einstellungen und Anmeldung, Kundinnen,
// Termine, Leistungen, das Team, Meldungen und Rueckmeldungen, die alten
// Server-Gespraeche und der Chat.
//
// Nicht hierher: alles mit Betrag und Buchung (`+Geld`), der einzelne
// Beleg (`+Belege`), Netz-Helfer (Kern).

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

extension AblageService {

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

    // MARK: - Dein Team

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
}
