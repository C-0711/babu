import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
}

/// Unlimited-OCR-Designsprache — identisch zu den --gc-*-Tokens der Web-App.
enum GC {
    // Hell und warm — kein neutrales Grau. Jeder dunkle Ton hat einen
    // Braunstich, damit die App nach Papier aussieht und nicht nach Formular.
    // Die Kontraste sind nachgerechnet (auf canvas): fg 13,9:1 · body 9,7:1 ·
    // desc 5,9:1 — alle über AA. `muted` liegt bei 3,5:1 und ist damit
    // besser lesbar als das frühere Grau (2,7:1), das AA schon riss.
    static let bg = Color(hex: 0xFFFFFF)
    static let canvas = Color(hex: 0xFDFCF9)
    static let desk = Color(hex: 0xF7F3EB)
    static let chrome = Color(hex: 0xFBF8F2)
    static let fg = Color(hex: 0x2E2A22)
    static let body = Color(hex: 0x4A4234)
    static let desc = Color(hex: 0x6B6151)
    static let muted = Color(hex: 0x8F8574)
    static let accent = Color(hex: 0x8A7C5C)
    static let accentHover = Color(hex: 0x736950)
    static let accentSubtle = Color(hex: 0xF7F1E6)
    static let ok = Color(hex: 0x6F8A6E)
    static let warn = Color(hex: 0xA8791C)
    static let danger = Color(hex: 0xA8433A)
    static let scan = Color(hex: 0x2A2620)
    static let gold = Color(hex: 0xB9A574)
    /// Feine Linien und Ränder — warm, nie grau.
    static let linie = Color(hex: 0xEBE4D8)
}

extension View {
    /// Listen und Formulare auf unsere warme Fläche stellen. iOS legt sonst
    /// sein eigenes Grau (#F2F2F7) darunter — das ist genau das Grau, das
    /// die App kühl aussehen lässt, egal wie warm die Schrift ist.
    func warmerGrund(_ farbe: Color = GC.canvas) -> some View {
        scrollContentBackground(.hidden).background(farbe.ignoresSafeArea())
    }
}

/// Confidence-Farbe wie im Web: ≥95 Bronze, ≥80 Grün, darunter Amber.
func confColor(_ c: Int) -> Color {
    if c >= 95 { return GC.accent }
    if c >= 80 { return GC.ok }
    return GC.warn
}

struct BadgeView: View {
    let text: String
    var color: Color = GC.muted

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 9, design: .monospaced))
            .kerning(0.5)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .overlay(Capsule().stroke(color.opacity(0.5), lineWidth: 1))
            .foregroundStyle(color)
    }
}

struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(16)
            .background(GC.bg, in: RoundedRectangle(cornerRadius: 14))
            .shadow(color: Color(hex: 0x1F1E1A).opacity(0.08), radius: 8, y: 3)
    }
}

extension View {
    func gcCard() -> some View { modifier(CardBackground()) }
}


/// Die Farbe zur Herkunft einer Angabe — an EINER Stelle, nicht in jeder
/// Ansicht neu ausgerechnet.
///
/// Sie war verkehrt herum: die Serverlesung bekam Warn-Orange, die Vermutung
/// des Geräts bekam Grün. Wer nur auf die Farbe schaut, hielt damit das
/// Unsicherste für das Sicherste. Das Modell (`Herkunft`) kennt keine Farben
/// — deshalb steht die Regel hier und nicht dort.
func herkunftsFarbe(_ h: Herkunft) -> Color {
    switch h {
    case .ki: return GC.ok          // vom Server gelesen — das gilt
    case .mensch: return GC.accent  // von Hand gesetzt — das gilt auch
    case .historie, .regel: return GC.muted   // vom Gerät geraten
    }
}
