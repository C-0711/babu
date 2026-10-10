import SwiftUI
import UIKit

/// Erster Bildschirm: erklärt in drei Sätzen, was die App tut — keine
/// Kontenrahmen-Entscheidung, kein Fachvokabular. SKR04 bleibt der
/// stille Standard (`store.skr`); wer das ändern muss, macht es später
/// mit dem Steuerbüro.
struct OnboardingView: View {
    @EnvironmentObject var store: AppStore
    /// Was schiefging beim Anlegen des Kontos. Ohne Konto gibt es keine
    /// Ablage, deshalb steht es hier und nicht in einer Einstellung.
    @State private var fehler: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Spacer()

            // „babu" oder „babu Pro" — dieselbe Begrüßung, der richtige Name.
            Text(Ausbaustufe.name)
                .font(.system(size: 34, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)

            Text("Fotografier deine Belege einfach zwischen zwei Terminen — den Rest erledigt die App.")
                .font(.subheadline)
                .foregroundStyle(GC.desc)

            VStack(alignment: .leading, spacing: 14) {
                punkt("viewfinder", "Beleg in den Rahmen halten — das Foto passiert von selbst.")
                punkt("checkmark.seal", "Jeder Beleg wird gelesen, eingeordnet und noch einmal gegengeprüft. Grüner Haken = alles gut.")
                punkt("square.and.arrow.up", "Am Monatsende ist deine Buchhaltung fertig — ganz ohne eigenes Steuerbüro.")
            }
            .padding(.top, 8)

            Spacer()

            Button {
                losgehen()
            } label: {
                Text("Los geht's")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)

            // Die zehn freien Belege gehören auf diese Seite: Wer „Los
            // geht's" drückt, soll vorher wissen, dass nichts kostet und
            // nichts gefragt wird. Kein Konto, keine E-Mail, kein Passwort.
            Text("Die ersten \(PlatzStand.belegeFrei) Belege sind frei — ohne "
                 + "Anmeldung, ohne E-Mail.")
                .font(.caption)
                .foregroundStyle(GC.desc)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.bottom, 18)
        }
        .padding(.horizontal, 24)
        .background(GC.canvas.ignoresSafeArea())
        .alert("Das hat nicht geklappt", isPresented: .init(
            get: { fehler != nil }, set: { if !$0 { fehler = nil } })) {
            Button("Noch einmal") { losgehen() }
            Button("Erst mal ohne", role: .cancel) {
                // Ohne Konto kann sie fotografieren; die Belege bleiben auf
                // dem Telefon und gehen los, sobald eine Ablage da ist. Das
                // ist derselbe Zustand wie bei einem Konto ohne Box — die
                // App kennt ihn und hält die Belege.
                store.onboarded = true
            }
        } message: {
            Text(fehler ?? "")
        }
    }

    /// Konto anlegen und los. Ein Telefon, das babu gerade geladen hat,
    /// bekommt hier seinen Zugang — ohne Anmeldung (seit 10.10.2026).
    /// Wer schon verbunden ist (Link aus der Mail, früheres Gerät), legt
    /// kein zweites Konto an.
    private func losgehen() {
        fehler = nil
        guard store.verbundenAls == nil, KeychainHelfer.ladePAT() == nil else {
            store.onboarded = true
            return
        }
        Task {
            if let grund = await store.geraetAnmelden(
                betrieb: nil, geraet: UIDevice.current.name) {
                fehler = grund
            } else {
                store.onboarded = true
            }
        }
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
