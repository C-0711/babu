import SwiftUI
import PhotosUI

/// Dein Team: wer im Salon arbeitet, was er kostet — und ein Bild dazu.
/// Das Foto wird in der App aufgenommen und liegt danach beim Konto.
struct TeamView: View {
    @EnvironmentObject var store: AppStore

    @State private var leute: [TeamPerson] = []
    @State private var kostenMonat: Double = 0
    @State private var laedt = true
    @State private var fehler: String?
    @State private var bearbeite: TeamPerson?
    @State private var fotos: [Int: UIImage] = [:]

    var body: some View {
        List {
            if laedt {
                HStack { ProgressView(); Text("Einen Moment …").foregroundStyle(GC.muted) }
            }
            if let fehler {
                Text(fehler).font(.footnote).foregroundStyle(GC.warn)
            }

            ForEach(leute) { person in
                Button {
                    bearbeite = person
                } label: {
                    HStack(spacing: 13) {
                        bild(fuer: person)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(person.name)
                                .font(.body.weight(.medium))
                                .foregroundStyle(GC.fg)
                            Text(person.kostenText)
                                .font(.caption)
                                .foregroundStyle(GC.desc)
                        }
                        Spacer()
                        if !person.aktiv {
                            Text("nicht mehr da")
                                .font(.caption2)
                                .foregroundStyle(GC.muted)
                        }
                    }
                    .opacity(person.aktiv ? 1 : 0.5)
                    .padding(.vertical, 3)
                }
                .swipeActions(edge: .trailing) {
                    Button(person.aktiv ? "Hört auf" : "Zurück") {
                        Task { await aktion(person, person.aktiv ? "beenden" : "zurueck") }
                    }
                    .tint(person.aktiv ? GC.warn : GC.ok)
                }
            }

            if !leute.isEmpty, kostenMonat > 0 {
                HStack {
                    Text("Zusammen im Monat").font(.subheadline)
                    Spacer()
                    Text(fmtEur(kostenMonat))
                        .font(.subheadline.weight(.semibold).monospaced())
                }
                .listRowBackground(GC.accentSubtle)
            }

            Section {
                Button {
                    bearbeite = TeamPerson(name: "")
                } label: {
                    Label("Jemanden eintragen", systemImage: "person.badge.plus")
                }
            } footer: {
                Text(leute.isEmpty
                     ? "Arbeitest du allein? Dann lass das hier einfach leer."
                     : "Die Summe rechnen wir in deiner Auswertung mit — auch ohne Lohnbeleg. Steuerklasse und Sozialversicherung bleiben beim Lohnbüro.")
            }
        }
        .navigationTitle("Dein Team")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $bearbeite) { person in
            TeamPersonView(person: person) { Task { await laden() } }
        }
        .task { await laden() }
    }

    @ViewBuilder
    private func bild(fuer person: TeamPerson) -> some View {
        ZStack {
            if let foto = fotos[person.id] {
                Image(uiImage: foto)
                    .resizable()
                    .scaledToFill()
            } else {
                Circle().fill(GC.accentSubtle)
                Text(person.name.prefix(1).uppercased())
                    .font(.headline)
                    .foregroundStyle(GC.accent)
            }
        }
        .frame(width: 46, height: 46)
        .clipShape(Circle())
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else {
            fehler = "Dafür braucht die App die Belegbox — einmal in den Einstellungen verbinden."
            laedt = false
            return
        }
        laedt = true
        if let ergebnis = await AblageService.teamLaden(basis: url, pat: pat) {
            leute = ergebnis.leute
            kostenMonat = ergebnis.kosten
            fehler = nil
            for person in ergebnis.leute where person.fotoPfad != nil && fotos[person.id] == nil {
                if let daten = await AblageService.teamFotoLaden(id: person.id, basis: url, pat: pat),
                   let bild = UIImage(data: daten) {
                    fotos[person.id] = bild
                }
            }
        } else {
            fehler = "Gerade keine Verbindung."
        }
        laedt = false
    }

    private func aktion(_ person: TeamPerson, _ was: String) async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT()
        else { return }
        if await AblageService.teamAktion(id: person.id, aktion: was, basis: url, pat: pat) {
            await laden()
        }
    }
}

