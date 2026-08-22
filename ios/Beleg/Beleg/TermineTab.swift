import SwiftUI

/// Der Tag im Salon. babu führt den Kalender selbst — kein fremdes
/// Buchungssystem, keine Anbindung. Oben, was der Tag macht; darunter die
/// Termine; ganz unten das Feld, in das man einfach hineinschreibt.
struct TermineTab: View {
    @EnvironmentObject var store: AppStore

    @State private var tag = Date()
    @State private var daten: [String: Any]?
    @State private var laedt = true
    @State private var fehler: String?
    @State private var satz = ""
    @State private var denktNach = false
    @State private var vorschlaege: [String] = []
    @State private var wunsch: [String: Any]?
    @State private var hinweis = ""
    @State private var vonHand = false

    private var datumText: String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "EEEE, d. MMMM"
        return f.string(from: tag)
    }

    private var iso: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: tag)
    }

    private var termine: [[String: Any]] {
        daten?["liste"] as? [[String: Any]] ?? []
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack {
                        Button { blaettern(-1) } label: {
                            Image(systemName: "chevron.left")
                        }
                        Spacer()
                        VStack(spacing: 2) {
                            Text(datumText).font(.body.weight(.medium))
                            if let satzDesTages = daten?["satz"] as? String {
                                Text(satzDesTages).font(.caption)
                                    .foregroundStyle(GC.desc)
                                    .multilineTextAlignment(.center)
                            }
                        }
                        Spacer()
                        Button { blaettern(1) } label: {
                            Image(systemName: "chevron.right")
                        }
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(GC.accent)
                }

                if let fehler {
                    Section { Text(fehler).font(.footnote).foregroundStyle(GC.warn) }
                }

                if laedt {
                    Section {
                        HStack { ProgressView(); Text("Einen Moment …")
                            .foregroundStyle(GC.muted) }
                    }
                } else if termine.isEmpty {
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Noch nichts eingetragen.")
                                .font(.body.weight(.medium))
                            Text("Schreib unten einfach hin, wer wann kommt — "
                                 + "babu sucht die Lücke.")
                                .font(.caption).foregroundStyle(GC.desc)
                        }
                        .padding(.vertical, 4)
                    }
                } else {
                    Section("Termine") {
                        ForEach(termine.indices, id: \.self) { i in
                            zeile(termine[i])
                        }
                    }
                }

                Section {
                    TextField("z. B. Frau Holder Donnerstag Farbe",
                              text: $satz, axis: .vertical)
                        .lineLimit(1...3)
                    Button {
                        Task { await verstehen() }
                    } label: {
                        HStack {
                            if denktNach { ProgressView().padding(.trailing, 6) }
                            Text(denktNach ? "babu schaut nach …" : "Lücke suchen")
                        }
                    }
                    .disabled(denktNach || satz.trimmed.count < 3)

                    if !hinweis.isEmpty {
                        Text(hinweis).font(.caption).foregroundStyle(GC.desc)
                    }
                    ForEach(vorschlaege, id: \.self) { zeit in
                        Button {
                            Task { await buchen(zeit) }
                        } label: {
                            Label("\(zeit) — eintragen", systemImage: "clock")
                                .font(.body.weight(.medium))
                                .foregroundStyle(GC.accent)
                        }
                    }

                    Button("Lieber von Hand eintragen") { vonHand = true }
                        .font(.footnote).foregroundStyle(GC.desc)
                } header: {
                    Text("Neuer Termin")
                } footer: {
                    Text("babu versteht den Satz und sucht die freie Zeit. "
                         + "Eingetragen wird erst, wenn du eine antippst.")
                }
            }
            .navigationTitle("Termine")
            .toolbarTitleDisplayMode(.inline)
            .mitKontoMenu()
            .warmerGrund()
            .task { await laden() }
            .refreshable { await laden() }
            .sheet(isPresented: $vonHand) {
                TerminVonHandView(tag: iso) { Task { await laden() } }
                    .environmentObject(store)
            }
        }
    }

    private func zeile(_ t: [String: Any]) -> some View {
        let start = String((t["start"] as? String ?? "").suffix(5))
        let minuten = t["minuten"] as? Int ?? 0
        return VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(start).font(.body.monospacedDigit().weight(.semibold))
                Text(t["kundin"] as? String ?? "—").font(.body)
                Spacer()
                Text("\(minuten) min").font(.caption).foregroundStyle(GC.muted)
            }
            HStack(spacing: 6) {
                if let l = t["leistung"] as? String, !l.isEmpty {
                    Text(l).font(.caption).foregroundStyle(GC.desc)
                }
                if let w = t["wer"] as? String, !w.isEmpty {
                    Text("· bei \(w)").font(.caption).foregroundStyle(GC.muted)
                }
            }
        }
        .padding(.vertical, 2)
        .swipeActions(edge: .trailing) {
            Button("Abgesagt") {
                Task { await absagen(t["id"] as? Int) }
            }
            .tint(GC.warn)
        }
    }

    private func blaettern(_ tage: Int) {
        tag = Calendar.current.date(byAdding: .day, value: tage, to: tag) ?? tag
        vorschlaege = []; hinweis = ""
        Task { await laden() }
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else {
            laedt = false
            fehler = "Erst verbinden — dann siehst du deine Termine."
            return
        }
        daten = await AblageService.termineLaden(tag: iso, basis: url, pat: pat)
        fehler = daten == nil ? "Die Termine konnten wir gerade nicht laden." : nil
        laedt = false
    }

    private func verstehen() async {
        guard let (url, pat) = zugang() else { return }
        denktNach = true
        fehler = nil
        defer { denktNach = false }
        let d = await AblageService.terminVorschlag(text: satz, basis: url, pat: pat)
        if let meldung = d.fehler { fehler = meldung; return }
        wunsch = d.wunsch
        vorschlaege = d.zeiten
        hinweis = d.hinweis.isEmpty && d.zeiten.isEmpty
            ? "An dem Tag ist nichts mehr frei." : d.hinweis
        if let datum = d.wunsch?["datum"] as? String {
            let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
            if let neu = f.date(from: datum) { tag = neu; await laden() }
        }
    }

    private func buchen(_ zeit: String) async {
        guard let (url, pat) = zugang(), let w = wunsch else { return }
        let felder: [String: Any] = [
            "start": "\(w["datum"] as? String ?? iso)T\(zeit)",
            "minuten": w["minuten"] as? Int ?? 60,
            "wer": w["wer"] as? String ?? "",
            "kundin": w["kundin"] as? String ?? "",
            "leistung": w["leistung"] as? String ?? "",
        ]
        if let meldung = await AblageService.terminSpeichern(felder, basis: url,
                                                             pat: pat) {
            fehler = meldung
            return
        }
        satz = ""; vorschlaege = []; hinweis = ""; wunsch = nil
        await laden()
    }

    private func absagen(_ id: Int?) async {
        guard let id, let (url, pat) = zugang() else { return }
        if await AblageService.terminAbsagen(id: id, basis: url, pat: pat) {
            await laden()
        }
    }
}

