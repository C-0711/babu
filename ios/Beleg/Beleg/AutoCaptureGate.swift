import Foundation
import CoreGraphics

// MARK: - Geometrie

/// Beleg-Viereck in normierten Vision-Koordinaten (Ursprung unten links, y nach oben).
struct Quad: Equatable {
    var topLeft: CGPoint
    var topRight: CGPoint
    var bottomRight: CGPoint
    var bottomLeft: CGPoint

    var ecken: [CGPoint] { [topLeft, topRight, bottomRight, bottomLeft] }

    /// Fläche nach Shoelace — in normierten Koordinaten direkt der Anteil am Frame.
    var flaeche: CGFloat {
        let p = ecken
        var summe: CGFloat = 0
        for i in 0..<4 {
            let a = p[i], b = p[(i + 1) % 4]
            summe += a.x * b.y - b.x * a.y
        }
        return abs(summe) / 2
    }

    /// Skaliert x mit dem Buffer-Seitenverhältnis (Breite/Höhe), damit Winkel
    /// und Abstände der echten Bildgeometrie entsprechen.
    func metrisch(aspekt: CGFloat) -> Quad {
        func s(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x * aspekt, y: p.y) }
        return Quad(topLeft: s(topLeft), topRight: s(topRight),
                    bottomRight: s(bottomRight), bottomLeft: s(bottomLeft))
    }

    /// Seitenverhältnis Höhe/Breite (Mittel der gegenüberliegenden Kanten).
    var hoeheZuBreite: CGFloat {
        let breite = (abstand(topLeft, topRight) + abstand(bottomLeft, bottomRight)) / 2
        let hoehe = (abstand(topLeft, bottomLeft) + abstand(topRight, bottomRight)) / 2
        guard breite > 0.0001 else { return 0 }
        return hoehe / breite
    }

    /// Konvex und alle Innenwinkel im Toleranzband um 90°?
    var istPlausibelRechteckig: Bool {
        let p = ecken
        var vorzeichen: CGFloat = 0
        for i in 0..<4 {
            let vor = p[(i + 3) % 4], ecke = p[i], nach = p[(i + 1) % 4]
            let v1 = CGVector(dx: vor.x - ecke.x, dy: vor.y - ecke.y)
            let v2 = CGVector(dx: nach.x - ecke.x, dy: nach.y - ecke.y)
            let kreuz = v1.dx * v2.dy - v1.dy * v2.dx
            if i == 0 { vorzeichen = kreuz }
            if kreuz * vorzeichen < 0 { return false }   // nicht konvex
            let punktP = v1.dx * v2.dx + v1.dy * v2.dy
            let winkel = abs(atan2(kreuz, punktP)) * 180 / .pi
            if abs(winkel - 90) > CaptureTuning.eckwinkelToleranz { return false }
        }
        return true
    }

    /// Größte Eckenbewegung gegenüber einem Referenz-Quad.
    func maxEckenAbstand(zu anderes: Quad) -> CGFloat {
        zip(ecken, anderes.ecken).map { abstand($0, $1) }.max() ?? 0
    }

    /// Linear gemischt (EMA-Schritt): `anteil` = Gewicht des neuen Quads.
    func gemischt(mit neu: Quad, anteil: CGFloat) -> Quad {
        func mix(_ a: CGPoint, _ b: CGPoint) -> CGPoint {
            CGPoint(x: a.x + (b.x - a.x) * anteil, y: a.y + (b.y - a.y) * anteil)
        }
        return Quad(topLeft: mix(topLeft, neu.topLeft),
                    topRight: mix(topRight, neu.topRight),
                    bottomRight: mix(bottomRight, neu.bottomRight),
                    bottomLeft: mix(bottomLeft, neu.bottomLeft))
    }

    /// Mittelpunkt, umgerechnet in Oben-links-Koordinaten (für Belichtungspunkt).
    var zentrumObenLinks: CGPoint {
        let mx = ecken.map { $0.x }.reduce(0, +) / 4
        let my = ecken.map { $0.y }.reduce(0, +) / 4
        return CGPoint(x: mx, y: 1 - my)
    }

    static func diagonale(aspekt: CGFloat) -> CGFloat { sqrt(aspekt * aspekt + 1) }

    private func abstand(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        hypot(a.x - b.x, a.y - b.y)
    }
}

