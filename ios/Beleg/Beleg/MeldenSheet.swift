import SwiftUI
import UIKit

/// Was Nina auffällt, wird ein Vorgang — ohne dass sie etwas dafür tut.
///
/// Sie merkt Dinge, die niemand sonst merkt: dass ein Beleg falsch gelesen
/// wurde, dass ein Knopf fehlt, dass etwas umständlich ist. Bisher musste
/// sie das erzählen, und jemand musste es aufschreiben. Dazwischen ging es
/// verloren.
///
/// Hier schreibt sie es dort auf, wo es ihr auffällt. Ein Feld, ein Knopf.
/// Den Zusammenhang — welche Ansicht, welcher Beleg, welches Gerät, welche
/// Fassung — hängt der Server an; genau das müsste man sonst zurückfragen,
/// und genau das hat sie bis dahin vergessen.
struct MeldenSheet: View {
    /// Woher der Knopf gedrückt wurde — steht später im Vorgang.
    let ansicht: String
    /// Welcher Beleg gerade offen war, falls einer.
    var beleg: String?

    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var zurueck

    @State private var text = ""
    @State private var art = "fehler"
    @State private var laeuft = false
    @State private var stand: String?
    @State private var fertig = false
    @FocusState private var imFeld: Bool

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 14) {
                Text("Schreib es einfach hin — in deinen Worten. Wir kümmern "
                     + "uns darum; du musst nichts weiter tun.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)

                Picker("", selection: $art) {
                    Text("Etwas stimmt nicht").tag("fehler")
                    Text("Ich hätte gern …").tag("wunsch")
                }
                .pickerStyle(.segmented)

                TextEditor(text: $text)
                    .font(.body)
                    .frame(minHeight: 140)
                    .padding(8)
                    .background(GC.bg, in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10)
                        .stroke(GC.linie, lineWidth: 1))
                    .focused($imFeld)
                    .overlay(alignment: .topLeading) {
                        if text.isEmpty {
                            Text("Zum Beispiel: Der Beleg vom Bäcker zeigt "
                                 + "19 % statt 7 %.")
                                .font(.body)
                                .foregroundStyle(GC.muted)
                                .padding(.horizontal, 13)
                                .padding(.top, 16)
                                .allowsHitTesting(false)
                        }
                    }

                if let stand {
                    Text(stand)
                        .font(.footnote)
                        .foregroundStyle(fertig ? GC.ok : GC.warn)
                }

                Button {
                    Task { await senden() }
                } label: {
                    if laeuft {
                        ProgressView().frame(maxWidth: .infinity)
                    } else {
                        Text("Abschicken").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(laeuft || text.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)

                Spacer()
            }
            .padding(18)
            .background(GC.canvas)
            .navigationTitle("Ist dir was aufgefallen?")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { zurueck() }
                }
            }
            .task { imFeld = true }
        }
    }

    private func senden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            stand = "Dafür muss die Belegbox verbunden sein (Konto → Verbinden)."
            return
        }
        laeuft = true
        defer { laeuft = false }
        let geraet = "\(UIDevice.current.model), iOS \(UIDevice.current.systemVersion)"
        let fassung = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        let antwort = await AblageService.rueckmeldenSenden(
            text: text.trimmingCharacters(in: .whitespacesAndNewlines),
            art: art, ansicht: ansicht, beleg: beleg,
            geraet: geraet, fassung: fassung, basis: url, pat: pat)
        if antwort.ok {
            fertig = true
            stand = "Angekommen ✓ — danke."
            try? await Task.sleep(for: .milliseconds(900))
            zurueck()
        } else {
            fertig = false
            stand = antwort.fehler ?? "Ging gerade nicht — gleich noch einmal."
        }
    }
}

/// Der Knopf dazu, überall gleich: oben rechts, eine Sprechblase.
struct MeldenKnopf: ViewModifier {
    let ansicht: String
    var beleg: String?
    @State private var offen = false

    func body(content: Content) -> some View {
        content
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { offen = true } label: {
                        Image(systemName: "exclamationmark.bubble")
                    }
                    .accessibilityLabel("Ist dir was aufgefallen?")
                }
            }
            .sheet(isPresented: $offen) {
                MeldenSheet(ansicht: ansicht, beleg: beleg)
            }
    }
}

extension View {
    /// Den Rückmeldeknopf oben anbringen. `ansicht` ist das, was später im
    /// Vorgang steht — also der Name, den Nina auf dem Bildschirm sieht.
    func mitMeldenKnopf(_ ansicht: String, beleg: String? = nil) -> some View {
        modifier(MeldenKnopf(ansicht: ansicht, beleg: beleg))
    }
}
