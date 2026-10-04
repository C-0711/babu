import Foundation

/// Auslagen der Mitarbeiterinnen (babu Expenses D1).
struct AuslageZeile: Identifiable, Decodable {
    let stamm: String
    let status: String
    let name: String?
    let lieferant: String?
    let datum: String?
    let betrag: Double?
    let grund: String?
    var id: String { stamm }

    /// „23,40 €“ — für Beträge in den Auslagen-Ansichten.
    static func euro(_ wert: Double) -> String {
        String(format: "%.2f €", wert).replacingOccurrences(of: ".", with: ",")
    }

    /// „2026-08-05“ → „05.08.2026“; alles andere bleibt, wie es kam.
    static func datumDE(_ iso: String) -> String {
        let t = iso.prefix(10).split(separator: "-")
        guard t.count == 3, t[0].count == 4 else { return iso }
        return "\(t[2]).\(t[1]).\(t[0])"
    }

    var standText: String {
        switch status {
        case "eingereicht": return "wartet auf Freigabe"
        case "freigegeben": return "freigegeben"
        case "abgelehnt": return "abgelehnt"
        case "zurueckgezogen": return "zurückgezogen"
        case "erstattet": return "erstattet ✓"
        default: return status
        }
    }
}

struct MeineAuslagen: Decodable {
    let auslagen: [AuslageZeile]
    let offen: Double
    let iban_da: Bool
}

extension AblageService {
    static func meineAuslagen(basis: URL, pat: String) async -> MeineAuslagen? {
        await holen(pfad: "api/auslagen/meine", basis: basis, pat: pat)
    }

    static func offeneAuslagen(basis: URL, pat: String) async -> [AuslageZeile]? {
        struct Antwort: Decodable { let auslagen: [AuslageZeile] }
        let a: Antwort? = await holen(pfad: "api/auslagen", abfrage: [URLQueryItem(name: "stand", value: "offen")],
                                      basis: basis, pat: pat)
        return a?.auslagen
    }

    static func auslagePost(_ pfad: String, koerper: [String: Any]? = nil,
                            basis: URL, pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent(pfad))
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: koerper ?? [:])
        guard let (_, antwort) = try? await URLSession.shared.data(for: request) else { return false }
        return (antwort as? HTTPURLResponse)?.statusCode == 200
    }

    private static func holen<T: Decodable>(pfad: String, abfrage: [URLQueryItem] = [],
                                            basis: URL, pat: String) async -> T? {
        var teile = URLComponents(url: basis.appendingPathComponent(pfad), resolvingAgainstBaseURL: false)
        if !abfrage.isEmpty { teile?.queryItems = abfrage }
        guard let url = teile?.url else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONDecoder().decode(T.self, from: daten)
    }
}
