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
    // `rechnungen` ist kein Tab mehr — Rechnungen liegen im Konto-Menü
    // unter Buchhaltung. Der Fall bleibt, damit alte gespeicherte
    // Stände nicht beim Laden stolpern.
    enum Tab: Hashable { case erfassen, belege, termine, kasse, rechnungen,
                         fragen, export }

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
    /// Die Rolle des angemeldeten Kontos — „salon" oder „mitarbeit".
    /// Wird beim Nachfragen mitgeliefert und im Konto angezeigt, damit
    /// sichtbar ist, WOMIT man angemeldet ist, nicht nur DASS.
    @Published var verbundenRolle: String? { didSet { speichern() } }

    /// Das Profil des Salons (Betriebsangaben) — liegt auf dem Telefon und
    /// reist mit jeder Einschätzungs-Anfrage mit. Quelle: api/einstellungen,
    /// beim ersten Bedarf geholt und hier gehalten.
    @Published var profil: [String: String] = [:] { didSet { speichern() } }

    /// Testphase: zeigt Werkzeuge, die im Alltag nichts zu suchen haben.
    /// Hinter dem Schalter, weil ein Zurücksetzen sonst einen Fingerbreit
    /// neben „Verbindung testen" liegt.
    @Published var testmodus = false { didSet { speichern() } }

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
            verbundenRolle = z.verbundenRolle
            testmodus = z.testmodus ?? false
            profil = z.profil ?? [:]
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
        var verbundenRolle: String?
        // Neu ab 22.08.2026 — optional, damit ältere Stände weiter laden.
        var vorlagen: [Rechnungsvorlage]?
        var testmodus: Bool?
        // Neu ab 24.08.2026: das Salon-Profil fürs Telefon.
        var profil: [String: String]?
    }

    private var zustand: Zustand {
        Zustand(onboarded: onboarded, skr: skr, belege: belege,
                exportiert: exportiert, geprueft: geprueft, pruefSekunden: pruefSekunden,
                ablageURL: ablageURL, ablageAktiv: ablageAktiv,
                kassenberichte: kassenberichte, chatVerlauf: chatVerlauf,
                verbundenAls: verbundenAls, verbundenRolle: verbundenRolle,
                vorlagen: vorlagen,
                testmodus: testmodus, profil: profil)
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
        if let w = felder.waehrung {
            // Fremdwährung: die gelesenen Zahlen sind KEINE Euro. Original
            // festhalten, Steuerfelder neutralisieren — den Euro-Wert setzt
            // die Buchhaltung (Kontoauszug-Abgleich oder Kurs).
            beleg.fremdBetrag = felder.brutto
            beleg.fremdWaehrung = w
            beleg.ust = 0
            beleg.netto = beleg.brutto
            beleg.ustSatz = 0
            beleg.steuerschluessel = "0"
        }

        // Das Telefon beurteilt die Qualität und liefert eine Erstauswertung —
        // verbindlich gebucht wird aus der Lesung der Belegbox (PaddleOCR),
        // sobald sie da ist (ausZweitpruefungUebernehmen). Nur OHNE Belegbox
        // bleibt der alte Sofort-Weg, sonst gäbe es gar keinen.
        if !ablageAktiv, beleg.confidence >= 95, beleg.fremdWaehrung == nil {
            siegeln(&beleg, status: .automatisch)
        }
        if ablageAktiv, bildJpeg != nil {
            beleg.ablageStatus = .ausstehend
            beleg.ablageDateiname = ablageDateiname(fuer: beleg)
        }
        belege.insert(beleg, at: 0)
        // Zielbild: hochgeladen wird erst NACH der Einschätzung — mit Gemmas
        // Buchung und Dokumentklasse im Gepäck (ablageErgebnisSetzen →
        // uebertrage). ablageRetry() bleibt das Netz für alles, was hängt.
        return beleg
    }

    /// Das Ergebnis der Einschätzung an den Beleg heften — Fach (Klasse) und
    /// Buchung reisen beim Upload mit und werden zur archivierten Lesung.
    func ablageErgebnisSetzen(id: UUID, klasse: String?, buchungJson: String?) {
        guard let i = belege.firstIndex(where: { $0.id == id }) else { return }
        belege[i].dokumentklasse = klasse
        if let buchungJson {
            let zeilen = belege[i].ocrText
                .split(separator: "\n").map { String($0) }
            let zeilenJson = (try? JSONSerialization.data(withJSONObject: zeilen))
                .flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
            belege[i].ergebnisJson = "{\"klasse\": \"\(klasse ?? "beleg")\", "
                + "\"buchung\": \(buchungJson), \"zeilen\": \(zeilenJson)}"
        }
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
    /// Beim Server nachfragen, als wer dieses Gerät angemeldet ist.
    ///
    /// Ein Gerät kann einen gültigen Schlüssel haben, ohne den Namen zu
    /// kennen — bei Ninas Telefon war das so, der Schlüssel stammt aus
    /// einer älteren Fassung. „Verbunden" ohne Namen ist keine Auskunft.
    /// Die Antwort sagt außerdem ehrlich, ob der Zugang noch gilt.
    @MainActor
    func kontoNachfragen() async {
        guard let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        let antwort = await AblageService.werBinIch(basis: url, pat: pat)
        if antwort.abgelaufen {
            zugangAbgelaufen = true
            return
        }
        guard let un = antwort.un else { return }   // kein Netz — nichts ändern
        zugangAbgelaufen = false
        if verbundenAls != un { verbundenAls = un }
        if verbundenRolle != antwort.rolle { verbundenRolle = antwort.rolle }
    }

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
            ergebnis: belege[i].ergebnisJson, basis: url, pat: pat)
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
            // Die Lesung liegt im SELBEN Commit wie das Foto (Zielbild:
            // keine zweite Lesung) — einmal die Prüfstempel holen genügt.
            Task {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                await self.auditLaden(id)
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

    /// Die Serverlesung holen — und ANWENDEN.
    ///
    /// Bis 23.08.2026 holte diese Stelle nur die Prüfstempel. Übernommen
    /// wurde die Lesung erst, wenn jemand den Beleg von Hand aufmachte
    /// (ListeView.reviewLaden). Bis dahin stand überall — in der Liste, in
    /// der Ergebniskarte, im Export — das, was das Telefon geraten hatte.
    ///
    /// Das Gerät liest mit Vision auf einem Foto; der Server liest mit
    /// Paddle und deutet mit Geometrie. Wenn die beiden sich unterscheiden,
    /// hat der Server recht. Also gilt seine Lesung, sobald sie da ist —
    /// nicht, sobald jemand hinsieht.
    func auditLaden(_ id: UUID) async {
        guard let url = URL(string: ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].auditReview == nil,
              let dateiname = belege[i].ablageDateiname else { return }
        let stamm = (dateiname as NSString).deletingPathExtension
        guard case .fertig(let review) = await AblageService.reviewAbrufen(
            stamm: stamm, basis: url, pat: pat) else { return }
        // Zielbild: die Lesung entsteht auf dem Telefon und wird archiviert —
        // NICHTS überschreibt Ninas Ergebnis nachträglich. Hier zählen nur
        // noch die Prüfstempel des Archivs.
        guard let audit = review.audit else { return }
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

    /// ISO in das Format bringen, das die App führt.
    ///
    /// Der Server schreibt Daten als `2026-03-05`, die App als `05.03.2026`.
    /// Das ist kein Schönheitsunterschied: `extfBelegdatum` zerlegt an
    /// Punkten, und aus einem ISO-Datum wird dort ein LEERES Belegdatum im
    /// DATEV-Stapel. Ein Buchungssatz ohne Belegdatum fällt beim
    /// Steuerberater durch — oder schlimmer, fällt nicht auf.
    private func deutschesDatum(_ iso: String?) -> String? {
        guard let iso, !iso.isEmpty else { return nil }
        let teile = iso.split(separator: "-")
        guard teile.count == 3, teile[0].count == 4,
              let j = Int(teile[0]), let m = Int(teile[1]), let t = Int(teile[2]),
              (1...12).contains(m), (1...31).contains(t)
        else { return iso.contains(".") ? iso : nil }   // schon deutsch, oder Murks
        return String(format: "%02d.%02d.%04d", t, m, j)
    }

    /// Was der Server gelesen hat, wird die Wahrheit des Belegs.
    ///
    /// Die App liest jeden Beleg auf dem Gerät selbst — schnell, offline,
    /// aus der Kamera heraus. Das ist gut für den Moment der Aufnahme, aber
    /// es ist eine Texterkennung auf einem Telefon. Der Server liest
    /// denselben Beleg danach mit PaddleOCR auf der Grafikkarte, deutet ihn
    /// über seine Geometrie und lässt ein Bildmodell gegenprüfen.
    ///
    /// An Beleg 0861 (Müller, 05.03.2026, 9,03 €) war das sichtbar: das
    /// Gerät las falsch, der Server richtig — und angezeigt wurde das
    /// Gerät. Also gilt ab jetzt: sobald die Zweitprüfung da ist, zählt
    /// sie.
    ///
    /// Drei Grenzen, und die sind wichtig:
    ///
    /// 1. Ein **fixierter** Beleg ist exportiert und unantastbar.
    /// 2. Was **ein Mensch korrigiert** hat, bleibt stehen. Wer von Hand
    ///    eingreift, hat den Beleg in der Hand gehabt — dagegen rechnet
    ///    keine Maschine an.
    /// 3. Übernommen wird nur, was der Server auch wirklich gelesen hat.
    ///    Ein leeres Feld überschreibt nie ein gefülltes.
    ///
    /// Gibt zurück, ob sich etwas geändert hat — dann lohnt das Speichern.
    @discardableResult
    func ausZweitpruefungUebernehmen(id: UUID, review: BelegReviewDaten) -> Bool {
        guard let i = belege.firstIndex(where: { $0.id == id }) else { return false }
        var b = belege[i]
        guard b.status != .fixiert, b.status != .korrigiert, !review.fehlgeschlagen
        else { return false }

        let f = review.felder ?? BelegReviewDaten.Felder()
        var geaendert = false
        func setz<T: Equatable>(_ pfad: WritableKeyPath<Beleg, T>, _ neu: T?) {
            guard let neu, b[keyPath: pfad] != neu else { return }
            b[keyPath: pfad] = neu
            geaendert = true
        }

        setz(\.lieferant, f.lieferant?.trimmingCharacters(in: .whitespacesAndNewlines)
                             .isEmpty == false ? f.lieferant : nil)
        setz(\.belegNr, f.belegNr?.isEmpty == false ? f.belegNr : nil)
        setz(\.datumText, deutschesDatum(f.datum))
        setz(\.brutto, f.brutto)
        setz(\.netto, f.netto)
        setz(\.ust, f.ust)
        setz(\.ustSatz, f.ustSatz)
        setz(\.konto, review.einschaetzung?.kontoSkr04)
        setz(\.steuerschluessel, review.einschaetzung?.steuerschluessel)

        // Die Buchhaltung (Gemma Vision) hat den Beleg SELBST gelesen — ihre
        // Lesung schlägt die Paddle-Felder, sonst zeigt die Übersicht alte
        // Werte, während das Protokoll längst die richtigen kennt.
        if review.buchung?.status == "gebucht", let g = review.buchung?.buchung {
            setz(\.lieferant, g.lieferant?.trimmingCharacters(in: .whitespacesAndNewlines)
                                 .isEmpty == false ? g.lieferant : nil)
            setz(\.datumText, deutschesDatum(g.datum))
            if let w = g.waehrung?.uppercased(), w != "EUR" {
                setz(\.fremdBetrag, g.betrag)
                setz(\.fremdWaehrung, w)
            }
            if let e = g.betragEur, e > 0 {
                let satz = g.ustSatz ?? 0
                setz(\.brutto, e)
                setz(\.netto, (e / (1 + Double(satz) / 100) * 100).rounded() / 100)
                setz(\.ust, ((e - e / (1 + Double(satz) / 100)) * 100).rounded() / 100)
                setz(\.ustSatz, satz)
            }
            setz(\.konto, g.konto)
            setz(\.begruendung, g.begruendung?.isEmpty == false ? g.begruendung : nil)
            if let satz = g.ustSatz {
                setz(\.steuerschluessel, satz == 19 ? "9" : satz == 7 ? "8" : "0")
            }
            if let tabelle = g.steuersaetze, !tabelle.isEmpty {
                steuertabelleAnwenden(&b, tabelle)
                geaendert = true
            }
        }

        if geaendert {
            b.summenprobeOK = abs(b.netto + b.ust - b.brutto) < 0.011
            // Die Herkunft sagt jetzt die Wahrheit: das kam nicht vom Gerät.
            b.herkunft = .ki
            // Eine übernommene Lesung macht die auf dem Gerät gelesene
            // Steuertabelle ungültig — sie gehört zu den alten Zahlen.
            b.steuerPositionen = nil
            if b.siegel != nil { siegeln(&b, status: b.status) }
        }

        // Erst mit der Serverlesung wird gebucht — das Telefon hatte nur
        // vorgeschlagen. Gebucht wird still aber nur, wenn nichts offen ist:
        // ohne Konto oder mit offener Bewirtungsfrage bleibt der Beleg im
        // Aufräumen-Stapel, statt falsch in den Export zu rutschen.
        if b.status == .offen,
           let konto = b.konto, !konto.isEmpty,
           !b.brauchtBewirtungsangaben,
           b.brutto > 0 {
            siegeln(&b, status: .automatisch)
            b.offeneFrage = nil
            geaendert = true
        } else if b.status == .offen, b.offeneFrage == nil {
            // Nicht still gebucht — dann hat die Buchhaltung Fragen. Der
            // Merker macht den Beleg in der Ablage als „noch nicht fertig"
            // sichtbar; die eigentlichen Fragen holt das Fragen-Blatt live.
            b.offeneFrage = "babu hat noch Fragen zu diesem Beleg."
            geaendert = true
        }

        guard geaendert else { return false }
        belege[i] = b
        return true
    }

    /// Die Buchung aus Gemmas Fragerunde übernehmen — die Belegbox hat
    /// entschieden, samt Konto aus dem geprüften Katalog. Bei Fremdwährung
    /// wird der Euro-Betrag gebucht; der Originalbetrag bleibt am Beleg.
    func gemmaBuchungAnwenden(id: UUID, konto: String, ustSatz: Int,
                              betragEur: Double, waehrung: String,
                              begruendung: String, lieferant: String? = nil,
                              datum: String? = nil,
                              steuersaetze: [SteuerPosition] = []) {
        guard let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].status != .fixiert else { return }
        var b = belege[i]
        b.konto = konto
        b.steuerschluessel = ustSatz == 19 ? "9" : (ustSatz == 7 ? "8" : "0")
        // Die Buchhaltung hat den Beleg selbst gelesen — ihre Felder gelten,
        // sonst zeigt die Übersicht weiter die alte Telefon-Lesung.
        if let l = lieferant?.trimmingCharacters(in: .whitespacesAndNewlines),
           !l.isEmpty { b.lieferant = l }
        if let d = deutschesDatum(datum) { b.datumText = d }
        if betragEur > 0, waehrung != "EUR" {
            b.fremdBetrag = b.fremdBetrag ?? b.brutto
            b.fremdWaehrung = waehrung
        }
        if betragEur > 0 {
            b.brutto = betragEur
            b.netto = (betragEur / (1 + Double(ustSatz) / 100) * 100).rounded() / 100
            b.ust = ((b.brutto - b.netto) * 100).rounded() / 100
            b.ustSatz = ustSatz
            b.summenprobeOK = true
        }
        if !begruendung.isEmpty { b.begruendung = begruendung }
        steuertabelleAnwenden(&b, steuersaetze)
        b.herkunft = .ki
        b.offeneFrage = nil
        siegeln(&b, status: .automatisch)
        belege[i] = b
        geprueft += 1
    }

    /// Die Steuertabelle der Buchhaltung übernehmen — aber nur, wenn sie den
    /// Beleg wirklich deckt (Summe ≈ Brutto). Bei Mischsätzen ersetzt sie die
    /// eine Zahl, die es dann nicht mehr gibt.
    private func steuertabelleAnwenden(_ b: inout Beleg,
                                       _ tabelle: [SteuerPosition]) {
        guard !tabelle.isEmpty else { return }
        let summe = tabelle.reduce(0) { $0 + $1.brutto }
        guard abs(summe - b.brutto) < 0.02 else { return }
        b.netto = ((tabelle.reduce(0) { $0 + $1.netto }) * 100).rounded() / 100
        b.ust = ((tabelle.reduce(0) { $0 + $1.ust }) * 100).rounded() / 100
        b.ustSatz = tabelle.max(by: { $0.brutto < $1.brutto })?.satz ?? b.ustSatz
        b.steuerPositionen = tabelle.count > 1 ? tabelle : nil
        b.summenprobeOK = abs(b.netto + b.ust - b.brutto) < 0.011
    }

    /// Fragenpaket weggelegt: der Beleg bleibt liegen, aber ehrlich markiert.
    func offeneFrageSetzen(id: UUID, _ text: String?) {
        guard let i = belege.firstIndex(where: { $0.id == id }),
              belege[i].status != .fixiert else { return }
        belege[i].offeneFrage = text
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

    /// Speichert den Bericht des Tages (einer pro Tag) und legt das Tagesblatt
    /// in der Belegbox ab (wenn verbunden).
    ///
    /// Seit 23.08.2026 überschreibt das nichts mehr stillschweigend. Ein Tag,
    /// dessen Blatt schon in der Belegbox liegt, ist festgeschrieben; ihn zu
    /// ändern ist eine Korrektur und braucht einen Grund, der stehen bleibt
    /// (GoBD, § 146 Abs. 4 AO — der ursprüngliche Inhalt muss feststellbar
    /// bleiben). Vorher hieß diese Zeile schlicht `kassenberichte[i] = neu`.
    ///
    /// Gibt `nil` zurück, wenn gespeichert wurde, sonst den Grund, warum
    /// nicht — die Oberfläche fragt dann nach.
    @discardableResult
    func kassenberichtSpeichern(_ bericht: Kassenbericht,
                                grund: String = "") -> Kassenfehler? {
        guard let i = kassenberichte.firstIndex(where: { $0.datum == bericht.datum })
        else {
            var neu = bericht
            neu.uebermittelt = nil
            kassenberichte.append(neu)
            let tag = neu.datum
            Task { await self.kassenblattSenden(tag) }
            return nil
        }
        do {
            kassenberichte[i] = try kassenberichtKorrigieren(
                alt: kassenberichte[i], neu: bericht, grund: grund)
        } catch Kassenfehler.keineAenderung {
            return nil          // nichts zu tun ist kein Fehler
        } catch let f as Kassenfehler {
            return f            // Grund fehlt — die Oberfläche fragt
        } catch {
            return nil
        }
        let tag = bericht.datum
        Task { await self.kassenblattSenden(tag) }
        return nil
    }

    /// Ist der Tag schon festgeschrieben? Die Oberfläche fragt danach, bevor
    /// sie eine Änderung ohne Grund überhaupt anbietet.
    func kassentagFestgeschrieben(_ tag: String) -> Bool {
        kassenbericht(fuer: tag)?.festgeschrieben ?? false
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

// MARK: - Werkseinstellung (Testphase)

extension AppStore {
    /// Was ein Zurücksetzen anfasst — und was ausdrücklich nicht.
    ///
    /// Der Unterschied ist der ganze Sinn der Sache: das Onboarding soll
    /// sich noch einmal ansehen lassen, ohne sich jedes Mal neu anmelden
    /// zu müssen. Und ohne dass Belege verschwinden — die liegen in der
    /// Belegbox, sind Auditmaterial und gehen eine App-Einstellung nichts
    /// an. Ein Zurücksetzen, das Belege löscht, wäre kein Testwerkzeug,
    /// sondern ein Unfall.
    static let werkseinstellungGeht = [
        "Das Onboarding — der Begrüßungsbildschirm kommt wieder",
        "Belege und Kassenberichte auf diesem Gerät",
        "Chatverlauf und Rechnungsvorlagen",
        "Deine Einrichtungsangaben (Betrieb, Steuernummer, Versteuerung)",
    ]
    static let werkseinstellungBleibt = [
        "Deine Anmeldung — du bleibst verbunden",
        "Deine Belegbox mit allen abgelegten Belegen",
        "Kundinnen, Termine und Preise",
    ]

    /// Zurück auf Anfang, ohne das Konto zu verlieren.
    ///
    /// Gibt zurück, ob auch die Einrichtungsangaben auf dem Server
    /// zurückgesetzt werden konnten — ohne Verbindung bleibt das lokale
    /// Zurücksetzen trotzdem gültig.
    @MainActor
    func aufWerkseinstellung() async -> Bool {
        // Erst der Server, solange die Anmeldung noch steht.
        var serverOk = false
        if let url = URL(string: ablageURL), let pat = KeychainHelfer.ladePAT() {
            serverOk = await AblageService.einrichtungZuruecksetzen(basis: url,
                                                                    pat: pat)
        }

        belege = []
        kassenberichte = []
        chatVerlauf = []
        vorlagen = []
        exportiert = false
        geprueft = 0
        pruefSekunden = []
        skr = "SKR04"
        // Zuletzt, weil es den Bildschirm wechselt: alles darüber soll
        // vorher durch sein.
        onboarded = false
        sichern()
        return serverOk
    }
}
