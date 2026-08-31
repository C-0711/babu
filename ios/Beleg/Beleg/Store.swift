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
    func routen(bildJpeg: Data?, ocrText: String,
                ocrGeoJson: String? = nil, seitenJpeg: [Data]? = nil) -> Beleg {
        // Der Parser ist raus aus dem Buchungsweg (26.08.2026, Kalugahair-
        // Beweis: Vision las alles, der Parser machte nil daraus). Der Beleg
        // entsteht als Hülle — Zahlen, Lieferant und Datum setzt Gemma über
        // die Einschätzung. Die erste Vision-Zeile dient nur als Anzeigename.
        let kopf = ocrText.split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            // Seiten-Marker der Mehrseiter sind kein Name („— Seite 1 von 2 —").
            .first { $0.count >= 3 && !$0.hasPrefix("— Seite") } ?? "Beleg"
        var beleg = Beleg(
            lieferant: String(kopf.prefix(40)),
            belegNr: "ohne Nr.",
            // Kein erfundenes Datum: der Hochlade-Tag ist NICHT das Belegdatum.
            // Leer heißt ehrlich „noch ungelesen" — die Einschätzung setzt das
            // echte Datum, die Liste sammelt es bis dahin unter „Ohne Datum".
            datumText: "",
            netto: 0, ust: 0, brutto: 0, ustSatz: 0,
            konto: nil,
            steuerschluessel: "0",
            kreditor: "70000",
            herkunft: .ki,
            confidence: 0,
            status: .offen,
            begruendung: "Wird von der Buchhaltung gelesen.",
            summenprobeOK: false
        )
        beleg.bildJpeg = bildJpeg
        beleg.ocrText = ocrText
        beleg.ocrGeoJson = ocrGeoJson
        // VOR dem Dateinamen setzen: Bündel bekommen die Endung .pdf.
        beleg.seitenJpeg = seitenJpeg
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
            let zeilenJson: String
            if let geo = belege[i].ocrGeoJson {
                zeilenJson = geo
            } else {
                let zeilen = belege[i].ocrText
                    .split(separator: "\n").map { String($0) }
                zeilenJson = (try? JSONSerialization.data(withJSONObject: zeilen))
                    .flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
            }
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

        // Mehrseitige Belege reisen als EIN PDF aus allen Seiten — gebaut
        // erst hier, damit zustand.json nur die JPEGs trägt. Schlägt der
        // PDF-Bau fehl, geht wenigstens Seite 1 — dann aber unter .jpg,
        // damit Endung und Inhalt zusammenpassen.
        var daten = jpeg
        var uploadName = dateiname
        if let seiten = belege[i].seitenJpeg, seiten.count > 1 {
            if let pdf = BelegBuendelPDF.bauen(seitenJpeg: seiten) {
                daten = pdf
            } else if uploadName.hasSuffix(".pdf") {
                uploadName = String(uploadName.dropLast(4)) + ".jpg"
                belege[i].ablageDateiname = uploadName
            }
        }
        // Der auf dem Gerät gelesene Text geht mit: daraus entscheidet der
        // Server, ob das ein Bon, ein Vertrag, ein Brief vom Amt oder ein
        // Kontoauszug ist — die Nutzerin muss nichts auswählen.
        let (ergebnis, serverDatei, art, wohin, _) = await AblageService.aufnahme(
            daten: daten, dateiname: uploadName, gelesenerText: belege[i].ocrText,
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

    /// Die Archiv-Bestätigung holen: die Prüfstempel (GitChain-Commits)
    /// des abgelegten Belegs. Die Lesung selbst entsteht auf dem Telefon
    /// und wird nur archiviert — nichts überschreibt Ninas Ergebnis.
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
        let antwort = await AblageService.kassenblattSenden(bericht, basis: url,
                                                           pat: pat)
        guard let i = kassenberichte.firstIndex(where: { $0.datum == tag })
        else { return }
        switch antwort {
        case .ok:
            kassenberichte[i].uebermittelt = Date()
            kassenberichte[i].abgelehnt = nil
        case .abgelehnt(let warum):
            // Nicht erneut versuchen: der Monat ist abgeschlossen oder es
            // fehlt eine Begründung. Beides löst sich nicht von allein.
            kassenberichte[i].abgelehnt = warum
        case .spaeterNochmal:
            break               // Netz weg — beim nächsten Start noch mal
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