/// Eine Person anlegen oder ändern — vier Angaben, plus Foto.
struct TeamPersonView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var zurueck

    @State var person: TeamPerson
    var fertig: () -> Void

    @State private var fotoAuswahl: PhotosPickerItem?
    @State private var foto: UIImage?
    @State private var betragText = ""
    @State private var stundenlohnText = ""
    @State private var stundenText = ""
    @State private var meldung: String?
    @State private var speichert = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        Spacer()
                        PhotosPicker(selection: $fotoAuswahl, matching: .images) {
                            ZStack {
                                if let foto {
                                    Image(uiImage: foto).resizable().scaledToFill()
                                } else {
                                    Circle().fill(GC.accentSubtle)
                                    VStack(spacing: 4) {
                                        Image(systemName: "camera")
                                            .font(.system(size: 22))
                                        Text("Bild").font(.caption2)
                                    }
                                    .foregroundStyle(GC.accent)
                                }
                            }
                            .frame(width: 96, height: 96)
                            .clipShape(Circle())
                        }
                        Spacer()
                    }
                } footer: {
                    Text("Ein Bild hilft beim Zuordnen. Frag kurz, ob es in Ordnung ist — es ist ihr Bild.")
                }

                Section("Wer ist das?") {
                    TextField("Name", text: $person.name)
                    TextField("E-Mail (wenn du magst)",
                              text: Binding(get: { person.email ?? "" },
                                            set: { person.email = $0 }))
                        .keyboardType(.emailAddress)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }

                Section("Was bekommt sie?") {
                    Picker("Lohn", selection: $person.lohnArt) {
                        Text("Fester Lohn").tag("fest")
                        Text("Nach Stunden").tag("stunden")
                    }
                    .pickerStyle(.segmented)
                    if person.lohnArt == "fest" {
                        HStack {
                            TextField("z. B. 2400", text: $betragText)
                                .keyboardType(.decimalPad)
                            Text("€ im Monat").foregroundStyle(GC.muted)
                        }
                    } else {
                        HStack {
                            TextField("Stundenlohn", text: $stundenlohnText)
                                .keyboardType(.decimalPad)
                            Text("€").foregroundStyle(GC.muted)
                        }
                        HStack {
                            TextField("Stunden im Monat", text: $stundenText)
                                .keyboardType(.decimalPad)
                            Text("Std").foregroundStyle(GC.muted)
                        }
                    }
                }

                if let meldung {
                    Text(meldung).font(.footnote).foregroundStyle(GC.warn)
                }
            }
            .navigationTitle(person.id > 0 ? "Ändern" : "Neu im Team")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { zurueck() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Sichern") { Task { await sichern() } }
                        .disabled(speichert || person.name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer(); Button("Fertig") { hideKeyboard() }
                }
            }
            .onAppear {
                betragText = person.betrag.map { fmtBetrag($0) } ?? ""
                stundenlohnText = person.stundenlohn.map { fmtBetrag($0) } ?? ""
                stundenText = person.stunden.map { String(Int($0)) } ?? ""
            }
            .onChange(of: fotoAuswahl) { _, neu in
                guard let neu else { return }
                Task {
                    if let daten = try? await neu.loadTransferable(type: Data.self),
                       let bild = UIImage(data: daten) { foto = bild }
                }
            }
        }
    }

    private func zahl(_ text: String) -> Double? {
        let sauber = text.replacingOccurrences(of: ".", with: "")
                         .replacingOccurrences(of: ",", with: ".")
                         .trimmingCharacters(in: .whitespaces)
        return sauber.isEmpty ? nil : Double(sauber)
    }

    private func sichern() async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else {
            meldung = "Dafür braucht die App die Belegbox — einmal in den Einstellungen verbinden."
            return
        }
        speichert = true
        person.name = person.name.trimmingCharacters(in: .whitespaces)
        person.betrag = zahl(betragText)
        person.stundenlohn = zahl(stundenlohnText)
        person.stunden = zahl(stundenText)

        if let fehler = await AblageService.teamSpeichern(person, basis: url, pat: pat) {
            meldung = fehler
            speichert = false
            return
        }
        // Foto nachreichen — die ID kennen wir erst nach dem Anlegen.
        if let foto, let jpeg = foto.jpegData(compressionQuality: 0.8) {
            var id = person.id
            if id == 0, let ergebnis = await AblageService.teamLaden(basis: url, pat: pat) {
                id = ergebnis.leute.first { $0.name == person.name }?.id ?? 0
            }
            if id > 0 {
                _ = await AblageService.teamFotoSenden(jpeg, id: id, basis: url, pat: pat)
            }
        }
        speichert = false
        fertig()
        zurueck()
    }

    private func hideKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),
                                        to: nil, from: nil, for: nil)
    }
}
