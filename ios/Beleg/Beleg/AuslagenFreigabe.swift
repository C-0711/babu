import SwiftUI

/// Die Inhaberin gibt Auslagen ihres Teams frei (babu Expenses D1).
/// Erstattet wird im Portal — die Bankdatei gehört an den Rechner.
struct AuslagenFreigabe: View {
    @EnvironmentObject var store: AppStore
    @State private var liste: [AuslageZeile]?
    @State private var ablehnen: AuslageZeile?
    @State private var grund = ""
    @State private var fehler: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let liste, liste.isEmpty {
                    leer
                }
                ForEach(liste ?? []) { z in zeile(z) }
                if liste?.isEmpty == false {
                    Text("Erstattet wird im Portal: dort entsteht die Bankdatei oder der Beleg für die Barauszahlung.")
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 4)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .warmerGrund()
        .navigationTitle("Auslagen freigeben")
        .toolbarTitleDisplayMode(.inline)
        .task { await laden() }
        .refreshable { await laden() }
        .alert("Warum nicht?", isPresented: .init(get: { ablehnen != nil },
                                                  set: { if !$0 { ablehnen = nil } })) {
            TextField("Ein Satz genügt", text: $grund)
            Button("Ablehnen", role: .destructive) {
                if let z = ablehnen {
                    Task { await post("api/auslagen/\(z.stamm)/ablehnen", ["grund": grund]) }
                }
            }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Die Mitarbeiterin sieht deinen Satz bei ihrer Auslage.")
        }
        .alert("Das hat nicht geklappt", isPresented: .init(get: { fehler != nil },
                                                           set: { if !$0 { fehler = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(fehler ?? "")
        }
    }

    private func zeile(_ z: AuslageZeile) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(z.lieferant ?? "Beleg")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(GC.fg)
                    Text([z.name, z.datum.map(AuslageZeile.datumDE)].compactMap { $0 }.filter { !$0.isEmpty }
                            .joined(separator: ", "))
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                }
                Spacer()
                Text(z.betrag.map(AuslageZeile.euro) ?? "ohne Betrag")
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(z.betrag == nil ? GC.warn : GC.fg)
            }
            HStack(spacing: 10) {
                Button("Freigeben") { Task { await post("api/auslagen/\(z.stamm)/freigeben") } }
                    .buttonStyle(.borderedProminent)
                Button("Ablehnen") { grund = ""; ablehnen = z }
                    .buttonStyle(.bordered)
            }
            .controlSize(.small)
        }
        .gcCard()
    }

    private var leer: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Nichts zu entscheiden")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            Text("Reicht jemand aus deinem Team eine Auslage ein, steht sie hier zur Freigabe.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 14))
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else { return }
        liste = await AblageService.offeneAuslagen(basis: url, pat: pat) ?? liste ?? []
    }

    private func post(_ pfad: String, _ koerper: [String: Any]? = nil) async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else { return }
        if let text = await AblageService.schicken(pfad, koerper ?? [:], basis: url, pat: pat) {
            fehler = text
        }
        await laden()
    }
}
