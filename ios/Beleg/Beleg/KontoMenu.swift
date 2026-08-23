import SwiftUI

/// Das Menü rechts oben: alles, was nicht tägliche Arbeit ist — dein Konto,
/// die Übergabe an die Buchhaltung und die Einstellungen. So bleibt die
/// Leiste unten für das Tagesgeschäft frei.
struct KontoMenuView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var zurueck

    // Drei Ansichten, die es längst gibt und die bisher niemand fand:
    // Briefkopf und Vorlagen lagen ganz unten im Rechnungs-Reiter, das
    // Aufräumen erschien nur, wenn gerade etwas offen war. Alle drei bringen
    // ihr eigenes Blatt mit (eigener NavigationStack, eigener Fertig-Knopf) —
    // deshalb sheet/fullScreenCover statt NavigationLink.
    @State private var zeigeBriefkopf = false
    @State private var zeigeVorlagen = false
    @State private var zeigeAufraeumen = false

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
        if store.zugangAbgelaufen { return "Der Zugang gilt nicht mehr — bitte neu verbinden" }
        // Sagen, WOMIT man angemeldet ist, nicht nur DASS: „Dein babu-Konto"
        // beantwortet die Frage nicht, die man sich hier stellt.
        switch store.verbundenRolle {
        case "mitarbeit": return "Angemeldet als Mitarbeiterin"
        case "kanzlei":   return "Angemeldet als Kanzlei"
        default:          return "Angemeldet — dein babu-Konto"
        }
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
                                .font(.callout.weight(.medium))
                                .foregroundStyle(GC.fg)
                                .lineLimit(1)
                                .minimumScaleFactor(0.7)
                                .textSelection(.enabled)
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
                    // Der Wischstapel für offene Belege. Stand bisher nur auf
                    // der Dokumentenliste, und dort auch nur, solange etwas
                    // offen war — wer ihn einmal gesehen hatte, fand ihn nie
                    // wieder. Hier steht er immer; ist nichts offen, sagt die
                    // Ansicht das ehrlich, statt einen toten Knopf zu zeigen.
                    blattZeile("Belege aufräumen", "rectangle.stack") {
                        zeigeAufraeumen = true
                    }
                    NavigationLink {
                        RechnungenTab()
                    } label: {
                        Label("Rechnungen", systemImage: "eurosign.circle")
                    }
                    blattZeile("Vorlagen", "doc.on.doc") { zeigeVorlagen = true }
                    blattZeile("Dein Briefkopf", "paintpalette") {
                        zeigeBriefkopf = true
                    }
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
                    // Name, Anschrift, Steuernummer: bisher nur im Portal im
                    // Browser zu ändern, obwohl die App hierher verwies.
                    NavigationLink {
                        BetriebsangabenView()
                    } label: {
                        Label("Dein Betrieb", systemImage: "building.2")
                    }
                    NavigationLink {
                        KundinnenView()
                    } label: {
                        Label("Kundinnen", systemImage: "person.crop.circle")
                    }
                    NavigationLink {
                        PreiseView()
                    } label: {
                        Label("Deine Preise", systemImage: "tag")
                    }
                    NavigationLink {
                        KartenzahlungView()
                    } label: {
                        Label("Kartenzahlung", systemImage: "creditcard")
                    }
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
                        KontoauszugView()
                    } label: {
                        Label("Kontoauszug", systemImage: "building.columns")
                    }
                    NavigationLink {
                        MarketingView()
                    } label: {
                        Label("Marketing", systemImage: "megaphone")
                    }
                }

                Section {
                    // Funktionen wurden bisher zufällig entdeckt — diese Seite
                    // zählt einmal alles auf, nach Anlass statt nach Technik.
                    NavigationLink {
                        WasBabuKannView { zurueck() }
                    } label: {
                        Label("Was babu alles kann", systemImage: "list.bullet.rectangle")
                    }
                    NavigationLink {
                        EinstellungenView()
                    } label: {
                        Label("Einstellungen", systemImage: "gearshape")
                    }
                } footer: {
                    Text("Den fertigen Stand bekommt dein Steuerbüro am Monatsende automatisch aus der Belegbox.")
                }
            }
            .warmerGrund()
            .navigationTitle("Dein Konto")
            .navigationBarTitleDisplayMode(.inline)
            // Beim Öffnen nachfragen, als wer dieses Gerät angemeldet ist.
            // Das füllt den Namen auch bei Zugängen aus älteren Fassungen
            // und sagt nebenbei, ob der Schlüssel überhaupt noch gilt.
            .task { await store.kontoNachfragen() }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { zurueck() }
                }
            }
            .sheet(isPresented: $zeigeVorlagen) {
                VorlagenView().environmentObject(store)
            }
            .sheet(isPresented: $zeigeBriefkopf) {
                BriefkopfView().environmentObject(store)
            }
            .fullScreenCover(isPresented: $zeigeAufraeumen) {
                AufraeumenView().environmentObject(store)
            }
        }
    }

    /// Eine Zeile, die ein Blatt aufschlägt, statt weiterzuschieben. Sieht
    /// aus wie die NavigationLink-Zeilen daneben — ein Knopf, der sich anders
    /// anfühlt als seine Nachbarn, wirkt kaputt, auch wenn er tut.
    private func blattZeile(_ titel: String, _ symbol: String,
                            _ tun: @escaping () -> Void) -> some View {
        Button(action: tun) {
            HStack {
                Label {
                    Text(titel).foregroundStyle(GC.fg)
                } icon: {
                    Image(systemName: symbol).foregroundStyle(GC.accent)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(GC.muted.opacity(0.7))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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
