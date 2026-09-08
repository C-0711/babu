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
                    // Die Zeile sagt „Mit E-Mail und Passwort verbinden" —
                    // also muss sie auch dorthin führen. Sie war reine
                    // Anzeige, und der einzige Weg zum Anmelden lag ganz
                    // unten in den Einstellungen: wer nicht verbunden ist,
                    // tippt genau hier und passiert nichts.
                    NavigationLink {
                        EinstellungenView()
                    } label: {
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
                                Text(unterzeile)
                                    .font(.caption)
                                    .foregroundStyle(store.zugangAbgelaufen ? GC.warn : GC.muted)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }

                // Was zusammengehört, steht zusammen: was die Zahlen angeht,
                // dann was den Salon angeht, dann das Konto selbst. Welche
                // Zeilen es in diesem Bau gibt, sagt `Ausbaustufe` — nicht
                // dieser Bildschirm.
                ForEach(abschnitte, id: \.self) { abschnitt in
                    Section {
                        ForEach(punkte(abschnitt), id: \.self) { punkt in
                            zeile(punkt)
                        }
                    } header: {
                        if let titel = abschnitt.titel { Text(titel) }
                    } footer: {
                        if abschnitt == .konto {
                            Text("Den fertigen Stand bekommt dein Steuerbüro am Monatsende automatisch aus der Belegbox.")
                        }
                    }
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

    // MARK: - Die Zeilen dieses Baus

    /// Nur Abschnitte, in denen in diesem Bau überhaupt etwas steht — sonst
    /// bliebe im schmalen Bau eine leere Überschrift stehen.
    private var abschnitte: [Kontomenuepunkt.Abschnitt] {
        [.buchhaltung, .salon, .konto].filter { !punkte($0).isEmpty }
    }

    private func punkte(_ abschnitt: Kontomenuepunkt.Abschnitt) -> [Kontomenuepunkt] {
        Ausbaustufe.kontomenue.filter { $0.abschnitt == abschnitt }
    }

    /// Eine Zeile: entweder ein Blatt oder ein Weiterschieben.
    @ViewBuilder
    private func zeile(_ punkt: Kontomenuepunkt) -> some View {
        if punkt.alsBlatt {
            blattZeile(punkt.titel, punkt.symbol) { blattOeffnen(punkt) }
        } else {
            NavigationLink {
                ziel(punkt)
            } label: {
                Label(punkt.titel, systemImage: punkt.symbol)
            }
        }
    }

    private func blattOeffnen(_ punkt: Kontomenuepunkt) {
        switch punkt {
        // Der Wischstapel für offene Belege. Stand bisher nur auf der
        // Dokumentenliste, und dort auch nur, solange etwas offen war — wer
        // ihn einmal gesehen hatte, fand ihn nie wieder. Hier steht er immer;
        // ist nichts offen, sagt die Ansicht das ehrlich.
        case .aufraeumen: zeigeAufraeumen = true
        case .vorlagen:   zeigeVorlagen = true
        case .briefkopf:  zeigeBriefkopf = true
        default: break
        }
    }

    @ViewBuilder
    private func ziel(_ punkt: Kontomenuepunkt) -> some View {
        switch punkt {
        case .rechnungen:      RechnungenTab()
        case .monatsabschluss: AbschlussView()
        case .export:          ExportView()
        // Was babu über den Betrieb weiß, was noch fehlt und woher es das
        // hat — an einer Stelle, statt über zwei Bildschirme verstreut.
        case .betrieb:         BetriebsprofilView()
        case .kundinnen:       KundinnenView()
        case .preise:          PreiseView()
        case .kartenzahlung:   KartenzahlungView()
        case .team:            TeamView()
        case .vertraege:       VertragskisteView()
        case .kontoauszug:     KontoauszugView()
        case .marketing:       MarketingView()
        // Funktionen wurden bisher zufällig entdeckt — diese Seite zählt
        // einmal alles auf, nach Anlass statt nach Technik.
        case .wasBabuKann:     WasBabuKannView { zurueck() }
        case .meldungen:       MeldungenListe()
        case .einstellungen:   EinstellungenView()
        // Blätter — kommen hier nie an, siehe `alsBlatt`.
        case .aufraeumen, .vorlagen, .briefkopf: EmptyView()
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