/// Wenn babu den Satz nicht versteht — oder man es einfach selbst tippen will.
struct TerminVonHandView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let tag: String
    let fertig: () -> Void

    @State private var kundin = ""
    @State private var leistung = ""
    @State private var wer = ""
    @State private var zeit = "10:00"
    @State private var minuten = 60
    @State private var fehler: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Wer kommt?") {
                    TextField("Name", text: $kundin)
                    TextField("Was wird gemacht?", text: $leistung)
                    TextField("Bei wem? (wenn ihr mehrere seid)", text: $wer)
                }
                Section("Wann?") {
                    TextField("Uhrzeit (z. B. 14:30)", text: $zeit)
                        .keyboardType(.numbersAndPunctuation)
                    Picker("Dauer", selection: $minuten) {
                        ForEach([30, 45, 60, 90, 120, 150, 180], id: \.self) { m in
                            Text(m < 60 ? "\(m) min" : "\(m / 60) Std"
                                 + (m % 60 == 0 ? "" : " \(m % 60) min")).tag(m)
                        }
                    }
                }
                if let fehler {
                    Section { Text(fehler).font(.footnote).foregroundStyle(GC.warn) }
                }
            }
            .navigationTitle("Termin eintragen")
            .navigationBarTitleDisplayMode(.inline)
            .warmerGrund()
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Eintragen") { Task { await sichern() } }
                        .disabled(kundin.trimmed.isEmpty)
                }
            }
        }
    }

    private func sichern() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        let meldung = await AblageService.terminSpeichern([
            "start": "\(tag)T\(zeit)", "minuten": minuten, "wer": wer,
            "kundin": kundin, "leistung": leistung,
        ], basis: url, pat: pat)
        if let meldung { fehler = meldung; return }
        fertig()
        dismiss()
    }
}
