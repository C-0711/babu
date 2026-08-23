import SwiftUI

/// Die Angaben zu deinem Betrieb — bisher gab es sie nur im Portal im
/// Browser, obwohl die App an drei Stellen darauf zeigt („ändern kannst du
/// es in den Einstellungen"). Hier sind sie, in derselben Reihenfolge, in der
/// die Einrichtungskarte sie zählt.
struct BetriebsangabenView: View {
    @EnvironmentObject var store: AppStore

    /// Alles, was vom Server kam — damit beim Sichern nichts verloren geht,
    /// was dieses Formular gar nicht zeigt.
    @State private var angaben: [String: String] = [:]
    @State private var laedt = true
    @State private var sichert = false
    @State private var fehler: String?
    @State private var gesichert = false

    /// Der Kontenrahmen läuft NICHT über `angaben`: er wird nicht gespeichert,
    /// sondern gewechselt, und ein Wechsel hat eine Rückfrage und ein
    /// Anfangsjahr. Deshalb eine eigene Route und ein eigener Zustand.
    @State private var rahmen: Kontenrahmenstand?
    @State private var rahmenFrage: String?
    @State private var rahmenWunsch: String?
    @State private var rahmenMeldung: String?

    private static let rechtsformen = ["Einzelunternehmen", "GbR",
                                       "UG (haftungsbeschränkt)", "GmbH"]

    /// Bindung an einen Schlüssel im Wörterbuch — spart sieben @State-Felder
    /// und hält das, was gesichert wird, identisch mit dem, was gezählt wird.
    private func feld(_ schluessel: String) -> Binding<String> {
        Binding(get: { angaben[schluessel] ?? "" },
                set: { angaben[schluessel] = $0; gesichert = false })
    }

    private var fehlend: [String] { Einrichtung.fehlendeBetriebsfelder(angaben) }
    private var fertig: Int { Einrichtung.betriebsfelder.count - fehlend.count }

    var body: some View {
        Form {
            if store.verbundenAls == nil {
                Section {
                    Text("Diese Angaben liegen in deinem babu-Konto. "
                         + "Verbinde dich zuerst mit E-Mail und Passwort, "
                         + "dann kannst du sie hier ausfüllen.")
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                }
            } else if laedt {
                Section {
                    HStack { ProgressView(); Text("Einen Moment …")
                        .font(.footnote).foregroundStyle(GC.muted) }
                }
            } else {
                standAnzeige
                salonAbschnitt
                erreichbarkeitAbschnitt
                steuerAbschnitt
                kontenrahmenAbschnitt
                sichernAbschnitt
            }
        }
        .warmerGrund()
        .navigationTitle("Dein Betrieb")
        .navigationBarTitleDisplayMode(.inline)
        .task { await laden() }
        .alert("Kontenrahmen wechseln", isPresented: .constant(rahmenFrage != nil)) {
            Button("Abbrechen", role: .cancel) {
                rahmenFrage = nil; rahmenWunsch = nil
            }
            Button("Umstellen") {
                let wunsch = rahmenWunsch
                rahmenFrage = nil; rahmenWunsch = nil
                Task { await rahmenSetzen(wunsch, bestaetigt: true) }
            }
        } message: {
            Text(rahmenFrage ?? "")
        }
    }

    // MARK: - Die Abschnitte

    private var standAnzeige: some View {
        Section {
            HStack {
                Text(fehlend.isEmpty ? "Alles ausgefüllt"
                                     : "\(fertig) von \(Einrichtung.betriebsfelder.count) ausgefüllt")
                    .font(.subheadline)
                    .foregroundStyle(fehlend.isEmpty ? GC.ok : GC.fg)
                Spacer()
                if fehlend.isEmpty {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(GC.ok)
                }
            }
        } footer: {
            Text(fehlend.isEmpty
                 ? "Damit steht alles auf deinen Rechnungen, was daraufstehen muss."
                 : "Es fehlt noch: " + fehlend.joined(separator: ", ") + ".")
        }
    }

    private var salonAbschnitt: some View {
        Section {
            TextField("z. B. Salon Nina", text: feld("betrieb_name"))
            TextField("Straße, PLZ und Ort", text: feld("anschrift"), axis: .vertical)
                .lineLimit(1...3)
            Picker("Wie du angemeldet bist", selection: feld("rechtsform")) {
                Text("Bitte wählen").tag("")
                ForEach(Self.rechtsformen, id: \.self) { Text($0).tag($0) }
            }
        } header: {
            Text("Dein Salon")
        } footer: {
            Text("Das steht oben auf jeder Rechnung, die du stellst.")
        }
    }

    private var erreichbarkeitAbschnitt: some View {
        Section {
            TextField("Telefon", text: feld("telefon"))
                .keyboardType(.phonePad)
            TextField("E-Mail", text: feld("email"))
                .keyboardType(.emailAddress)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
        } header: {
            Text("Wie man dich erreicht")
        } footer: {
            Text("Kommt auf die Rechnung, damit Kundinnen bei Fragen wissen, wohin.")
        }
    }

