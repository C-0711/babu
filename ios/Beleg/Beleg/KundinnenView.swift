import SwiftUI

/// Der Karteikasten hinterm Spiegel — nur eben auffindbar.
///
/// Was hier steht, ist persönlich: Telefonnummern, Notizen, Allergien,
/// Farbformeln. Es liegt deshalb nicht in der Belegbox, wo jede Fassung für
/// immer bliebe, sondern in der Datenbank — und geht auf einen Knopf wieder
/// weg, mit dem ganzen Verlauf.
struct KundinnenView: View {
    @EnvironmentObject var store: AppStore

    @State private var suche = ""
    @State private var liste: [[String: Any]] = []
    @State private var laedt = true
    @State private var neueAnlegen = false

    var body: some View {
        List {
            if laedt {
                Section {
                    HStack { ProgressView(); Text("Einen Moment …")
                        .foregroundStyle(GC.muted) }
                }
            } else if liste.isEmpty {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(suche.trimmed.isEmpty
                             ? "Noch keine Kundin angelegt."
                             : "Niemanden gefunden.")
                            .font(.body.weight(.medium))
                        Text("Trag ein, wer regelmäßig kommt — dann steht beim "
                             + "nächsten Mal da, was letztes Mal gut war.")
                            .font(.caption).foregroundStyle(GC.desc)
                    }
                    .padding(.vertical, 4)
                }
            } else {
                Section {
                    ForEach(liste.indices, id: \.self) { i in
                        let k = liste[i]
                        NavigationLink {
                            KundinView(id: k["id"] as? Int ?? 0) { Task { await laden() } }
                                .environmentObject(store)
                        } label: {
                            HStack {
                                Text(k["name"] as? String ?? "—")
                                if let a = k["allergie"] as? String, !a.isEmpty {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .font(.caption).foregroundStyle(GC.warn)
                                }
                                Spacer()
                                if let z = k["zuletzt"] as? String, !z.isEmpty {
                                    Text(z).font(.caption).foregroundStyle(GC.muted)
                                }
                            }
                        }
                    }
                }
            }
        }
        .searchable(text: $suche, prompt: "Name suchen")
        .onChange(of: suche) { Task { await laden() } }
        .navigationTitle("Kundinnen")
        .toolbarTitleDisplayMode(.inline)
        .warmerGrund()
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { neueAnlegen = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $neueAnlegen) {
            KundinBearbeitenView(vorhandene: nil) { Task { await laden() } }
                .environmentObject(store)
        }
        .task { await laden() }
        .refreshable { await laden() }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { laedt = false; return }
        liste = await AblageService.kundinnen(suche: suche, basis: url, pat: pat)
        laedt = false
    }
}

