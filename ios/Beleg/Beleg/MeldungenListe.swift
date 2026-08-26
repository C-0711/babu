import SwiftUI

/// Nina sieht hier, was aus ihren Meldungen wurde — und gibt Fixe frei.
///
/// Die Schleife schließt sich in der App: melden (Rückmeldeknopf), verfolgen
/// (diese Liste), freigeben (zwei Knöpfe). GitLab führt Buch; Nina muss es
/// nie öffnen. „Bitte prüfen" steht zuoberst, denn das ist der einzige
/// Zustand, in dem sie gebraucht wird.
struct MeldungenListe: View {
    @EnvironmentObject var store: AppStore
    @State private var zeilen: [Meldungszeile]?
    @State private var beanstandung: Meldungszeile?
    @State private var beanstandungsText = ""
    @State private var laeuft = false

    private static let statusText = [
        "gemeldet": "Gemeldet", "in-arbeit": "In Arbeit",
        "bitte-pruefen": "Bitte prüfen", "erledigt": "Erledigt"]

    var body: some View {
        List {
            if let zeilen {
                if zeilen.isEmpty {
                    Text("Noch keine Meldungen — der Knopf mit der Sprechblase "
                         + "wartet oben rechts in jeder Ansicht.")
                        .font(.footnote).foregroundStyle(GC.desc)
                }
                ForEach(zeilen) { z in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(z.titel).font(.subheadline).lineLimit(2)
                            Spacer()
                            Text(Self.statusText[z.status] ?? z.status)
                                .font(.caption2.weight(.semibold))
                                .padding(.horizontal, 8).padding(.vertical, 3)
                                .background(z.status == "bitte-pruefen" ? GC.ok.opacity(0.15)
                                            : GC.bg, in: Capsule())
                        }
                        if z.status == "bitte-pruefen" {
                            if let k = z.kommentar {
                                Text(k).font(.footnote).foregroundStyle(GC.desc).lineLimit(3)
                            }
                            HStack {
                                Button("Passt ✓") { Task { await freigeben(z) } }
                                    .buttonStyle(.borderedProminent).tint(GC.ok)
                                Button("Stimmt noch nicht") {
                                    beanstandungsText = ""
                                    beanstandung = z
                                }
                                .buttonStyle(.bordered)
                            }
                            .disabled(laeuft)
                            .controlSize(.small)
                        }
                    }
                    .padding(.vertical, 2)
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Meine Meldungen")
        .task { await laden() }
        .refreshable { await laden() }
        .alert("Was stimmt noch nicht?", isPresented: .init(
            get: { beanstandung != nil },
            set: { if !$0 { beanstandung = nil } })) {
            TextField("Ein Satz genügt", text: $beanstandungsText)
            Button("Abschicken") { Task { await beanstanden() } }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { zeilen = []; return }
        zeilen = await AblageService.meldungenHolen(basis: url, pat: pat) ?? zeilen ?? []
    }

    private func freigeben(_ z: Meldungszeile) async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        laeuft = true
        defer { laeuft = false }
        if await AblageService.meldungFreigeben(iid: z.iid, basis: url, pat: pat) {
            await laden()
        }
    }

    private func beanstanden() async {
        guard let z = beanstandung, let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              beanstandungsText.trimmingCharacters(in: .whitespaces).count >= 3
        else { return }
        laeuft = true
        defer { laeuft = false }
        if await AblageService.meldungBeanstanden(iid: z.iid, text: beanstandungsText,
                                                  basis: url, pat: pat) {
            beanstandung = nil
            await laden()
        }
    }
}
