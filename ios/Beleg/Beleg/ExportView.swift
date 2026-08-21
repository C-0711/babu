import SwiftUI

struct ExportView: View {
    @EnvironmentObject var store: AppStore
    @State private var datei: URL?
    @State private var zeigeFixiertInfo = false

    var body: some View {
        ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(extfMonat().titel)
                            .font(.headline)
                            .fontDesign(.serif)
                        Text("\(store.exportierbar.count) Buchungen · \(fmtEur(store.stapelSumme)) · bereit für den Import beim Steuerberater.")
                            .font(.footnote)
                            .foregroundStyle(GC.desc)

                        ScrollView(.horizontal) {
                            Text(store.exportierbar.isEmpty ? "— Stapel ist leer —" : store.extfText())
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(GC.desc)
                                .padding(11)
                        }
                        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 9))

                        if let url = datei {
                            ShareLink(item: url) {
                                Label("Stapel teilen", systemImage: "square.and.arrow.up")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            Text("Die Datei geht nur dorthin, wo du sie teilst — von allein passiert nichts.")
                                .font(.caption2)
                                .foregroundStyle(GC.muted)
                        }

                        Button {
                            // Erzeugt die Datei aus dem Schnappschuss und fixiert
                            // danach genau diese Belege (Reihenfolge wichtig).
                            if let url = store.exportieren() { datei = url }
                        } label: {
                            Text(store.exportierbar.isEmpty && store.exportiert
                                 ? "Stapel fixiert ✓" : "Stapel erzeugen & fixieren")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(store.exportierbar.isEmpty)

                        if store.exportiert {
                            Button {
                                zeigeFixiertInfo = true
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "checkmark.seal")
                                    Text("Exportierte Buchungen sind fixiert und bleiben unverändert.")
                                        .font(.caption2.monospaced())
                                        .multilineTextAlignment(.leading)
                                    Image(systemName: "info.circle")
                                        .font(.caption)
                                }
                                .foregroundStyle(GC.accent)
                            }
                            .accessibilityLabel("Was heißt fixiert?")
                        }
                    }
                    .gcCard()

                    Text("Das hier ist die Vorschau für unterwegs. Den fertigen Stapel bekommt dein Steuerbüro automatisch aus der Belegbox am Monatsende — Teilen brauchst du nur, wenn du die Datei selbst irgendwohin schicken willst.")
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                        .padding(.horizontal, 4)

                    Text("Der Stapel enthält nur Belege. Dein Kassenbuch geht Tag für Tag einzeln in die Belegbox.")
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                        .padding(.horizontal, 4)
                }
                .padding(20)
            }
            .background(GC.canvas)
            .warmerGrund()
            .navigationTitle("Export")
            .toolbarTitleDisplayMode(.inline)
            .alert("Was heißt „fixiert“?", isPresented: $zeigeFixiertInfo) {
                Button("Verstanden") {}
            } message: {
                Text("Fixiert heißt festgeschrieben: Diese Buchungen ändern sich nicht mehr — so verlangt es das Finanzamt für die Buchhaltung. Neue Belege kommen einfach in den nächsten Stapel.")
            }
        .onAppear {
            if !store.exportierbar.isEmpty {
                datei = store.extfDatei()
            } else if store.exportiert, !store.fixierte.isEmpty {
                // Nach App-Neustart bleibt der fixierte Stapel teilbar.
                datei = store.extfDatei(fuer: store.fixierte)
            }
        }
    }
}
