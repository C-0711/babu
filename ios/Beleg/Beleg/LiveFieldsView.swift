import SwiftUI

/// „Instant Reading im Sucher": erkannte Werte als Kapsel-Chips über der
/// Statuszeile — Mono-Ziffern, Gold-Labels, analog zur `BadgeView`-Optik.
struct LiveFieldsView: View {
    let befund: LiveTextBefund?

    private var anzeige: [(label: String, wert: String)] {
        guard let b = befund else { return [] }
        var chips: [(String, String)] = []
        if let brutto = b.brutto { chips.append(("BRUTTO", fmtEur(brutto))) }
        if let datum = b.datumText { chips.append(("DATUM", datum)) }
        if let nr = b.belegNr { chips.append(("RE-NR", nr)) }
        return chips
    }

    var body: some View {
        HStack(spacing: 8) {
            ForEach(anzeige, id: \.label) { chip in
                HStack(spacing: 5) {
                    Text(chip.label)
                        .font(.system(size: 9, design: .monospaced))
                        .kerning(0.5)
                        .foregroundStyle(GC.gold.opacity(0.7))
                    Text(chip.wert)
                        .font(.caption.monospaced())
                        .foregroundStyle(.white)
                }
                .padding(.horizontal, 9)
                .padding(.vertical, 4)
                .background(GC.scan.opacity(0.75), in: Capsule())
                .overlay(Capsule().stroke(GC.accent.opacity(0.5), lineWidth: 1))
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: anzeige.map(\.wert))
    }
}
