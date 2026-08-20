import Foundation
import Security

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

/// Fehlermeldung aus dem Chat-Stream (SSE-Frame `{"fehler": …}`).
struct ChatFehler: Error {
    let meldung: String
}

/// Client für die GitChain-Ablage auf der H200V:
/// `POST <basis>/ablage`, Multipart-Feld `file`, `Authorization: Bearer <PAT>`.
/// Jeder erfolgreiche Upload wird serverseitig ein Commit `aufnahme: …` in babu.git.
enum AblageService {

    /// Upload; liefert bei Erfolg auch den serverseitigen Dateinamen aus der
    /// Antwort (`{ok, ref, commit, datei}`) — der ist der Schlüssel zum Review.
    static func lade(bildJpeg: Data, dateiname: String, basis: URL,
                     pat: String) async -> (ergebnis: AblageErgebnis, serverDatei: String?) {
        let (body, contentType) = multipartBody(feld: "file", dateiname: dateiname,
                                                mime: "image/jpeg", daten: bildJpeg)
        var request = URLRequest(url: basis.appendingPathComponent("ablage"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        let (ergebnis, daten) = await ausfuehrenMitDaten(request)
        var serverDatei: String?
        if ergebnis == .uebertragen, let daten,
           let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
           let pfad = json["datei"] as? String {
            serverDatei = (pfad as NSString).lastPathComponent
        }
        return (ergebnis, serverDatei)
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

    /// Erklärung zum abgelegten Brief holen (entsteht im Hintergrund).
    static func briefErklaerung(pfad: String, basis: URL,
                                pat: String) async -> (einfach: String, wasTun: String?,
                                                       bisWann: String?)? {
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
        return (einfach, e["was_tun"] as? String, e["bis_wann"] as? String)
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
            "privateinlagen": b.privateinlagen, "barabhebungBank": b.barabhebungBank,
            "ecZahlungen": b.ecZahlungen, "gutscheineEingeloest": b.gutscheineEingeloest,
            "trinkgeldTeamEC": b.trinkgeldTeamEC,
            "sonstigeAusgaben": b.sonstigeAusgaben, "privatentnahmen": b.privatentnahmen,
            "einzahlungBank": b.einzahlungBank, "gezaehltSchluss": b.gezaehltSchluss,
        ]
        if let grund = b.differenzGrund, !grund.isEmpty { blatt["differenzGrund"] = grund }
        if let notiz = b.sonstigeNotiz, !notiz.isEmpty { blatt["sonstigeNotiz"] = notiz }
        request.httpBody = try? JSONSerialization.data(withJSONObject: blatt)
        let (ergebnis, _) = await ausfuehrenMitDaten(request)
        return ergebnis == .uebertragen
    }

    /// Frage an den Belegbox-Assistenten — gestreamt (SSE): liefert Text-Stücke,
    /// sobald Gemma sie erzeugt.
    static func fragenStream(_ frage: String, basis: URL,
                             pat: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                var request = URLRequest(url: basis.appendingPathComponent("chat"))
                request.httpMethod = "POST"
                request.timeoutInterval = 180
                request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try? JSONSerialization.data(
                    withJSONObject: ["frage": frage, "stream": true])
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
    static func fragen(_ frage: String, basis: URL, pat: String) async -> String? {
        var request = URLRequest(url: basis.appendingPathComponent("chat"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["frage": frage])
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any] else {
            return nil
        }
        return json["antwort"] as? String
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

/// Ergebnis der Server-Verifikation (BelegReview auf der H200V):
/// PaddleOCR-Lane + steuerliche Ersteinschätzung, aus `review/<name>.json`.
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
    }
    struct Einschaetzung: Codable {
        var belegart: String?
        var kontoSkr04: String?
        var steuerschluessel: String?
        var hinweise: [String]?
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
    var vlm: Vlm?
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
