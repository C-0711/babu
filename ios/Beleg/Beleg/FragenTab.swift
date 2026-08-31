import SwiftUI
import PhotosUI

// `ChatNachricht`, `ChatUnterhaltung` und die Textarbeit liegen in
// `Chattexte.swift` — ohne SwiftUI, damit sie im Harness prüfbar sind.

/// Fragen an die Belegbox: Chat mit Gemma 4 auf der H200V — Antworten
/// aus den BelegReview-Daten, zu allgemeinen Steuerfragen und zu Briefen
/// vom Amt (`POST /chat`).
struct FragenTab: View {
    @EnvironmentObject var store: AppStore

    @State private var eingabe = ""
    @State private var laeuft = false
    @State private var aktuelleID: UUID?
    @State private var zeigeVerlauf = false
    @State private var briefAuswahl: PhotosPickerItem?
    @State private var zeigeBriefDateien = false
    @State private var briefLaeuft = false
    @State private var vertragAuswahl: PhotosPickerItem?
    @State private var zeigeVertragDateien = false
    // Was der Server FRÜHER mitgeschrieben hat (BABU-25). Neues kommt keins
    // mehr dazu; was liegt, muss sie sehen und wegwerfen können.
    @State private var serverGespraeche: [ServerGespraech] = []
    @State private var serverGeoeffnet: ServerGespraech?
    @State private var serverNachrichten: [ChatNachricht] = []
    @State private var serverFrageLoeschen = false
    @FocusState private var feldAktiv: Bool

