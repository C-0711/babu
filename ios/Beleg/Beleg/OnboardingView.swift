import SwiftUI

/// Erster Bildschirm: erklärt in drei Sätzen, was die App tut — keine
/// Kontenrahmen-Entscheidung, kein Fachvokabular. SKR04 bleibt der
/// stille Standard (`store.skr`); wer das ändern muss, macht es später
/// mit dem Steuerbüro.
struct OnboardingView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Spacer()

            Text("Beleg")
                .font(.system(size: 34, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)

            Text("Fotografier deine Belege einfach zwischen zwei Terminen — den Rest erledigt die App.")
                .font(.subheadline)
                .foregroundStyle(GC.desc)

            VStack(alignment: .leading, spacing: 14) {
                punkt("viewfinder", "Beleg in den Rahmen halten — das Foto passiert von selbst.")
                punkt("checkmark.seal", "Jeder Beleg wird gelesen, eingeordnet und noch einmal gegengeprüft. Grüner Haken = alles gut.")
                punkt("square.and.arrow.up", "Dein Steuerbüro bekommt am Monatsende einen fertigen Stapel.")
            }
            .padding(.top, 8)

            Spacer()

            Button {
                store.onboarded = true
            } label: {
                Text("Los geht's")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.bottom, 18)
        }
        .padding(.horizontal, 24)
        .background(GC.canvas.ignoresSafeArea())
    }

    private func punkt(_ symbol: String, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: symbol)
                .font(.body)
                .foregroundStyle(GC.accent)
                .frame(width: 26)
            Text(text)
                .font(.footnote)
                .foregroundStyle(GC.body)
        }
    }
}
