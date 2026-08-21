import SwiftUI

/// „Zu dieser Abbuchung fehlt ein Beleg — hast du ihn noch?"
///
/// Die Frage, die am Jahresende Geld kostet: eine Ausgabe ohne Beleg zählt
/// steuerlich nicht. Und sie lässt sich nur beantworten, solange die
/// Erinnerung frisch ist — deshalb fragt babu jetzt und nicht im Februar.
struct BelegjagdAbschnitt: View {
    @EnvironmentObject var store: AppStore

    @State private var fragen: [[String: Any]] = []
    @State private var summe: Double = 0
    @State private var gruende: [[String: Any]] = []
    @State private var klaert: [String: Any]?

    var body: some View {
        Group {
            if !fragen.isEmpty {
                Section {
                    ForEach(fragen.indices, id: \.self) { i in
                        let f = fragen[i]
                        VStack(alignment: .leading, spacing: 6) {
                            Text(f["frage"] as? String ?? "")
                                .font(.body.weight(.medium))
                                .foregroundStyle(GC.fg)
                                .fixedSize(horizontal: false, vertical: true)
                            HStack(spacing: 14) {
                                Button("Beleg fotografieren") {
                                    store.tab = .erfassen
                                }
                                .font(.footnote.weight(.medium))
                                .foregroundStyle(GC.accent)
                                Button("Kein Beleg nötig") {
                                    klaert = f
                                }
                                .font(.footnote)
                                .foregroundStyle(GC.desc)
                            }
                        }
                        .padding(.vertical, 3)
                    }
                } header: {
                    Text("Dazu fehlt ein Beleg")
                } footer: {
                    Text("Zusammen \(fmtEur(summe)) — ohne Beleg zählt das "
                         + "steuerlich nicht. Je frischer die Erinnerung, "
                         + "desto leichter die Antwort.")
                }
            }
        }
        .task { await laden() }
        .confirmationDialog("Warum gibt es keinen Beleg?",
                            isPresented: Binding(get: { klaert != nil },
                                                 set: { if !$0 { klaert = nil } })) {
            ForEach(gruende.indices, id: \.self) { i in
                let g = gruende[i]
                Button(g["name"] as? String ?? "") {
                    Task { await klaeren(g["schluessel"] as? String ?? "") }
                }
            }
            Button("Abbrechen", role: .cancel) { klaert = nil }
        }
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else { return }
        let d = await AblageService.fehlendeBelege(basis: url, pat: pat)
        fragen = d.fragen
        summe = d.summe
        gruende = d.gruende
    }

    private func klaeren(_ grund: String) async {
        guard let frage = klaert,
              let schluessel = frage["schluessel"] as? String,
              let (url, pat) = zugang(), !grund.isEmpty else { return }
        klaert = nil
        if await AblageService.belegFrageKlaeren(schluessel: schluessel,
                                                  grund: grund, basis: url, pat: pat) {
            await laden()
        }
    }
}