    private var aktuelleIndex: Int? {
        guard let id = aktuelleID else { return nil }
        return store.chatVerlauf.firstIndex { $0.id == id }
    }
    private var nachrichten: [ChatNachricht] {
        aktuelleIndex.map { store.chatVerlauf[$0].nachrichten } ?? []
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
                                    Text("Einen Moment — ich schaue nach …")
                                        .font(.footnote)
                                        .foregroundStyle(GC.muted)
                                }
                                .padding(.horizontal, 4)
                            }
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: nachrichten) { _, neu in
                        if let letzte = neu.last {
                            withAnimation { leser.scrollTo(letzte.id, anchor: .bottom) }
                        }
                    }
                }

                eingabeleiste
            }
            .background(GC.canvas)
            .warmerGrund()
            .navigationTitle("Fragen")
            .mitMeldenKnopf("Fragen")
            .mitKontoMenu()
            .toolbarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        zeigeVerlauf = true
                    } label: {
                        Image(systemName: "clock.arrow.circlepath")
                    }
                    .accessibilityLabel("Frühere Fragen")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        aktuelleID = nil
                        feldAktiv = true
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                    .accessibilityLabel("Neue Frage")
                    .disabled(nachrichten.isEmpty)
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button {
                        senden()
                    } label: {
                        Label("Senden", systemImage: "arrow.up.circle.fill")
                    }
                    .disabled(eingabe.trimmingCharacters(in: .whitespaces).isEmpty || laeuft)
                    Button("Fertig") { feldAktiv = false }
                }
            }
            .sheet(isPresented: $zeigeVerlauf) { verlaufsListe }
            .onAppear {
                // Der Verlauf überlebt jeden Neustart — dann soll der Reiter
                // auch dort weitermachen, wo das Gespräch aufgehört hat,
                // statt jedes Mal mit dem leeren Begrüßungsblatt zu starten.
                if aktuelleID == nil {
                    aktuelleID = store.chatVerlauf.max(by: { $0.zuletzt < $1.zuletzt })?.id
                }
            }
            .fileImporter(isPresented: $zeigeBriefDateien,
                          allowedContentTypes: [.pdf, .image]) { ergebnis in
                guard case .success(let url) = ergebnis else { return }
                let zugriff = url.startAccessingSecurityScopedResource()
                defer { if zugriff { url.stopAccessingSecurityScopedResource() } }
                if let daten = try? Data(contentsOf: url) {
                    briefSchicken(daten, name: url.lastPathComponent)
                }
            }
            .fileImporter(isPresented: $zeigeVertragDateien,
                          allowedContentTypes: [.pdf, .image]) { ergebnis in
                guard case .success(let url) = ergebnis else { return }
                let zugriff = url.startAccessingSecurityScopedResource()
                defer { if zugriff { url.stopAccessingSecurityScopedResource() } }
                if let daten = try? Data(contentsOf: url) {
                    vertragSchicken(daten, name: url.lastPathComponent)
                }
            }
            .onChange(of: vertragAuswahl) { _, neu in
                guard let neu else { return }
                Task {
                    let daten = try? await neu.loadTransferable(type: Data.self)
                    vertragAuswahl = nil
                    if let daten { vertragSchicken(daten, name: "vertrag.jpg") }
                }
            }
            .onChange(of: briefAuswahl) { _, neu in
                guard let neu else { return }
                Task {
                    let daten = try? await neu.loadTransferable(type: Data.self)
                    briefAuswahl = nil
                    if let daten { briefSchicken(daten, name: "brief.jpg") }
                }
            }
        }
    }

    // MARK: - Brief vom Amt: ablegen, lesen lassen, erklären

    private func briefSchicken(_ daten: Data, name: String) {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else {
            _ = anhaengen(ChatNachricht(vonMir: false,
                text: "Dafür braucht die App die Belegbox — verbinde dich einmal oben im Menü unter ‚Einstellungen'."))
            return
        }
        briefLaeuft = true
        _ = anhaengen(ChatNachricht(vonMir: true, text: "📄 Brief vom Amt"))
        let index = anhaengen(ChatNachricht(vonMir: false,
            text: "Ich lese deinen Brief — das dauert einen Moment …"))
        Task {
            guard let pfad = await AblageService.briefAblegen(daten: daten, dateiname: name,
                                                              basis: url, pat: pat) else {
                textSetzen(index, "Der Brief ließ sich gerade nicht ablegen — später noch einmal versuchen.")
                briefLaeuft = false
                return
            }
            // Die Erklärung entsteht im Hintergrund — geduldig nachfragen.
            for wartezeit: UInt64 in [6, 8, 10, 15, 20, 30] {
                try? await Task.sleep(nanoseconds: wartezeit * 1_000_000_000)
                if let e = await AblageService.briefErklaerung(pfad: pfad, basis: url, pat: pat) {
                    textSetzen(index, Chattexte.briefAntwort(
                        einfach: e.einfach, wasTun: e.wasTun,
                        bisWann: e.bisWann, hinweis: e.hinweis))
                    briefLaeuft = false
                    return
                }
            }
            textSetzen(index, "Der Brief liegt in deiner Belegbox. Die Erklärung dauert diesmal länger — schau gleich noch einmal rein.")
            briefLaeuft = false
        }
    }

    /// Wird nicht monatlich gezahlt, nennen wir auch den Betrag, der im
    /// Vertrag steht — sonst sieht die Umrechnung wie ein Lesefehler aus.
    private func vertragsbetrag(_ monatlich: Double,
                                _ zahlweise: String) -> (Double, String)? {
        switch zahlweise {
        case "jaehrlich":        return (monatlich * 12, "im Jahr")
        case "halbjaehrlich":    return (monatlich * 6, "im halben Jahr")
        case "vierteljaehrlich": return (monatlich * 3, "im Vierteljahr")
        default:                 return nil
        }
    }

    /// Vertrag fotografiert: ablegen, lesen lassen, Eckdaten zeigen.
    private func vertragSchicken(_ daten: Data, name: String) {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else {
            _ = anhaengen(ChatNachricht(vonMir: false,
                text: "Dafür braucht die App die Belegbox — einmal oben rechts im Menü verbinden."))
            return
        }
        briefLaeuft = true
        _ = anhaengen(ChatNachricht(vonMir: true, text: "📄 Vertrag"))
        let index = anhaengen(ChatNachricht(vonMir: false,
            text: "Ich lese deinen Vertrag — einen Moment …"))
        Task {
            guard let pfad = await AblageService.vertragAblegen(
                daten: daten, dateiname: name, basis: url, pat: pat) else {
                textSetzen(index, "Der Vertrag ließ sich gerade nicht ablegen — später noch einmal.")
                briefLaeuft = false
                return
            }
            for wartezeit: UInt64 in [6, 8, 10, 15, 20, 30] {
                try? await Task.sleep(nanoseconds: wartezeit * 1_000_000_000)
                if let v = await AblageService.vertragDaten(pfad: pfad, basis: url, pat: pat) {
                    var text = "\(v.art)\(v.partner.map { " mit \($0)" } ?? "")\n\n\(v.einfach)"
                    if let betrag = v.betrag {
                        text += "\n\nIch rechne ab jetzt mit \(fmtEur(betrag)) im Monat — "
                             + "auch wenn dafür mal keine Rechnung kommt."
                        // Bei Jahresbeiträgen sonst Verwirrung: im Vertrag steht
                        // 1.440 €, in der Auswertung 120 € — das muss dastehen.
                        if let (summe, wort) = vertragsbetrag(betrag, v.zahlweise) {
                            text += " Im Vertrag steht \(fmtEur(summe)) \(wort)."
                        }
                    }
                    textSetzen(index, text)
                    briefLaeuft = false
                    return
                }
            }
            textSetzen(index, "Der Vertrag liegt in deiner Ablage. Das Lesen dauert diesmal länger.")
            briefLaeuft = false
        }
    }

    private var leerHinweis: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Frag babu")
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
            Text("Zu deinen Belegen, zur App — und zu allem Steuerlichen, auch wenn es mit keinem einzelnen Beleg zu tun hat. Mit der Büroklammer fotografierst du einen Brief vom Amt: babu sagt dir, was er will und bis wann. Zum Beispiel:")
                .font(.footnote)
                .foregroundStyle(GC.desc)
            ForEach(["Wie viel habe ich im Juli für Bewirtung ausgegeben?",
                     "Muss ich die Rechnung aufheben?",
                     "Was ist eine Umsatzsteuervoranmeldung?",
                     "Was kann ich als Friseurin absetzen?",
                     "Brauche ich eine Kasse mit TSE?"], id: \.self) { beispiel in
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

    // MARK: - Verlauf (frühere Unterhaltungen, wie man es von Chats kennt)

    private var verlaufsListe: some View {
        NavigationStack {
            Group {
                if store.chatVerlauf.isEmpty && serverGespraeche.isEmpty {
                    Text("Noch keine früheren Fragen — stell einfach die erste.")
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                        .padding(24)
                } else {
                    List {
                        ForEach(store.chatVerlauf.sorted { $0.zuletzt > $1.zuletzt }) { u in
                            Button {
                                aktuelleID = u.id
                                zeigeVerlauf = false
                            } label: {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(u.titel)
                                        .font(.subheadline.weight(.medium))
                                        .foregroundStyle(GC.fg)
                                        .lineLimit(2)
                                    Text(u.zuletzt.formatted(date: .abbreviated,
                                                            time: .shortened))
                                        .font(.caption2)
                                        .foregroundStyle(GC.muted)
                                }
                            }
                            .swipeActions {
                                Button(role: .destructive) {
                                    store.chatVerlauf.removeAll { $0.id == u.id }
                                    if aktuelleID == u.id { aktuelleID = nil }
                                } label: {
                                    Label("Löschen", systemImage: "trash")
                                }
                            }
                        }
                        if !serverGespraeche.isEmpty { serverAbschnitt }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Frühere Fragen")
            .navigationBarTitleDisplayMode(.inline)
            .task { await serverGespraecheLaden() }
            .sheet(item: $serverGeoeffnet) { g in serverGespraechAnsicht(g) }
            .confirmationDialog("Alles vom Server löschen?",
                                isPresented: $serverFrageLoeschen,
                                titleVisibility: .visible) {
                Button("Alle \(serverGespraeche.count) löschen", role: .destructive) {
                    Task { await serverAllesLoeschen() }
                }
                Button("Abbrechen", role: .cancel) {}
            } message: {
                Text("Die Gespräche verschwinden vom Server. Deine Fragen hier "
                     + "in der App bleiben.")
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { zeigeVerlauf = false }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        aktuelleID = nil
                        zeigeVerlauf = false
                        feldAktiv = true
                    } label: {
                        Label("Neue Frage", systemImage: "square.and.pencil")
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    // MARK: - Was früher auf dem Server lag (BABU-25)
    //
    // Der Server hat jede Frage zusätzlich mitgeschrieben — unsichtbar, ohne
    // Weg dorthin und ohne Weg weg. Mitgeschrieben wird nicht mehr; was noch
    // liegt, steht hier: ansehen (Art. 15 DSGVO) und löschen (Art. 17).

    private var serverAbschnitt: some View {
        Section {
            ForEach(serverGespraeche) { g in
                Button {
                    serverGeoeffnet = g
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(g.titel)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(GC.fg)
                            .lineLimit(2)
                        Text("\(g.nachrichten) Nachricht"
                             + (g.nachrichten == 1 ? "" : "en")
                             + (Chattexte.datumDeutsch(g.zuletzt).map { " · \($0)" } ?? ""))
                            .font(.caption2)
                            .foregroundStyle(GC.muted)
                    }
                }
                .swipeActions {
                    Button(role: .destructive) {
                        Task { await serverLoeschen(g) }
                    } label: {
                        Label("Löschen", systemImage: "trash")
                    }
                }
            }
            Button(role: .destructive) {
                serverFrageLoeschen = true
            } label: {
                Label("Alle vom Server löschen", systemImage: "trash")
                    .font(.subheadline)
            }
        } header: {
            Text("Früher auf dem Server gespeichert")
        } footer: {
            Text("babu hat diese Gespräche früher zusätzlich auf dem Server "
                 + "abgelegt. Das tut es nicht mehr. Was damals gespeichert "
                 + "wurde, kannst du hier ansehen und löschen.")
                .font(.caption2)
        }
    }

    private func serverGespraechAnsicht(_ g: ServerGespraech) -> some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if serverNachrichten.isEmpty {
                        Text("Wird geladen …")
                            .font(.footnote)
                            .foregroundStyle(GC.muted)
                    }
                    ForEach(serverNachrichten) { blase($0) }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(GC.canvas)
            .navigationTitle(g.titel)
            .navigationBarTitleDisplayMode(.inline)
            .task {
                serverNachrichten = []
                guard let url = URL(string: store.ablageURL),
                      let pat = KeychainHelfer.ladePAT(),
                      let n = await AblageService.gespraechNachrichten(
                        id: g.id, basis: url, pat: pat) else { return }
                serverNachrichten = n.map {
                    ChatNachricht(vonMir: $0.vonMir, text: $0.text)
                }
            }
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { serverGeoeffnet = nil }
                }
                ToolbarItem(placement: .topBarLeading) {
                    Button("Löschen", role: .destructive) {
                        Task {
                            await serverLoeschen(g)
                            serverGeoeffnet = nil
                        }
                    }
                }
            }
        }
    }

    private func serverGespraecheLaden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        serverGespraeche = await AblageService.gespraecheLaden(basis: url, pat: pat) ?? []
    }

    private func serverLoeschen(_ g: ServerGespraech) async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        if await AblageService.gespraechLoeschen(id: g.id, basis: url, pat: pat) {
            serverGespraeche.removeAll { $0.id == g.id }
        }
    }

    private func serverAllesLoeschen() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        if await AblageService.gespraecheAlleLoeschen(basis: url, pat: pat) {
            serverGespraeche = []
        }
    }

    private func blase(_ nachricht: ChatNachricht) -> some View {
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
            Menu {
                Section("Brief vom Amt") {
                    PhotosPicker(selection: $briefAuswahl, matching: .images,
                                 photoLibrary: .shared()) {
                        Label("Fotografieren oder aus Fotos", systemImage: "camera")
                    }
                    Button {
                        zeigeBriefDateien = true
                    } label: {
                        Label("Aus Dateien (PDF)", systemImage: "folder")
                    }
                }
                Section("Vertrag") {
                    PhotosPicker(selection: $vertragAuswahl, matching: .images,
                                 photoLibrary: .shared()) {
                        Label("Mietvertrag & Co. fotografieren", systemImage: "doc.text")
                    }
                    Button {
                        zeigeVertragDateien = true
                    } label: {
                        Label("Vertrag aus Dateien (PDF)", systemImage: "folder")
                    }
                }
            } label: {
                Image(systemName: briefLaeuft ? "hourglass" : "paperclip")
                    .font(.system(size: 22))
                    .foregroundStyle(briefLaeuft ? GC.muted : GC.accent)
            }
            .disabled(briefLaeuft)
            .accessibilityLabel("Brief vom Amt ablegen")
            TextField("Frag mich etwas …", text: $eingabe, axis: .vertical)
                .lineLimit(1...4)
                .focused($feldAktiv)
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

    // MARK: - Senden (Verlauf liegt im Store und überlebt Neustarts)

    private func anhaengen(_ nachricht: ChatNachricht) -> Int {
        if aktuelleIndex == nil {
            let neu = ChatUnterhaltung(titel: nachricht.text, nachrichten: [],
                                       zuletzt: Date())
            store.chatVerlauf.append(neu)
            aktuelleID = neu.id
        }
        let i = aktuelleIndex!
        store.chatVerlauf[i].nachrichten.append(nachricht)
        store.chatVerlauf[i].zuletzt = Date()
        return store.chatVerlauf[i].nachrichten.count - 1
    }

    private func textSetzen(_ index: Int, _ text: String) {
        guard let i = aktuelleIndex,
              store.chatVerlauf[i].nachrichten.indices.contains(index) else { return }
        store.chatVerlauf[i].nachrichten[index].text = text
    }

    private func senden() {
        let frage = eingabe.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !frage.isEmpty, !laeuft else { return }
        eingabe = ""
        // Vor dem Anhängen greifen: die neue Frage geht als `frage` mit,
        // nicht noch einmal im Verlauf.
        let verlauf = Chattexte.verlaufFuerServer(nachrichten)
        _ = anhaengen(ChatNachricht(vonMir: true, text: frage))

        guard let url = URL(string: store.ablageURL), KeychainHelfer.ladePAT() != nil else {
            _ = anhaengen(ChatNachricht(vonMir: false,
                text: "Dafür braucht die App die Belegbox — verbinde dich einmal oben im Menü unter ‚Einstellungen'."))
            return
        }
        laeuft = true
        Task {
            let pat = KeychainHelfer.ladePAT() ?? ""
            let index = anhaengen(ChatNachricht(vonMir: false, text: ""))

            // Stream: Text erscheint, während die Antwort entsteht.
            var gestreamt = false
            var gesammelt = ""
            var gemeldet: String?
            do {
                for try await stueck in AblageService.fragenStream(
                        frage, verlauf: verlauf, basis: url, pat: pat) {
                    gestreamt = true
                    gesammelt += stueck
                    textSetzen(index, gesammelt)
                }
            } catch let fehler as ChatFehler {
                // Klarer Serverbescheid — anzeigen statt noch einmal 2 Minuten warten.
                gemeldet = "Das klappt gerade nicht: \(fehler.meldung). Später noch einmal versuchen."
            } catch {
                // Stream fehlgeschlagen — unten klassischer Fallback.
            }
            if let gemeldet {
                textSetzen(index, gemeldet)
            } else if !gestreamt {
                let antwort = await AblageService.fragen(frage, verlauf: verlauf,
                                                         basis: url, pat: pat)
                textSetzen(index, antwort
                    ?? "Gerade keine Verbindung — die Einstellungen oben im Menü prüfen und noch einmal fragen.")
            }
            laeuft = false
        }
    }
}
