import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @Published var onboarded = false
    @Published var skr = "SKR04"
    @Published var belege: [Beleg] = Demo.archiv()
    @Published var exportiert = false
    @Published var geprueft = 0
    @Published var pruefSekunden: [Double] = []

    /// OCR-Felder → geroutete Buchung (auto / bestätigen / prüfen).
    func routen(felder: Felder, bildJpeg: Data?, bildAufbereitet: Data?, ocrText: String) -> Beleg {
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
        beleg.bildAufbereitetJpeg = bildAufbereitet
        beleg.boxen = felder.boxen
        beleg.ocrText = ocrText

        if beleg.confidence >= 95 {
            siegeln(&beleg, status: .automatisch)
        }
        belege.insert(beleg, at: 0)
        return beleg
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
