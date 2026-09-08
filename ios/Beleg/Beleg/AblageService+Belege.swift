import Foundation
import UIKit

// Alles rund um den einzelnen Beleg: Aufnahme und Ablage, die Prueflesung
// samt Protokoll, der Kontenkatalog, die Server-Vorschau, Gemmas
// Einschaetzung und die Frage, welcher Beleg noch fehlt.
//
// Nicht hierher: Kassenbuch, Abschluss und Rechnungen (`+Geld`),
// Termine, Team und Chat (`+Betrieb`), Netz-Helfer (Kern).

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

extension AblageService {

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

    /// Der Buchungs-Kontenkatalog des Servers (`GET /api/kategorien`) —
    /// Ninas Wörter samt Kontonummer im Rahmen des Betriebs. Der Server
    /// führt die Liste, die App führt keine zweite (Ninas Anmerkung #73:
    /// die eingebaute Auswahl war zu klein).
    static func kategorien(basis: URL, pat: String) async -> [Konto] {
        var request = URLRequest(url: basis.appendingPathComponent("api/kategorien"))
        request.timeoutInterval = 10
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any],
              let liste = json["kategorien"] as? [[String: Any]] else { return [] }
        var gesehen = Set<String>()
        var konten: [Konto] = []
        for k in liste {
            guard let konto = k["konto"] as? String,
                  let name = k["name"] as? String,
                  !gesehen.contains(konto) else { continue }
            gesehen.insert(konto)
            konten.append(Konto(nr: konto, bez: name, individuell: false))
        }
        return konten
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
