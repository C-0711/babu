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
                sichernAbschnitt
            }
        }
        .warmerGrund()
        .navigationTitle("Dein Betrieb")
        .navigationBarTitleDisplayMode(.inline)
        .task { await laden() }
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
        laedt = false
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

extension AblageService {
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
