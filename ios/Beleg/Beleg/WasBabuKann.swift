import SwiftUI

/// Was babu alles kann — eine Seite, sortiert nach Anlass, nicht nach Technik.
///
/// Funktionen entdeckt man in dieser App bisher zufällig: der Briefkopf liegt
/// hinter „Rechnungen", das Aufräumen erscheint nur, wenn etwas offen ist, und
/// den Karteikasten für Kundinnen findet, wer das Menü durchklickt. Diese Liste
/// zählt einmal alles auf und tippt an die Stelle, wo es weitergeht.
struct WasBabuKannView: View {
    @EnvironmentObject var store: AppStore

    /// Das Konto-Blatt schließen — Reiter unten erreicht man sonst nicht,
    /// weil sie hinter diesem Blatt liegen.
    var schliessen: () -> Void

    var body: some View {
        List {
            Section {
                Text("Das alles macht babu für dich. Tipp eine Zeile an, "
                     + "dann bist du dort.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .padding(.vertical, 2)
            }

            Section("Jeden Tag") {
                zumReiter("Belege", "camera.viewfinder",
                          "Bon fotografieren — babu liest ihn, ordnet ihn ein "
                          + "und legt ihn ab. Auch Verträge und Post vom Amt.",
                          .erfassen)
                zumReiter("Kassenbuch", "banknote",
                          "Was am Tag bar in die Kasse kam und rausging. "
                          + "Eine Frage nach der anderen, eine Zahl pro Schritt.",
                          .kasse)
                zumReiter("Termine", "calendar",
                          "Der Kalender des Salons: Termine eintragen, "
                          + "absagen und nach der Behandlung abrechnen.",
                          .termine)
            }

            Section("Wenn Geld reinkommt") {
                zurAnsicht("Rechnungen", "eurosign.circle",
                           "Stuhlmiete, Hochzeit, Firmenkundin: eine Rechnung "
                           + "schreiben und sehen, was noch offen ist.") {
                    RechnungenTab()
                }
                zurAnsicht("Deine Preise", "tag",
                           "Was deine Leistungen kosten. Daraus rechnet babu "
                           + "beim Abrechnen die Beträge aus.") {
                    PreiseView()
                }
                zurAnsicht("Kartenzahlung", "creditcard",
                           "Ob dieses iPhone Karten annehmen kann — und was "
                           + "dafür noch fehlt.") {
                    KartenzahlungView()
                }
            }

            Section("Dein Salon") {
                zurAnsicht("Kundinnen", "person.crop.circle",
                           "Der Karteikasten hinterm Spiegel: Nummern, Notizen, "
                           + "Allergien, Farbformeln.") {
                    KundinnenView()
                }
                zurAnsicht("Personal", "person.2",
                           "Wer im Salon arbeitet, was er kostet — und die "
                           + "Verträge dazu.") {
                    TeamView()
                }
                zurAnsicht("Deine Verträge", "shippingbox",
                           "Miete, Strom, Leasing: was jeden Monat sicher abgeht.") {
                    VertragskisteView()
                }
                zurAnsicht("Marketing", "megaphone",
                           "Aushang, Beitrag, Gutschein, Preisliste — in deiner "
                           + "Farbe und mit deinem Zeichen.") {
                    MarketingView()
                }
            }

            Section("Am Monatsende") {
                zurAnsicht("Auswertung", "chart.bar.doc.horizontal",
                           "Was reinkam, was rausging und was dir bleibt.") {
                    AbschlussView()
                }
                zurAnsicht("Export", "square.and.arrow.up",
                           "Die Buchungen als Datei für dein Steuerbüro. "
                           + "Meist brauchst du sie nicht — die Belegbox "
                           + "übergibt von allein.") {
                    ExportView()
                }
            }

            Section {
                zumReiter("Fragen", "questionmark.bubble",
                          "Alles, was du nicht weißt: „Kann ich den Föhn "
                          + "absetzen?“ Antwort in deiner Sprache.",
                          .fragen)
                zurAnsicht("Dein Betrieb", "building.2",
                           "Name, Anschrift, Finanzamt, Steuernummer — das, "
                           + "was auf jeder Rechnung steht.") {
                    BetriebsangabenView()
                }
            } header: {
                Text("Und außerdem")
            } footer: {
                Text("Fehlt dir etwas? Sag es über den Melden-Knopf oben rechts "
                     + "auf jedem Bildschirm.")
            }
        }
        .warmerGrund()
        .navigationTitle("Was babu kann")
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: - Die zwei Sorten Zeile

    /// Führt an einen Reiter unten — dafür muss das Konto-Blatt zu.
    private func zumReiter(_ titel: String, _ symbol: String, _ satz: String,
                           _ reiter: AppStore.Tab) -> some View {
        Button {
            store.tab = reiter
            schliessen()
        } label: {
            HStack(spacing: 8) {
                zeile(titel, symbol, satz)
                // Ein Reiter unten ist kein NavigationLink und bekommt vom
                // System keinen Pfeil — ohne ihn sähen diese drei Zeilen aus,
                // als führten sie nirgendwohin.
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(GC.muted.opacity(0.7))
            }
        }
        .buttonStyle(.plain)
    }

    /// Führt an eine Ansicht, die im Konto-Blatt selbst aufgeht.
    private func zurAnsicht<Ziel: View>(_ titel: String, _ symbol: String,
                                        _ satz: String,
                                        @ViewBuilder ziel: () -> Ziel) -> some View {
        NavigationLink {
            ziel()
        } label: {
            zeile(titel, symbol, satz)
        }
    }

    private func zeile(_ titel: String, _ symbol: String, _ satz: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 15))
                .foregroundStyle(GC.accent)
                .frame(width: 24)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                Text(titel)
                    .font(.body.weight(.medium))
                    .foregroundStyle(GC.fg)
                Text(satz)
                    .font(.caption)
                    .foregroundStyle(GC.desc)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 3)
    }
}
