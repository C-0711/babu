import SwiftUI

/// Korrektur der Kernfelder — wenn die Lesung danebenlag, ändert die
/// Nutzerin das hier, statt zu löschen und neu zu fotografieren.
struct FeldEditorSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let belegID: UUID

    @State private var lieferant = ""
    @State private var belegNr = ""
    @State private var datum = ""
    @State private var brutto = ""
    @State private var netto = ""
    @State private var ust = ""

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    private func zahl(_ s: String) -> Double? {
        let t = s.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return nil }
        return FeldParser.parseBetrag(t) ?? Double(t.replacingOccurrences(of: ",", with: "."))
    }

    private var bruttoWert: Double? { zahl(brutto) }
    private var nettoWert: Double? { zahl(netto) }
    private var ustWert: Double? { zahl(ust) }

    private var datumOK: Bool { FeldParser.datumPlausibel(datum.trimmingCharacters(in: .whitespaces)) }
    private var speicherbar: Bool {
        bruttoWert != nil && nettoWert != nil && ustWert != nil && datumOK
            && !lieferant.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Beleg") {
                    TextField("Lieferant", text: $lieferant)
                    TextField("Beleg-Nummer", text: $belegNr)
                    TextField("Datum (TT.MM.JJJJ)", text: $datum)
                        .keyboardType(.numbersAndPunctuation)
                    if !datum.isEmpty && !datumOK {
                        Label("Bitte als Tag.Monat.Jahr, z. B. 05.08.2026",
                              systemImage: "calendar.badge.exclamationmark")
                            .font(.footnote)
                            .foregroundStyle(GC.warn)
                    }
                }
                Section("Beträge in €") {
                    TextField("Gesamt (brutto)", text: $brutto)
                        .keyboardType(.decimalPad)
                    TextField("Ohne Steuer (netto)", text: $netto)
                        .keyboardType(.decimalPad)
                    TextField("Steuer", text: $ust)
                        .keyboardType(.decimalPad)
                    if let b = bruttoWert, let n = nettoWert, let u = ustWert {
                        if abs(n + u - b) < 0.011 {
                            Label("Die Beträge passen zusammen.", systemImage: "checkmark.circle")
                                .font(.footnote)
                                .foregroundStyle(GC.ok)
                        } else {
                            Label("Netto + Steuer ergibt nicht den Gesamtbetrag — bitte prüfen.",
                                  systemImage: "exclamationmark.triangle")
                                .font(.footnote)
                                .foregroundStyle(GC.warn)
                        }
                    }
                }
            }
            .navigationTitle("Angaben korrigieren")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Speichern") {
                        store.felderKorrigieren(id: belegID,
                                                lieferant: lieferant, belegNr: belegNr,
                                                datumText: datum,
                                                netto: nettoWert ?? 0,
                                                ust: ustWert ?? 0,
                                                brutto: bruttoWert ?? 0)
                        dismiss()
                    }
                    .disabled(!speicherbar)
                }
            }
            .onAppear {
                guard let b = beleg else { return }
                lieferant = b.lieferant
                belegNr = b.belegNr
                datum = b.datumText
                brutto = fmtBetrag(b.brutto)
                netto = fmtBetrag(b.netto)
                ust = fmtBetrag(b.ust)
            }
        }
    }
}
