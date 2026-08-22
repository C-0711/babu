import SwiftUI

/// Nach der Behandlung: bar oder Karte, und fertig.
///
/// Was daraus wird, ist ein Vorschlag fürs Kassenbuch — keine Buchung.
/// Das ist Absicht: sobald babu Umsätze selbst festschreibt, ist es eine
/// Kasse im Sinne von § 146a AO und braucht eine zertifizierte
/// Sicherheitseinrichtung. babu rechnet zusammen, bestätigen tut sie.
struct AbrechnenSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let termin: [String: Any]
    let fertig: () -> Void

    @State private var preis = ""
    @State private var zahlart = "bar"
    @State private var leistungen: [[String: Any]] = []
    @State private var fehler: String?
    @State private var laeuft = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        Text(termin["kundin"] as? String ?? "—")
                            .font(.body.weight(.medium))
                        Spacer()
                        Text(String((termin["start"] as? String ?? "").suffix(5)))
                            .font(.callout.monospacedDigit())
                            .foregroundStyle(GC.muted)
                    }
                    if let l = termin["leistung"] as? String, !l.isEmpty {
                        Text(l).font(.callout).foregroundStyle(GC.desc)
                    }
                }

                Section("Was hat es gekostet?") {
                    TextField("z. B. 49,00", text: $preis)
                        .keyboardType(.decimalPad)
                    if !leistungen.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(leistungen.indices, id: \.self) { i in
                                    let l = leistungen[i]
                                    Button {
                                        preis = euroText(l["preis"] as? Double ?? 0)
                                    } label: {
                                        Text("\(l["name"] as? String ?? "") · "
                                             + euroText(l["preis"] as? Double ?? 0))
                                            .font(.caption)
                                    }
                                    .buttonStyle(.bordered)
                                }
                            }
                        }
                    }
                }

                Section("Womit?") {
                    Picker("Bezahlt", selection: $zahlart) {
                        Text("Bar").tag("bar")
                        Text("Karte").tag("karte")
                    }
                    .pickerStyle(.segmented)
                }

                if let fehler {
                    Section { Text(fehler).font(.footnote).foregroundStyle(GC.warn) }
                }

                Section {
                    EmptyView()
                } footer: {
                    Text("Das ergibt abends einen Vorschlag fürs Kassenbuch. "
                         + "Eingetragen wird er erst, wenn du ihn bestätigst.")
                }
            }
            .navigationTitle("Abrechnen")
            .navigationBarTitleDisplayMode(.inline)
            .warmerGrund()
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { Task { await sichern() } }
                        .disabled(laeuft || preis.trimmed.isEmpty)
                }
            }
            .task { await leistungenLaden() }
            .onAppear {
                if let p = termin["preis"] as? Double, p > 0 { preis = euroText(p) }
            }
        }
    }

    private func euroText(_ wert: Double) -> String {
        String(format: "%.2f", wert).replacingOccurrences(of: ".", with: ",")
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func leistungenLaden() async {
        guard let (url, pat) = zugang() else { return }
        leistungen = await AblageService.leistungen(basis: url, pat: pat)
    }

    private func sichern() async {
        guard let (url, pat) = zugang(),
              let id = termin["id"] as? Int else { return }
        laeuft = true
        defer { laeuft = false }
        if let meldung = await AblageService.terminAbrechnen(
            id: id, preis: preis, zahlart: zahlart, basis: url, pat: pat) {
            fehler = meldung
            return
        }
        fertig()
        dismiss()
    }
}

/// Was der Salon anbietet, was es kostet. Ohne Preis kann ein Termin nichts
/// wert sein — deshalb liegt die Liste gleich neben dem Kalender.
struct PreiseView: View {
    @EnvironmentObject var store: AppStore

    @State private var liste: [[String: Any]] = []
    @State private var name = ""
    @State private var preis = ""
    @State private var minuten = 60
    @State private var fehler: String?

    var body: some View {
        List {
            if liste.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Noch keine Preise hinterlegt.")
                            .font(.body.weight(.medium))
                        Text("Trag ein, was du anbietest — danach genügt am "
                             + "Termin ein Tippen.")
                            .font(.caption).foregroundStyle(GC.desc)
                    }
                    .padding(.vertical, 4)
                }
            } else {
                Section("Deine Leistungen") {
                    ForEach(liste.indices, id: \.self) { i in
                        let l = liste[i]
                        HStack {
                            Text(l["name"] as? String ?? "")
                            Spacer()
                            Text("\(l["minuten"] as? Int ?? 0) min")
                                .font(.caption).foregroundStyle(GC.muted)
                            Text(String(format: "%.2f €", l["preis"] as? Double ?? 0)
                                    .replacingOccurrences(of: ".", with: ","))
                                .font(.body.monospacedDigit())
                        }
                    }
                }
            }

            Section("Neue Leistung") {
                TextField("Waschen, Schneiden, Föhnen", text: $name)
                TextField("49,00", text: $preis).keyboardType(.decimalPad)
                Picker("Dauer", selection: $minuten) {
                    ForEach([15, 30, 45, 60, 90, 120, 150, 180], id: \.self) { m in
                        Text(m < 60 ? "\(m) min" : "\(m / 60) Std"
                             + (m % 60 == 0 ? "" : " \(m % 60) min")).tag(m)
                    }
                }
                Button("Aufnehmen") { Task { await aufnehmen() } }
                    .disabled(name.trimmed.isEmpty || preis.trimmed.isEmpty)
            }

            if let fehler {
                Section { Text(fehler).font(.footnote).foregroundStyle(GC.warn) }
            }
        }
        .navigationTitle("Deine Preise")
        .toolbarTitleDisplayMode(.inline)
        .warmerGrund()
        .task { await laden() }
        .refreshable { await laden() }
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else { return }
        liste = await AblageService.leistungen(basis: url, pat: pat)
    }

    private func aufnehmen() async {
        guard let (url, pat) = zugang() else { return }
        if let meldung = await AblageService.leistungSpeichern(
            ["name": name, "preis": preis, "minuten": minuten],
            basis: url, pat: pat) {
            fehler = meldung
            return
        }
        name = ""; preis = ""; fehler = nil
        await laden()
    }
}
