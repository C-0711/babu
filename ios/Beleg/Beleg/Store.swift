import Foundation
import SwiftUI

/// Ablageort des persistierten App-Zustands (Application Support/Beleg).
private let zustandsDatei: URL = {
    let fm = FileManager.default
    let dir = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Beleg", isDirectory: true)
    try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir.appendingPathComponent("zustand.json")
}()

@MainActor
final class AppStore: ObservableObject {
    enum Tab: Hashable { case erfassen, belege, export }

    @Published var onboarded = false { didSet { speichern() } }
    @Published var skr = "SKR04" { didSet { speichern() } }
    @Published var belege: [Beleg] = [] { didSet { speichern() } }
    @Published var exportiert = false { didSet { speichern() } }
    @Published var geprueft = 0 { didSet { speichern() } }
    @Published var pruefSekunden: [Double] = [] { didSet { speichern() } }
    @Published var tab: Tab = .erfassen   // nicht persistiert

    // Belegbox-Übertragung (GitChain-Ablage) — Opt-in.
    // Öffentliche Route mit TLS via Cloudflare; funktioniert von überall.
    static let ablageStandardURL = "https://babu.0711.io"
    @Published var ablageURL = AppStore.ablageStandardURL { didSet { speichern() } }
    @Published var ablageAktiv = false { didSet { speichern() } }

    private var geladen = false
    private var speicherTask: Task<Void, Never>?

    init() {
        if let daten = try? Data(contentsOf: zustandsDatei),
           let z = try? JSONDecoder().decode(Zustand.self, from: daten) {
            onboarded = z.onboarded
            skr = z.skr
            belege = z.belege
            exportiert = z.exportiert
            geprueft = z.geprueft
            pruefSekunden = z.pruefSekunden
            // Migration: alte LAN-/Brücken-URLs auf die öffentliche Route heben.
            let alteURLs = ["http://192.168.145.10:7843", "http://192.168.5.93:7843"]
            if let gespeichert = z.ablageURL, !alteURLs.contains(gespeichert) {
                ablageURL = gespeichert
            } else {
                ablageURL = AppStore.ablageStandardURL
            }
            ablageAktiv = z.ablageAktiv ?? false
        } else {
            belege = Demo.archiv()   // Erststart: Demo-Archiv als Ausgangslage
        }
        geladen = true
    }

    // MARK: - Persistenz

    /// Alles, was einen App-Neustart überleben muss — Belege inkl. Bild-JPEGs.
    /// Neue Felder optional, damit ältere zustand.json weiter dekodiert.
    private struct Zustand: Codable {
        var onboarded: Bool
        var skr: String
        var belege: [Beleg]
        var exportiert: Bool
        var geprueft: Int
        var pruefSekunden: [Double]
        var ablageURL: String?
        var ablageAktiv: Bool?
    }

    private var zustand: Zustand {
        Zustand(onboarded: onboarded, skr: skr, belege: belege,
                exportiert: exportiert, geprueft: geprueft, pruefSekunden: pruefSekunden,
                ablageURL: ablageURL, ablageAktiv: ablageAktiv)
    }

    /// Entprellt auf ~0,25 s, damit Serien-Änderungen nicht pro Mutation schreiben.
    private func speichern() {
        guard geladen else { return }
        let z = zustand
        speicherTask?.cancel()
        speicherTask = Task.detached(priority: .utility) {
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            Self.schreibe(z)
        }
    }

    /// Sofort schreiben — beim Wechsel in den Hintergrund aufgerufen.
    func sichern() {
        guard geladen else { return }
        speicherTask?.cancel()
        Self.schreibe(zustand)
    }

    private nonisolated static func schreibe(_ z: Zustand) {
        guard let daten = try? JSONEncoder().encode(z) else { return }
        try? daten.write(to: zustandsDatei, options: .atomic)
    }

    /// OCR-Felder → geroutete Buchung (auto / bestätigen / prüfen).
    func routen(felder: Felder, bildJpeg: Data?, ocrText: String) -> Beleg {
        let v = Kontierung.vorschlag(felder: felder)
        var beleg = Beleg(
            lieferant: felder.lieferant ?? "Unbekannter Lieferant",
            belegNr: felder.belegNr ?? "ohne Nr.",
            datumText: felder.datumText ?? DateFormatter.kurz.string(from: Date()),
            netto: felder.netto ?? 0,
            ust: felder.ust ?? 0,
            brutto: felder.brutto ?? 0,
            ustSatz: felder.ustSatz,
            konto: v.konto,
            steuerschluessel: v.steuerschluessel,
            kreditor: v.kreditor,
            herkunft: v.herkunft,
            confidence: v.confidence,
            status: .offen,
            begruendung: v.begruendung,
            summenprobeOK: felder.summenprobeOK
        )
        beleg.bildJpeg = bildJpeg
        beleg.ocrText = ocrText

        if beleg.confidence >= 95 {
            siegeln(&beleg, status: .automatisch)
        }
        if ablageAktiv, bildJpeg != nil {
            beleg.ablageStatus = .ausstehend
            beleg.ablageDateiname = ablageDateiname(fuer: beleg)
        }
        belege.insert(beleg, at: 0)
        if beleg.ablageStatus == .ausstehend {
            let id = beleg.id
            Task { await self.uebertrage(id) }
        }
        return beleg
    }

