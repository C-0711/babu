import UIKit

/// Bündelt die Seiten eines mehrseitigen Belegs zu EINEM PDF für den Upload.
///
/// Jede Seite behält ihr eigenes Format (entzerrte Fotos sind selten exakt
/// A4); die lange Kante wird auf 2200 px begrenzt — dieselbe Grenze wie beim
/// PDF-Import (CaptureTab.ladeDatei). Das PDF wird nicht gespeichert,
/// sondern beim Übertragen aus `Beleg.seitenJpeg` gebaut.
enum BelegBuendelPDF {

    static let maxKante: CGFloat = 2200

    static func bauen(seitenJpeg: [Data]) -> Data? {
        let seiten = seitenJpeg.compactMap { UIImage(data: $0) }
        guard !seiten.isEmpty else { return nil }
        // Die Bounds des Renderers sind nur der Startwert — beginPage(withBounds:)
        // setzt je Seite ihr eigenes Format.
        let renderer = UIGraphicsPDFRenderer(bounds: rechteck(fuer: seiten[0]))
        return renderer.pdfData { ctx in
            for seite in seiten {
                let feld = rechteck(fuer: seite)
                ctx.beginPage(withBounds: feld, pageInfo: [:])
                seite.draw(in: feld)
            }
        }
    }

    private static func rechteck(fuer bild: UIImage) -> CGRect {
        let px = CGSize(width: bild.size.width * bild.scale,
                        height: bild.size.height * bild.scale)
        let skala = min(1, maxKante / max(px.width, px.height, 1))
        return CGRect(x: 0, y: 0,
                      width: (px.width * skala).rounded(),
                      height: (px.height * skala).rounded())
    }
}
