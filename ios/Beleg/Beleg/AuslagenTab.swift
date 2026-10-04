import SwiftUI

/// Der Reiter „Auslagen“ einer Mitarbeiterin (babu Expenses D1).
struct AuslagenTab: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.scenePhase) private var phase
    @State private var daten: MeineAuslagen?
    @State private var fotografieren = false
    @State private var iban = ""
    @State private var ibanFalsch = false

    /// Was sie fotografiert hat, das aber noch nicht im Betrieb liegt.
    private var aufDemTelefon: [Beleg] {
        store.belege.filter { $0.istAuslage == true && $0.ablageStatus != .uebertragen }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Button {
                        store.auslageModus = true
                        fotografieren = true
                    } label: {
                        Label("Auslage fotografieren", systemImage: "camera")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    if let d = daten, d.offen > 0 {
                        offenKarte(d.offen)
                    }
                    if let d = daten, !d.iban_da {
                        ibanKarte
                    }
                    if !aufDemTelefon.isEmpty {
                        abschnitt("Noch auf dem Telefon")
                        ForEach(aufDemTelefon) { b in telefonZeile(b) }
                    }
                    abschnitt("Meine Auslagen")
                    if let liste = daten?.auslagen, !liste.isEmpty {
                        ForEach(liste) { z in auslageZeile(z) }
                    } else if daten != nil, aufDemTelefon.isEmpty {
                        leer
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
            }
            .warmerGrund()
            .navigationTitle("Auslagen")
            .toolbarTitleDisplayMode(.inline)
            .mitMeldenKnopf("Auslagen")
            .mitKontoMenu()
            .task { await laden() }
            .refreshable { await laden() }
            // Nach „freigegeben"/„erstattet" (Push) öffnet sie die App — dann
            // soll der neue Stand dastehen, ohne dass sie ziehen muss.
            .onChange(of: phase) { _, neu in
                if neu == .active { Task { await laden() } }
            }
            .sheet(isPresented: $fotografieren, onDismiss: {
                store.auslageModus = false
                Task { await laden() }
            }) {
                CaptureTab().environmentObject(store)
            }
            .alert("Die IBAN stimmt so nicht — bitte noch einmal prüfen.", isPresented: $ibanFalsch) {
                Button("OK", role: .cancel) {}
            }
        }
    }

    // MARK: - Teile

    private func abschnitt(_ titel: String) -> some View {
        Text(titel)
            .font(.headline)
            .fontDesign(.serif)
            .foregroundStyle(GC.fg)
            .padding(.top, 6)
    }

    private func offenKarte(_ betrag: Double) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(AuslageZeile.euro(betrag)) bekommst du noch zurück")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            Text(daten?.auslagen.contains { $0.status == "eingereicht" } == true
                 ? "Sobald die Inhaberin freigibt und auszahlt, steht es hier als erstattet."
                 : "Freigegeben. Das Geld kommt mit der nächsten Überweisung oder bar.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 14))
    }

    private var ibanKarte: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Wohin soll das Geld?")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            Text("Deine IBAN braucht die Inhaberin nur für die Überweisung. Bar geht auch ohne.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
                .fixedSize(horizontal: false, vertical: true)
            TextField("IBAN", text: $iban)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)
            Button("IBAN speichern") { Task { await ibanSpeichern() } }
                .buttonStyle(.bordered)
                .disabled(iban.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .gcCard()
    }

    private func telefonZeile(_ b: Beleg) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(b.lieferant.isEmpty ? "Beleg" : b.lieferant)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(GC.fg)
                Spacer()
                if b.brutto > 0 {
                    Text(AuslageZeile.euro(b.brutto))
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(GC.body)
                }
            }
            if let hinweis = b.ablageHinweis {
                Text(hinweis)
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 18) {
                    Button("Nochmal versuchen") { store.auslageNochmal(b.id) }
                    Button("Entfernen", role: .destructive) { store.auslageVerwerfen(b.id) }
                }
                .font(.footnote)
                .buttonStyle(.borderless)
            } else {
                Text("Geht los, sobald das Telefon Netz hat.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
            }
        }
        .gcCard()
    }

    private func auslageZeile(_ z: AuslageZeile) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(z.lieferant ?? "Beleg")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(GC.fg)
                Spacer()
                if let betrag = z.betrag {
                    Text(AuslageZeile.euro(betrag))
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(GC.body)
                }
            }
            HStack(spacing: 8) {
                Text(z.standText)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(standFarbe(z.status))
                if let datum = z.datum, !datum.isEmpty {
                    Text(AuslageZeile.datumDE(datum)).font(.footnote).foregroundStyle(GC.muted)
                }
            }
            if let g = z.grund, !g.isEmpty {
                Text(g)
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if z.status == "eingereicht" {
                Button("Zurückziehen") { Task { await zurueckziehen(z) } }
                    .font(.footnote)
                    .buttonStyle(.borderless)
            }
        }
        .gcCard()
    }

    private var leer: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Noch keine Auslage")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            Text("Hast du etwas für den Salon bezahlt? Fotografier den Beleg. Die Inhaberin gibt ihn frei, und du bekommst das Geld zurück.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 14))
    }

    private func standFarbe(_ status: String) -> Color {
        switch status {
        case "eingereicht": return GC.warn
        case "freigegeben": return GC.accent
        case "erstattet": return GC.ok
        case "abgelehnt": return GC.danger
        default: return GC.muted
        }
    }

    // MARK: - Netz

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else { return }
        daten = await AblageService.meineAuslagen(basis: url, pat: pat) ?? daten
    }

    private func ibanSpeichern() async {
        guard let (url, pat) = zugang() else { return }
        if await AblageService.auslagePost("api/auslagen/konto", koerper: ["iban": iban], basis: url, pat: pat) {
            iban = ""
            await laden()
        } else {
            ibanFalsch = true
        }
    }

    private func zurueckziehen(_ z: AuslageZeile) async {
        guard let (url, pat) = zugang() else { return }
        _ = await AblageService.auslagePost("api/auslagen/\(z.stamm)/zurueckziehen", basis: url, pat: pat)
        await laden()
    }
}
