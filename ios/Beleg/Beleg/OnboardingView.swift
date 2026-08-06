import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var store: AppStore
    @State private var skr = "SKR04"

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("0711 INTELLIGENCE · MANDANTEN-EINRICHTUNG")
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.2)
                .foregroundStyle(GC.accent)
                .padding(.top, 28)

            Text("Beleg")
                .font(.system(size: 34, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)

            Text("Belege erfassen, automatisch kontieren, GoBD-konform siegeln, an DATEV übergeben. Eine Angabe genügt zum Start.")
                .font(.subheadline)
                .foregroundStyle(GC.desc)

            VStack(spacing: 12) {
                skrKarte("SKR03", "Prozessgegliedert — folgt dem Ablauf des Geschäftsprozesses. Verbreitet bei Handel & Handwerk.")
                skrKarte("SKR04", "Abschlussgegliedert — folgt Bilanz- und GuV-Struktur. Standard bei Kapitalgesellschaften.")
            }
            .padding(.top, 8)

            Text("Unsicher? Ihr Steuerberater weiß es sofort — die Angabe steht im DATEV-Mandantenstammblatt.")
                .font(.caption)
                .foregroundStyle(GC.muted)
                .padding(.leading, 10)
                .overlay(alignment: .leading) {
                    Rectangle().fill(GC.desk).frame(width: 2)
                }

            Spacer()

            Button {
                store.skr = skr
                store.onboarded = true
            } label: {
                Text("Demo-Mandant laden & starten")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.bottom, 18)
        }
        .padding(.horizontal, 24)
        .background(GC.canvas.ignoresSafeArea())
    }

    private func skrKarte(_ name: String, _ text: String) -> some View {
        Button {
            skr = name
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                Text(name)
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                    .foregroundStyle(GC.fg)
                Text(text)
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(skr == name ? GC.accentSubtle : GC.bg,
                        in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14)
                .stroke(skr == name ? GC.accent : Color(hex: 0xEFEFEF), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}
