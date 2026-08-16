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
    enum Tab: Hashable { case erfassen, belege, fragen, export }

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
            // Ältere Stände: Demo-Belege am festen Demo-Siegel nachträglich
            // markieren, damit sie nie im echten Stapel landen.
            let demoSiegel: Set<String> = ["77b2e0c4 9a11 f38d", "0d31f6a8 5be2 c974"]
            for i in belege.indices where belege[i].istDemo != true && demoSiegel.contains(belege[i].siegel ?? "") {
                belege[i].istDemo = true
            }
        } else {
            #if targetEnvironment(simulator)
            belege = Demo.archiv()   // Nur im Simulator: Demo-Archiv als Ausgangslage
            #endif
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

        let (ergebnis, serverDatei) = await AblageService.lade(bildJpeg: jpeg, dateiname: dateiname,
                                                               basis: url, pat: pat)
        guard let j = belege.firstIndex(where: { $0.id == id }) else { return }
        switch ergebnis {
        case .uebertragen:
            belege[j].ablageStatus = .uebertragen
            belege[j].ablageZeit = Date()
            // Serverseitiger Name (mit Zeitstempel-Präfix) ist der Schlüssel
            // zum BelegReview-Ergebnis.
            if let serverDatei { belege[j].ablageDateiname = serverDatei }
            // Audit-Stempel nachladen, sobald der Watcher reviewt hat (~30 s).
            Task {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                await self.auditLaden(id)
            }
        default:
            belege[j].ablageStatus = .fehlgeschlagen
        }
    }

    // MARK: - Audit-Stempel (GitChain-Commits am Beleg persistieren)

    /// Für alle übertragenen Belege ohne Stempel das Review abfragen.
    func auditNachladen() {
        guard ablageAktiv, KeychainHelfer.ladePAT() != nil else { return }
        for b in belege where b.ablageStatus == .uebertragen && b.auditReview == nil {
            let id = b.id
            Task { await self.auditLaden(id) }
        }
    }

    func auditLaden(_ id: UUID) async {
        guard let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].auditReview == nil,
              let dateiname = belege[i].ablageDateiname else { return }
        let stamm = (dateiname as NSString).deletingPathExtension
        guard let review = await AblageService.reviewAbrufen(stamm: stamm, basis: url, pat: pat),
              let audit = review.audit else { return }
        auditSetzen(id: id, aufnahme: audit.aufnahme?.commit, review: audit.review?.commit)
    }

    func auditSetzen(id: UUID, aufnahme: String?, review: String?) {
        guard let i = belege.firstIndex(where: { $0.id == id }) else { return }
        if let aufnahme { belege[i].auditAufnahme = aufnahme }
        if let review { belege[i].auditReview = review }
    }

    /// Bewirtungsangaben (§4 Abs. 5 EStG) am Beleg erfassen.
    func bewirtungSetzen(id: UUID, anlass: String, personen: String) {
        guard let i = belege.firstIndex(where: { $0.id == id }) else { return }
        belege[i].bewirtungAnlass = anlass.trimmingCharacters(in: .whitespacesAndNewlines)
        belege[i].bewirtungPersonen = personen.trimmingCharacters(in: .whitespacesAndNewlines)
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

    /// Beleg entfernen — fixierte (exportierte) Belege sind unantastbar.
    func loeschen(id: UUID) {
        belege.removeAll { $0.id == id && $0.status != .fixiert }
    }

    var exportierbar: [Beleg] {
        exportierbareBelege(belege)
    }

    var stapelSumme: Double { exportierbar.reduce(0) { $0 + $1.brutto } }

    // MARK: - EXTF

    /// Vorschau des aktuellen Stapels (Logik in ExtfWriter.swift, harness-getestet).
    func extfText() -> String {
        let monat = extfMonat()
        return extfStapelText(belege: exportierbar, von: monat.von, bis: monat.bis)
    }

    /// Schreibt eine feste Belegmenge als CP1252-kodierte Datei (DATEV-Kodierung).
    func extfDatei(fuer stapel: [Beleg]) -> URL? {
        let monat = extfMonat()
        let text = extfStapelText(belege: stapel, von: monat.von, bis: monat.bis)
        let data = text.data(using: .windowsCP1252, allowLossyConversion: true) ?? Data(text.utf8)
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(monat.dateiname)
        do {
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            return nil
        }
    }

    /// Vorschau-Datei über den aktuell exportierbaren Stapel.
    func extfDatei() -> URL? { extfDatei(fuer: exportierbar) }

    /// Stapel exportieren: ERST die Datei aus dem Schnappschuss erzeugen,
    /// DANN genau diese Belege fixieren — andersherum wäre die Datei leer,
    /// weil `exportierbar` fixierte Belege ausfiltert.
    func exportieren() -> URL? {
        let stapel = exportierbar
        guard !stapel.isEmpty, let url = extfDatei(fuer: stapel) else { return nil }
        let ids = Set(stapel.map(\.id))
        for i in belege.indices where ids.contains(belege[i].id) {
            belege[i].status = .fixiert
        }
        exportiert = true
        return url
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
