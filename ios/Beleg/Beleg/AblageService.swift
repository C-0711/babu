import Foundation
import Security

// Kern des Ablage-Clients: Basis-URL, Bearer-Zugang, die beiden
// Netz-Helfer (`holen`/`schicken`), der Multipart-Bau, das
// Ergebnis-Enum und die Keychain.
//
// Hier gehoert nur hinein, was ALLE Sparten brauchen. Jede fachliche
// Route steht in einer der drei Erweiterungen daneben:
// `AblageService+Belege` · `AblageService+Betrieb` · `AblageService+Geld`.

/// Ergebnis eines Ablage-Aufrufs (Upload oder Verbindungstest).
enum AblageErgebnis: Equatable {
    case uebertragen          // 2xx — bzw. beim Verbindungstest: Server + Token OK
    case tokenFehler          // 401
    case abgelehnt(Int)       // sonstiger HTTP-Status
    case nichtErreichbar      // Netzfehler (kein WLAN, falsches Netz, Timeout)
}

/// Client für die GitChain-Ablage auf der H200V:
/// `POST <basis>/ablage`, Multipart-Feld `file`, `Authorization: Bearer <PAT>`.
/// Jeder erfolgreiche Upload wird serverseitig ein Commit `aufnahme: …` in babu.git.
enum AblageService {

    // MARK: - Zwei kleine Helfer, damit sich das oben nicht zehnmal wiederholt
    //
    // Sie waren `private`, solange alle Routen in einer Datei standen.
    // Seit die Sparten getrennt liegen, rufen sie die Erweiterungen —
    // und `private` reicht in Swift nur bis zum Dateirand.

    static func holen(_ pfad: String, basis: URL, pat: String) async
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
    static func schicken(_ pfad: String, _ felder: [String: Any],
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

    static func ausfuehren(_ request: URLRequest, erfolg2xx: Bool) async -> AblageErgebnis {
        await ausfuehrenMitDaten(request).0
    }

    static func ausfuehrenMitDaten(_ request: URLRequest) async -> (AblageErgebnis, Data?) {
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
