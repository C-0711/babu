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
                        Text("Buchungsstapel August 2026")
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
                            store.fixieren()
                            datei = store.extfDatei()
                        } label: {
                            Text(store.exportiert ? "Stapel fixiert ✓" : "Stapel erzeugen & fixieren")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(store.exportierbar.isEmpty && !store.exportiert)

                        if store.exportiert {
                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.seal")
                                Text("Stapel 08/26 gesiegelt · exportierte Buchungen sind fixiert")
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
