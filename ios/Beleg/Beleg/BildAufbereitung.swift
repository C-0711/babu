import UIKit
import CoreImage
import CoreImage.CIFilterBuiltins

/// Aus dem Kamera-Foto ein Dokument machen: Schatten anheben, Papier
/// aufhellen, Kontrast und Schärfe für Druck/Thermodruck. Das Original
/// bleibt unangetastet im Archiv (GoBD) — aufbereitet wird nur die
/// Anzeige- und OCR-Fassung.
enum BildAufbereitung {

    private static let context = CIContext()

    static func aufbereiten(_ image: UIImage) -> UIImage {
        guard let input = CIImage(image: image) else { return image }
        var img = input

        // Schatten (Hand, Tischkante) anheben, Lichter halten
        let shadow = CIFilter.highlightShadowAdjust()
        shadow.inputImage = img
        shadow.shadowAmount = 0.45
        shadow.highlightAmount = 1.0
        img = shadow.outputImage ?? img

        // Papier Richtung Weiß, Druck Richtung Schwarz
        let cc = CIFilter.colorControls()
        cc.inputImage = img
        cc.saturation = 0.82
        cc.contrast = 1.18
        cc.brightness = 0.06
        img = cc.outputImage ?? img

        let gamma = CIFilter.gammaAdjust()
        gamma.inputImage = img
        gamma.power = 0.88
        img = gamma.outputImage ?? img

        // Blassen Thermodruck nachschärfen
        let sharp = CIFilter.unsharpMask()
        sharp.inputImage = img
        sharp.radius = 1.6
        sharp.intensity = 0.5
        img = sharp.outputImage ?? img

        guard let cg = context.createCGImage(img, from: img.extent) else { return image }
        return UIImage(cgImage: cg, scale: image.scale, orientation: image.imageOrientation)
    }
}
