import SwiftUI

/// Fragen an die Belegbox: Chat mit Gemma 4 auf der H200V — Antworten
/// ausschließlich aus den BelegReview-Daten (`POST /chat`, PAT-geschützt).
struct FragenTab: View {
    @EnvironmentObject var store: AppStore

    @State private var eingabe = ""
    @State private var nachrichten: [Nachricht] = []
    @State private var laeuft = false

    struct Nachricht: Identifiable, Equatable {
        let id = UUID()
        let vonMir: Bool
        var text: String
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { leser in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            if nachrichten.isEmpty {
                                leerHinweis
                            }
                            ForEach(nachrichten) { nachricht in
                                blase(nachricht)
                            }
                            if laeuft, nachrichten.last?.text.isEmpty != false {
                                HStack(spacing: 8) {
                                    ProgressView()
                                    Text("Einen Moment — ich schaue in deine Belege …")
                                        .font(.footnote)
                                        .foregroundStyle(GC.muted)
                                }
                                .padding(.horizontal, 4)
                            }
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .onChange(of: nachrichten) { _, neu in
                        if let letzte = neu.last {
                            withAnimation { leser.scrollTo(letzte.id, anchor: .bottom) }
                        }
                    }
                }

                eingabeleiste
            }
            .background(GC.canvas)
            .navigationTitle("Fragen")
            .toolbarTitleDisplayMode(.inline)
        }
    }

    private var leerHinweis: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Frag die Belegbox")
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
            Text("Die Antworten kommen nur aus deinen eigenen Belegen — zum Beispiel:")
                .font(.footnote)
                .foregroundStyle(GC.desc)
            ForEach(["Wie viel habe ich im Juli für Bewirtung ausgegeben?",
                     "Welche Belege haben offene Punkte?",
                     "Was war der letzte Beleg und wie ist er kontiert?"], id: \.self) { beispiel in
                Button {
                    eingabe = beispiel
                    senden()
                } label: {
                    Text("„\(beispiel)“")
                        .font(.footnote)
                        .multilineTextAlignment(.leading)
                        .foregroundStyle(GC.accentHover)
                }
            }
        }
        .padding(.top, 24)
    }

    private func blase(_ nachricht: Nachricht) -> some View {
        HStack {
            if nachricht.vonMir { Spacer(minLength: 40) }
            Text(nachricht.text)
                .font(.subheadline)
                .foregroundStyle(nachricht.vonMir ? Color.white : GC.body)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(nachricht.vonMir ? GC.accent : GC.bg,
                            in: RoundedRectangle(cornerRadius: 14))
                .shadow(color: Color(hex: 0x1F1E1A).opacity(nachricht.vonMir ? 0 : 0.06),
                        radius: 5, y: 2)
            if !nachricht.vonMir { Spacer(minLength: 40) }
        }
        .id(nachricht.id)
    }

    private var eingabeleiste: some View {
        HStack(spacing: 10) {
            TextField("Frage zu deinen Belegen …", text: $eingabe, axis: .vertical)
                .lineLimit(1...4)
                .padding(.horizontal, 13)
                .padding(.vertical, 9)
                .background(GC.bg, in: RoundedRectangle(cornerRadius: 18))
                .onSubmit { senden() }
            Button {
                senden()
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(eingabe.trimmingCharacters(in: .whitespaces).isEmpty || laeuft
                                     ? GC.muted : GC.accent)
            }
            .disabled(eingabe.trimmingCharacters(in: .whitespaces).isEmpty || laeuft)
            .accessibilityLabel("Senden")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(GC.chrome)
    }

    private func senden() {
        let frage = eingabe.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !frage.isEmpty, !laeuft else { return }
        eingabe = ""
        nachrichten.append(Nachricht(vonMir: true, text: frage))

        guard let url = URL(string: store.ablageURL), KeychainHelfer.ladePAT() != nil else {
            nachrichten.append(Nachricht(vonMir: false,
                text: "Dafür braucht die App die Belegbox — einmal im Export-Tab über das Zahnrad verbinden."))
            return
        }
        laeuft = true
        Task {
            let pat = KeychainHelfer.ladePAT() ?? ""
            nachrichten.append(Nachricht(vonMir: false, text: ""))
            let index = nachrichten.count - 1

            // Stream: Text erscheint, während die Antwort entsteht.
            var gestreamt = false
            var gemeldet: String?
            do {
                for try await stueck in AblageService.fragenStream(frage, basis: url, pat: pat) {
                    gestreamt = true
                    nachrichten[index].text += stueck
                }
            } catch let fehler as ChatFehler {
                // Klarer Serverbescheid — anzeigen statt noch einmal 2 Minuten warten.
                gemeldet = "Das klappt gerade nicht: \(fehler.meldung). Später noch einmal versuchen."
            } catch {
                // Stream fehlgeschlagen — unten klassischer Fallback.
            }
            if let gemeldet {
                nachrichten[index].text = gemeldet
            } else if !gestreamt {
                let antwort = await AblageService.fragen(frage, basis: url, pat: pat)
                nachrichten[index].text = antwort
                    ?? "Gerade keine Verbindung — im Export-Tab (Zahnrad) prüfen und noch einmal fragen."
            }
            laeuft = false
        }
    }
}