// MARK: - Beobachtungen

/// Ergebnis einer Frame-Analyse (Detektion + Luma-Metriken vom Y-Plane).
struct BelegBeobachtung {
    var quad: Quad?
    var confidence: Double = 0
    var szeneLuma: Double = 0     // Mittelwert ganzes Bild, 0–1
    var quadLuma: Double = 0      // Mittelwert innerhalb der Quad-Bounding-Box
    var clipAnteil: Double = 0    // Anteil Pixel > 250 innerhalb des Quads
    var bufferBreite: Int = 0
    var bufferHoehe: Int = 0
    var zeit = Date()
}

/// Befund der Live-OCR im Sucher: entprellte Anzeige-Felder + rohe Signale fürs Gate.
struct LiveTextBefund: Equatable {
    var brutto: Double?
    var datumText: String?
    var belegNr: String?
    var zeilenZahl: Int = 0
    var hatBelegSignal = false    // deutscher Betrag oder Datum im Text
    var zeit = Date()

    var hatAnzeige: Bool { brutto != nil || datumText != nil || belegNr != nil }
}

// MARK: - Zustände & Konstanten

enum CapturePhase: Equatable {
    case suchen
    case kandidat(hinweis: String)
    case zuDunkel
    case blendung
    case erkannt(fortschritt: Double)   // 0–1 über das Stabilitätsfenster
    case ausgeloest
}

/// Startwerte — am Gerät zu justieren (Testplan im Bauplan-Dokument).
enum CaptureTuning {
    static let minConfidence = 0.85
    static let fuellMin: CGFloat = 0.20
    static let fuellMax: CGFloat = 0.90
    static let seitenMin: CGFloat = 1.05      // Höhe/Breite: Beleg hochkant
    static let seitenMax: CGFloat = 6.0       // sehr langer Bon
    static let eckwinkelToleranz: CGFloat = 35
    static let stabilFrames = 8               // ~0,6–0,8 s bei 10–15 Hz Analyse
    static let maxEckenDrift: CGFloat = 0.018 // Anteil der Frame-Diagonale
    static let gnadenFrames = 2               // kurze Aussetzer resetten nicht
    static let lumaMin = 0.15
    static let clipMax = 0.08
    static let clipMaxTorch = 0.12            // Torch wirft Spekular-Highlights
    static let screenLumaFaktor = 2.5         // Quad strahlt heller als Umfeld …
    static let screenUmfeldMax = 0.25         // … nur verdächtig bei dunklem Umfeld
    static let ocrMinZeilen = 3
    static let ocrBefundMaxAlter: TimeInterval = 1.2
    static let nachAbbruchSperre: TimeInterval = 1.0
    static let liveOcrIntervall: TimeInterval = 0.7
}

// MARK: - Zustandsmaschine

/// Auto-Auslöse-Logik: rein, deterministisch, ohne UIKit/AVFoundation —
/// mit synthetischen `BelegBeobachtung`-Sequenzen ohne Kamera testbar.
/// Auto-Fire nur, wenn ALLE Gates halten; der manuelle Auslöser umgeht sie.
struct AutoCaptureGate {
    private(set) var phase: CapturePhase = .suchen
    private var stabil = 0
    private var gnade = 0
    private var referenzQuad: Quad?     // Roh-Quad des letzten Frames (Drift-Maß)
    private var gesperrtBis = Date.distantPast

    /// Nach Fehlschlag/Abbruch: kurz sperren, damit nichts doppelt auslöst.
    mutating func sperren(fuer dauer: TimeInterval, ab zeit: Date = Date()) {
        gesperrtBis = zeit.addingTimeInterval(dauer)
        stabil = 0; gnade = 0; referenzQuad = nil
        phase = .suchen
    }

