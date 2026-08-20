import SwiftUI

/// Sucher-Overlay in der Unlimited-OCR-Designsprache: Eck-Marker statt Rahmen,
/// feine Konturlinie, die dem Beleg folgt, Klartext-Statuszeile, Torch-Toggle
/// und ein dezenter Fallback-Auslöser — der Happy Path löst automatisch aus.
struct CaptureOverlayView: View {
    @ObservedObject var model: CaptureViewModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GeometryReader { geo in
            ZStack {
                konturEbene(in: geo.size)
                EckMarkerView(zurueckgezogen: istErkannt)

                if let bild = model.eingefroren {
                    eingefrorenAnsicht(bild)
                }

                VStack(spacing: 0) {
                    kopfleiste
                    Spacer()
                    if model.eingefroren == nil {
                        LiveFieldsView(befund: model.liveFelder)
                            .padding(.bottom, 10)
                        statuszeile
                        ausloeser
                            .padding(.top, 14)
                            .padding(.bottom, 28)
                    }
                }
            }
        }
    }

    private var istErkannt: Bool {
        if case .erkannt = model.phase { return true }
        return model.phase == .ausgeloest
    }

    // MARK: - Kontur

    @ViewBuilder
    private func konturEbene(in groesse: CGSize) -> some View {
        if model.eingefroren == nil,
           let quad = model.anzeigeQuad,
           model.bufferGroesse != .zero {
            let punkte = quad.inView(groesse: groesse, buffer: model.bufferGroesse)
            let shape = KonturShape(p0: punkte[0], p1: punkte[1], p2: punkte[2], p3: punkte[3])

            shape.stroke(konturFarbe, lineWidth: 1.5)
                .animation(reduceMotion ? nil : .linear(duration: 0.08), value: punkte)

            if case .erkannt(let fortschritt) = model.phase {
                // Stabilitäts-Fortschritt als heller werdender Umlauf der Kontur.
                shape.trim(from: 0, to: fortschritt)
                    .stroke(GC.gold, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .animation(reduceMotion ? nil : .linear(duration: 0.1), value: fortschritt)
            }
            if model.phase == .ausgeloest {
                // Motion-Moment 1: die Kontur „rastet ein".
                shape.stroke(.white.opacity(0.85), lineWidth: 3)
                    .transition(.opacity)
            }
        }
    }

    private var konturFarbe: Color {
        switch model.phase {
        case .erkannt, .ausgeloest: return GC.gold
        default: return GC.gold.opacity(0.45)
        }
    }

    // MARK: - Snap-Moment

    private func eingefrorenAnsicht(_ bild: UIImage) -> some View {
        ZStack {
            GC.scan.ignoresSafeArea()
            Image(uiImage: bild)
                .resizable()
                .scaledToFit()
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .shadow(color: .black.opacity(0.5), radius: 18, y: 8)
                .padding(28)
        }
        .transition(reduceMotion
            ? .opacity
            : .scale(scale: 1.04).combined(with: .opacity))
    }

    // MARK: - Bedienelemente

    private var kopfleiste: some View {
        HStack {
            rundKnopf(symbol: "xmark", label: "Abbrechen") { model.abbrechen() }
            Spacer()
            if model.eingefroren == nil {
                rundKnopf(symbol: model.torchAn ? "bolt.fill" : "bolt.slash",
                          label: model.torchAn ? "Licht ausschalten" : "Licht einschalten",
                          tint: model.torchAn ? GC.gold : .white) {
                    model.torchUmschalten()
                }
                .symbolEffect(.pulse, isActive: model.phase == .zuDunkel && !model.torchAn)
            }
        }
        .padding(.horizontal, 18)
        .padding(.top, 10)
    }

    private func rundKnopf(symbol: String, label: String,
                           tint: Color = .white, aktion: @escaping () -> Void) -> some View {
        Button(action: aktion) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(tint)
                .frame(width: 44, height: 44)
                .background(GC.scan.opacity(0.55), in: Circle())
        }
        .accessibilityLabel(label)
    }

    private var statuszeile: some View {
        Text(model.statusText)
            .font(.footnote)
            .foregroundStyle(.white.opacity(0.75))
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(GC.scan.opacity(0.55), in: Capsule())
            .opacity(model.statusText.isEmpty ? 0 : 1)
            .animation(.easeInOut(duration: 0.2), value: model.statusText)
    }

    /// Fallback-Auslöser: bewusst nur ein dünner Ring — dem Auto-Capture
    /// untergeordnet, aber immer erreichbar (umgeht alle Gates).
    private var ausloeser: some View {
        Button {
            model.manuellAusloesen()
        } label: {
            Circle()
                .strokeBorder(.white.opacity(0.35), lineWidth: 2)
                .frame(width: 56, height: 56)
        }
        .accessibilityLabel("Auslöser")
    }
}

