import SwiftUI

/// Gemma bucht — und was nur Nina wissen kann, fragt es hier.
///
/// Ein Fragenpaket, eine Frage pro Bildschirm, jede als Multiple Choice
/// (mit eigener Antwort als Ausweg). Am Ende gehen alle Antworten gesammelt
/// zurück, und der Beleg bekommt seinen grünen Haken. Wer vorher aufhört,
/// verliert nichts: Der Beleg bleibt in der Ablage, ehrlich markiert als
/// „noch nicht fertig".
struct BuchungsfragenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var schliessen
    let belegID: UUID

    @State private var laedt = true
    @State private var fragen: [AblageService.BuchungsFrage] = []
    @State private var index = 0
    @State private var antworten: [(frage: String, antwort: String)] = []
    @State private var freitext = ""
    @State private var meldung: String?
    @State private var fertig: AblageService.GemmaBuchung?

    var body: some View {
        NavigationStack {
            Group {
                if let b = fertig {
                    gebuchtAnsicht(b)
                } else if laedt {
                    VStack(spacing: 10) {
                        ProgressView()
                        Text(antworten.isEmpty
                             ? "babu sieht sich den Beleg an …"
                             : "babu bucht mit deinen Antworten …")
                            .font(.footnote).foregroundStyle(GC.desc)
                    }
                } else if let meldung {
                    VStack(spacing: 12) {
                        Image(systemName: "tray.full")
                            .font(.system(size: 34)).foregroundStyle(GC.warn)
                        Text(meldung).font(.body)
                            .multilineTextAlignment(.center)
                        Button("Alles klar") { schliessen() }
                            .buttonStyle(.bordered)
                    }
                    .padding()
                } else if fragen.indices.contains(index) {
                    frageAnsicht(fragen[index])
                }
            }
            .warmerGrund()
            .navigationTitle("Kurz nachgefragt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Später") { schliessen() }
                }
            }
            .task { await runde() }
            .onDisappear {
                // Vorzeitig weggelegt? Dann bleibt der Beleg ehrlich markiert.
                if fertig == nil {
                    store.offeneFrageSetzen(id: belegID,
                        "babu hat noch Fragen zu diesem Beleg.")
                }
            }
        }
    }

    // MARK: - Eine Frage, ein Bildschirm

    private func frageAnsicht(_ f: AblageService.BuchungsFrage) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            if fragen.count > 1 {
                Text("Frage \(index + 1) von \(fragen.count)")
                    .font(.caption).foregroundStyle(GC.muted)
            }
            Text(f.frage)
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(f.optionen, id: \.self) { option in
                Button {
                    antworten.append((f.frage, option))
                    weiter()
                } label: {
                    Text(option)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 4)
                }
                .buttonStyle(.bordered)
            }

            HStack(spacing: 8) {
                TextField("Oder in deinen Worten …", text: $freitext)
                    .textFieldStyle(.roundedBorder)
                Button("Weiter") {
                    let t = freitext.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !t.isEmpty else { return }
                    antworten.append((f.frage, t))
                    freitext = ""
                    weiter()
                }
                .buttonStyle(.borderedProminent)
                .disabled(freitext.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            Spacer()
        }
        .padding(18)
    }

    private func weiter() {
        if index + 1 < fragen.count {
            index += 1
        } else {
            Task { await runde() }
        }
    }

    // MARK: - Der grüne Haken

    private func gebuchtAnsicht(_ b: AblageService.GemmaBuchung) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 52))
                .foregroundStyle(GC.ok)
            Text("Gebucht").font(.title2.weight(.semibold)).fontDesign(.serif)
            VStack(spacing: 4) {
                Text("\(b.kategorieName) · Konto \(b.konto)")
                    .font(.subheadline)
                if b.waehrung != "EUR", let betrag = b.betrag {
                    Text("\(betrag, format: .number.precision(.fractionLength(2))) \(b.waehrung) ≈ \(fmtEur(b.betragEur))")
                        .font(.subheadline.monospacedDigit())
                } else {
                    Text(fmtEur(b.betragEur))
                        .font(.subheadline.monospacedDigit())
                }
            }
            if !b.begruendung.isEmpty {
                Text(b.begruendung)
                    .font(.footnote).foregroundStyle(GC.desc)
                    .multilineTextAlignment(.center)
            }
            Button("Fertig") { schliessen() }
                .buttonStyle(.borderedProminent)
                .padding(.top, 6)
        }
        .padding(24)
    }

    // MARK: - Die Runde zum Server

    private func runde() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            meldung = "Erst verbinden — dann kann babu buchen."
            laedt = false
            return
        }
        guard let beleg = store.belege.first(where: { $0.id == belegID }) else {
            meldung = "Der Beleg ist nicht mehr da."
            laedt = false
            return
        }
        let zeilen = beleg.ocrText.split(separator: "\n").map(String.init)
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        guard !zeilen.isEmpty else {
            meldung = "Zu diesem Beleg liegt keine Lesung vor — bitte neu fotografieren."
            laedt = false
            return
        }
        laedt = true
        // Das Profil liegt auf dem Telefon; beim allerersten Mal wird es
        // einmal aus dem Konto geholt und dann hier gehalten.
        if store.profil.isEmpty,
           let frisch = await AblageService.stammdatenLaden(basis: url, pat: pat) {
            store.profil = frisch
        }
        // „18.07.2026" → „2026-07" für den Kontobewegungs-Kontext.
        let t = beleg.datumText.split(separator: ".")
        let monat = t.count == 3 ? "\(t[2])-\(t[1])" : nil
        let ergebnis = await AblageService.einschaetzung(
            zeilen: zeilen, profil: store.profil, monat: monat,
            antworten: antworten, basis: url, pat: pat)
        switch ergebnis {
        case .fragen(let neue):
            fragen = neue
            index = 0
        case .gebucht(let b):
            store.gemmaBuchungAnwenden(id: belegID, konto: b.konto,
                                       ustSatz: b.ustSatz, betragEur: b.betragEur,
                                       waehrung: b.waehrung,
                                       begruendung: b.begruendung,
                                       lieferant: b.lieferant, datum: b.datum)
            fertig = b
        case .aufgeben(let hinweis):
            store.offeneFrageSetzen(id: belegID, "Für den Schreibtisch: " + hinweis)
            meldung = hinweis
        case .fehler(let text):
            meldung = text
        }
        laedt = false
    }
}