/// Eine Kundin mit ihrem Verlauf.
struct KundinView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let id: Int
    let geaendert: () -> Void

    @State private var daten: [String: Any]?
    @State private var neueLeistung = ""
    @State private var neueFormel = ""
    @State private var bearbeiten = false
    @State private var loeschfrage = false

    private var verlauf: [[String: Any]] {
        daten?["verlauf"] as? [[String: Any]] ?? []
    }

    var body: some View {
        List {
            if let a = daten?["allergie"] as? String, !a.isEmpty {
                Section {
                    Label(a, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(GC.warn)
                } header: { Text("Vorsicht") }
            }

            Section("Erreichbar") {
                zeile("Telefon", daten?["telefon"] as? String)
                zeile("E-Mail", daten?["email"] as? String)
                if let n = daten?["notiz"] as? String, !n.isEmpty {
                    Text(n).font(.callout)
                }
            }

            // Ninas Wort dafür, im Portal seit dem 27.08. so benannt — in
            // der App war es liegen geblieben (beim Schreiben der
            // Abnahmeliste aufgefallen).
            Section("Termin-Historie") {
                if verlauf.isEmpty {
                    Text("Noch nichts eingetragen.")
                        .font(.callout).foregroundStyle(GC.muted)
                }
                ForEach(verlauf.indices, id: \.self) { i in
                    let b = verlauf[i]
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text(b["datum"] as? String ?? "")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(GC.muted)
                            Text(b["leistung"] as? String ?? "—")
                                .font(.body.weight(.medium))
                        }
                        if let f = b["formel"] as? String, !f.isEmpty {
                            Text(f).font(.callout).foregroundStyle(GC.accent)
                        }
                        if let n = b["notiz"] as? String, !n.isEmpty {
                            Text(n).font(.caption).foregroundStyle(GC.desc)
                        }
                    }
                    .padding(.vertical, 2)
                }
            }

            Section {
                TextField("Was war es? (Farbe, Schnitt …)", text: $neueLeistung)
                TextField("Formel, Zeit, was du dir merken willst",
                          text: $neueFormel, axis: .vertical)
                    .lineLimit(1...3)
                Button("Eintragen") { Task { await eintragen() } }
                    .disabled(neueLeistung.trimmed.isEmpty && neueFormel.trimmed.isEmpty)
            } header: {
                Text("Heute")
            } footer: {
                Text("Beim nächsten Mal steht es oben — dann musst du nicht "
                     + "raten, was letztes Mal gut war.")
            }

            Section {
                Button("Angaben ändern") { bearbeiten = true }
                Button("Kundin löschen", role: .destructive) { loeschfrage = true }
            }
        }
        .navigationTitle(daten?["name"] as? String ?? "Kundin")
        .toolbarTitleDisplayMode(.inline)
        .warmerGrund()
        .sheet(isPresented: $bearbeiten) {
            KundinBearbeitenView(vorhandene: daten) {
                Task { await laden() }
                geaendert()
            }
            .environmentObject(store)
        }
        .alert("Wirklich löschen?", isPresented: $loeschfrage) {
            Button("Abbrechen", role: .cancel) { }
            Button("Löschen", role: .destructive) { Task { await loeschen() } }
        } message: {
            Text("Der ganze Verlauf geht mit — Formeln, Notizen, alles.")
        }
        .task { await laden() }
    }

    private func zeile(_ titel: String, _ wert: String?) -> some View {
        Group {
            if let wert, !wert.isEmpty {
                HStack {
                    Text(titel).foregroundStyle(GC.desc)
                    Spacer()
                    Text(wert)
                }
                .font(.callout)
            }
        }
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else { return }
        daten = await AblageService.kundin(id: id, basis: url, pat: pat)
    }

    private func eintragen() async {
        guard let (url, pat) = zugang() else { return }
        _ = await AblageService.behandlungSpeichern(
            kundin: id, ["leistung": neueLeistung, "formel": neueFormel],
            basis: url, pat: pat)
        neueLeistung = ""; neueFormel = ""
        await laden()
        geaendert()
    }

    private func loeschen() async {
        guard let (url, pat) = zugang() else { return }
        if await AblageService.kundinLoeschen(id: id, basis: url, pat: pat) {
            geaendert()
            dismiss()
        }
    }
}

/// Anlegen und Ändern — dasselbe Formular, einmal leer, einmal gefüllt.
struct KundinBearbeitenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let vorhandene: [String: Any]?
    let fertig: () -> Void

    @State private var name = ""
    @State private var telefon = ""
    @State private var email = ""
    @State private var allergie = ""
    @State private var notiz = ""
    @State private var fehler: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Wer ist es?") {
                    TextField("Name", text: $name)
                    TextField("Telefon", text: $telefon)
                        .keyboardType(.phonePad)
                    TextField("E-Mail", text: $email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                }
                Section {
                    TextField("z. B. keine PPD-Farben", text: $allergie)
                } header: {
                    Text("Verträgt sie etwas nicht?")
                } footer: {
                    Text("Steht dann ganz oben, in Rot — damit es niemand übersieht.")
                }
                Section("Notiz") {
                    TextField("Was du dir merken willst", text: $notiz,
                              axis: .vertical)
                        .lineLimit(2...5)
                }
                if let fehler {
                    Section { Text(fehler).font(.footnote).foregroundStyle(GC.warn) }
                }
            }
            .navigationTitle(vorhandene == nil ? "Neue Kundin" : "Angaben ändern")
            .navigationBarTitleDisplayMode(.inline)
            .warmerGrund()
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sichern") { Task { await sichern() } }
                        .disabled(name.trimmed.isEmpty)
                }
            }
            .onAppear {
                guard let v = vorhandene else { return }
                name = v["name"] as? String ?? ""
                telefon = v["telefon"] as? String ?? ""
                email = v["email"] as? String ?? ""
                allergie = v["allergie"] as? String ?? ""
                notiz = v["notiz"] as? String ?? ""
            }
        }
    }

    private func sichern() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        var felder: [String: Any] = ["name": name, "telefon": telefon,
                                     "email": email, "allergie": allergie,
                                     "notiz": notiz]
        if let id = vorhandene?["id"] as? Int { felder["id"] = id }
        if let meldung = await AblageService.kundinSpeichern(felder, basis: url,
                                                             pat: pat) {
            fehler = meldung
            return
        }
        fertig()
        dismiss()
    }
}