    private var steuerAbschnitt: some View {
        Section {
            TextField("Dein Finanzamt", text: feld("finanzamt"))
            Picker("Umsatzsteuer", selection: feld("kleinunternehmer")) {
                Text("Bitte wählen").tag("")
                Text("Ich weise keine aus").tag("Ja")
                Text("Ich weise Umsatzsteuer aus").tag("Nein")
            }
            TextField("Steuernummer", text: feld("steuernummer"))
            TextField("USt-IdNr. (wenn du eine hast)", text: feld("ust_id"))
                .autocapitalization(.allCharacters)
                .autocorrectionDisabled()
        } header: {
            Text("Finanzamt und Steuer")
        } footer: {
            Text("„Ich weise keine aus“ heißt Kleinunternehmerin nach § 19 UStG — "
                 + "auf deinen Rechnungen steht dann keine Umsatzsteuer. "
                 + "Eine Steuernummer oder eine USt-IdNr. gehört auf jede Rechnung; "
                 + "eines von beiden reicht.")
        }
    }

    /// SKR03 oder SKR04. Die Entscheidung trifft meistens die Kanzlei, die den
    /// Abschluss macht — aber sie muss hier stehen, sonst kennt babu sie nicht.
    ///
    /// Bewusst kein stilles Picker-Speichern: der Wechsel geht über eine
    /// Rückfrage, und der Fußtext sagt vorher, warum das kein Schalter ist.
    @ViewBuilder
    private var kontenrahmenAbschnitt: some View {
        Section {
            if let rahmen {
                Picker("Kontenrahmen", selection: Binding(
                    get: { rahmen.rahmen },
                    set: { neu in
                        guard neu != rahmen.rahmen else { return }
                        Task { await rahmenSetzen(neu, bestaetigt: false) }
                    })) {
                    ForEach(rahmen.liste, id: \.self) { Text($0).tag($0) }
                }
                if !rahmen.gewaehlt {
                    Text("Noch nicht festgelegt — babu bucht so lange im "
                         + "\(rahmen.rahmen).")
                        .font(.footnote).foregroundStyle(GC.desc)
                }
                if let geplant = rahmen.geplantText {
                    Label(geplant, systemImage: "calendar")
                        .font(.footnote).foregroundStyle(GC.desc)
                }
                if let rahmenMeldung {
                    Text(rahmenMeldung).font(.footnote).foregroundStyle(GC.warn)
                }
            } else {
                Text("Wird geladen …").font(.footnote).foregroundStyle(GC.muted)
            }
        } header: {
            Text("Kontenrahmen")
        } footer: {
            Text("SKR03 und SKR04 vergeben dieselben Kontonummern für "
                 + "verschiedene Dinge. Ein Wechsel gilt deshalb erst ab dem "
                 + "nächsten 1. Januar — alles, was vorher gebucht ist, bleibt "
                 + "im alten Rahmen. Wenn du eine Steuerberatung hast, frag "
                 + "dort nach, welchen sie führt.")
        }
    }

    private var sichernAbschnitt: some View {
        Section {
            Button {
                Task { await sichern() }
            } label: {
                HStack {
                    Text(sichert ? "Wird gesichert …" : "Sichern")
                    if sichert { Spacer(); ProgressView() }
                }
            }
            .disabled(sichert)
            if let fehler {
                Text(fehler).font(.footnote).foregroundStyle(GC.warn)
            }
            if gesichert {
                Label("Gesichert", systemImage: "checkmark.circle")
                    .font(.footnote).foregroundStyle(GC.ok)
            }
        } footer: {
            Text("Die Angaben liegen in deinem babu-Konto — auf jedem Gerät dieselben.")
        }
    }

