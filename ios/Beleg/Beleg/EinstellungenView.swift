import SwiftUI
import UIKit

/// Verbindung zur Belegbox — so einfach wie das Portal: E-Mail + Passwort,
/// der Geräteschlüssel entsteht unsichtbar im Hintergrund und wandert in die
/// Keychain. Der technische Zugangscode-Weg bleibt für die Einrichtung
/// erreichbar, aber außer Sicht.
struct EinstellungenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var email = ""
    @State private var passwort = ""
    @State private var kontoFehler: String?
    @State private var verbindet = false

    @State private var pat = ""
    @State private var patGespeichert = KeychainHelfer.ladePAT() != nil
    @State private var testErgebnis: String?
    @State private var testLaeuft = false
    @State private var zeigeLoeschDialog = false

    var body: some View {
        NavigationStack {
            Form {
                if patGespeichert {
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
                    .disabled(testLaeuft || !patGespeichert)
                    if let ergebnis = testErgebnis {
                        Text(ergebnis)
                            .font(.footnote)
                            .foregroundStyle(ergebnis.hasPrefix("Verbunden") ? GC.ok : GC.warn)
                    }
                } footer: {
                    Text("Ohne Verbindung bleiben Belege in der Warteschlange und werden nachgereicht, sobald es wieder klappt.")
                }

                DisclosureGroup("Für die Einrichtung (Technik)") {
                    TextField(AppStore.ablageStandardURL, text: $store.ablageURL)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .font(.callout.monospaced())
                    SecureField(patGespeichert ? "Zugangscode ersetzen — neu einfügen"
                                               : "Zugangscode einfügen",
                                text: $pat)
                        .font(.callout.monospaced())
                }
            }
            .navigationTitle("Belegbox")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") {
                        patSpeichernFallsEingegeben()
                        dismiss()
                    }
                }
            }
        }
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
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(GC.ok)
                Text(store.verbundenAls.map { "Verbunden als \($0)" } ?? "Verbunden ✓")
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
                patGespeichert = false
                pat = ""
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
        guard let url = URL(string: store.ablageURL) else {
            kontoFehler = "Die Adresse sieht nicht richtig aus — bitte unter Technik prüfen."
            return
        }
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
                patGespeichert = true
                store.verbundenAls = ergebnis.un
                store.ablageAktiv = true
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

    // MARK: - Technik-Weg (Zugangscode) — für die Einrichtung, nicht für den Alltag

    private func patSpeichernFallsEingegeben() {
        let neu = pat.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !neu.isEmpty else { return }
        KeychainHelfer.speicherePAT(neu)
        patGespeichert = true
        pat = ""
    }

    private func teste() {
        patSpeichernFallsEingegeben()
        guard let url = URL(string: store.ablageURL) else {
            testErgebnis = "Die Adresse sieht nicht richtig aus — bitte prüfen."
            return
        }
        guard let gespeichert = KeychainHelfer.ladePAT() else {
            testErgebnis = "Bitte zuerst mit deinem Konto verbinden."
            return
        }
        testLaeuft = true
        testErgebnis = nil
        Task {
            let ergebnis = await AblageService.verbindungstest(basis: url, pat: gespeichert)
            switch ergebnis {
            case .uebertragen: testErgebnis = "Verbunden ✓ — alles bereit."
            case .tokenFehler: testErgebnis = "Die Verbindung stimmt nicht mehr — bitte neu mit deinem Konto verbinden."
            case .abgelehnt: testErgebnis = "Die Belegbox meldet einen Fehler — später noch einmal versuchen."
            case .nichtErreichbar: testErgebnis = "Keine Verbindung — Internet prüfen und noch einmal versuchen."
            }
            testLaeuft = false
        }
    }
}
