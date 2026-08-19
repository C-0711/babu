import SwiftUI

/// Das Menü rechts oben: alles, was nicht tägliche Arbeit ist — dein Konto,
/// die Übergabe an die Buchhaltung und die Einstellungen. So bleibt die
/// Leiste unten für das Tagesgeschäft frei.
struct KontoMenuView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var zurueck

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 11) {
                        Image(systemName: store.verbundenAls == nil
                              ? "person.crop.circle" : "checkmark.circle.fill")
                            .font(.system(size: 26))
                            .foregroundStyle(store.verbundenAls == nil ? GC.muted : GC.ok)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(store.verbundenAls ?? "Noch nicht verbunden")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(GC.fg)
                            Text(store.verbundenAls == nil
                                 ? "Mit E-Mail und Passwort verbinden"
                                 : "Dein babu-Konto")
                                .font(.caption)
                                .foregroundStyle(GC.muted)
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section {
                    NavigationLink {
                        ExportView()
                    } label: {
                        Label("Export für die Buchhaltung", systemImage: "square.and.arrow.up")
                    }
                    NavigationLink {
                        EinstellungenView()
                    } label: {
                        Label("Einstellungen", systemImage: "gearshape")
                    }
                } footer: {
                    Text("Den fertigen Stapel bekommt dein Steuerbüro am Monatsende automatisch aus der Belegbox.")
                }
            }
            .navigationTitle("Dein Konto")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { zurueck() }
                }
            }
        }
    }
}

/// Hängt den Menü-Button oben rechts an einen Tab.
struct KontoMenuKnopf: ViewModifier {
    @State private var zeigeMenu = false

    func body(content: Content) -> some View {
        content
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        zeigeMenu = true
                    } label: {
                        Image(systemName: "line.3.horizontal")
                    }
                    .accessibilityLabel("Dein Konto, Export und Einstellungen")
                }
            }
            .sheet(isPresented: $zeigeMenu) { KontoMenuView() }
    }
}

extension View {
    func mitKontoMenu() -> some View { modifier(KontoMenuKnopf()) }
}
