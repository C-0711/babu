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
    static let bg = Color(hex: 0xFFFFFF)
    static let canvas = Color(hex: 0xFAF9F5)
    static let desk = Color(hex: 0xEFECE6)
    static let chrome = Color(hex: 0xF4F1EC)
    static let fg = Color(hex: 0x111111)
    static let body = Color(hex: 0x333333)
    static let desc = Color(hex: 0x555555)
    static let muted = Color(hex: 0x999999)
    static let accent = Color(hex: 0x857B61)
    static let accentHover = Color(hex: 0x736950)
    static let accentSubtle = Color(hex: 0xF0EBE3)
    static let ok = Color(hex: 0x6F8A6E)
    static let warn = Color(hex: 0xB0821F)
    static let danger = Color(hex: 0xA8433A)
    static let scan = Color(hex: 0x1F1E1A)
    static let gold = Color(hex: 0xC9B98D)
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
