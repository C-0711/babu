import Foundation
import CryptoKit

enum Herkunft: String, Codable {
    case historie = "Historie"
    case regel = "Regel"
    case ki = "KI"
    case mensch = "Manuell"
}

enum BelegStatus: String, Codable {
    case offen, automatisch, bestaetigt, korrigiert, fixiert

    var label: String {
        switch self {
        case .offen: return "offen"
        case .automatisch: return "automatisch"
        case .bestaetigt: return "bestätigt"
        case .korrigiert: return "korrigiert → lernt"
        case .fixiert: return "exportiert · fixiert"
        }
    }
}

struct Konto: Identifiable, Hashable {
    let nr: String
    let bez: String
    let individuell: Bool
    var id: String { nr }
}

/// SKR04-Auszug + individuelle Mandantenkonten.
enum Kontenplan {
    static let konten: [Konto] = [
        Konto(nr: "6325", bez: "Gas, Strom, Wasser", individuell: false),
        Konto(nr: "6530", bez: "Kfz-Betriebskosten", individuell: false),
        Konto(nr: "6531", bez: "Fahrzeugpflege", individuell: true),
        Konto(nr: "6600", bez: "Werbekosten", individuell: false),
        Konto(nr: "6610", bez: "Geschenke bis 50 €", individuell: false),
        Konto(nr: "6640", bez: "Bewirtungskosten 70 %", individuell: false),
        Konto(nr: "6673", bez: "Reisekosten Fahrtkosten", individuell: false),
        Konto(nr: "6805", bez: "Telefon / Kommunikation", individuell: false),
        Konto(nr: "6815", bez: "Bürobedarf", individuell: false),
        Konto(nr: "6820", bez: "Fachliteratur", individuell: false),
        Konto(nr: "6837", bez: "Hosting / IT-Dienste", individuell: true),
        Konto(nr: "6850", bez: "Sonstiger Betriebsbedarf", individuell: false)
    ]

    static func bezeichnung(_ nr: String) -> String {
        konten.first { $0.nr == nr }?.bez ?? "Sachkonto"
    }
}

struct Beleg: Identifiable, Codable {
    var id = UUID()
    var lieferant: String
    var belegNr: String
    var datumText: String
    var netto: Double
    var ust: Double
    var brutto: Double
    var ustSatz: Int          // 19, 7, 0
    var konto: String?
    var steuerschluessel: String   // "9", "8", "0"
    var kreditor: String
    var herkunft: Herkunft
    var confidence: Int
    var status: BelegStatus
    var begruendung: String
    var summenprobeOK: Bool
    var siegel: String?
    var siegelZeit: Date?
    var bildJpeg: Data?
    var ocrText: String = ""

    var ksLabel: String {
        switch steuerschluessel {
        case "9": return "VSt 19 %"
        case "8": return "VSt 7 %"
        default: return "keine VSt"
        }
    }
}

/// Merkle-Siegel-Kurzform: SHA-256 über Beleginhalt + Zeitstempel.
func siegelHash(_ beleg: Beleg, zeit: Date) -> String {
    let basis = "\(beleg.lieferant)|\(beleg.belegNr)|\(beleg.brutto)|\(beleg.konto ?? "-")|\(zeit.timeIntervalSince1970)"
    let digest = SHA256.hash(data: Data(basis.utf8))
    let hex = digest.map { String(format: "%02x", $0) }.joined()
    let a = hex.prefix(8)
    let b = hex.dropFirst(8).prefix(4)
    let c = hex.dropFirst(12).prefix(4)
    return "\(a) \(b) \(c)"
}

func fmtEur(_ n: Double) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    f.locale = Locale(identifier: "de_DE")
    f.minimumFractionDigits = 2
    f.maximumFractionDigits = 2
    return (f.string(from: NSNumber(value: n)) ?? "0,00") + " €"
}

func fmtBetrag(_ n: Double) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    f.locale = Locale(identifier: "de_DE")
    f.minimumFractionDigits = 2
    f.maximumFractionDigits = 2
    return f.string(from: NSNumber(value: n)) ?? "0,00"
}

/// Bereits archivierte Demo-Belege, damit Liste und Export nicht leer starten.
enum Demo {
    static func archiv() -> [Beleg] {
        var a = Beleg(lieferant: "Stadtwerke Stuttgart", belegNr: "Abschlag 08/26", datumText: "03.08.2026",
                      netto: 346.22, ust: 65.78, brutto: 412.00, ustSatz: 19,
                      konto: "6325", steuerschluessel: "9", kreditor: "70012",
                      herkunft: .regel, confidence: 96, status: .automatisch,
                      begruendung: "Regel „Stadtwerke → Energie“ griff.", summenprobeOK: true)
        a.siegel = "77b2e0c4 9a11 f38d"
        a.siegelZeit = Date(timeIntervalSinceNow: -3 * 86400)

        var b = Beleg(lieferant: "Hetzner Online GmbH", belegNr: "R2026-0psd83", datumText: "01.08.2026",
                      netto: 200.00, ust: 38.00, brutto: 238.00, ustSatz: 19,
                      konto: "6837", steuerschluessel: "9", kreditor: "70003",
                      herkunft: .historie, confidence: 98, status: .automatisch,
                      begruendung: "Kreditor 9× zuvor auf 6837 gebucht.", summenprobeOK: true)
        b.siegel = "0d31f6a8 5be2 c974"
        b.siegelZeit = Date(timeIntervalSinceNow: -5 * 86400)

        return [a, b]
    }
}