    // MARK: - Belegbox-Übertragung

    /// Alle offenen Übertragungen erneut anstoßen (App-Start, Foreground, manuell).
    func ablageRetry() {
        guard ablageAktiv else { return }
        for b in belege where b.ablageStatus == .ausstehend || b.ablageStatus == .fehlgeschlagen {
            let id = b.id
            Task { await self.uebertrage(id) }
        }
    }

    /// Einzelnen Beleg in die GitChain-Ablage hochladen; Status am Beleg nachführen.
    func uebertrage(_ id: UUID) async {
        guard ablageAktiv,
              let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].ablageStatus != .uebertragen,
              let jpeg = belege[i].bildJpeg else { return }

        let dateiname = belege[i].ablageDateiname ?? ablageDateiname(fuer: belege[i])
        belege[i].ablageDateiname = dateiname
        belege[i].ablageStatus = .ausstehend

        let ergebnis = await AblageService.lade(bildJpeg: jpeg, dateiname: dateiname,
                                                basis: url, pat: pat)
        guard let j = belege.firstIndex(where: { $0.id == id }) else { return }
        switch ergebnis {
        case .uebertragen:
            belege[j].ablageStatus = .uebertragen
            belege[j].ablageZeit = Date()
        default:
            belege[j].ablageStatus = .fehlgeschlagen
        }
    }

    func siegeln(_ beleg: inout Beleg, status: BelegStatus) {
        let zeit = Date()
        beleg.status = status
        beleg.siegelZeit = zeit
        beleg.siegel = siegelHash(beleg, zeit: zeit)
    }

    /// Bestätigen/Korrigieren aus Ein-Tap-Karte oder Review.
    func buchen(id: UUID, konto: String?, steuerschluessel: String?, dauer: Double?) {
        guard let i = belege.firstIndex(where: { $0.id == id }) else { return }
        var b = belege[i]
        var korrigiert = false
        if let k = konto, k != b.konto { b.konto = k; korrigiert = true }
        if let ks = steuerschluessel, ks != b.steuerschluessel { b.steuerschluessel = ks; korrigiert = true }
        if korrigiert { b.herkunft = .mensch }
        siegeln(&b, status: korrigiert ? .korrigiert : .bestaetigt)
        belege[i] = b
        geprueft += 1
        if let d = dauer { pruefSekunden.append(d) }
    }

    var exportierbar: [Beleg] {
        belege.filter { [.automatisch, .bestaetigt, .korrigiert].contains($0.status) }
    }

    var stapelSumme: Double { exportierbar.reduce(0) { $0 + $1.brutto } }

    // MARK: - EXTF

    /// Vereinfachte EXTF-Vorschau — der vollständige v13-Writer ist ein
    /// Backend-Modul (siehe docs/build-plan.md, Phase 5).
    func extfText() -> String {
        var zeilen = ["\"EXTF\";700;21;\"Buchungsstapel\";13;;;", ";\"RE\";\"DE\";;\"20260801\";\"20260831\";"]
        for b in exportierbar {
            let betrag = fmtBetrag(b.brutto)
            let dd = String(b.datumText.replacingOccurrences(of: ".", with: "").prefix(4))
            zeilen.append("\(betrag);\"S\";\"EUR\";;;;\"\(b.kreditor)\";\"\(b.konto ?? "")\";\(b.steuerschluessel);\"\(dd)\";\"\(b.belegNr)\";\"\(b.lieferant)\"")
        }
        return zeilen.joined(separator: "\r\n")
    }

    /// Schreibt den Stapel als CP1252-kodierte Datei (DATEV-Kodierung).
    func extfDatei() -> URL? {
        let text = extfText()
        let data = text.data(using: .windowsCP1252, allowLossyConversion: true) ?? Data(text.utf8)
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("EXTF_Buchungsstapel_2026-08.csv")
        do {
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            return nil
        }
    }

    func fixieren() {
        for i in belege.indices where [.automatisch, .bestaetigt, .korrigiert].contains(belege[i].status) {
            belege[i].status = .fixiert
        }
        exportiert = true
    }

    var durchsatzText: String? {
        guard geprueft > 0, !pruefSekunden.isEmpty else { return nil }
        let avg = pruefSekunden.reduce(0, +) / Double(pruefSekunden.count)
        return "\(geprueft) geprüft · ø \(Int(avg.rounded())) s/Beleg"
    }
}

extension DateFormatter {
    static let kurz: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "dd.MM.yyyy"
        return f
    }()

    static let siegel: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "dd.MM.yyyy HH:mm:ss"
        return f
    }()
}
