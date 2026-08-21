import SwiftUI

/// Nachfrage für Bewirtungsbelege (§4 Abs. 5 Nr. 2 EStG): Anlass und
/// bewirtete Personen sind Pflichtangaben — ohne sie ist der Abzug weg.
/// Erscheint beim Bestätigen eines 6640-Belegs ohne Angaben und ist
/// jederzeit aus dem Beleg-Detail erreichbar.
struct BewirtungsangabenSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let belegID: UUID
    /// Wird nach dem Speichern aufgerufen (z. B. „jetzt buchen").
    var danach: (() -> Void)?

    @State private var anlass = ""
    @State private var personen = ""

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("z. B. Essen mit der Produktvertreterin", text: $anlass, axis: .vertical)
                        .lineLimit(1...3)
                } header: {
                    Text("Anlass der Bewirtung")
                }

                Section {
                    TextField("Alle Teilnehmer, inkl. dir", text: $personen, axis: .vertical)
                        .lineLimit(2...6)
                } header: {
                    Text("Bewirtete Personen")
                } footer: {
                    Text("Pflichtangaben nach §4 Abs. 5 Nr. 2 EStG — ohne Anlass und Teilnehmer entfällt der Betriebsausgabenabzug. Ort, Tag und Betrag stehen auf dem Beleg; die Unterschrift gehört aufs Papier.")
                }

                Section {
                    Button {
                        store.bewirtungSetzen(id: belegID, anlass: anlass, personen: personen)
                        dismiss()
                        danach?()
                    } label: {
                        Text(danach == nil ? "Angaben speichern" : "Speichern & buchen")
                            .frame(maxWidth: .infinity)
                    }
                    .disabled(personen.trimmingCharacters(in: .whitespaces).isEmpty)
                    if danach != nil {
                        Button("Ohne Angaben buchen — später ergänzen", role: .destructive) {
                            dismiss()
                            danach?()
                        }
                        .font(.footnote)
                    }
                }
            }
            .warmerGrund()
            .navigationTitle("Bewirtungsangaben")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
            .onAppear {
                anlass = beleg?.bewirtungAnlass ?? ""
                personen = beleg?.bewirtungPersonen ?? ""
            }
        }
        .presentationDetents([.medium])
    }
}
