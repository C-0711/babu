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
    /// Der zweite, kleine Weg: mit Passwort statt Link (seit 08.10.2026).
    @State private var mitPasswort = false
    /// Der Link ist unterwegs — jetzt zählt das Postfach, nicht dieses Formular.
    @State private var linkGeschicktAn: String?

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

                // Nur in Entwicklungs-Builds: „Dieses Gerät leer räumen" gehört
                // nicht vor eingeladene Betriebe. Ein TestFlight-Build ist
                // Release — dort gibt es den Abschnitt nicht.
                #if DEBUG
                testphase
                #endif

                // Die drei Seiten, die jede Nutzerin ohne Konto lesen kann —
                // dieselben, die Apple bei der Einreichung verlangt.
                Section {
                    if let ds = URL(string: store.ablageURL + "/datenschutz") {
                        Link("Datenschutz", destination: ds)
                    }
                    if let ab = URL(string: store.ablageURL + "/agb") {
                        Link("Nutzungsbedingungen", destination: ab)
                    }
                    if let im = URL(string: store.ablageURL + "/impressum") {
                        Link("Impressum", destination: im)
                    }
                    if let avv = URL(string: store.ablageURL + "/app/avv.pdf") {
                        Link("Auftragsverarbeitung (PDF)", destination: avv)
                    }
                } header: {
                    Text("Rechtliches")
                }

                Section {
                } footer: {
                    // Sprachregel (HANDOVER §1): keine Systemnamen in der UI.
                    // Bis 17.09.2026 stand hier „running on GitChain“.
                    HStack(spacing: 6) {
                        Image(systemName: "seal")
                        Text("babu · 0711 Intelligence")
                    }
                    .frame(maxWidth: .infinity)
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.muted)
                }
            }
        .warmerGrund()
        .navigationTitle("Einstellungen")
        .navigationBarTitleDisplayMode(.inline)
        // Der Link aus der Mail meldet an, während diese Seite offen ist
        // (meist ist sie es noch — hier wurde er bestellt). Dann soll sie
        // nicht weiter „Schau in dein Postfach" sagen.
        .onChange(of: store.verbundenAls) { _, neu in
            guard neu != nil, KeychainHelfer.ladePAT() != nil else { return }
            verbunden = true
            linkGeschicktAn = nil
            abgemeldet = false
            kontoFehler = nil
            testErgebnis = store.istAmbassador == true && store.ablageFehlt
                ? "Verbunden ✓ — unter „Empfehlen“ geht es los."
                : "Verbunden ✓"
        }
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
                 + "liegt, bleibt dort. Neue Belege "
                 + (Ausbaustufe.erreichbar(.kasse) ? "und Kassenbuchblätter " : "")
                 + "kommen von diesem Telefon aus aber nicht mehr an, und "
                 + "Fragen bleiben unbeantwortet. Wieder anmelden kannst du "
                 + "dich jederzeit mit deiner E-Mail.")
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
                // Konzeptstudie V2: eine Seite statt Reiter. Der Schalter
                // tauscht die Wurzel — diese Einstellungen gehen damit zu.
                Toggle(isOn: $store.einKnopf) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Konzept „Ein Knopf“ ausprobieren")
                        Text("Eine Seite statt Reiter: eine Zahl, ein Satz, ein Knopf. "
                             + "Zurück geht es über das kleine „Konzept“ oben rechts.")
                            .font(.caption).foregroundStyle(GC.desc)
                    }
                }

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

    /// Seit 08.10.2026 der Hauptweg: E-Mail eintippen (das iPhone schlägt
    /// sie vor), Link schicken lassen, in der Mail antippen — drin. Kein
    /// Passwort, das sie sich merken oder abtippen muss. Das Passwort bleibt
    /// als kleiner zweiter Weg darunter.
    @ViewBuilder
    private var anmeldenBereich: some View {
        Section {
            // Nach dem Abmelden keine leere Ansicht, sondern der Weg zurück.
            // Sonst steht da nur ein Formular und die Frage, was gerade
            // passiert ist.
            if abgemeldet, linkGeschicktAn == nil {
                Label {
                    Text("Abgemeldet. Mit deiner E-Mail wieder anmelden.")
                        .font(.footnote)
                        .foregroundStyle(GC.body)
                } icon: {
                    Image(systemName: "checkmark.circle").foregroundStyle(GC.ok)
                }
            }
            if let an = linkGeschicktAn, !mitPasswort {
                postfachHinweis(an)
            } else {
                TextField("Deine E-Mail", text: $email)
                    .keyboardType(.emailAddress)
                    .textContentType(.emailAddress)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                if mitPasswort {
                    SecureField("Passwort", text: $passwort)
                        .textContentType(.password)
                    // Der Weg zum neuen Passwort führt über das Portal — dort
                    // steht dasselbe Formular, das die Mail mit dem Link
                    // verschickt. Die App braucht dafür keinen eigenen
                    // Bildschirm, nur die Tür.
                    if let portal = URL(string: store.ablageURL + "/portal#passwort-vergessen") {
                        Link("Passwort vergessen?", destination: portal)
                            .font(.footnote)
                    }
                    Button {
                        verbinden()
                    } label: {
                        HStack {
                            Text("Verbinden")
                            if verbindet { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(verbindet || emailLeer || passwort.isEmpty)
                } else {
                    // Eine Zeile wie „Verbinden" und „Verbindung testen" —
                    // im Formular sehen Knöpfe hier überall so aus.
                    Button {
                        linkSchicken()
                    } label: {
                        HStack {
                            Label("Link schicken", systemImage: "envelope")
                            if verbindet { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(verbindet || emailLeer)
                }
            }
            if let fehler = kontoFehler {
                Text(fehler)
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
            }
            Button(mitPasswort ? "Lieber einen Link per E-Mail" : "Mit Passwort anmelden") {
                mitPasswort.toggle()
                kontoFehler = nil
            }
            .font(.footnote)
        } header: {
            Text("Dein babu-Konto")
        } footer: {
            Text(mitPasswort
                 ? "Dieselbe Anmeldung wie im Portal. Mehr braucht es nicht — alles Weitere passiert von selbst."
                 : "Wir schicken dir einen Link. Ein Tipp darauf, und du bist drin — ganz ohne Passwort.")
        }
    }

    private var emailLeer: Bool {
        email.trimmingCharacters(in: .whitespaces).isEmpty
    }

    /// „Schau in dein Postfach" — und was zu tun ist, wenn nichts kommt.
    private func postfachHinweis(_ an: String) -> some View {
        // Gebaut wie „Deine Ablage wird noch eingerichtet": Zeichen,
        // Überschrift in Serife, ein Satz darunter.
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "envelope.open")
                    .font(.title3)
                    .foregroundStyle(GC.accent)
                    .padding(.top, 2)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Schau in dein Postfach — tipp dort auf den Link.")
                        .font(.headline)
                        .fontDesign(.serif)
                        .foregroundStyle(GC.fg)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Er ist unterwegs an \(an). Kommt nichts, schau auch im Spam-Ordner nach.")
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            HStack(spacing: 18) {
                Button("Nochmal schicken") { linkSchicken() }
                    .disabled(verbindet)
                Button("Andere E-Mail") {
                    linkGeschicktAn = nil
                    kontoFehler = nil
                }
            }
            .font(.footnote)
            .buttonStyle(.borderless)
            .padding(.top, 2)
        }
        .padding(.vertical, 6)
    }

    private func linkSchicken() {
        guard let url = URL(string: store.ablageURL) else { return }
        let an = email.trimmingCharacters(in: .whitespaces)
        guard !an.isEmpty else { return }
        verbindet = true
        kontoFehler = nil
        Task {
            if let fehler = await AblageService.anmeldelinkSchicken(email: an, basis: url) {
                kontoFehler = fehler
            } else {
                linkGeschicktAn = an
                abgemeldet = false
            }
            verbindet = false
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
                 + "Belege, "
                 + (Ausbaustufe.erreichbar(.kasse) ? "dein Kassenbuch " : "deine Dokumente ")
                 + "und dein Konto bleiben, wie sie sind.")
        }
        // Die Rückfrage dazu hängt am Form, nicht hier: eine Section ist keine
        // eigene Ansicht, ihre Modifier landen je Zeile — und ein Alert je
        // Zeile ist einer zu viel.
    }

    /// Dieses Gerät abmelden. Steht als eigene Funktion da, weil die
    /// Rückfrage oben am Form hängt und der Knopf hier unten sitzt.
    private func abmelden() {
        store.abmelden()
        verbunden = false
        linkGeschicktAn = nil
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
                verbunden = true
                email = ""
                passwort = ""
                // Derselbe Weg wie beim Link aus der Mail: Keychain, Name,
                // Ablage, Rolle und Rechte (`AppStore.anmeldungUebernehmen`).
                await store.anmeldungUebernehmen(schluessel: schluessel, un: ergebnis.un,
                                                 rolle: nil, ablage: ergebnis.ablage)
                // Nur „alles bereit" sagen, wenn es das auch ist. Ein
                // selbst angelegtes Konto hat noch keine Ablage; bis
                // 08.09.2026 behauptete die App trotzdem, es sei alles
                // fertig, und schickte jeden Beleg gegen eine Wand.
                if ergebnis.ablage {
                    testErgebnis = "Verbunden ✓ — alles bereit."
                } else if store.istAmbassador == true {
                    // Eine Ambassadorin ohne eigenen Salon bekommt keine
                    // Ablage — für sie gibt es nichts, worauf sie warten müsste.
                    testErgebnis = "Verbunden ✓ — unter „Empfehlen“ geht es los."
                } else {
                    testErgebnis = "Verbunden ✓ — deine Ablage wird noch "
                        + "eingerichtet. Fotografier ruhig weiter: alles "
                        + "bleibt auf dem Telefon und geht los, sobald sie da ist."
                }
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
                store.ablageFehlt = false
            case .tokenFehler:
                testErgebnis = "Die Verbindung stimmt nicht mehr — bitte neu mit deinem Konto verbinden."
                store.zugangAbgelaufen = true
            case .keineAblage:
                // Das ist kein Fehler, sondern ein Zwischenstand: das Konto
                // stimmt, die Ablage wird noch eingerichtet. Eine
                // Ambassadorin ohne Salon bekommt keine — ihr Konto stimmt.
                testErgebnis = store.istAmbassador == true
                    ? "Verbunden ✓ — dein Konto stimmt."
                    : "Dein Konto stimmt — deine Ablage wird noch "
                    + "eingerichtet. Bis dahin bleibt alles auf dem Telefon."
                store.zugangAbgelaufen = false
                store.ablageFehlt = true
            case .abgelehnt: testErgebnis = "Die Belegbox meldet einen Fehler — später noch einmal versuchen."
            case .nichtErreichbar: testErgebnis = "Keine Verbindung — Internet prüfen und noch einmal versuchen."
            }
            testLaeuft = false
        }
    }
}
