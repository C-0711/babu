import UIKit
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins

/// Entzerrt das aufgenommene Foto auf den Beleg-Ausschnitt — das Gegenstück zu
/// dem, was `VNDocumentCameraScan.imageOfPage` lieferte. Die Ecken kommen aus
/// einer Neu-Detektion auf dem hochauflösenden Foto (präziser als der Video-Quad);
/// Fallbacks: der Live-Quad, zuletzt das unbeschnittene Vollbild.
enum Dewarper {

    private static let kontext = CIContext(options: [.cacheIntermediates: false])

    static func entzerre(_ foto: UIImage, liveQuad: Quad?) -> UIImage {
        let aufrecht = normalisiere(foto)
        guard let cg = aufrecht.cgImage else { return aufrecht }
        guard let quad = detektiere(cg) ?? liveQuad else { return aufrecht }

        let w = CGFloat(cg.width), h = CGFloat(cg.height)
        // Vision und CoreImage haben beide den Ursprung unten links —
        // normierte Punkte werden direkt skaliert, keine y-Spiegelung.
        let filter = CIFilter.perspectiveCorrection()
        filter.inputImage = CIImage(cgImage: cg)
        filter.topLeft = CGPoint(x: quad.topLeft.x * w, y: quad.topLeft.y * h)
        filter.topRight = CGPoint(x: quad.topRight.x * w, y: quad.topRight.y * h)
        filter.bottomRight = CGPoint(x: quad.bottomRight.x * w, y: quad.bottomRight.y * h)
        filter.bottomLeft = CGPoint(x: quad.bottomLeft.x * w, y: quad.bottomLeft.y * h)

        guard let ausgabe = filter.outputImage,
              !ausgabe.extent.isEmpty,
              let ergebnis = kontext.createCGImage(ausgabe, from: ausgabe.extent) else {
            return aufrecht
        }
        return UIImage(cgImage: ergebnis)
    }

    private static func detektiere(_ cg: CGImage) -> Quad? {
        let request = VNDetectDocumentSegmentationRequest()
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
        // Niedrigere Schwelle als im Live-Gate: die Entscheidung zur Aufnahme
        // ist gefallen, hier geht es nur noch um die besten Ecken.
        guard let o = request.results?.max(by: { $0.confidence < $1.confidence }),
              o.confidence >= 0.7 else { return nil }
        return Quad(topLeft: o.topLeft, topRight: o.topRight,
                    bottomRight: o.bottomRight, bottomLeft: o.bottomLeft)
    }

    /// EXIF-Orientierung einbrennen, damit Vision- und CI-Koordinaten stimmen.
    private static func normalisiere(_ bild: UIImage) -> UIImage {
        guard bild.imageOrientation != .up else { return bild }
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        return UIGraphicsImageRenderer(size: bild.size, format: format).image { _ in
            bild.draw(in: CGRect(origin: .zero, size: bild.size))
        }
    }
}
