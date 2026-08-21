import Foundation
import SwiftUI

/// Ablageort des persistierten App-Zustands (Application Support/Beleg).
private let zustandsDatei: URL = {
    let fm = FileManager.default
    let dir = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Beleg", isDirectory: true)
    try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir.appendingPathComponent("zustand.json")
}()

@MainActor
final class AppStore: ObservableObject {
    enum Tab: Hashable { case erfassen, belege, kasse, rechnungen, fragen, export }

    @Published var onboarded = false { didSet { speichern() } }
    @Published var skr = "SKR04" { didSet { speichern() } }
    @Published var belege: [Beleg] = [] { didSet { speichern() } }
    @Published var kassenberichte: [Kassenbericht] = [] { didSet { speichern() } }
    @Published var chatVerlauf: [ChatUnterhaltung] = [] { didSet { speichern() } }
    /// Rechnungsvorlagen — Empfängerin plus die Positionen, die sich
    /// wiederholen. Bleiben auf dem Gerät; gestellt wird über den Server.
    @Published var vorlagen: [Rechnungsvorlage] = [] { didSet { speichern() } }
    @Published var exportiert = false { didSet { speichern() } }
    @Published var geprueft = 0 { didSet { speichern() } }
    @Published var pruefSekunden: [Double] = [] { didSet { speichern() } }
    @Published var tab: Tab = .erfassen   // nicht persistiert
    /// Von außen geteilte Datei („Teilen → In babu öffnen") — der
    /// Erfassen-Bereich holt sie ab und verarbeitet sie wie einen Scan.
    @Published var geteilteDatei: URL?    // nicht persistiert

    // Belegbox-Übertragung (GitChain-Ablage) — Opt-in.
    // Öffentliche Route mit TLS via Cloudflare; funktioniert von überall.
    static let ablageStandardURL = "https://babu.0711.io"
    @Published var ablageURL = AppStore.ablageStandardURL { didSet { speichern() } }
    @Published var ablageAktiv = false { didSet { speichern() } }
    @Published var verbundenAls: String? { didSet { speichern() } }   // E-Mail des Kontos
    /// Der Server hat den Zugang abgelehnt (Konto abgeschaltet oder Schlüssel
    /// zurückgezogen). Dann darf die App nicht weiter „Verbunden ✓" behaupten.
    @Published var zugangAbgelaufen = false

    private var geladen = false
    private var speicherTask: Task<Void, Never>?

    init() {
        if let daten = try? Data(contentsOf: zustandsDatei),
           let z = try? JSONDecoder().decode(Zustand.self, from: daten) {
            onboarded = z.onboarded
            skr = z.skr
            belege = z.belege
            exportiert = z.exportiert
            geprueft = z.geprueft
            pruefSekunden = z.pruefSekunden
            // Migration: alte LAN-/Brücken-URLs auf die öffentliche Route heben.
            let alteURLs = ["http://192.168.145.10:7843", "http://192.168.5.93:7843"]
            if let gespeichert = z.ablageURL, !alteURLs.contains(gespeichert) {
                ablageURL = gespeichert
            } else {
                ablageURL = AppStore.ablageStandardURL
            }
            ablageAktiv = z.ablageAktiv ?? false
            kassenberichte = z.kassenberichte ?? []
            chatVerlauf = z.chatVerlauf ?? []
        vorlagen = z.vorlagen ?? []
            verbundenAls = z.verbundenAls
            // Ältere Stände: Demo-Belege am festen Demo-Siegel nachträglich
            // markieren, damit sie nie im echten Stapel landen.
            let demoSiegel: Set<String> = ["77b2e0c4 9a11 f38d", "0d31f6a8 5be2 c974"]
            for i in belege.indices where belege[i].istDemo != true && demoSiegel.contains(belege[i].siegel ?? "") {
                belege[i].istDemo = true
            }
        } else {
            #if targetEnvironment(simulator)
            belege = Demo.archiv()   // Nur im Simulator: Demo-Archiv als Ausgangslage
            #endif
        }
        geladen = true
    }

    // MARK: - Persistenz

