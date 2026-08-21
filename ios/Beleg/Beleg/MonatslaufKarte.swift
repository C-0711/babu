import SwiftUI

/// Der Monat, der wartet. Früher musste man hingehen, einen Monat wählen und
/// rechnen lassen — jetzt liegt er ab dem 3. von selbst da. Aus „ich muss
/// noch" wird „ich schau kurz drüber".
struct MonatslaufKarte: View {
    @EnvironmentObject var store: AppStore

    @State private var lauf: [String: Any]?
    @State private var zeigeAbschluss = false

    private var faellig: Bool { lauf?["faellig"] as? Bool == true }
    private var bereit: Bool { lauf?["bereit"] as? Bool == true }
    private var satz: String { lauf?["satz"] as? String ?? "" }
    private var offen: [[String: Any]] { lauf?["offen"] as? [[String: Any]] ?? [] }
    private var zahlen: [String: Any]? { lauf?["zahlen"] as? [String: Any] }

    var body: some View {
        Group {
            if faellig, !satz.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(satz)
                            .font(.body.weight(.medium))
                            .foregroundStyle(GC.fg)
                            .fixedSize(horizontal: false, vertical: true)

                        if let zahlen, let ergebnis = zahlen["ergebnis"] as? Double {
                            HStack {
                                Text("Bleibt dir").font(.caption).foregroundStyle(GC.desc)
                                Spacer()
                                Text(fmtEur(ergebnis))
                                    .font(.body.monospacedDigit().weight(.semibold))
                            }
                        }

                        ForEach(offen.indices, id: \.self) { i in
                            Label(offen[i]["text"] as? String ?? "",
                                  systemImage: "circle.dotted")
                                .font(.caption).foregroundStyle(GC.desc)
                        }

                        Button {
                            zeigeAbschluss = true
                        } label: {
                            Text(bereit ? "Anschauen und freigeben" : "Was fehlt noch?")
                                .font(.footnote.weight(.medium))
                                .foregroundStyle(GC.accent)
                        }
                    }
                    .padding(.vertical, 3)
                } header: {
                    Text("Dein Monat")
                }
            }
        }
        .task { await laden() }
        .sheet(isPresented: $zeigeAbschluss) {
            NavigationStack { AbschlussView() }.environmentObject(store)
        }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        lauf = await AblageService.monatslauf(basis: url, pat: pat)
    }
}
