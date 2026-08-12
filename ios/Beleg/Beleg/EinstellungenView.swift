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
                    Toggle("Belege automatisch in die Belegbox übertragen",
                           isOn: $store.ablageAktiv)
                } footer: {
                    Text("Jeder gesiegelte Beleg wird als Commit „aufnahme: …“ im Container babu abgelegt — Grundlage für BelegReview (Server-Verifikation + steuerliche Einschätzung).")
                }

                Section("Server") {
                    TextField("http://192.168.145.10:7843", text: $store.ablageURL)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .font(.callout.monospaced())
                }

                Section {
                    SecureField(patGespeichert ? "PAT gespeichert ✓ — zum Ersetzen neu eingeben"
                                               : "Upload-PAT (aus dem --zeigen-Lauf)",
                                text: $pat)
                        .font(.callout.monospaced())
                    if patGespeichert {
                        Button("PAT löschen", role: .destructive) {
                            KeychainHelfer.loeschePAT()
                            patGespeichert = false
                            pat = ""
                        }
                    }
                } header: {
                    Text("Zugriffstoken")
                } footer: {
                    Text("Der Token wird ausschließlich in der iOS-Keychain abgelegt — nie in Dateien oder Logs.")
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
                            .font(.footnote.monospaced())
                            .foregroundStyle(ergebnis.hasPrefix("Verbunden") ? GC.ok : GC.warn)
                    }
                } footer: {
                    Text("Stufe 1 ist LAN-only ohne TLS: Übertragung funktioniert nur im eigenen Netz (WLAN mit der H200V). Unterwegs bleiben Belege in der Warteschlange und werden nachgereicht.")
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
            testErgebnis = "Ungültige Server-URL"
            return
        }
        guard let gespeichert = KeychainHelfer.ladePAT() else {
            testErgebnis = "Kein PAT gespeichert"
            return
        }
        testLaeuft = true
        testErgebnis = nil
        Task {
            let ergebnis = await AblageService.verbindungstest(basis: url, pat: gespeichert)
            switch ergebnis {
            case .uebertragen: testErgebnis = "Verbunden ✓ — Server erreichbar, Token gültig"
            case .tokenFehler: testErgebnis = "Token ungültig (401)"
            case .abgelehnt(let code): testErgebnis = "Server meldet HTTP \(code)"
            case .nichtErreichbar: testErgebnis = "Server nicht erreichbar — im WLAN mit der H200V?"
            }
            testLaeuft = false
        }
    }
}
