import SwiftUI
import UIKit

/// Verbindung zur Belegbox — genau eine Sache: mit dem babu-Konto anmelden.
/// Der Geräteschlüssel kommt automatisch vom Server und wandert unsichtbar
/// in die Keychain. Technik (GitChain, Schlüssel, Adressen) bleibt komplett
/// hinter den Kulissen — sichtbar ist nur „running on GitChain".
struct EinstellungenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var email = ""
    @State private var passwort = ""
    @State private var kontoFehler: String?
    @State private var verbindet = false

    @State private var verbunden = KeychainHelfer.ladePAT() != nil
    @State private var testErgebnis: String?
    @State private var testLaeuft = false
    @State private var zeigeLoeschDialog = false
    /// Gerade abgemeldet — dann steht über dem Anmeldeformular, was passiert
    /// ist und wie es weitergeht.
    @State private var abgemeldet = false
    @State private var zeigeWerksDialog = false
    @State private var setztZurueck = false
    @State private var werksErgebnis: String?
    /// Gehört der Startseite (CaptureTab), wird hier aber zurückgesetzt.
    @AppStorage("einrichtungFertig") private var einrichtungFertig = false

    var body: some View {
        Form {
                if verbunden {
                    verbundenBereich
                } else {
                    anmeldenBereich
                }

                // Die App verwies an drei Stellen auf „die Einstellungen",
                // wenn Betriebsname, Anschrift oder Steuernummer fehlten —
                // nur gab es sie hier nie, sondern ausschließlich im Portal
                // im Browser. Jetzt gibt es sie hier.
                Section {
                    NavigationLink {
                        BetriebsangabenView()
                    } label: {
                        Label("Dein Betrieb", systemImage: "building.2")
                    }
                } footer: {
                    Text("Name, Anschrift, Finanzamt und Steuernummer — das, "
                         + "was auf jeder Rechnung stehen muss.")
                }

                Section {
                    Toggle("Belege automatisch ablegen und gegenprüfen",
                           isOn: $store.ablageAktiv)
                } footer: {
                    Text("Jeder Beleg wandert nach der Aufnahme in deine Belegbox und wird dort ein zweites Mal geprüft.")
                }
                .onChange(of: store.ablageAktiv) { _, an in
                    if an { store.altBelegeNachreichen() }
                }

                Section {
                    Button {
                        teste()
                    } label: {
                        HStack {
                            Text("Verbindung testen")
                            if testLaeuft { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(testLaeuft || !verbunden)
                    if let ergebnis = testErgebnis {
                        Text(ergebnis)
                            .font(.footnote)
                            .foregroundStyle(ergebnis.hasPrefix("Verbunden") ? GC.ok : GC.warn)
                    }
                } footer: {
                    Text("Ohne Verbindung bleiben Belege in der Warteschlange und werden nachgereicht, sobald es wieder klappt.")
                }

                testphase

                Section {
                } footer: {
                    HStack(spacing: 6) {
                        Image(systemName: "seal")
                        Text("running on GitChain")
                    }
                    .frame(maxWidth: .infinity)
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.muted)
                }
            }
        .warmerGrund()
        .navigationTitle("Einstellungen")
        .navigationBarTitleDisplayMode(.inline)
        // Beide Rückfragen dieser Seite hängen hier am Form — und beide sind
        // `alert`, nicht mehr `confirmationDialog`. Grund, im Simulator
        // nachgemessen (iOS 26, iPhone 16e): ein `confirmationDialog` wird
        // dort an seinen Auslöser geheftet und als schmales Popover gezeigt.
        // Darin fällt der Abbrechen-Knopf ersatzlos weg — sichtbar blieb
        // allein „Ja, leer räumen“ bzw. „Ja, abmelden“, der lange Erklärtext
        // gequetscht auf halbe Breite. Eine Rückfrage, bei der man das Nein
        // nicht sieht, ist keine Rückfrage, sondern eine Falle. `alert`
        // erscheint mittig, in voller Breite und zeigt beide Knöpfe.
        //
        // Was NICHT die Ursache war: die Schalter. Der frühere Kommentar hier
        // vermutete, ein Dialog schlucke die Berührungen. Nachgemessen legen
        // sich „Belege automatisch ablegen“ und „Testwerkzeuge zeigen“ bei
        // jeder Berührung um — angemeldet wie abgemeldet, mit beiden Dialogen
        // im Baum.
        //
        // Die Rückfrage nennt außerdem alles, was verschwindet: der Knopf
        // räumt neben Onboarding und Einrichtungsangaben auch Belege,
        // Kassenberichte, Chatverlauf und Rechnungsvorlagen von diesem Gerät.
        .alert("Dieses Gerät leer räumen?", isPresented: $zeigeWerksDialog) {
            Button("Abbrechen", role: .cancel) { }
            Button("Ja, leer räumen", role: .destructive) {
                Task { await zuruecksetzen() }
            }
        } message: {
            Text("Von diesem Telefon verschwinden: deine Belege und "
                 + "Kassenberichte, der Chatverlauf, deine Rechnungsvorlagen "
                 + "und deine Angaben zum Betrieb. "
                 + "In deiner Belegbox bleibt alles erhalten, und angemeldet "
                 + "bleibst du auch. Danach fängt die App wieder mit dem "
                 + "Begrüßungsbildschirm an.")
        }
        .alert("Dieses Gerät abmelden?", isPresented: $zeigeLoeschDialog) {
            Button("Abbrechen", role: .cancel) { }
            Button("Ja, abmelden", role: .destructive) { abmelden() }
        } message: {
            Text("Es geht nichts verloren: Alles, was schon in deiner Belegbox "
                 + "liegt, bleibt dort. Neue Belege und Kassenbuchblätter "
                 + "kommen von diesem Telefon aus aber nicht mehr an, und "
                 + "Fragen bleiben unbeantwortet. Wieder anmelden kannst du "
                 + "dich jederzeit mit E-Mail und Passwort.")
        }
    }

    // MARK: - Testphase

    /// Solange babu erprobt wird, muss sich das Onboarding wieder ansehen
    /// lassen — ohne sich jedes Mal neu anzumelden und ohne dass Belege
    /// verschwinden. Beides steht ausdrücklich im Dialog, weil ein
    /// Zurücksetzen sonst zu Recht Angst macht.
    @ViewBuilder
    private var testphase: some View {
        Section {
            Toggle("Testwerkzeuge zeigen", isOn: $store.testmodus)

            if store.testmodus {
                VStack(alignment: .leading, spacing: 10) {
                    liste("Wird zurückgesetzt", AppStore.werkseinstellungGeht,
                          symbol: "arrow.counterclockwise", farbe: GC.accent)
                    liste("Bleibt", AppStore.werkseinstellungBleibt,
                          symbol: "lock", farbe: GC.ok)
                }
                .padding(.vertical, 4)

                Button(role: .destructive) {
                    zeigeWerksDialog = true
                } label: {
                    HStack {
                        if setztZurueck { ProgressView().padding(.trailing, 6) }
                        Text(setztZurueck ? "Räume leer …"
                                          : "Dieses Gerät leer räumen")
                    }
                }
                .disabled(setztZurueck)

                if let werksErgebnis {
                    Text(werksErgebnis).font(.footnote).foregroundStyle(GC.muted)
                }
            }
        } header: {
            Text("Testphase")
        } footer: {
            Text(store.testmodus
                 ? "Danach startet die App wieder mit dem Begrüßungsbildschirm. "
                   + "Du bleibst angemeldet."
                 : "Werkzeuge zum Erproben — im Alltag ausgeschaltet lassen.")
        }
    }

    private func liste(_ titel: String, _ punkte: [String],
                       symbol: String, farbe: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(titel, systemImage: symbol)
                .font(.caption.weight(.semibold)).foregroundStyle(farbe)
            ForEach(punkte, id: \.self) { punkt in
                Text("· " + punkt).font(.caption).foregroundStyle(GC.desc)
            }
        }
    }

    private func zuruecksetzen() async {
        setztZurueck = true
        werksErgebnis = nil
        // Wer wieder bei null anfängt, soll auch wieder die Einrichtungskarte
        // sehen — sonst führt der Weg zurück ins Leere.
        einrichtungFertig = false
        let serverOk = await store.aufWerkseinstellung()
        setztZurueck = false
        // Die App wechselt gleich auf den Begrüßungsbildschirm; die Meldung
        // zählt nur für den Fall, dass der Server nicht erreichbar war.
        werksErgebnis = serverOk ? nil
            : "Lokal zurückgesetzt. Die Einrichtungsangaben auf dem Server "
            + "blieben stehen — ohne Verbindung geht das nicht."
    }

    // MARK: - Verbinden mit dem ganz normalen Konto

    private var anmeldenBereich: some View {
        Section {
            // Nach dem Abmelden keine leere Ansicht, sondern der Weg zurück.
            // Sonst steht da nur ein Formular und die Frage, was gerade
            // passiert ist.
            if abgemeldet {
                Label {
                    Text("Abgemeldet. Mit E-Mail und Passwort wieder verbinden.")
                        .font(.footnote)
                        .foregroundStyle(GC.body)
                } icon: {
                    Image(systemName: "checkmark.circle").foregroundStyle(GC.ok)
                }
            }
            TextField("E-Mail", text: $email)
                .keyboardType(.emailAddress)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
            SecureField("Passwort", text: $passwort)
            Button {
                verbinden()
            } label: {
                HStack {
                    Text("Verbinden")
                    if verbindet { Spacer(); ProgressView() }
                }
            }
            .disabled(verbindet || email.trimmingCharacters(in: .whitespaces).isEmpty
                      || passwort.isEmpty)
            if let fehler = kontoFehler {
                Text(fehler)
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
            }
        } header: {
            Text("Dein babu-Konto")
        } footer: {
            Text("Dieselbe Anmeldung wie im Portal. Mehr braucht es nicht — alles Weitere passiert von selbst.")
        }
    }

    private var verbundenBereich: some View {
        Section {
            HStack(spacing: 10) {
                Image(systemName: store.zugangAbgelaufen
                      ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                    .foregroundStyle(store.zugangAbgelaufen ? GC.warn : GC.ok)
                VStack(alignment: .leading, spacing: 2) {
                    Text(store.verbundenAls.map { "Verbunden als \($0)" } ?? "Verbunden ✓")
                    if store.zugangAbgelaufen {
                        Text("Der Zugang gilt nicht mehr — bitte neu verbinden.")
                            .font(.caption)
                            .foregroundStyle(GC.warn)
                    }
                }
            }
            // „Verbindung trennen" sagte nicht, was getrennt wird — und wer
            // einen roten Knopf drückt, dessen Wort er nicht kennt, glaubt
            // hinterher, etwas gelöscht zu haben. Der Knopf heißt jetzt, was
            // er tut: dieses eine Gerät meldet sich ab.
            Button("Dieses Gerät abmelden", role: .destructive) {
                zeigeLoeschDialog = true
            }
        } header: {
            Text("Dein babu-Konto")
        } footer: {
            Text("Abmelden heißt: Dieses Telefon schickt nichts mehr in deine "
                 + "Belegbox. Es heißt NICHT, dass etwas gelöscht wird — deine "
                 + "Belege, dein Kassenbuch und dein Konto bleiben, wie sie sind.")
        }
        // Die Rückfrage dazu hängt am Form, nicht hier: eine Section ist keine
        // eigene Ansicht, ihre Modifier landen je Zeile — und ein Alert je
        // Zeile ist einer zu viel.
    }

    /// Dieses Gerät abmelden. Steht als eigene Funktion da, weil die
    /// Rückfrage oben am Form hängt und der Knopf hier unten sitzt.
    private func abmelden() {
        KeychainHelfer.loeschePAT()
        verbunden = false
        store.verbundenAls = nil
        store.ablageAktiv = false   // ehrlich: ohne Verbindung geht nichts mehr
        testErgebnis = nil
        kontoFehler = nil
        abgemeldet = true
    }

    private func verbinden() {
        guard let url = URL(string: store.ablageURL) else { return }
        verbindet = true
        kontoFehler = nil
        Task {
            let ergebnis = await AblageService.appAnmelden(
                email: email.trimmingCharacters(in: .whitespaces),
                passwort: passwort,
                geraet: UIDevice.current.name,
                basis: url)
            if let schluessel = ergebnis.schluessel {
                KeychainHelfer.speicherePAT(schluessel)
                verbunden = true
                store.verbundenAls = ergebnis.un
                store.ablageAktiv = true
                store.zugangAbgelaufen = false
                email = ""
                passwort = ""
                testErgebnis = "Verbunden ✓ — alles bereit."
                store.ablageRetry()
            } else {
                kontoFehler = ergebnis.fehler
            }
            verbindet = false
        }
    }

    private func teste() {
        guard let url = URL(string: store.ablageURL) else { return }
        guard let gespeichert = KeychainHelfer.ladePAT() else {
            testErgebnis = "Bitte zuerst mit deinem Konto verbinden."
            return
        }
        testLaeuft = true
        testErgebnis = nil
        Task {
            let ergebnis = await AblageService.verbindungstest(basis: url, pat: gespeichert)
            switch ergebnis {
            case .uebertragen:
                testErgebnis = "Verbunden ✓ — alles bereit."
                store.zugangAbgelaufen = false
            case .tokenFehler:
                testErgebnis = "Die Verbindung stimmt nicht mehr — bitte neu mit deinem Konto verbinden."
                store.zugangAbgelaufen = true
            case .abgelehnt: testErgebnis = "Die Belegbox meldet einen Fehler — später noch einmal versuchen."
            case .nichtErreichbar: testErgebnis = "Keine Verbindung — Internet prüfen und noch einmal versuchen."
            }
            testLaeuft = false
        }
    }
}
