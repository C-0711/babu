import Foundation
import CoreGraphics

/// Findet die Bildpositionen der gelesenen Kernfelder — für die grünen
/// Markierungen auf dem Beleg-Foto nach der Aufnahme. Die Rechtecke sind
/// Vision-normiert (Ursprung unten links); die View spiegelt y beim Zeichnen.
enum FeldMarker {

    static func markierungen(zeilen: [OCRService.Ergebnis.Zeile], felder: Felder) -> [CGRect] {
        var rects: [CGRect] = []
        func merke(_ box: CGRect?) {
            guard let box, !rects.contains(where: { abs($0.midY - box.midY) < 0.005
                && abs($0.midX - box.midX) < 0.005 }) else { return }
            rects.append(box)
        }

        // Lieferant: die Zeile, die der Parser gewählt hat.
        if let l = felder.lieferant {
            merke(zeilen.first { $0.text.trimmingCharacters(in: .whitespaces) == l }?.box)
        }
        // Datum und Beleg-Nr.: erste Zeile, die den Wert enthält.
        if let d = felder.datumText {
            merke(zeilen.first { $0.text.contains(d) }?.box)
        }
        if let n = felder.belegNr, n.count >= 3 {
            merke(zeilen.first { $0.text.contains(n) }?.box)
        }
        // Brutto: LETZTE Zeile mit dem Betrag — die Summe steht auf Bons unten,
        // gleiche Beträge weiter oben sind meist Positionszeilen.
        if let b = felder.brutto {
            let mitPunkt = fmtBetrag(b)                                        // "1.234,56"
            let ohnePunkt = mitPunkt.replacingOccurrences(of: ".", with: "")   // "1234,56"
            merke(zeilen.last { $0.text.contains(mitPunkt) || $0.text.contains(ohnePunkt) }?.box)
        }
        return rects
    }

    /// Variante für gespeicherte Belege (Detail-Ansicht): baut die Feldwerte
    /// aus dem Beleg zusammen und markiert dieselben Stellen.
    static func markierungen(zeilen: [OCRService.Ergebnis.Zeile], beleg: Beleg) -> [CGRect] {
        var f = Felder()
        f.lieferant = beleg.lieferant
        f.belegNr = beleg.belegNr == "ohne Nr." ? nil : beleg.belegNr
        f.datumText = beleg.datumText
        f.brutto = beleg.brutto > 0 ? beleg.brutto : nil
        return markierungen(zeilen: zeilen, felder: f)
    }
}
