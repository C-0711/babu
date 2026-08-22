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
    @State private var zeigeWerksDialog = false
    @State private var setztZurueck = false
    @State private var werksErgebnis: String?

    var body: some View {
        Form {
                if verbunden {
                    verbundenBereich
                } else {
                    anmeldenBereich
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
        // Am Form, nicht an der Section: ein Dialog auf einer Section wird
        // je Zeile angelegt und schluckt dort die Berührungen — der
        // Testschalter ließ sich deshalb nicht umlegen.
        .confirmationDialog("Auf Werkseinstellung zurücksetzen?",
                            isPresented: $zeigeWerksDialog,
                            titleVisibility: .visible) {
            Button("Zurücksetzen", role: .destructive) {
                Task { await zuruecksetzen() }
            }
            Button("Abbrechen", role: .cancel) { }
        } message: {
            Text("Das Onboarding und die Einrichtungsangaben gehen zurück "
                 + "auf Anfang. Deine Anmeldung und deine Belegbox bleiben.")
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
                        Text(setztZurueck ? "Setze zurück …"
                                          : "Auf Werkseinstellung zurücksetzen")
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
            Button("Verbindung trennen", role: .destructive) {
                zeigeLoeschDialog = true
            }
        } header: {
            Text("Dein babu-Konto")
        } footer: {
            Text("Die Verbindung bleibt sicher auf diesem Gerät.")
        }
        .confirmationDialog("Verbindung wirklich trennen?",
                            isPresented: $zeigeLoeschDialog,
                            titleVisibility: .visible) {
            Button("Ja, trennen", role: .destructive) {
                KeychainHelfer.loeschePAT()
                verbunden = false
                store.verbundenAls = nil
                store.ablageAktiv = false   // ehrlich: ohne Verbindung geht nichts mehr
                testErgebnis = nil
                kontoFehler = nil
            }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Danach kann die App keine Belege und kein Kassenbuch mehr in deine Belegbox legen, und Fragen bleiben unbeantwortet. Zum Wiederverbinden reichen E-Mail und Passwort.")
        }
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
