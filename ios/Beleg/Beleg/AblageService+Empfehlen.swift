import Foundation

// Empfehlen (Ambassadorinnen) und Anmelden per Link — beides Wege, auf
// denen niemand tippt, was das iPhone schon weiß.
//
// Die Regeln, was davon auf dem Bildschirm steht, liegen in
// `Empfehlen.swift` (harness-geprüft); hier steht nur das Netz.

extension AblageService {

    // MARK: - Empfehlen

    /// Was `GET /api/ambassador/me` über dieses Konto sagt.
    enum AmbassadorAuskunft {
        /// 200 — sie ist Ambassadorin, mit allem, was dazugehört.
        case da(EmpfehlenStand)
        /// 404 — keine Ambassadorin; der Reiter bleibt unsichtbar.
        case keine
        /// Kein Netz, abgelaufen, Serverfehler: sagt nichts über sie aus.
        case unbekannt
    }

    static func ambassadorStand(basis: URL, pat: String) async -> AmbassadorAuskunft {
        var request = URLRequest(url: basis.appendingPathComponent("api/ambassador/me"))
        // Die Zeitgrenze, nach der die Ansicht „Gerade keine Verbindung" sagt.
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else { return .unbekannt }
        switch http.statusCode {
        case 200:
            guard let stand = EmpfehlenStand(daten: daten) else { return .unbekannt }
            return .da(stand)
        case 404:
            return .keine
        default:
            return .unbekannt
        }
    }

    /// Einen Salon einladen (`POST /api/ambassador/link`). Mit Handynummer
    /// schreibt der Server den Text und den WhatsApp-Link gleich mit; ohne
    /// kommt nur der Link. `nummerFalsch`: der Server kann mit der Nummer
    /// nichts anfangen (400) — dann geht es ohne Nummer weiter.
    static func salonEinladen(person: String, telefon: String?, basis: URL,
                              pat: String) async
            -> (einladung: EmpfehlenStand.Einladung?, fehler: String?, nummerFalsch: Bool) {
        var request = URLRequest(url: basis.appendingPathComponent("api/ambassador/link"))
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var koerper = ["person": person]
        if let telefon, !telefon.isEmpty { koerper["telefon"] = telefon }
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return (nil, "Gerade keine Verbindung — gleich noch einmal versuchen.", false)
        }
        if http.statusCode == 200, let einladung = EmpfehlenStand.einladung(daten) {
            return (einladung, nil, false)
        }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        let fehler = EmpfehlenStand.text(json?["fehler"])
            ?? "Das ging gerade nicht — gleich noch einmal versuchen."
        return (nil, fehler, http.statusCode == 400 && koerper["telefon"] != nil)
    }

    /// Sie hat die vorgeschlagene Nachricht verschickt — der Server merkt
    /// es sich, damit er nicht am nächsten Tag wieder dasselbe vorschlägt.
    @discardableResult
    static func ambassadorErinnert(nr: Int, art: String, basis: URL,
                                   pat: String) async -> Bool {
        await auslagePost("api/ambassador/erinnert", koerper: ["nr": nr, "art": art],
                          basis: basis, pat: pat)
    }

    // MARK: - Anmelden per Link

    /// Den Anmelde-Link schicken lassen (`POST /api/anmeldelink`). Der Server
    /// antwortet immer gleich — ob es das Konto gibt, verrät er nicht.
    /// Gibt nil zurück, wenn es geklappt hat, sonst den Satz für sie.
    static func anmeldelinkSchicken(email: String, basis: URL) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("api/anmeldelink"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject:
            ["email": email, "app": true] as [String: Any])
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return "Gerade keine Verbindung — Internet prüfen und noch einmal versuchen."
        }
        if http.statusCode == 200 { return nil }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        return EmpfehlenStand.text(json?["fehler"])
            ?? "Das hat gerade nicht geklappt — gleich noch einmal versuchen."
    }

    /// Den Link aus der Mail einlösen (`POST /api/anmeldelink/einloesen`).
    /// Die Antwort ist dieselbe wie bei `/api/app-anmelden`: ein
    /// Geräteschlüssel, der in die Keychain wandert und den sie nie sieht.
    static func anmeldelinkEinloesen(token: String, geraet: String, basis: URL) async
            -> (schluessel: String?, un: String?, rolle: String?, ablage: Bool, fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/anmeldelink/einloesen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject:
            ["token": token, "geraet": geraet, "app": true] as [String: Any])
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else {
            return (nil, nil, nil, false,
                    "Gerade keine Verbindung — Internet prüfen und den Link noch einmal antippen.")
        }
        let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        if http.statusCode == 200, let schluessel = EmpfehlenStand.text(json?["schluessel"]) {
            // Wie bei der Passwort-Anmeldung: ohne `box` gilt der alte Stand.
            return (schluessel, EmpfehlenStand.text(json?["un"]),
                    EmpfehlenStand.text(json?["rolle"]), json?["box"] as? Bool ?? true, nil)
        }
        return (nil, nil, nil, false, EmpfehlenStand.text(json?["fehler"])
                ?? "Das hat gerade nicht geklappt — schick dir einfach einen neuen Link.")
    }
}
