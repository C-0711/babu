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
    /// Der Katalog des Servers — die eingebaute Kurzliste ist nur noch
    /// Fallback, wenn keine Verbindung besteht (Ninas Anmerkung #73).
    @State private var serverKonten: [Konto] = []

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    private var alleKonten: [Konto] {
        serverKonten.isEmpty ? Kontenplan.konten : serverKonten
    }

    private var treffer: [Konto] {
        let q = suche.lowercased().trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return alleKonten }
        return alleKonten.filter {
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
            .warmerGrund()
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
                        gewaehlt = alleKonten.first { $0.nr == k }
                            ?? Konto(nr: k, bez: Kontenplan.bezeichnung(k), individuell: false)
                    }
                }
            }
            .task {
                guard store.ablageAktiv, let url = URL(string: store.ablageURL),
                      let pat = KeychainHelfer.ladePAT() else { return }
                let geladen = await AblageService.kategorien(basis: url, pat: pat)
                if !geladen.isEmpty { serverKonten = geladen }
            }
        }
    }
}
