import Foundation
import CryptoKit

enum Herkunft: String, Codable {
    case historie = "Historie"
    case regel = "Regel"
    case ki = "KI"
    case mensch = "Manuell"

    /// Anzeige ohne Technik-Vokabular (Rohwerte bleiben stabil — persistiert).
    var anzeige: String {
        switch self {
        case .historie: return "vom Gerät, nach deiner Historie"
        case .regel: return "vom Gerät, nach fester Regel"
        // Seit 23.08.2026 steht `.ki` für genau eines: die Lesung vom Server
        // wurde übernommen. Das ist die verlässlichste Quelle, die es gibt —
        // „Vorschlag" wäre dafür das falsche Wort, und die Zahlen vom Gerät
        // klängen daneben sicherer, als sie sind.
        case .ki: return "geprüft gelesen"
        case .mensch: return "von dir festgelegt"
        }
    }

    /// Kurzform für Badges.
    var kurz: String {
        switch self {
        case .historie: return "vom Gerät"
        case .regel: return "vom Gerät"
        case .ki: return "geprüft"
        case .mensch: return "Manuell"
        }
    }
}

// CaseIterable, damit der Harness ALLE Statuswörter durchgehen kann und
// nicht nur die, an die jemand gerade gedacht hat.
enum BelegStatus: String, Codable, CaseIterable {
    case offen, automatisch, bestaetigt, korrigiert, fixiert