    /// Alles, was einen App-Neustart überleben muss — Belege inkl. Bild-JPEGs.
    /// Neue Felder optional, damit ältere zustand.json weiter dekodiert.
    private struct Zustand: Codable {
        var onboarded: Bool
        var skr: String
        var belege: [Beleg]
        var exportiert: Bool
        var geprueft: Int
        var pruefSekunden: [Double]
        var ablageURL: String?
        var ablageAktiv: Bool?
        var kassenberichte: [Kassenbericht]?
        var chatVerlauf: [ChatUnterhaltung]?
        var verbundenAls: String?
        // Neu ab 22.08.2026 — optional, damit ältere Stände weiter laden.
        var vorlagen: [Rechnungsvorlage]?
    }

    private var zustand: Zustand {
        Zustand(onboarded: onboarded, skr: skr, belege: belege,
                exportiert: exportiert, geprueft: geprueft, pruefSekunden: pruefSekunden,
                ablageURL: ablageURL, ablageAktiv: ablageAktiv,
                kassenberichte: kassenberichte, chatVerlauf: chatVerlauf,
                verbundenAls: verbundenAls, vorlagen: vorlagen)
    }

    /// Entprellt auf ~0,25 s, damit Serien-Änderungen nicht pro Mutation schreiben.
    private func speichern() {
        guard geladen else { return }
        let z = zustand
        speicherTask?.cancel()
        speicherTask = Task.detached(priority: .utility) {
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            Self.schreibe(z)
        }
    }

    /// Sofort schreiben — beim Wechsel in den Hintergrund aufgerufen.
    func sichern() {
        guard geladen else { return }
        speicherTask?.cancel()
        Self.schreibe(zustand)
    }

    private nonisolated static func schreibe(_ z: Zustand) {
        guard let daten = try? JSONEncoder().encode(z) else { return }
        try? daten.write(to: zustandsDatei, options: .atomic)
    }

    /// OCR-Felder → geroutete Buchung (auto / bestätigen / prüfen).
    func routen(felder: Felder, bildJpeg: Data?, ocrText: String) -> Beleg {
        let v = Kontierung.vorschlag(felder: felder)
        var beleg = Beleg(
            lieferant: felder.lieferant ?? "Unbekannter Lieferant",
            belegNr: felder.belegNr ?? "ohne Nr.",
            datumText: felder.datumText ?? DateFormatter.kurz.string(from: Date()),
            netto: felder.netto ?? 0,
            ust: felder.ust ?? 0,
            brutto: felder.brutto ?? 0,
            ustSatz: felder.ustSatz,
            konto: v.konto,
            steuerschluessel: v.steuerschluessel,
            kreditor: v.kreditor,
            herkunft: v.herkunft,
            confidence: v.confidence,
            status: .offen,
            begruendung: v.begruendung,
            summenprobeOK: felder.summenprobeOK
        )
        beleg.bildJpeg = bildJpeg
        beleg.ocrText = ocrText
        beleg.steuerPositionen = felder.steuerPositionen.isEmpty ? nil : felder.steuerPositionen
        beleg.gutschriftSignal = felder.gutschriftSignal ? true : nil

        if beleg.confidence >= 95 {
            siegeln(&beleg, status: .automatisch)
        }
        if ablageAktiv, bildJpeg != nil {
            beleg.ablageStatus = .ausstehend
            beleg.ablageDateiname = ablageDateiname(fuer: beleg)
        }
        belege.insert(beleg, at: 0)
        if beleg.ablageStatus == .ausstehend {
            let id = beleg.id
            Task { await self.uebertrage(id) }
        }
        return beleg
    }

    // MARK: - Belegbox-Übertragung

    /// Beim Einschalten der Belegbox: Bestandsbelege ohne Übertragungsstatus
    /// in die Warteschlange nehmen — sonst würden sie nie zweitgeprüft.
    func altBelegeNachreichen() {
        guard ablageAktiv else { return }
        for i in belege.indices where belege[i].ablageStatus == nil
            && belege[i].bildJpeg != nil && belege[i].istDemo != true {
            belege[i].ablageStatus = .ausstehend
            belege[i].ablageDateiname = belege[i].ablageDateiname
                ?? ablageDateiname(fuer: belege[i])
        }
        ablageRetry()
    }

    /// Alle offenen Übertragungen erneut anstoßen (App-Start, Foreground, manuell).
    func ablageRetry() {
        guard ablageAktiv else { return }
        for b in belege where b.ablageStatus == .ausstehend || b.ablageStatus == .fehlgeschlagen {
            let id = b.id
            Task { await self.uebertrage(id) }
        }
        kassenRetry()
    }

    /// Läuft gerade ein Upload für diese ID? Verhindert doppelte
    /// `aufnahme:`-Commits, wenn routen() und ablageRetry() zusammenfallen.
    private var uploadLaeuft: Set<UUID> = []

