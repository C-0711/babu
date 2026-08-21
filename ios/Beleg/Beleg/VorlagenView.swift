import SwiftUI

/// Der Vorlagen-Bau: Empfängerin und die Positionen, die sich wiederholen,
/// einmal hinterlegen. Danach ist eine Rechnung zwei Handgriffe statt
/// Abtippen. Vorlagen bleiben auf dem Gerät — gestellt wird über den Server.
struct VorlagenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var bearbeite: Rechnungsvorlage?
    @State private var neu = false

    var body: some View {
        NavigationStack {
            List {
                if store.vorlagen.isEmpty {
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Noch keine Vorlage.")
                                .font(.body.weight(.medium))
                            Text("Was du jeden Monat gleich berechnest — Stuhlmiete, "
                                 + "eine feste Miete — hinterlegst du einmal und "
                                 + "übernimmst es danach mit einem Tippen.")
                                .font(.caption).foregroundStyle(GC.desc)
                        }
                        .padding(.vertical, 4)
                    }
                }

                ForEach(store.vorlagen) { v in
                    Button {
                        bearbeite = v
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(v.name.isEmpty ? v.empfaenger.name : v.name)
                                .font(.body.weight(.medium)).foregroundStyle(GC.fg)
                            Text(zusammenfassung(v)).font(.caption)
                                .foregroundStyle(GC.desc)
                        }
                        .padding(.vertical, 2)
                    }
                }
                .onDelete { store.vorlagen.remove(atOffsets: $0) }

                Section {
                    Button {
                        neu = true
                    } label: {
                        Label("Neue Vorlage", systemImage: "plus.circle")
                    }
                }
            }
            .navigationTitle("Vorlagen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fertig") { dismiss() }
                }
            }
            .sheet(isPresented: $neu) {
                VorlageBearbeitenView(vorlage: Rechnungsvorlage()) { fertig in
                    store.vorlagen.append(fertig)
                }
            }
            .sheet(item: $bearbeite) { v in
                VorlageBearbeitenView(vorlage: v) { fertig in
                    if let i = store.vorlagen.firstIndex(where: { $0.id == fertig.id }) {
                        store.vorlagen[i] = fertig
                    }
                }
            }
        }
    }

    private func zusammenfassung(_ v: Rechnungsvorlage) -> String {
        let summe = v.positionen.reduce(0) { $0 + $1.gesamt }
        let zeilen = v.positionen.count == 1 ? "1 Zeile" : "\(v.positionen.count) Zeilen"
        guard summe > 0 else { return "\(v.empfaenger.name) · \(zeilen)" }
        return "\(v.empfaenger.name) · \(zeilen) · \(fmtEur(summe))"
    }
}

/// Eine Vorlage anlegen oder ändern.
struct VorlageBearbeitenView: View {
    @Environment(\.dismiss) private var dismiss

    @State var vorlage: Rechnungsvorlage
    let sichern: (Rechnungsvorlage) -> Void

    private var summe: Double {
        vorlage.positionen.reduce(0) { $0 + $1.gesamt }
    }

    private var kannSichern: Bool {
        !vorlage.empfaenger.name.trimmed.isEmpty && !vorlage.positionen.isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Wie soll die Vorlage heißen?") {
                    TextField("z. B. Stuhlmiete Jana", text: $vorlage.name)
                }

                Section("Wer bekommt die Rechnung?") {
                    TextField("Name", text: $vorlage.empfaenger.name)
                    TextField("Anschrift", text: $vorlage.empfaenger.anschrift,
                              axis: .vertical)
                        .lineLimit(1...3)
                    TextField("USt-IdNr. (wenn vorhanden)",
                              text: $vorlage.empfaenger.ustId)
                        .autocapitalization(.allCharacters)
                }

                Section {
                    ForEach($vorlage.positionen) { $p in
                        VStack(spacing: 6) {
                            TextField("z. B. Stuhlmiete", text: $p.text)
                            HStack {
                                TextField("0,00", text: betragBindung($p))
                                    .keyboardType(.decimalPad)
                                Picker("", selection: $p.ustSatz) {
                                    Text("19 %").tag(19)
                                    Text("7 %").tag(7)
                                    Text("0 %").tag(0)
                                }
                                .pickerStyle(.segmented)
                                .frame(width: 150)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    .onDelete { vorlage.positionen.remove(atOffsets: $0) }

                    Button {
                        vorlage.positionen.append(RechnungPosition())
                    } label: {
                        Label("Zeile hinzufügen", systemImage: "plus.circle")
                    }
                } header: {
                    Text("Was steht drauf?")
                } footer: {
                    if summe > 0 {
                        Text("Zusammen \(fmtEur(summe)) netto — den Betrag kannst du "
                             + "bei jeder Rechnung noch ändern.")
                    } else {
                        Text("Die Beträge lassen sich später bei jeder Rechnung "
                             + "anpassen — die Vorlage spart nur das Abtippen.")
                    }
                }
            }
            .navigationTitle(vorlage.name.isEmpty ? "Neue Vorlage" : vorlage.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sichern") {
                        if vorlage.name.trimmed.isEmpty {
                            vorlage.name = vorlage.empfaenger.name
                        }
                        sichern(vorlage)
                        dismiss()
                    }
                    .disabled(!kannSichern)
                }
            }
            .onAppear {
                if vorlage.positionen.isEmpty {
                    vorlage.positionen = [RechnungPosition()]
                }
            }
        }
    }

    private func betragBindung(_ p: Binding<RechnungPosition>) -> Binding<String> {
        Binding(get: { betragAlsText(p.wrappedValue.einzelpreis) },
                set: { p.wrappedValue.einzelpreis = betragAusText($0) })
    }
}
