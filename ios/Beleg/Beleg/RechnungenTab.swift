import SwiftUI

/// Rechnungen stellen — die dritte Geldsorte neben Belegen und Kasse.
/// Oben, was noch offen ist; darunter die bezahlten. Und daneben die
/// Vertragskiste: was jeden Monat sicher abgeht.
struct RechnungenTab: View {
    @EnvironmentObject var store: AppStore

    @State private var rechnungen: [Rechnung] = []
    @State private var offenSumme: Double = 0
    @State private var versteuerung = "ist"
    @State private var laedt = true
    @State private var fehler: String?
    @State private var neueRechnung = false
    @State private var zeigeVorlagen = false
    @State private var zeigeBriefkopf = false
    @State private var zahlungen: [[String: Any]] = []

    private var offene: [Rechnung] { rechnungen.filter(\.istOffen) }
    private var erledigte: [Rechnung] { rechnungen.filter { !$0.istOffen } }

    var body: some View {
        Group {
            List {
                if laedt {
                    HStack { ProgressView(); Text("Einen Moment …").foregroundStyle(GC.muted) }
                }
                if let fehler {
                    Text(fehler).font(.footnote).foregroundStyle(GC.warn)
                }

                // Was der Kontoauszug schon weiß: babu schlägt vor, die
                // Inhaberin bestätigt. Ein „bezahlt" verschiebt Umsatz in die
                // Voranmeldung — das entscheidet niemand automatisch.
                if !zahlungen.isEmpty {
                    Section {
                        ForEach(zahlungen.indices, id: \.self) { i in
                            let z = zahlungen[i]
                            VStack(alignment: .leading, spacing: 6) {
                                Text(z["text"] as? String ?? "")
                                    .font(.body.weight(.medium)).foregroundStyle(GC.fg)
                                HStack(spacing: 6) {
                                    Text("Nr. \(z["nummer"] as? String ?? "")")
                                        .font(.caption2).foregroundStyle(GC.muted)
                                    if z["sicher"] as? Bool != true {
                                        Text("· bitte kurz prüfen")
                                            .font(.caption2).foregroundStyle(GC.warn)
                                    }
                                }
                                Button("Stimmt — als bezahlt eintragen") {
                                    Task { await zahlungUebernehmen(z) }
                                }
                                .font(.footnote.weight(.medium))
                                .foregroundStyle(GC.accent)
                            }
                            .padding(.vertical, 3)
                        }
                    } header: {
                        Text("Vom Konto")
                    } footer: {
                        Text("Aus deinem Kontoauszug. babu trägt nichts von "
                             + "allein ein — bezahlt heißt, es zählt als Umsatz.")
                    }
                }

                if !offene.isEmpty {
                    Section {
                        ForEach(offene) { r in zeile(r) }
                    } header: {
                        Text("Offen — \(fmtEur(offenSumme))")
                    } footer: {
                        Text(versteuerung == "ist"
                             ? "Offene Rechnungen zählen erst als Umsatz, wenn das Geld da ist."
                             : "Diese Rechnungen zählen bereits als Umsatz — auch unbezahlt.")
                    }
                }

                if !erledigte.isEmpty {
                    Section("Erledigt") {
                        ForEach(erledigte) { r in zeile(r) }
                    }
                }

                if !laedt && rechnungen.isEmpty {
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Noch keine Rechnung gestellt.")
                                .font(.body.weight(.medium))
                            Text("Stuhlmiete, eine Hochzeit, ein Firmenkunde — "
                                 + "was du anderen berechnest, gehört hierher.")
                                .font(.caption).foregroundStyle(GC.desc)
                        }
                        .padding(.vertical, 4)
                    }
                }

                Section {
                    Button {
                        zeigeVorlagen = true
                    } label: {
                        Label("Vorlagen", systemImage: "doc.on.doc")
                    }
                    Button {
                        zeigeBriefkopf = true
                    } label: {
                        Label("Dein Briefkopf", systemImage: "paintpalette")
                    }
                }
            }
            .warmerGrund()
            .navigationTitle("Rechnungen")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { neueRechnung = true } label: {
                        Label("Neue Rechnung", systemImage: "plus")
                    }
                }
            }
            .refreshable { await laden() }
            .task { await laden() }
            .sheet(isPresented: $neueRechnung) {
                NeueRechnungView { await laden() }
                    .environmentObject(store)
            }
            .sheet(isPresented: $zeigeVorlagen) {
                VorlagenView().environmentObject(store)
            }
            .sheet(isPresented: $zeigeBriefkopf) {
                BriefkopfView().environmentObject(store)
            }
        }
    }

    private func zeile(_ r: Rechnung) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(r.empfaengerName).font(.body.weight(.medium)).foregroundStyle(GC.fg)
                Spacer()
                Text(fmtEur(r.brutto)).font(.body.monospacedDigit())
                    .foregroundStyle(r.stand == "storniert" ? GC.muted : GC.fg)
            }
            HStack(spacing: 6) {
                Text("Nr. \(r.nummer)").font(.caption2).foregroundStyle(GC.muted)
                Text("·").font(.caption2).foregroundStyle(GC.muted)
                Text(r.standText).font(.caption)
                    .foregroundStyle(r.istOffen ? GC.warn : GC.desc)
            }
        }
        .padding(.vertical, 2)
        .swipeActions(edge: .trailing) {
            if r.istOffen {
                Button("Bezahlt") { Task { await bezahlt(r) } }.tint(.green)
                Button("Storno", role: .destructive) { Task { await storno(r) } }
            }
        }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            laedt = false
            fehler = "Erst verbinden — dann kannst du Rechnungen stellen."
            return
        }
        zahlungen = await AblageService.zahlungsvorschlaege(basis: url, pat: pat)
        if let d = await AblageService.rechnungenLaden(basis: url, pat: pat) {
            rechnungen = d.rechnungen
            offenSumme = d.offenSumme
            versteuerung = d.versteuerung
            fehler = nil
        } else {
            fehler = "Die Rechnungen konnten wir gerade nicht laden."
        }
        laedt = false
    }

    private func zahlungUebernehmen(_ z: [String: Any]) async {
        guard let nummer = z["nummer"] as? String,
              let am = z["bezahlt_am"] as? String,
              let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        if await AblageService.zahlungUebernehmen(nummer: nummer, am: am,
                                                   basis: url, pat: pat) {
            await laden()
        } else {
            fehler = "Das konnten wir gerade nicht eintragen."
        }
    }

    private func bezahlt(_ r: Rechnung) async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        let heute = ISO8601DateFormatter().string(from: Date()).prefix(10)
        if await AblageService.rechnungBezahlt(nummer: r.nummer, am: String(heute),
                                               basis: url, pat: pat) {
            await laden()
        } else {
            fehler = "Das konnten wir gerade nicht speichern."
        }
    }

    private func storno(_ r: Rechnung) async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        if await AblageService.rechnungStornieren(nummer: r.nummer, basis: url, pat: pat) {
            await laden()
        } else {
            fehler = "Das Storno hat gerade nicht geklappt."
        }
    }
}

