import SwiftUI

/// Die Inhaberin gibt Auslagen ihres Teams frei (babu Expenses D1).
/// Erstattet wird im Portal — die Bankdatei gehört an den Rechner.
struct AuslagenFreigabe: View {
    @EnvironmentObject var store: AppStore
    @State private var liste: [AuslageZeile] = []
    @State private var ablehnen: AuslageZeile?
    @State private var grund = ""

    var body: some View {
        List(liste) { z in
            VStack(alignment: .leading, spacing: 6) {
                Text("\(z.name ?? "") · \(z.lieferant ?? "Beleg")").font(.subheadline)
                Text("\(z.datum ?? "") · \(String(format: "%.2f", z.betrag ?? 0).replacingOccurrences(of: ".", with: ",")) €")
                    .font(.caption)
                HStack {
                    Button("Freigeben") { Task { await post("api/auslagen/\(z.stamm)/freigeben") } }
                        .buttonStyle(.borderedProminent)
                    Button("Ablehnen") { grund = ""; ablehnen = z }
                        .buttonStyle(.bordered)
                }
                .controlSize(.small)
            }
        }
        .overlay { if liste.isEmpty { Text("Nichts offen").foregroundStyle(.secondary) } }
        .navigationTitle("Auslagen freigeben")
        .task { await laden() }
        .refreshable { await laden() }
        .alert("Warum nicht?", isPresented: .init(get: { ablehnen != nil },
                                                  set: { if !$0 { ablehnen = nil } })) {
            TextField("Ein Satz genügt", text: $grund)
            Button("Ablehnen") {
                if let z = ablehnen {
                    Task { await post("api/auslagen/\(z.stamm)/ablehnen", ["grund": grund]) }
                }
            }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else { return }
        liste = await AblageService.offeneAuslagen(basis: url, pat: pat) ?? liste
    }

    private func post(_ pfad: String, _ koerper: [String: Any]? = nil) async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else { return }
        _ = await AblageService.auslagePost(pfad, koerper: koerper, basis: url, pat: pat)
        await laden()
    }
}