// MARK: - Kontur-Shape

/// Geschlossenes Viereck mit animierbaren Eckpunkten (Punkte in View-Koordinaten).
struct KonturShape: Shape {
    var p0: CGPoint
    var p1: CGPoint
    var p2: CGPoint
    var p3: CGPoint

    var animatableData: AnimatablePair<
        AnimatablePair<CGPoint.AnimatableData, CGPoint.AnimatableData>,
        AnimatablePair<CGPoint.AnimatableData, CGPoint.AnimatableData>
    > {
        get {
            AnimatablePair(AnimatablePair(p0.animatableData, p1.animatableData),
                           AnimatablePair(p2.animatableData, p3.animatableData))
        }
        set {
            p0.animatableData = newValue.first.first
            p1.animatableData = newValue.first.second
            p2.animatableData = newValue.second.first
            p3.animatableData = newValue.second.second
        }
    }

    func path(in rect: CGRect) -> Path {
        var pfad = Path()
        pfad.move(to: p0)
        pfad.addLine(to: p1)
        pfad.addLine(to: p2)
        pfad.addLine(to: p3)
        pfad.closeSubpath()
        return pfad
    }
}

// MARK: - Eck-Marker

/// Vier dezente L-Marker um den Zielbereich — sie weichen zurück, sobald die
/// Kontur den Beleg übernommen hat.
struct EckMarkerView: View {
    let zurueckgezogen: Bool

    var body: some View {
        GeometryReader { geo in
            let rahmen = CGRect(x: geo.size.width * 0.14,
                                y: geo.size.height * 0.18,
                                width: geo.size.width * 0.72,
                                height: geo.size.height * 0.52)
            Path { p in
                let laenge: CGFloat = 22
                // oben links
                p.move(to: CGPoint(x: rahmen.minX, y: rahmen.minY + laenge))
                p.addLine(to: CGPoint(x: rahmen.minX, y: rahmen.minY))
                p.addLine(to: CGPoint(x: rahmen.minX + laenge, y: rahmen.minY))
                // oben rechts
                p.move(to: CGPoint(x: rahmen.maxX - laenge, y: rahmen.minY))
                p.addLine(to: CGPoint(x: rahmen.maxX, y: rahmen.minY))
                p.addLine(to: CGPoint(x: rahmen.maxX, y: rahmen.minY + laenge))
                // unten rechts
                p.move(to: CGPoint(x: rahmen.maxX, y: rahmen.maxY - laenge))
                p.addLine(to: CGPoint(x: rahmen.maxX, y: rahmen.maxY))
                p.addLine(to: CGPoint(x: rahmen.maxX - laenge, y: rahmen.maxY))
                // unten links
                p.move(to: CGPoint(x: rahmen.minX + laenge, y: rahmen.maxY))
                p.addLine(to: CGPoint(x: rahmen.minX, y: rahmen.maxY))
                p.addLine(to: CGPoint(x: rahmen.minX, y: rahmen.maxY - laenge))
            }
            .stroke(GC.gold.opacity(0.6), lineWidth: 1.5)
        }
        .opacity(zurueckgezogen ? 0.15 : 1)
        .animation(.easeOut(duration: 0.25), value: zurueckgezogen)
        .allowsHitTesting(false)
    }
}

// MARK: - Koordinaten

extension Quad {
    /// Normierte Vision-Koordinaten (y von unten) → View-Punkte unter
    /// aspectFill-Beschnitt der Vorschau.
    func inView(groesse: CGSize, buffer: CGSize) -> [CGPoint] {
        guard buffer.width > 0, buffer.height > 0 else { return ecken }
        let skala = max(groesse.width / buffer.width, groesse.height / buffer.height)
        let versatzX = (groesse.width - buffer.width * skala) / 2
        let versatzY = (groesse.height - buffer.height * skala) / 2
        return ecken.map { p in
            CGPoint(x: p.x * buffer.width * skala + versatzX,
                    y: (1 - p.y) * buffer.height * skala + versatzY)
        }
    }
}
