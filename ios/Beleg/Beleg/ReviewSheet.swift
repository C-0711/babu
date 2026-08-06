import SwiftUI

/// Kontierungs-Editor: Fuzzy-Kontensuche + Steuerschlüssel, wie im Prototyp.
struct ReviewSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let belegID: UUID
    let startZeit: Date

    @State private var suche = ""
    @State private var gewaehlt: Konto?
    @State private var steuerschluessel = "9"

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    private var treffer: [Konto] {
        let q = suche.lowercased().trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return Kontenplan.konten }
        return Kontenplan.konten.filter {
            $0.nr.hasPrefix(q) || $0.bez.lowercased().contains(q)
        }
    }

    var body: some View {
        NavigationStack {
            List {
                if let b = beleg {
                    Section {
                        HStack {
                            Text(b.lieferant).fontDesign(.serif).fontWeight(.semibold)
                            Spacer()
                            Text(fmtEur(b.brutto)).monospaced()
                        }
                        Text(b.begruendung)
                            .font(.footnote)
                            .foregroundStyle(GC.desc)
                    }

                    Section("Sachkonto (\(store.skr))") {
                        TextField("Nummer oder Bezeichnung suchen …", text: $suche)
                            .autocorrectionDisabled()
                        ForEach(treffer) { k in
                            Button {
                                gewaehlt = k
                            } label: {
                                HStack {
                                    Text(k.nr)
                                        .monospaced()
                                        .foregroundStyle(GC.accent)
                                    Text(k.bez)
                                        .foregroundStyle(GC.body)
                                    Spacer()
                                    if k.individuell {
                                        BadgeView(text: "Individuell", color: GC.ok)
                                    }
                                    if gewaehlt?.id == k.id {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(GC.accent)
                                    }
                                }
                            }
                        }
                    }

                    Section("Steuerschlüssel") {
                        Picker("Steuerschlüssel", selection: $steuerschluessel) {
                            Text("9 · Vorsteuer 19 %").tag("9")
                            Text("8 · Vorsteuer 7 %").tag("8")
                            Text("0 · keine").tag("0")
                        }
                        .pickerStyle(.inline)
                        .labelsHidden()
                    }
                }
            }
            .navigationTitle("Kontierung prüfen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Buchen") {
                        store.buchen(id: belegID,
                                     konto: gewaehlt?.nr,
                                     steuerschluessel: steuerschluessel,
                                     dauer: Date().timeIntervalSince(startZeit))
                        dismiss()
                    }
                    .disabled(gewaehlt == nil && beleg?.konto == nil)
                }
            }
            .onAppear {
                if let b = beleg {
                    steuerschluessel = b.steuerschluessel
                    if let k = b.konto {
                        gewaehlt = Kontenplan.konten.first { $0.nr == k }
                    }
                }
            }
        }
    }
}
