import SwiftUI

struct ExportView: View {
    @EnvironmentObject var store: AppStore
    @State private var datei: URL?
    @State private var zeigeEinstellungen = false

    var body: some View {
        NavigationStack {
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
                                Label("EXTF-Stapel teilen (CP1252)", systemImage: "square.and.arrow.up")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
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
                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.seal")
                                Text("Exportierte Buchungen sind fixiert und bleiben unverändert.")
                                    .font(.caption2.monospaced())
                            }
                            .foregroundStyle(GC.accent)
                        }
                    }
                    .gcCard()

                    Text("Vereinfachte EXTF-Vorschau — der vollständige DATEV-v13-Writer mit Golden-File-Tests ist Phase 5 des Bauplans. Später: Direct-Push über den DATEV-Buchungsdatenservice.")
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                        .padding(.horizontal, 4)
                }
                .padding(20)
            }
            .background(GC.canvas)
            .navigationTitle("Export")
            .toolbarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        zeigeEinstellungen = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("Belegbox-Einstellungen")
                }
            }
            .sheet(isPresented: $zeigeEinstellungen) {
                EinstellungenView()
            }
            .onAppear {
                if !store.exportierbar.isEmpty { datei = store.extfDatei() }
            }
        }
    }
}
