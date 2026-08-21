import SwiftUI

/// Das Menü rechts oben: alles, was nicht tägliche Arbeit ist — dein Konto,
/// die Übergabe an die Buchhaltung und die Einstellungen. So bleibt die
/// Leiste unten für das Tagesgeschäft frei.
struct KontoMenuView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var zurueck

    /// Drei ehrliche Zustände: nicht verbunden, verbunden, oder verbunden
    /// gewesen — der Server nimmt den Zugang nicht mehr an.
    private var zeichen: String {
        if store.verbundenAls == nil { return "person.crop.circle" }
        return store.zugangAbgelaufen ? "exclamationmark.triangle.fill" : "checkmark.circle.fill"
    }

    private var farbe: Color {
        if store.verbundenAls == nil { return GC.muted }
        return store.zugangAbgelaufen ? GC.warn : GC.ok
    }

    private var unterzeile: String {
        if store.verbundenAls == nil { return "Mit E-Mail und Passwort verbinden" }
        return store.zugangAbgelaufen
            ? "Der Zugang gilt nicht mehr — bitte neu verbinden"
            : "Dein babu-Konto"
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 11) {
                        Image(systemName: zeichen)
                            .font(.system(size: 26))
                            .foregroundStyle(farbe)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(store.verbundenAls ?? "Noch nicht verbunden")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(GC.fg)
                            Text(unterzeile)
                                .font(.caption)
                                .foregroundStyle(store.zugangAbgelaufen ? GC.warn : GC.muted)
                        }
                    }
                    .padding(.vertical, 4)
                }

                // Was zusammengehört, steht zusammen: was die Zahlen angeht,
                // dann was den Salon angeht, dann das Konto selbst.
                Section("Buchhaltung") {
                    NavigationLink {
                        AbschlussView()
                    } label: {
                        Label("Monatsabschluss", systemImage: "chart.bar.doc.horizontal")
                    }
                    NavigationLink {
                        ExportView()
                    } label: {
                        Label("Export für die Buchhaltung", systemImage: "square.and.arrow.up")
                    }
                }

                Section("Dein Salon") {
                    NavigationLink {
                        TeamView()
                    } label: {
                        Label("Dein Team", systemImage: "person.2")
                    }
                    NavigationLink {
                        VertragskisteView()
                    } label: {
                        Label("Deine Verträge", systemImage: "shippingbox")
                    }
                    NavigationLink {
                        MarketingView()
                    } label: {
                        Label("Marketing", systemImage: "megaphone")
                    }
                }

                Section {
                    NavigationLink {
                        EinstellungenView()
                    } label: {
                        Label("Einstellungen", systemImage: "gearshape")
                    }
                } footer: {
                    Text("Den fertigen Stapel bekommt dein Steuerbüro am Monatsende automatisch aus der Belegbox.")
                }
            }
            .warmerGrund()
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