    /// Einzelnen Beleg in die GitChain-Ablage hochladen; Status am Beleg nachführen.
    func uebertrage(_ id: UUID) async {
        guard !uploadLaeuft.contains(id) else { return }
        guard ablageAktiv,
              let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].ablageStatus != .uebertragen,
              let jpeg = belege[i].bildJpeg else { return }
        uploadLaeuft.insert(id)
        defer { uploadLaeuft.remove(id) }

        let dateiname = belege[i].ablageDateiname ?? ablageDateiname(fuer: belege[i])
        belege[i].ablageDateiname = dateiname
        belege[i].ablageStatus = .ausstehend

        // Der auf dem Gerät gelesene Text geht mit: daraus entscheidet der
        // Server, ob das ein Bon, ein Vertrag, ein Brief vom Amt oder ein
        // Kontoauszug ist — die Nutzerin muss nichts auswählen.
        let (ergebnis, serverDatei, art, wohin, _) = await AblageService.aufnahme(
            daten: jpeg, dateiname: dateiname, gelesenerText: belege[i].ocrText,
            basis: url, pat: pat)
        pruefeZugang(ergebnis)
        guard let j = belege.firstIndex(where: { $0.id == id }) else { return }
        switch ergebnis {
        case .uebertragen:
            belege[j].ablageStatus = .uebertragen
            belege[j].ablageZeit = Date()
            belege[j].abgelegtAls = art
            belege[j].abgelegtWohin = wohin
            // Serverseitiger Name (mit Zeitstempel-Präfix) ist der Schlüssel
            // zum BelegReview-Ergebnis.
            if let serverDatei { belege[j].ablageDateiname = serverDatei }
            // Audit-Stempel nachladen — Backoff-Polling statt Einmal-Schuss:
            // die Prüfung braucht je nach Rückstau Sekunden bis Minuten.
            Task {
                for wartezeit: UInt64 in [10, 20, 40, 80, 160] {
                    try? await Task.sleep(nanoseconds: wartezeit * 1_000_000_000)
                    await self.auditLaden(id)
                    if self.belege.first(where: { $0.id == id })?.auditReview != nil { break }
                }
            }
        default:
            belege[j].ablageStatus = .fehlgeschlagen
        }
    }

    // MARK: - Audit-Stempel (GitChain-Commits am Beleg persistieren)

    /// Für alle übertragenen Belege ohne Stempel das Review abfragen.
    func auditNachladen() {
        guard ablageAktiv, KeychainHelfer.ladePAT() != nil else { return }
        for b in belege where b.ablageStatus == .uebertragen && b.auditReview == nil {
            let id = b.id
            Task { await self.auditLaden(id) }
        }
    }

    func auditLaden(_ id: UUID) async {
        guard let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].auditReview == nil,
              let dateiname = belege[i].ablageDateiname else { return }
        let stamm = (dateiname as NSString).deletingPathExtension
        guard case .fertig(let review) = await AblageService.reviewAbrufen(
            stamm: stamm, basis: url, pat: pat), let audit = review.audit else { return }
        auditSetzen(id: id, aufnahme: audit.aufnahme?.commit, review: audit.review?.commit,
                    status: review.fehlgeschlagen ? "fehlgeschlagen" : "ok")
    }

    func auditSetzen(id: UUID, aufnahme: String?, review: String?, status: String? = nil) {
        guard let i = belege.firstIndex(where: { $0.id == id }) else { return }
        if let aufnahme { belege[i].auditAufnahme = aufnahme }
        if let review { belege[i].auditReview = review }
        if let status { belege[i].reviewStatus = status }
    }

    /// Bewirtungsangaben (§4 Abs. 5 EStG) am Beleg erfassen. Fixierte Belege
    /// sind unantastbar; gesiegelte werden mit den Angaben neu gesiegelt —
    /// das Siegel deckt die Bewirtungsangaben mit ab.
    func bewirtungSetzen(id: UUID, anlass: String, personen: String) {
        guard let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].status != .fixiert else { return }
        var b = belege[i]
        b.bewirtungAnlass = anlass.trimmingCharacters(in: .whitespacesAndNewlines)
        b.bewirtungPersonen = personen.trimmingCharacters(in: .whitespacesAndNewlines)
        if b.siegel != nil { siegeln(&b, status: b.status) }
        belege[i] = b
    }

    func siegeln(_ beleg: inout Beleg, status: BelegStatus) {
        let zeit = Date()
        beleg.status = status
        beleg.siegelZeit = zeit
        beleg.siegel = siegelHash(beleg, zeit: zeit)
    }

    /// Bestätigen/Korrigieren aus Ein-Tap-Karte oder Review.
    func buchen(id: UUID, konto: String?, steuerschluessel: String?, dauer: Double?) {
        guard let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].status != .fixiert else { return }
        var b = belege[i]
        var korrigiert = false
        if let k = konto, k != b.konto { b.konto = k; korrigiert = true }
        if let ks = steuerschluessel, ks != b.steuerschluessel { b.steuerschluessel = ks; korrigiert = true }
        if korrigiert { b.herkunft = .mensch }
        siegeln(&b, status: korrigiert ? .korrigiert : .bestaetigt)
        belege[i] = b
        geprueft += 1
        if let d = dauer { pruefSekunden.append(d) }
    }

    /// Kernfelder von Hand korrigieren — die Lesung kann danebenliegen
    /// (119 → 19 €), und Löschen + neu fotografieren ist keine Antwort.
    /// Fixierte Belege sind unantastbar; gesiegelte werden neu gesiegelt.
    func felderKorrigieren(id: UUID, lieferant: String, belegNr: String,
                           datumText: String, netto: Double, ust: Double, brutto: Double) {
        guard let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].status != .fixiert else { return }
        var b = belege[i]
        b.lieferant = lieferant.trimmingCharacters(in: .whitespacesAndNewlines)
        b.belegNr = belegNr.trimmingCharacters(in: .whitespacesAndNewlines)
        b.datumText = datumText.trimmingCharacters(in: .whitespaces)
        b.netto = netto
        b.ust = ust
        b.brutto = brutto
        b.summenprobeOK = abs(netto + ust - brutto) < 0.011
        b.herkunft = .mensch
        // Handkorrektur ersetzt die gelesene Tabelle — sie passt nicht mehr.
        b.steuerPositionen = nil
        if b.siegel != nil { siegeln(&b, status: b.status) }
        belege[i] = b
    }

    /// Beleg entfernen — fixierte (exportierte) Belege sind unantastbar.
    func loeschen(id: UUID) {
        belege.removeAll { $0.id == id && $0.status != .fixiert }
    }

    var exportierbar: [Beleg] {
        exportierbareBelege(belege)
    }

    var stapelSumme: Double { exportierbar.reduce(0) { $0 + $1.brutto } }

    // MARK: - EXTF

    /// Vorschau des aktuellen Stapels (Logik in ExtfWriter.swift, harness-getestet).
    func extfText() -> String {
        let monat = extfMonat()
        return extfStapelText(belege: exportierbar, von: monat.von, bis: monat.bis)
    }

    /// Schreibt eine feste Belegmenge als CP1252-kodierte Datei (DATEV-Kodierung).
    func extfDatei(fuer stapel: [Beleg]) -> URL? {
        let monat = extfMonat()
        let text = extfStapelText(belege: stapel, von: monat.von, bis: monat.bis)
        let data = text.data(using: .windowsCP1252, allowLossyConversion: true) ?? Data(text.utf8)
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent(monat.dateiname)
        do {
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            return nil
        }
    }

    /// Vorschau-Datei über den aktuell exportierbaren Stapel.
    func extfDatei() -> URL? { extfDatei(fuer: exportierbar) }

    /// Bereits fixierte Belege — damit die Datei nach einem App-Neustart
    /// weiter teilbar ist (sie lässt sich jederzeit neu erzeugen).
    var fixierte: [Beleg] {
        belege.filter { $0.status == .fixiert && $0.istDemo != true }
    }

    /// Stapel exportieren: ERST die Datei aus dem Schnappschuss erzeugen,
    /// DANN genau diese Belege fixieren — andersherum wäre die Datei leer,
    /// weil `exportierbar` fixierte Belege ausfiltert.
    func exportieren() -> URL? {
        let stapel = exportierbar
        guard !stapel.isEmpty, let url = extfDatei(fuer: stapel) else { return nil }
        let ids = Set(stapel.map(\.id))
        for i in belege.indices where ids.contains(belege[i].id) {
            belege[i].status = .fixiert
        }
        exportiert = true
        return url
    }

    // MARK: - Kassenbuch (Tagessummen, siehe Kassenbuch.swift)

    func kassenbericht(fuer tag: String) -> Kassenbericht? {
        kassenberichte.first { $0.datum == tag }
    }

    /// Speichert oder ersetzt den Bericht des Tages (ein Bericht pro Tag)
    /// und legt das Tagesblatt in der Belegbox ab (wenn verbunden).
    func kassenberichtSpeichern(_ bericht: Kassenbericht) {
        var neu = bericht
        neu.uebermittelt = nil   // geänderte Zahlen → frisch übermitteln
        if let i = kassenberichte.firstIndex(where: { $0.datum == bericht.datum }) {
            kassenberichte[i] = neu
        } else {
            kassenberichte.append(neu)
        }
        let tag = neu.datum
        Task { await self.kassenblattSenden(tag) }
    }

    /// Ein Tagesblatt an die Belegbox senden (POST /api/kassenbuch).
    func kassenblattSenden(_ tag: String) async {
        guard ablageAktiv,
              let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              let bericht = kassenbericht(fuer: tag),
              bericht.uebermittelt == nil else { return }
        let ok = await AblageService.kassenblattSenden(bericht, basis: url, pat: pat)
        if ok, let i = kassenberichte.firstIndex(where: { $0.datum == tag }) {
            kassenberichte[i].uebermittelt = Date()
        }
    }

    /// Alles, was beim Sichtbarwerden der App zu erledigen ist.
    ///
    /// Muss von ZWEI Stellen kommen: `scenePhase` meldet nur Wechsel, beim
    /// Kaltstart ist die Szene schon aktiv und es feuert nichts. Ohne den
    /// zweiten Aufruf bliebe ein Beleg, der ohne Netz aufgenommen wurde,
    /// liegen, bis man die App zufällig verlässt und zurückkehrt.
    /// Doppelt aufgerufen zu werden schadet nicht — alle drei prüfen selbst,
    /// ob es etwas zu tun gibt.
    func beimSichtbarwerden() {
        ablageRetry()        // offene Belegbox-Uploads nachholen
        auditNachladen()     // Prüfstempel für Übertragene holen
        zugangNachsehen()    // gilt der Zugang überhaupt noch?
    }

    /// Beim App-Start still nachsehen, ob der Zugang noch gilt. Sonst
    /// stünde bis zum nächsten Beleg „Verbunden ✓" da, obwohl nichts
    /// mehr ankommt.
    func zugangNachsehen() {
        guard verbundenAls != nil, ablageAktiv,
              let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        Task {
            let ergebnis = await AblageService.verbindungstest(basis: url, pat: pat)
            switch ergebnis {
            case .tokenFehler: self.zugangAbgelaufen = true
            case .uebertragen: self.zugangAbgelaufen = false
            default: break   // offline sagt nichts über den Zugang aus
            }
        }
    }

    /// Sagt der Server „dein Zugang gilt nicht", hört die App auf, das
    /// Gegenteil zu behaupten — sonst wandern Belege still ins Leere.
    func pruefeZugang(_ ergebnis: AblageErgebnis) {
        if ergebnis == .tokenFehler {
            zugangAbgelaufen = true
        } else if ergebnis == .uebertragen {
            zugangAbgelaufen = false
        }
    }

    /// Noch nicht übermittelte Tagesblätter nachreichen (App-Start/Foreground).
    func kassenRetry() {
        guard ablageAktiv else { return }
        for b in kassenberichte where b.uebermittelt == nil {
            let tag = b.datum
            Task { await self.kassenblattSenden(tag) }
        }
    }

    /// Vorschlag für „Bestand am Vortag": der gezählte Schluss des jüngsten
    /// Berichts VOR dem Tag — so muss die Zahl nicht abgetippt werden.
    func kassenVortagsbestand(vor tag: String) -> Double? {
        kassenberichte.filter { $0.datum < tag }
            .max { $0.datum < $1.datum }?.gezaehltSchluss
    }

    var durchsatzText: String? {
        guard geprueft > 0, !pruefSekunden.isEmpty else { return nil }
        let avg = pruefSekunden.reduce(0, +) / Double(pruefSekunden.count)
        return "\(geprueft) geprüft · ø \(Int(avg.rounded())) s/Beleg"
    }
}

extension DateFormatter {
    static let kurz: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "dd.MM.yyyy"
        return f
    }()

    static let siegel: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "dd.MM.yyyy HH:mm:ss"
        return f
    }()
}