// MARK: - Neue Rechnung

struct NeueRechnungView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let fertig: () async -> Void

    @State private var empfaenger = Empfaenger()
    @State private var positionen: [RechnungPosition] = [RechnungPosition()]
    @State private var hinweis = ""
    @State private var laeuft = false
    @State private var fehler: String?
    @State private var stammdaten: [String: String] = [:]
    @State private var fertigesPdf: URL?
    @State private var vorlageWaehlen = false
    @State private var vorlageBauen = false

    private var kleinunternehmer: Bool { stammdaten["kleinunternehmer"] == "Ja" }
    private var summe: RechnungsSumme {
        Rechnungsrechnung.summe(positionen, kleinunternehmer: kleinunternehmer)
    }
    /// Was oben auf der Rechnung noch fehlt — § 14 verlangt es, und es kommt
    /// aus dem Einrichten, nicht aus diesem Formular.
    private var kopfMaengel: [String] {
        var fehlt: [String] = []
        if (stammdaten["betrieb_name"] ?? "").isEmpty {
            fehlt.append("Dein Betriebsname fehlt noch.")
        }
        if (stammdaten["anschrift"] ?? "").isEmpty {
            fehlt.append("Deine Anschrift fehlt noch — sie gehört auf jede Rechnung.")
        }
        if (stammdaten["steuernummer"] ?? "").isEmpty
            && (stammdaten["ust_id"] ?? "").isEmpty {
            fehlt.append("Deine Steuernummer fehlt noch.")
        }
        return fehlt
    }

    private var maengel: [String] {
        Rechnungsrechnung.fehlt(empfaenger: empfaenger, positionen: positionen,
                                brutto: summe.brutto)
    }

    var body: some View {
        NavigationStack {
            Form {
                if !store.vorlagen.isEmpty {
                    Section {
                        Button {
                            vorlageWaehlen = true
                        } label: {
                            Label("Aus Vorlage übernehmen", systemImage: "doc.on.doc")
                        }
                    }
                }

                // Was schon feststeht, wird gezeigt, nicht erfragt: es kam
                // beim Einrichten und steht in den Einstellungen.
                Section {
                    if stammdaten.isEmpty {
                        HStack { ProgressView(); Text("Einen Moment …")
                            .font(.footnote).foregroundStyle(GC.muted) }
                    } else {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(stammdaten["betrieb_name"] ?? "—")
                                .font(.body.weight(.medium))
                            if let a = stammdaten["anschrift"], !a.isEmpty {
                                Text(a).font(.caption).foregroundStyle(GC.desc)
                            }
                            if let st = stammdaten["steuernummer"], !st.isEmpty {
                                Text("Steuernummer \(st)").font(.caption2)
                                    .foregroundStyle(GC.muted)
                            }
                            if kleinunternehmer {
                                Text("Ohne Umsatzsteuer nach § 19 UStG")
                                    .font(.caption2).foregroundStyle(GC.muted)
                            }
                        }
                        .padding(.vertical, 2)
                        ForEach(kopfMaengel, id: \.self) { m in
                            Label(m, systemImage: "exclamationmark.circle")
                                .font(.caption).foregroundStyle(GC.warn)
                        }
                    }
                } header: {
                    Text("Das steht oben auf der Rechnung")
                } footer: {
                    Text("Kommt aus deinen Angaben beim Einrichten — ändern "
                         + "kannst du es in den Einstellungen.")
                }

                Section("Wer bekommt die Rechnung?") {
                    TextField("Name", text: $empfaenger.name)
                        .textContentType(.name)
                    TextField("Anschrift", text: $empfaenger.anschrift, axis: .vertical)
                        .lineLimit(1...3)
                    TextField("USt-IdNr. (wenn vorhanden)", text: $empfaenger.ustId)
                        .autocapitalization(.allCharacters)
                }

                Section("Was berechnest du?") {
                    ForEach($positionen) { $p in
                        VStack(spacing: 6) {
                            TextField("z. B. Stuhlmiete August", text: $p.text)
                            HStack {
                                TextField("0,00", text: betragBindung($p))
                                    .keyboardType(.decimalPad)
                                if !kleinunternehmer {
                                    Picker("", selection: $p.ustSatz) {
                                        Text("19 %").tag(19)
                                        Text("7 %").tag(7)
                                        Text("0 %").tag(0)
                                    }
                                    .pickerStyle(.segmented)
                                    .frame(width: 150)
                                }
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    .onDelete { positionen.remove(atOffsets: $0) }

                    Button {
                        positionen.append(RechnungPosition())
                    } label: {
                        Label("Zeile hinzufügen", systemImage: "plus.circle")
                    }
                }

                Section("Summe") {
                    zeile("Netto", summe.netto)
                    ForEach(summe.jeSatz, id: \.satz) { s in
                        zeile("Umsatzsteuer \(s.satz) %", s.ust)
                    }
                    zeile("Gesamt", summe.brutto, fett: true)
                    if kleinunternehmer {
                        Text("Kein Ausweis von Umsatzsteuer nach § 19 UStG.")
                            .font(.caption).foregroundStyle(GC.desc)
                    }
                }

                Section("Hinweis auf der Rechnung (wenn du magst)") {
                    TextField("z. B. Zahlbar bis 15.09.2026", text: $hinweis,
                              axis: .vertical)
                        .lineLimit(1...3)
                }

                if let fehler {
                    Section { Text(fehler).font(.footnote).foregroundStyle(GC.warn) }
                }
                if !maengel.isEmpty {
                    Section {
                        ForEach(maengel, id: \.self) { m in
                            Label(m, systemImage: "exclamationmark.circle")
                                .font(.caption).foregroundStyle(GC.desc)
                        }
                    }
                }

                Section {
                    Button {
                        Task { await stellen() }
                    } label: {
                        HStack {
                            if laeuft { ProgressView().padding(.trailing, 6) }
                            Text(laeuft ? "Wird gestellt …" : "Rechnung stellen")
                        }
                    }
                    .disabled(laeuft || !maengel.isEmpty)

                    Button("Als Vorlage merken") { vorlageBauen = true }
                        .disabled(empfaenger.name.trimmed.isEmpty)
                }
            }
            .navigationTitle("Neue Rechnung")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
            .task {
                guard let url = URL(string: store.ablageURL),
                      let pat = KeychainHelfer.ladePAT() else { return }
                stammdaten = await AblageService.stammdatenLaden(basis: url, pat: pat) ?? [:]
            }
            .confirmationDialog("Vorlage", isPresented: $vorlageWaehlen) {
                ForEach(store.vorlagen) { v in
                    Button(v.kurz) {
                        empfaenger = v.empfaenger
                        positionen = v.positionen.map {
                            RechnungPosition(text: $0.text, menge: $0.menge,
                                             einzelpreis: $0.einzelpreis,
                                             ustSatz: $0.ustSatz)
                        }
                    }
                }
            }
            .sheet(item: $fertigesPdf) { url in
                TeilenBlatt(datei: url) { dismiss() }
            }
            .sheet(isPresented: $vorlageBauen) {
                VorlageBearbeitenView(vorlage: alsVorlage) { fertig in
                    store.vorlagen.append(fertig)
                }
            }
        }
    }

    /// Der Betrag als Text — damit ein leeres Feld leer bleibt und die Summe
    /// bei jedem Tastendruck mitläuft.
    private func betragBindung(_ p: Binding<RechnungPosition>) -> Binding<String> {
        Binding(get: { betragAlsText(p.wrappedValue.einzelpreis) },
                set: { p.wrappedValue.einzelpreis = betragAusText($0) })
    }

    private func zeile(_ titel: String, _ betrag: Double, fett: Bool = false) -> some View {
        HStack {
            Text(titel).font(fett ? .body.weight(.semibold) : .body)
            Spacer()
            Text(fmtEur(betrag)).font(.body.monospacedDigit())
                .fontWeight(fett ? .semibold : .regular)
        }
    }

    /// Was gerade getippt ist, wird zur Vorlage — im Editor, damit die
    /// Nutzerin ihr noch einen Namen geben kann.
    private var alsVorlage: Rechnungsvorlage {
        Rechnungsvorlage(name: empfaenger.name, empfaenger: empfaenger,
                         positionen: positionen)
    }

    /// Erst festschreiben (der Server vergibt die Nummer), dann das PDF bauen
    /// und nachreichen. Ohne Verbindung bleibt es ein Entwurf — und das sagen
    /// wir, statt „gespeichert" zu behaupten.
    private func stellen() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            fehler = "Erst verbinden — dann kannst du Rechnungen stellen."
            return
        }
        laeuft = true
        defer { laeuft = false }
        let heute = String(ISO8601DateFormatter().string(from: Date()).prefix(10))
        let ergebnis = await AblageService.rechnungStellen(
            datum: heute, empfaenger: empfaenger, positionen: positionen,
            leistungszeitpunkt: nil, hinweis: hinweis, basis: url, pat: pat)
        guard let nummer = ergebnis.nummer else {
            fehler = ergebnis.fehler
            return
        }
        // Briefkopf: Farbe und Logo, so wie in vier Schritten eingerichtet.
        let akzent = UIColor(Color(hexText: stammdaten["marke_farbe"] ?? "#1F1D1B"))
        let logo = await AblageService.logoLaden(basis: url, pat: pat)
            .flatMap(UIImage.init(data:))
        let pdf = RechnungPDF.bauen(
            nummer: nummer, datum: heute, leistungszeitpunkt: heute,
            kopf: stammdaten, empfaenger: empfaenger, positionen: positionen,
            summe: summe, kleinunternehmer: kleinunternehmer, hinweis: hinweis,
            akzent: akzent, logo: logo)
        _ = await AblageService.rechnungPdfSenden(pdf, nummer: nummer,
                                                  basis: url, pat: pat)
        let ziel = FileManager.default.temporaryDirectory
            .appendingPathComponent("Rechnung-\(nummer).pdf")
        try? pdf.write(to: ziel)
        await fertig()
        fertigesPdf = ziel
    }
}