    // MARK: - Laden und sichern

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { laedt = false; return }
        angaben = await AblageService.stammdatenLaden(basis: url, pat: pat) ?? [:]
        rahmen = await AblageService.kontenrahmenLaden(basis: url, pat: pat)
        laedt = false
    }

    /// Wechseln, nicht speichern: ohne Bestätigung antwortet der Server mit
    /// seiner Rückfrage, und die stellen wir wörtlich. Sie in der App neu zu
    /// formulieren hieße, zwei Wahrheiten zu pflegen.
    private func rahmenSetzen(_ neu: String?, bestaetigt: Bool) async {
        guard let neu,
              let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        rahmenMeldung = nil
        let antwort = await AblageService.kontenrahmenSetzen(
            neu, bestaetigt: bestaetigt, basis: url, pat: pat)
        if let stand = antwort.stand { rahmen = stand }
        if let frage = antwort.rueckfrage, !bestaetigt {
            rahmenWunsch = neu
            rahmenFrage = frage
        } else if let grund = antwort.fehler {
            rahmenMeldung = grund
        }
    }

    private func sichern() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            fehler = "Dafür musst du zuerst mit deinem Konto verbinden."
            return
        }
        sichert = true
        fehler = nil
        // Nur die Felder senden, die dieses Formular auch zeigt. Was der
        // Server sonst noch führt (Briefkopf, Öffnungszeiten), bleibt so
        // unangetastet, selbst wenn es beim Laden mitkam.
        var meine = Dictionary(uniqueKeysWithValues:
            Einrichtung.betriebsfelder.map { ($0.schluessel, angaben[$0.schluessel] ?? "") })
        meine["steuernummer"] = angaben["steuernummer"] ?? ""
        meine["ust_id"] = angaben["ust_id"] ?? ""
        let ok = await AblageService.betriebsangabenSichern(meine, basis: url, pat: pat)
        sichert = false
        gesichert = ok
        fehler = ok ? nil
            : "Das hat gerade nicht geklappt — Internet prüfen und noch einmal versuchen."
    }
}

/// Was der Server über den Kontenrahmen des Betriebs sagt.
struct Kontenrahmenstand {
    let rahmen: String
    let liste: [String]
    /// Hat der Betrieb selbst gewählt, oder gilt nur die Vorgabe des Dienstes?
    let gewaehlt: Bool
    /// Ein bestätigter, aber noch nicht wirksamer Wechsel.
    let geplantJahr: Int?
    let geplantRahmen: String?

    var geplantText: String? {
        guard let geplantJahr, let geplantRahmen else { return nil }
        return "Ab 1. Januar \(geplantJahr) wird auf \(geplantRahmen) "
             + "umgestellt. Bis dahin bucht babu weiter im \(rahmen)."
    }

    init?(_ json: [String: Any]) {
        guard let rahmen = json["rahmen"] as? String else { return nil }
        self.rahmen = rahmen
        self.liste = (json["rahmen_liste"] as? [String]) ?? [rahmen]
        self.gewaehlt = (json["gewaehlt"] as? Bool) ?? false
        let geplant = json["wechsel_geplant"] as? [String: Any]
        self.geplantJahr = geplant?["jahr"] as? Int
        self.geplantRahmen = geplant?["rahmen"] as? String
    }
}

extension AblageService {
    /// Den Kontenrahmen abrufen (`GET /api/kontenrahmen`).
    static func kontenrahmenLaden(basis: URL, pat: String) async -> Kontenrahmenstand? {
        var request = URLRequest(url: basis.appendingPathComponent("api/kontenrahmen"))
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else { return nil }
        return Kontenrahmenstand(json)
    }

    /// Den Kontenrahmen wechseln (`POST /api/kontenrahmen`).
    ///
    /// Ohne `bestaetigt` antwortet der Server mit 409 und einer Rückfrage —
    /// das ist kein Fehler, sondern der vorgesehene Weg. Deshalb kommen Stand,
    /// Rückfrage und Fehler getrennt zurück.
    static func kontenrahmenSetzen(_ rahmen: String, bestaetigt: Bool,
                                   basis: URL, pat: String) async
            -> (stand: Kontenrahmenstand?, rueckfrage: String?, fehler: String?) {
        var request = URLRequest(url: basis.appendingPathComponent("api/kontenrahmen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["rahmen": rahmen, "bestaetigt": bestaetigt])
        guard let (daten, _) = try? await URLSession.shared.data(for: request),
              let json = try? JSONSerialization.jsonObject(with: daten) as? [String: Any]
        else {
            return (nil, nil, "Das hat gerade nicht geklappt — Internet prüfen.")
        }
        // Bei Erfolg trägt die Antwort auch eine Begründung („Wechsel von …
        // zum 1. Januar …"). Die ist keine Fehlermeldung und darf nicht als
        // eine erscheinen — nur ein abgelehnter Wechsel wird gemeldet.
        let erlaubt = (json["erlaubt"] as? Bool) ?? true
        let grund = (json["fehler"] as? String)
            ?? (erlaubt ? nil : json["begruendung"] as? String)
        return (Kontenrahmenstand(json), json["rueckfrage"] as? String, grund)
    }

    /// Betriebsangaben ins babu-Konto schreiben (`POST /api/einstellungen`).
    /// Der Server nimmt nur bekannte Schlüssel an und ignoriert den Rest.
    static func betriebsangabenSichern(_ angaben: [String: String], basis: URL,
                                       pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent("api/einstellungen"))
        request.httpMethod = "POST"
        request.timeoutInterval = 30
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: angaben)
        guard let (_, antwort) = try? await URLSession.shared.data(for: request),
              let http = antwort as? HTTPURLResponse else { return false }
        return (200..<300).contains(http.statusCode)
    }
}