    mutating func verarbeite(_ b: BelegBeobachtung,
                             liveText: LiveTextBefund?,
                             torchAn: Bool) -> CapturePhase {
        if phase == .ausgeloest { return phase }   // wartet auf expliziten Reset
        if b.zeit < gesperrtBis { phase = .suchen; return phase }

        // Zu dunkel geht vor — ohne Licht ist auch die Detektion unzuverlässig.
        if b.szeneLuma < CaptureTuning.lumaMin {
            verliereStabilitaet()
            phase = .zuDunkel
            return phase
        }

        // Gate 1: Detektion + Confidence (mit Gnaden-Frames gegen kurze Aussetzer).
        guard let quad = b.quad, b.confidence >= CaptureTuning.minConfidence else {
            if gnade < CaptureTuning.gnadenFrames, referenzQuad != nil {
                gnade += 1
                return phase
            }
            stabil = 0; gnade = 0; referenzQuad = nil
            phase = .suchen
            return phase
        }
        gnade = 0

        let aspekt = b.bufferHoehe > 0
            ? CGFloat(b.bufferBreite) / CGFloat(b.bufferHoehe) : 1
        let metrisch = quad.metrisch(aspekt: aspekt)

        // Gates 2–4: Füllgrad, Hochformat, Geometrie → Hinweis statt Auslösung.
        var hinweis: String?
        if quad.flaeche < CaptureTuning.fuellMin {
            hinweis = "Näher heranhalten"
        } else if quad.flaeche > CaptureTuning.fuellMax {
            hinweis = "Ganzen Beleg ins Bild nehmen"
        } else if !(CaptureTuning.seitenMin...CaptureTuning.seitenMax)
            .contains(metrisch.hoeheZuBreite) {
            hinweis = "Beleg hochkant ins Bild nehmen"
        } else if !metrisch.istPlausibelRechteckig {
            hinweis = "Beleg flach und vollständig ins Bild nehmen"
        }
        if let hinweis {
            verliereStabilitaet()
            phase = .kandidat(hinweis: hinweis)
            return phase
        }

        // Gate 6: Blendung (nur innerhalb eines Quads sinnvoll messbar).
        let clipMax = torchAn ? CaptureTuning.clipMaxTorch : CaptureTuning.clipMax
        if b.clipAnteil > clipMax {
            verliereStabilitaet()
            phase = .blendung
            return phase
        }

        // Gate 7: Emissiv-Heuristik — ein leuchtender Bildschirm strahlt deutlich
        // heller als sein Umfeld; Papier reflektiert nur.
        if b.quadLuma >= CaptureTuning.screenLumaFaktor * b.szeneLuma,
           b.szeneLuma <= CaptureTuning.screenUmfeldMax {
            verliereStabilitaet()
            phase = .kandidat(hinweis: "Bildschirm erkannt — zum Aufnehmen Auslöser tippen")
            return phase
        }

        // Gate 5: Stabilität über aufeinanderfolgende Frames.
        if let ref = referenzQuad {
            let drift = metrisch.maxEckenAbstand(zu: ref.metrisch(aspekt: aspekt))
                / Quad.diagonale(aspekt: aspekt)
            stabil = drift <= CaptureTuning.maxEckenDrift ? stabil + 1 : 0
        }
        referenzQuad = quad

        guard stabil >= CaptureTuning.stabilFrames else {
            phase = .erkannt(fortschritt: Double(stabil) / Double(CaptureTuning.stabilFrames))
            return phase
        }

        // Gate 8: Content — der jüngste Fast-OCR-Befund muss frisch sein und
        // nach Beleg aussehen. Ein Rechnungs-PDF am Bildschirm passiert bewusst.
        guard let text = liveText,
              b.zeit.timeIntervalSince(text.zeit) <= CaptureTuning.ocrBefundMaxAlter else {
            phase = .erkannt(fortschritt: 0.9)   // stabil — auf frische OCR warten
            return phase
        }
        if text.zeilenZahl >= CaptureTuning.ocrMinZeilen, text.hatBelegSignal {
            phase = .ausgeloest
        } else {
            phase = .kandidat(hinweis: "Kein Belegtext erkennbar — zum Aufnehmen Auslöser tippen")
        }
        return phase
    }

    private mutating func verliereStabilitaet() {
        stabil = 0
        referenzQuad = nil
    }
}