/// Das iOS-Teilen-Blatt — babu verschickt nichts selbst, das macht die
/// Nutzerin mit Mail oder WhatsApp.
struct TeilenBlatt: UIViewControllerRepresentable {
    let datei: URL
    let danach: () -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let vc = UIActivityViewController(activityItems: [datei],
                                          applicationActivities: nil)
        vc.completionWithItemsHandler = { _, _, _, _ in danach() }
        return vc
    }

    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

extension URL: Identifiable {
    public var id: String { absoluteString }
}

// MARK: - Die Vertragskiste

struct VertragskisteView: View {
    @EnvironmentObject var store: AppStore

    @State private var vertraege: [Vertrag] = []
    @State private var anstehend: [Vertrag] = []
    @State private var monatlich: Double = 0
    @State private var laedt = true
    @State private var fehler: String?

    var body: some View {
        Group {
            List {
                if laedt {
                    HStack { ProgressView(); Text("Einen Moment …").foregroundStyle(GC.muted) }
                }
                if let fehler {
                    Text(fehler).font(.footnote).foregroundStyle(GC.warn)
                }

                if !laedt && vertraege.isEmpty {
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Noch keine Verträge abgelegt.")
                                .font(.body.weight(.medium))
                            Text("Fotografiere Miete, Versicherung oder Leasing — "
                                 + "babu liest, was sie kosten und wann sie laufen.")
                                .font(.caption).foregroundStyle(GC.desc)
                        }
                        .padding(.vertical, 4)
                    }
                }

                if monatlich > 0 {
                    Section("Das geht jeden Monat ab") {
                        HStack {
                            Text("Zusammen").font(.body.weight(.medium))
                            Spacer()
                            Text(fmtEur(monatlich)).font(.title3.monospacedDigit().weight(.semibold))
                        }
                        HStack {
                            Text("Im Jahr").font(.caption).foregroundStyle(GC.desc)
                            Spacer()
                            Text(fmtEur(monatlich * 12)).font(.caption.monospacedDigit())
                                .foregroundStyle(GC.desc)
                        }
                    }
                }

                if !anstehend.isEmpty {
                    Section {
                        ForEach(anstehend) { v in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(v.partner).font(.body.weight(.medium))
                                Text(v.fristText).font(.caption).foregroundStyle(GC.warn)
                            }
                            .padding(.vertical, 2)
                        }
                    } header: {
                        Text("Da musst du bald ran")
                    } footer: {
                        Text("Eine verpasste Frist verlängert den Vertrag — "
                             + "meist um ein ganzes Jahr.")
                    }
                }

