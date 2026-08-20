import SwiftUI
import PhotosUI

/// Eine Chat-Nachricht — Codable, damit der Verlauf App-Neustarts überlebt.
struct ChatNachricht: Identifiable, Equatable, Codable {
    var id = UUID()
    let vonMir: Bool
    var text: String
}

/// Eine Unterhaltung: Titel ist die erste Frage — wie man es von Chats kennt.
struct ChatUnterhaltung: Identifiable, Equatable, Codable {
    var id = UUID()
    var titel: String
    var nachrichten: [ChatNachricht]
    var zuletzt: Date
}

/// Fragen an die Belegbox: Chat mit Gemma 4 auf der H200V — Antworten
/// aus den BelegReview-Daten plus Steuer-Grundfragen (`POST /chat`).
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
            .navigationTitle("Fragen")
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
                    Button("Fertig") { feldAktiv = false }
                }
            }
            .sheet(isPresented: $zeigeVerlauf) { verlaufsListe }
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
                text: "Dafür braucht die App die Belegbox — einmal im Export-Tab über das Zahnrad verbinden."))
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
                    var text = e.einfach
                    if let tun = e.wasTun, !tun.isEmpty { text += "\n\nWas du tun musst: \(tun)" }
                    if let bis = e.bisWann, !bis.isEmpty { text += "\n\nZeit bis: \(bis)" }
                    text += "\n\nDer Brief liegt jetzt sicher in deiner Belegbox."
                    textSetzen(index, text)
                    briefLaeuft = false
                    return
                }
            }
            textSetzen(index, "Der Brief liegt in deiner Belegbox. Die Erklärung dauert diesmal länger — schau gleich noch einmal rein.")
            briefLaeuft = false
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
            Text("Zu deinen Belegen, zur App und zu Steuerfragen. Mit der Büroklammer legst du Briefe vom Amt und Verträge ab — babu liest sie. Zum Beispiel:")
                .font(.footnote)
                .foregroundStyle(GC.desc)
            ForEach(["Wie viel habe ich im Juli für Bewirtung ausgegeben?",
                     "Was kann ich als Friseurin absetzen?",
                     "Wie trage ich mein Kassenbuch ein?",
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
                if store.chatVerlauf.isEmpty {
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
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Frühere Fragen")
            .navigationBarTitleDisplayMode(.inline)
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
        _ = anhaengen(ChatNachricht(vonMir: true, text: frage))

        guard let url = URL(string: store.ablageURL), KeychainHelfer.ladePAT() != nil else {
            _ = anhaengen(ChatNachricht(vonMir: false,
                text: "Dafür braucht die App die Belegbox — einmal im Export-Tab über das Zahnrad verbinden."))
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
                for try await stueck in AblageService.fragenStream(frage, basis: url, pat: pat) {
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
                let antwort = await AblageService.fragen(frage, basis: url, pat: pat)
                textSetzen(index, antwort
                    ?? "Gerade keine Verbindung — im Export-Tab (Zahnrad) prüfen und noch einmal fragen.")
            }
            laeuft = false
        }
    }
}
