import Foundation
import Vision
import UIKit

/// On-Device-OCR über das Vision-Framework — das "Instant Reading" der App.
enum OCRService {

    struct Ergebnis {
        /// Eine erkannte Zeile inkl. Position im Bild (Vision-normiert,
        /// Ursprung unten links) — Grundlage für die grünen Feld-Markierungen.
        struct Zeile {
            let text: String
            let conf: Double
            let box: CGRect
        }
        let zeilen: [Zeile]
        var text: String { zeilen.map { $0.text }.joined(separator: "\n") }
        /// Das Übergabeformat an die Buchhaltung (seit 27.08.): Visions
        /// Rohausgabe als {text, conf, box} — box in Prozent des Blatts,
        /// y von oben. Kein Parser, keine Deutung: nur Serialisierung.
        var geoZeilen: [[String: Any]] {
            zeilen.map { z in
                let x: Double = (Double(z.box.origin.x) * 1000).rounded() / 10
                let yOben: Double = 1 - Double(z.box.origin.y) - Double(z.box.height)
                let y: Double = (yOben * 1000).rounded() / 10
                let breite: Double = (Double(z.box.width) * 1000).rounded() / 10
                let hoehe: Double = (Double(z.box.height) * 1000).rounded() / 10
                let konf: Double = (z.conf * 100).rounded() / 100
                return ["text": z.text, "conf": konf,
                        "box": [x, y, breite, hoehe]]
            }
        }
        var geoJson: String? {
            (try? JSONSerialization.data(withJSONObject: geoZeilen))
                .flatMap { String(data: $0, encoding: .utf8) }
        }
    }

    static func erkenne(_ image: UIImage) async -> Ergebnis {
        guard let cg = image.cgImage else { return Ergebnis(zeilen: []) }
        return await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, _ in
                let obs = (request.results as? [VNRecognizedTextObservation]) ?? []
                // Von oben nach unten sortieren (Vision liefert normierte Koordinaten, y=0 unten).
                let sortiert = obs.sorted { $0.boundingBox.midY > $1.boundingBox.midY }
                let zeilen: [Ergebnis.Zeile] = sortiert.compactMap { o in
                    guard let best = o.topCandidates(1).first else { return nil }
                    return Ergebnis.Zeile(text: best.string, conf: Double(best.confidence),
                                          box: o.boundingBox)
                }
                continuation.resume(returning: Ergebnis(zeilen: zeilen))
            }
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["de-DE", "en-US"]
            request.usesLanguageCorrection = true

            DispatchQueue.global(qos: .userInitiated).async {
                let handler = VNImageRequestHandler(cgImage: cg, options: [:])
                do {
                    try handler.perform([request])
                } catch {
                    continuation.resume(returning: Ergebnis(zeilen: []))
                }
            }
        }
    }
}

/// Demo-Beleg für den Simulator (dort gibt es keine Kamera):
/// rendert eine Beispielrechnung als Bild, die dann durch die echte
/// OCR-Pipeline läuft — derselbe Codepfad wie ein Kamera-Scan.
enum DemoBeleg {
    static func bild() -> UIImage {
        let size = CGSize(width: 620, height: 840)
        let renderer = UIGraphicsImageRenderer(size: size)
        return renderer.image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))

            func zeichne(_ text: String, _ y: CGFloat, size fs: CGFloat, fett: Bool = false, rechts: Bool = false) {
                let font = fett ? UIFont.boldSystemFont(ofSize: fs) : UIFont.systemFont(ofSize: fs)
                let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: UIColor.black]
                let s = NSAttributedString(string: text, attributes: attrs)
                let x = rechts ? 620 - 50 - s.size().width : 50
                s.draw(at: CGPoint(x: x, y: y))
            }

            zeichne("Bürobedarf Müller GmbH", 60, size: 30, fett: true)
            zeichne("Königstraße 41 · 70173 Stuttgart", 100, size: 16)
            zeichne("USt-IdNr. DE 214 883 901", 124, size: 16)
            zeichne("Rechnung RE-2026-4711", 180, size: 20, fett: true)
            zeichne("Datum: 05.08.2026", 210, size: 16)
            zeichne("Kopierpapier A4, 5 x 500 Blatt", 280, size: 17)
            zeichne("34,50", 280, size: 17, rechts: true)
            zeichne("Toner HP 207X schwarz", 315, size: 17)
            zeichne("51,90", 315, size: 17, rechts: true)
            zeichne("Ordner A4, 10 Stück", 350, size: 17)
            zeichne("13,60", 350, size: 17, rechts: true)
            zeichne("Summe netto", 430, size: 17)
            zeichne("100,00", 430, size: 17, rechts: true)
            zeichne("USt 19 %", 465, size: 17)
            zeichne("19,00", 465, size: 17, rechts: true)
            zeichne("Gesamtbetrag EUR", 505, size: 19, fett: true)
            zeichne("119,00", 505, size: 19, fett: true, rechts: true)
            zeichne("Zahlbar innerhalb 14 Tagen", 580, size: 14)
        }
    }
}