    var label: String {
        switch self {
        case .offen: return "offen"
        case .automatisch: return "automatisch"
        case .bestaetigt: return "bestätigt"
        case .korrigiert: return "korrigiert → lernt"
        // „fixiert" ist unser Wort, nicht Ninas. Auf dem Bildschirm steht
        // dasselbe Wort, das der Export-Knopf verwendet: festgeschrieben.
        // In der DATEV-Datei darf „Buchungsstapel" stehen bleiben — die liest
        // das Steuerbüro, nicht sie.
        case .fixiert: return "exportiert · festgeschrieben"
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

/// Übertragungsstatus eines Belegs in die GitChain-Belegbox (Ablage auf der H200V).
enum AblageStatus: String, Codable {
    case ausstehend, uebertragen, fehlgeschlagen
}

/// Dateiname für den Ablage-Upload: `beleg_<jjjj-mm-tt>_<lieferant-slug>_<id8>.jpg`.
/// Der Server prefixt zusätzlich Zeitstempel + Hex — Kollisionen sind unkritisch.
func ablageDateiname(fuer beleg: Beleg) -> String {
    let teile = beleg.datumText.split(separator: ".")
    let datum: String
    if teile.count == 3, let tag = Int(teile[0]), let monat = Int(teile[1]) {
        let jahr = teile[2].count == 2 ? "20\(teile[2])" : String(teile[2])
        datum = String(format: "%@-%02d-%02d", jahr, monat, tag)
    } else {
        datum = "0000-00-00"
    }
    let id8 = beleg.id.uuidString.replacingOccurrences(of: "-", with: "").prefix(8).lowercased()
    // Mehrseitige Bündel reisen als EIN PDF. Der Slug darf dabei nie
    // „auszug" tragen — der Server sortiert PDFs mit „auszug" im Namen ins
    // Kontoauszugsfach, egal was die Buchhaltung entschieden hat.
    let endung = (beleg.seitenJpeg?.count ?? 0) > 1 ? "pdf" : "jpg"
    var name = slug(beleg.lieferant)
    if endung == "pdf" { name = name.replacingOccurrences(of: "auszug", with: "beleg") }
    return "beleg_\(datum)_\(name)_\(id8).\(endung)"
}

/// Monats-Schlüssel eines Belegs für die Einteilung der Dokumentenliste:
/// „03.08.2026" → „2026-08". Der Monat eines Belegs ist der seines DATUMS,
/// nicht der des Hochladens — dieselbe Regel wie im Kassenbuch und auf dem
/// Server. Zweistellige Jahre („26") sind 20xx, Unlesbares wird nil.
func belegMonatSchluessel(_ datumText: String) -> String? {
    let t = datumText.split(separator: ".")
    guard t.count == 3, let tag = Int(t[0]), let monat = Int(t[1]),
          var jahr = Int(t[2]), (1...31).contains(tag),
          (1...12).contains(monat) else { return nil }
    if jahr < 100 { jahr += 2000 }
    guard jahr >= 2000 else { return nil }
    return String(format: "%04d-%02d", jahr, monat)
}

/// Ergebnis der Betrags-Gegenprobe: leer ist ein eigener Zustand —
/// 0+0=0 stimmt zwar rechnerisch, hat aber nichts bewiesen.
enum Summenprobe { case leer, passt, passtNicht }

func summenprobe(netto: Double, ust: Double, brutto: Double) -> Summenprobe {
    if abs(netto) < 0.005, abs(ust) < 0.005, abs(brutto) < 0.005 { return .leer }
    return abs(netto + ust - brutto) < 0.011 ? .passt : .passtNicht
}

private let monatsNamen = ["Januar", "Februar", "März", "April", "Mai",
                           "Juni", "Juli", "August", "September", "Oktober",
                           "November", "Dezember"]

/// Überschrift eines Monats-Abschnitts: „2026-08" → „August 2026".
func belegMonatTitel(_ schluessel: String) -> String {
    let t = schluessel.split(separator: "-")
    guard t.count == 2, let jahr = Int(t[0]), let monat = Int(t[1]),
          (1...12).contains(monat) else { return schluessel }
    return "\(monatsNamen[monat - 1]) \(jahr)"
}

/// ASCII-Slug: Umlaute transliteriert, alles außer [a-z0-9] wird zu Bindestrichen.
private func slug(_ text: String) -> String {
    var s = text.lowercased()
    for (u, e) in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")] {
        s = s.replacingOccurrences(of: u, with: e)
    }
    let teile = s.split(whereSeparator: { !($0.isASCII && ($0.isLetter || $0.isNumber)) })
    let ergebnis = teile.joined(separator: "-").prefix(40)
    return ergebnis.isEmpty ? "beleg" : String(ergebnis)
}

/// Eine Zeile der Steuertabelle des Belegs (7 % und 19 % getrennt) — wird
/// persistiert, damit der Export Mehrsatz-Belege korrekt aufteilen kann.
struct SteuerPosition: Codable, Equatable {
    var satz: Int
    var netto: Double
    var ust: Double
    var brutto: Double
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
    /// Wohin babu es einsortiert hat — „vertrag", „behoerde", „kontoauszug"
    /// oder „beleg". Optional: alte Stände kennen das Feld nicht.
    var abgelegtAls: String?
    /// Derselbe Ort in Worten, wie ihn die App zeigt („Bei deinen Verträgen").
    var abgelegtWohin: String?
    // Belegbox-Übertragung (alle optional — ältere zustand.json lädt weiter)
    var ablageStatus: AblageStatus?
    var ablageDateiname: String?
    // Zielbild: Gemmas Dokumentklasse und das Einschätzungs-Ergebnis reisen
    // beim Upload mit — daraus wird Fach und archivierte Lesung.
    var dokumentklasse: String?
    var ergebnisJson: String?
    /// Visions Zeilen mit Ort und Konfidenz, serialisiert — die eine Lesung.
    var ocrGeoJson: String?
    /// Mehrseitiger Beleg: ALLE Seiten als JPEG (bildJpeg bleibt Seite 1,
    /// damit jede bestehende Anzeige weiterlebt). Optional — alte
    /// zustand.json laden unverändert. Hochgeladen wird daraus EIN PDF.
    var seitenJpeg: [Data]?
    var ablageZeit: Date?
    // Audit-Stempel: GitChain-Commits der vollständigen Kette
    var auditAufnahme: String?
    var auditReview: String?
    // Ergebnis der Archiv-Ablage: "ok" oder "fehlgeschlagen" (nil = unbekannt)
    var reviewStatus: String?
    // Bewirtungsangaben (§4 Abs. 5 Nr. 2 EStG): Pflicht bei Konto 6640
    var bewirtungAnlass: String?
    var bewirtungPersonen: String?
    // Beispiel-Beleg (Erststart/Simulator) — niemals exportieren
    var istDemo: Bool?
    // Steuertabelle je Satz (Mehrsatz-Belege)
    var steuerPositionen: [SteuerPosition]?
    // Fremdwährung: der Originalbetrag und seine Währung (z. B. 55,74 AED).
    // brutto/netto/ust sind dann der EURO-Wert aus der Buchhaltung — bis er
    // da ist, bleibt der Beleg offen statt falsch in Euro gebucht.
    var fremdBetrag: Double?
    var fremdWaehrung: String?
    // Die Buchhaltung (Gemma) hat noch Fragen — der Beleg wartet auf Nina.
    // Gesetzt, wenn nicht gebucht werden konnte oder sie das Fragenpaket
    // vorzeitig weggelegt hat.
    var offeneFrage: String?

    /// Bewirtungsbeleg ohne erfasste Angaben? Dann fragt die App nach.
    var brauchtBewirtungsangaben: Bool {
        konto == "6640" && (bewirtungPersonen ?? "").trimmingCharacters(in: .whitespaces).isEmpty
    }

    /// 0,00 € heißt: die Lesung fehlt noch — nicht „kostenloser Beleg".
    /// Vor dem Buchen muss der Betrag geklärt sein; eine Gutschrift
    /// (negativ) ist dagegen ein echter Betrag.
    var brauchtBetrag: Bool {
        abs(brutto) < 0.005
    }

    /// Das Etikett neben dem Vertrauensbalken. Ein Beleg, den noch niemand
    /// gelesen hat (offen, ohne jedes Vertrauen), darf nicht „geprüft"
    /// tragen — das Wort ist erst nach der Lesung verdient.
    var herkunftEtikett: String {
        if status == .offen && confidence == 0 { return "wird gelesen" }
        return herkunft.kurz
    }

    /// Was hinter „Festgehalten am …" steht. Unveränderlichkeit wird erst
    /// mit der Fixierung versprochen — vorher ist eine Korrektur möglich
    /// und wird ihrerseits neu festgehalten.
    var siegelZusatz: String {
        status == .fixiert ? "bleibt unverändert"
                           : "eine Korrektur wird neu festgehalten"
    }

    /// Grüner Haken nur, wenn das Archiv den Beleg bestätigt hat (Review-
    /// Commit da) UND die Ablage nicht gescheitert ist.
    var archivBestaetigt: Bool {
        auditReview != nil && reviewStatus != "fehlgeschlagen"
    }

    var ksLabel: String {
        switch steuerschluessel {
        case "9": return "VSt 19 %"
        case "8": return "VSt 7 %"
        default: return "keine VSt"
        }
    }
}

/// Merkle-Siegel-Kurzform: SHA-256 über ALLE buchungsrelevanten Felder
/// inkl. Belegbild — vorher deckte das Siegel nur 4 Felder ab, Netto/USt/
/// Datum/Bild konnten sich unbemerkt ändern.
func siegelHash(_ beleg: Beleg, zeit: Date) -> String {
    var bildHash = "-"
    if let seiten = beleg.seitenJpeg, seiten.count > 1 {
        // Bündel: das Siegel deckt JEDE Seite — eine Kette aus Seiten-Hashes.
        bildHash = seiten.map { seite in
            String(SHA256.hash(data: seite)
                .map { String(format: "%02x", $0) }.joined().prefix(16))
        }.joined(separator: "+")
    } else if let bild = beleg.bildJpeg {
        bildHash = String(SHA256.hash(data: bild)
            .map { String(format: "%02x", $0) }.joined().prefix(16))
    }
    let basis = [beleg.lieferant, beleg.belegNr, beleg.datumText,
                 String(beleg.netto), String(beleg.ust), String(beleg.brutto),
                 String(beleg.ustSatz), beleg.konto ?? "-", beleg.steuerschluessel,
                 beleg.kreditor, beleg.bewirtungAnlass ?? "-",
                 beleg.bewirtungPersonen ?? "-", bildHash,
                 String(zeit.timeIntervalSince1970)].joined(separator: "|")
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
        a.istDemo = true

        var b = Beleg(lieferant: "Hetzner Online GmbH", belegNr: "R2026-0psd83", datumText: "01.08.2026",
                      netto: 200.00, ust: 38.00, brutto: 238.00, ustSatz: 19,
                      konto: "6837", steuerschluessel: "9", kreditor: "70003",
                      herkunft: .historie, confidence: 98, status: .automatisch,
                      begruendung: "Kreditor 9× zuvor auf 6837 gebucht.", summenprobeOK: true)
        b.siegel = "0d31f6a8 5be2 c974"
        b.siegelZeit = Date(timeIntervalSinceNow: -5 * 86400)
        b.istDemo = true

        return [a, b]
    }
}
