import Foundation

// Gerätekonto und Platz (seit 10.10.2026) — die drei Wege, die das neue
// Modell braucht. Alles andere der Ablage steht in AblageService.swift und
// AblageService+Betrieb.swift.

extension AblageService {

    /// Ein Konto anlegen, ohne dass sich jemand anmeldet
    /// (`POST /api/geraet/anlegen`).
    ///
    /// Das ist der erste Schritt der App im App Store: kein Passwort, keine
    /// E-Mail, keine Einladung. Der Schlüssel kommt genau einmal zurück und
    /// wandert in die Keychain — die Nutzerin sieht ihn nie.
    ///
    /// Die Belegbox richtet der Server gleich darauf ein; bis sie steht,
    /// bleiben die Belege auf dem Telefon (derselbe Weg wie bei einem Konto
    /// ohne Ablage, `ablageFehlt`).
    static func geraetAnlegen(geraet: String, betrieb: String?,
                              basis: URL) async
        -> (schluessel: String?, un: String?, stufen: [PlatzStufe],
            fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/geraet/anlegen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var koerper: [String: Any] = ["geraet": geraet]
        if let betrieb, !betrieb.isEmpty { koerper["betrieb"] = betrieb }
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        do {
            let (daten, antwort) = try await URLSession.shared.data(for: request)
            let code = (antwort as? HTTPURLResponse)?.statusCode ?? 0
            let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
            if code == 200, let schluessel = json?["schluessel"] as? String {
                return (schluessel, json?["un"] as? String,
                        stufenAus(json?["stufen"]), nil)
            }
            return (nil, nil, [], json?["fehler"] as? String
                    ?? "Das hat gerade nicht geklappt — später noch einmal versuchen.")
        } catch {
            return (nil, nil, [], "Gerade keine Verbindung — Internet prüfen "
                    + "und noch einmal versuchen.")
        }
    }

    /// Die E-Mail nachreichen (`POST /api/konto/email`).
    ///
    /// Freiwillig und jederzeit: für die Wiederherstellung auf einem neuen
    /// Telefon und für die Rechnung. Geht auch dann, wenn der Platz voll
    /// ist — sie ist der Weg zurück zu den Belegen.
    static func kontoEmail(_ email: String, basis: URL, pat: String) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("api/konto/email"))
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["email": email])
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return "Gerade keine Verbindung — gleich noch einmal."
        }
        if http.statusCode == 200 { return nil }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        return json?["fehler"] as? String ?? "Das hat gerade nicht geklappt."
    }

    /// Einen Kaufbeleg von Apple melden (`POST /api/abo/apple`).
    ///
    /// Geschickt wird der signierte Beleg, nicht die ausgepackte Zahl: der
    /// Server prüft die Kette gegen Apples Wurzelzertifikat. Rückgabe: der
    /// Platzstand, wie er jetzt gilt — damit die Ansicht nicht erst
    /// `/api/ich` nachladen muss.
    static func apfelKaufMelden(_ jws: String, basis: URL, pat: String) async
        -> (stufe: String?, platz: PlatzStand?, fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/abo/apple"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["signed": jws])
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return (nil, nil, "Gerade keine Verbindung — gleich noch einmal.")
        }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        guard http.statusCode == 200 else {
            return (nil, nil, json?["fehler"] as? String
                    ?? "Das hat gerade nicht geklappt.")
        }
        return (json?["stufe"] as? String, platzAus(json?["speicher"]), nil)
    }

    // MARK: - Aus dem JSON

    /// Der Platzstand aus `/api/ich` oder der Antwort auf einen Kauf.
    /// Fehlt er, ist es kein Konto aus dem App Store — dann gibt es keine
    /// Stufen, und die App zeigt nichts davon.
    static func platzAus(_ roh: Any?) -> PlatzStand? {
        guard let d = roh as? [String: Any] else { return nil }
        return PlatzStand(stufe: d["stufe"] as? String,
                          grenze: d["grenze"] as? Int,
                          verbraucht: d["verbraucht"] as? Int ?? 0,
                          voll: d["voll"] as? Bool ?? false,
                          knapp: d["knapp"] as? Bool ?? false,
                          belege: d["belege"] as? Int ?? 0,
                          freiOffen: d["frei_offen"] as? Int)
    }

    static func stufenAus(_ roh: Any?) -> [PlatzStufe] {
        guard let liste = roh as? [[String: Any]] else { return [] }
        return liste.compactMap { d in
            guard let stufe = d["stufe"] as? String, let gb = d["gb"] as? Int,
                  let cent = d["cent"] as? Int, let apple = d["apple"] as? String
            else { return nil }
            return PlatzStufe(stufe: stufe, gb: gb, cent: cent, apple: apple)
        }
    }
}
