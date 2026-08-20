import AVFoundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins

/// Analysiert die Video-Frames: Dokument-Segmentierung (dasselbe ML-Modell, das
/// VisionKit nutzt) + billige Luma-Metriken direkt auf dem Y-Plane. Läuft synchron
/// im Delegate-Callback auf der videoDataQueue — verspätete Frames verwirft die
/// Output-Konfiguration, dadurch pendelt sich die Analyse-Rate von selbst ein.
final class DocumentDetector: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {

    /// Wird auf der videoDataQueue aufgerufen — Empfänger hüpft selbst auf @MainActor.
    var onBeobachtung: ((BelegBeobachtung) -> Void)?
    /// Entzerrter Quad-Ausschnitt für die Live-OCR, gedrosselt auf das OCR-Intervall.
    var onCrop: ((CGImage) -> Void)?

    private let ciContext = CIContext(options: [.cacheIntermediates: false])
    private var letzterCrop = Date.distantPast

    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let request = VNDetectDocumentSegmentationRequest()
        try? VNImageRequestHandler(cvPixelBuffer: pixelBuffer, options: [:]).perform([request])
        let beobachtung = request.results?.max { $0.confidence < $1.confidence }

        var quad: Quad?
        var confidence = 0.0
        if let o = beobachtung {
            quad = Quad(topLeft: o.topLeft, topRight: o.topRight,
                        bottomRight: o.bottomRight, bottomLeft: o.bottomLeft)
            confidence = Double(o.confidence)
        }

        let (szene, quadLuma, clip) = lumaMetriken(pixelBuffer, quad: quad)
        var b = BelegBeobachtung(quad: quad, confidence: confidence,
                                 szeneLuma: szene, quadLuma: quadLuma, clipAnteil: clip)
        b.bufferBreite = CVPixelBufferGetWidth(pixelBuffer)
        b.bufferHoehe = CVPixelBufferGetHeight(pixelBuffer)
        onBeobachtung?(b)

        // Crop für die Live-OCR: klein gerendert, damit der SampleBuffer sofort
        // frei wird und die OCR nie den Live-PixelBuffer anfasst.
        if let quad, confidence >= CaptureTuning.minConfidence,
           Date().timeIntervalSince(letzterCrop) >= CaptureTuning.liveOcrIntervall,
           let crop = erzeugeCrop(pixelBuffer, quad: quad) {
            letzterCrop = Date()
            onCrop?(crop)
        }
    }

    // MARK: - Luma-Metriken (Y-Plane, 8×8-Downsample)

    private func lumaMetriken(_ pb: CVPixelBuffer, quad: Quad?) -> (Double, Double, Double) {
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
        guard let basis = CVPixelBufferGetBaseAddressOfPlane(pb, 0) else { return (0, 0, 0) }

        let breite = CVPixelBufferGetWidthOfPlane(pb, 0)
        let hoehe = CVPixelBufferGetHeightOfPlane(pb, 0)
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pb, 0)
        let ptr = basis.assumingMemoryBound(to: UInt8.self)
        let schritt = 8

        // Quad-Bounding-Box in Pixel (Zeile 0 = oben; Vision-y zählt von unten).
        // Die Box genügt als Näherung für Mittelwert und Clip-Anteil.
        var qx0 = 0, qx1 = -1, qy0 = 0, qy1 = -1
        if let q = quad {
            let xs = q.ecken.map(\.x), ys = q.ecken.map(\.y)
            qx0 = max(0, Int(xs.min()! * CGFloat(breite)))
            qx1 = min(breite - 1, Int(xs.max()! * CGFloat(breite)))
            qy0 = max(0, Int((1 - ys.max()!) * CGFloat(hoehe)))
            qy1 = min(hoehe - 1, Int((1 - ys.min()!) * CGFloat(hoehe)))
        }

        var szeneSumme = 0, szeneN = 0
        var quadSumme = 0, quadN = 0, clipN = 0
        var y = 0
        while y < hoehe {
            let zeile = ptr + y * stride
            var x = 0
            while x < breite {
                let wert = Int(zeile[x])
                szeneSumme += wert; szeneN += 1
                if y >= qy0, y <= qy1, x >= qx0, x <= qx1 {
                    quadSumme += wert; quadN += 1
                    if wert > 250 { clipN += 1 }
                }
                x += schritt
            }
            y += schritt
        }

        let szene = szeneN > 0 ? Double(szeneSumme) / Double(szeneN) / 255 : 0
        let quadLuma = quadN > 0 ? Double(quadSumme) / Double(quadN) / 255 : szene
        let clip = quadN > 0 ? Double(clipN) / Double(quadN) : 0
        return (szene, quadLuma, clip)
    }

    // MARK: - OCR-Crop

    private func erzeugeCrop(_ pb: CVPixelBuffer, quad: Quad) -> CGImage? {
        let ci = CIImage(cvPixelBuffer: pb)
        let w = ci.extent.width, h = ci.extent.height

        // CoreImage hat wie Vision den Ursprung unten links → direkt skalieren.
        let filter = CIFilter.perspectiveCorrection()
        filter.inputImage = ci
        filter.topLeft = CGPoint(x: quad.topLeft.x * w, y: quad.topLeft.y * h)
        filter.topRight = CGPoint(x: quad.topRight.x * w, y: quad.topRight.y * h)
        filter.bottomRight = CGPoint(x: quad.bottomRight.x * w, y: quad.bottomRight.y * h)
        filter.bottomLeft = CGPoint(x: quad.bottomLeft.x * w, y: quad.bottomLeft.y * h)
        guard var ausgabe = filter.outputImage else { return nil }

        let langeKante = max(ausgabe.extent.width, ausgabe.extent.height)
        if langeKante > 1280 {
            let s = 1280 / langeKante
            ausgabe = ausgabe.transformed(by: CGAffineTransform(scaleX: s, y: s))
        }
        return ciContext.createCGImage(ausgabe, from: ausgabe.extent)
    }
}
