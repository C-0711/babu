import Foundation
import Vision
import CoreGraphics

/// „Instant Reading im Sucher": Fast-OCR auf dem Quad-Ausschnitt, strikt
/// sequenziell auf eigener Queue (max. ein Lauf pro Intervall) — rührt weder
/// die Analyse-Frames noch die Detektionsrate an. Der Parse läuft über den
/// unveränderten `FeldParser` (dieselbe Heuristik wie nach der Aufnahme).
final class LiveFieldsReader {

    /// Wird auf der ocrQueue aufgerufen — Empfänger hüpft selbst auf @MainActor.
    var onBefund: ((LiveTextBefund) -> Void)?

    private let ocrQueue = DispatchQueue(label: "io.0711.beleg.liveocr", qos: .utility)

    // Nur auf der ocrQueue berührt:
    private var letzterStart = Date.distantPast
    private var vorherigeFelder = Felder()
    private var anzeige = LiveTextBefund()
    private var anzeigeZeit = Date.distantPast

    private static let anzeigeHaltezeit: TimeInterval = 2.0

    func verarbeite(_ crop: CGImage) {
        ocrQueue.async { [self] in
            // Der Detector drosselt bereits aufs Intervall; das hier fängt nur
            // Rückstau ab, falls ein Lauf länger dauerte als geplant.
            guard Date().timeIntervalSince(letzterStart) >= CaptureTuning.liveOcrIntervall * 0.8 else { return }
            letzterStart = Date()

            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .fast
            request.recognitionLanguages = ["de-DE"]
            request.usesLanguageCorrection = false
            try? VNImageRequestHandler(cgImage: crop, options: [:]).perform([request])

            let beobachtungen = request.results ?? []
            let zeilen: [(text: String, conf: Double)] = beobachtungen
                .sorted { $0.boundingBox.midY > $1.boundingBox.midY }
                .compactMap { o in
                    guard let best = o.topCandidates(1).first else { return nil }
                    return (best.string, Double(best.confidence))
                }

            let text = zeilen.map(\.text).joined(separator: "\n")
            let hatSignal =
                text.range(of: #"\d+,\d{2}"#, options: .regularExpression) != nil ||
                text.range(of: #"\d{1,2}\.\d{1,2}\.\d{2,4}"#, options: .regularExpression) != nil

            let felder = FeldParser.parse(zeilen: zeilen)

            // Entprellung: ein Wert erscheint erst, wenn zwei aufeinanderfolgende
            // Läufe ihn identisch lesen — und bleibt danach kurz stehen.
            let jetzt = Date()
            var neueAnzeige = jetzt.timeIntervalSince(anzeigeZeit) <= Self.anzeigeHaltezeit
                ? anzeige : LiveTextBefund()
            var bestaetigt = false
            if let b = felder.brutto, b == vorherigeFelder.brutto { neueAnzeige.brutto = b; bestaetigt = true }
            if let d = felder.datumText, d == vorherigeFelder.datumText { neueAnzeige.datumText = d; bestaetigt = true }
            if let n = felder.belegNr, n == vorherigeFelder.belegNr { neueAnzeige.belegNr = n; bestaetigt = true }
            if bestaetigt { anzeigeZeit = jetzt }
            vorherigeFelder = felder

            // Rohsignale (fürs Content-Gate) sind immer frisch — nur die
            // Anzeige-Felder sind entprellt.
            neueAnzeige.zeilenZahl = zeilen.count
            neueAnzeige.hatBelegSignal = hatSignal
            neueAnzeige.zeit = jetzt
            anzeige = neueAnzeige

            onBefund?(neueAnzeige)
        }
    }
}
