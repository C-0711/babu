import SwiftUI

/// Der Reiter „Auslagen“ einer Mitarbeiterin (babu Expenses D1).
struct AuslagenTab: View {
    @EnvironmentObject var store: AppStore
    @State private var daten: MeineAuslagen?
    @State private var fotografieren = false
    @State private var iban = ""
    @State private var ibanFalsch = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button {
                        store.auslageModus = true
                        fotografieren = true
                    } label: { Label("Auslage fotografieren", systemImage: "camera") }
                    if let d = daten, d.offen > 0 {
                        Text("Noch offen: \(String(format: "%.2f", d.offen).replacingOccurrences(of: ".", with: ",")) €")
                    }
                }
                if let d = daten, !d.iban_da {
                    Section("Konto für Erstattungen") {
                        TextField("IBAN", text: $iban)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                        Button("Speichern") { Task { await ibanSpeichern() } }
                    }
                }
                Section("Meine Auslagen") {
                    ForEach(daten?.auslagen ?? []) { z in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(z.lieferant ?? "Beleg").font(.subheadline)
                            Text("\(z.datum ?? "") · \(z.standText)").font(.caption)
                            if let g = z.grund { Text(g).font(.caption).foregroundStyle(.secondary) }
                        }
                        .swipeActions {
                            if z.status == "eingereicht" {
                                Button("Zurückziehen") { Task { await zurueckziehen(z) } }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Auslagen")
            .task { await laden() }
            .refreshable { await laden() }
            .sheet(isPresented: $fotografieren, onDismiss: {
                store.auslageModus = false
                Task { await laden() }
            }) {
                CaptureTab().environmentObject(store)
            }
            .alert("Die IBAN stimmt so nicht — bitte noch einmal prüfen.", isPresented: $ibanFalsch) {
                Button("OK", role: .cancel) {}
            }
        }
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else { return }
        daten = await AblageService.meineAuslagen(basis: url, pat: pat) ?? daten
    }

    private func ibanSpeichern() async {
        guard let (url, pat) = zugang() else { return }
        if await AblageService.auslagePost("api/auslagen/konto", koerper: ["iban": iban], basis: url, pat: pat) {
            iban = ""
            await laden()
        } else {
            ibanFalsch = true
        }
    }

    private func zurueckziehen(_ z: AuslageZeile) async {
        guard let (url, pat) = zugang() else { return }
        _ = await AblageService.auslagePost("api/auslagen/\(z.stamm)/zurueckziehen", basis: url, pat: pat)
        await laden()
    }
}
