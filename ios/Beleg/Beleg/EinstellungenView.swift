import SwiftUI

/// Konfiguration der Belegbox-Übertragung (GitChain-Ablage auf der H200V).
/// Opt-in: ohne aktivierten Toggle + gespeicherten PAT bleibt die App
/// vollständig on-device.
struct EinstellungenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var pat = ""
    @State private var patGespeichert = KeychainHelfer.ladePAT() != nil
    @State private var testErgebnis: String?
    @State private var testLaeuft = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Belege automatisch ablegen und gegenprüfen",
                           isOn: $store.ablageAktiv)
                } footer: {
                    Text("Jeder Beleg wandert nach der Aufnahme in deine Belegbox und wird dort ein zweites Mal geprüft.")
                }
                .onChange(of: store.ablageAktiv) { _, an in
                    if an { store.altBelegeNachreichen() }
                }

                Section("Adresse der Belegbox") {
                    TextField(AppStore.ablageStandardURL, text: $store.ablageURL)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .font(.callout.monospaced())
                }

                Section {
                    SecureField(patGespeichert ? "Zugangsschlüssel gespeichert ✓ — zum Ersetzen neu einfügen"
                                               : "Zugangsschlüssel einfügen",
                                text: $pat)
                        .font(.callout.monospaced())
                    if patGespeichert {
                        Button("Zugangsschlüssel löschen", role: .destructive) {
                            KeychainHelfer.loeschePAT()
                            patGespeichert = false
                            pat = ""
                        }
                    }
                } header: {
                    Text("Zugangsschlüssel")
                } footer: {
                    Text("Der Schlüssel bleibt sicher auf diesem Gerät.")
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
                    .disabled(testLaeuft)
                    if let ergebnis = testErgebnis {
                        Text(ergebnis)
                            .font(.footnote)
                            .foregroundStyle(ergebnis.hasPrefix("Verbunden") ? GC.ok : GC.warn)
                    }
                } footer: {
                    Text("Ohne Verbindung bleiben Belege in der Warteschlange und werden nachgereicht, sobald es wieder klappt.")
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
            testErgebnis = "Bitte zuerst den Zugangsschlüssel einfügen."
            return
        }
        testLaeuft = true
        testErgebnis = nil
        Task {
            let ergebnis = await AblageService.verbindungstest(basis: url, pat: gespeichert)
            switch ergebnis {
            case .uebertragen: testErgebnis = "Verbunden ✓ — alles bereit."
            case .tokenFehler: testErgebnis = "Der Zugangsschlüssel stimmt nicht — bitte neu einfügen."
            case .abgelehnt: testErgebnis = "Die Belegbox meldet einen Fehler — später noch einmal versuchen."
            case .nichtErreichbar: testErgebnis = "Keine Verbindung — Internet prüfen und noch einmal versuchen."
            }
            testLaeuft = false
        }
    }
}