                if !vertraege.isEmpty {
                    Section("Alle Verträge") {
                        ForEach(vertraege) { v in
                            VStack(alignment: .leading, spacing: 3) {
                                HStack {
                                    Text(v.partner).font(.body.weight(.medium))
                                    Spacer()
                                    Text(v.betragMonat.map { fmtEur($0) } ?? "—")
                                        .font(.body.monospacedDigit())
                                }
                                Text(v.artName).font(.caption2).foregroundStyle(GC.muted)
                                Text(v.fristText).font(.caption).foregroundStyle(GC.desc)
                            }
                            .padding(.vertical, 2)
                        }
                    }
                }
            }
            // Ohne das stand diese eine Liste als einzige der App auf iOS-Grau
            // (#F2F2F7) statt auf der warmen Fläche — siehe Theme.swift.
            .warmerGrund()
            .navigationTitle("Deine Verträge")
            .navigationBarTitleDisplayMode(.inline)
            .task { await laden() }
            .refreshable { await laden() }
        }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            laedt = false
            fehler = "Erst verbinden — dann siehst du deine Verträge."
            return
        }
        if let d = await AblageService.vertraegeLaden(basis: url, pat: pat) {
            vertraege = d.vertraege
            anstehend = d.anstehend
            monatlich = d.monatlich
            fehler = nil
        } else {
            fehler = "Die Verträge konnten wir gerade nicht laden."
        }
        laedt = false
    }
}
