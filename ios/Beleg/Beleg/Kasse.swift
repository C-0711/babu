import Foundation
import StoreKit

/// Die Kasse: Stufen bei Apple kaufen und dem Server melden.
///
/// Bezahlt wird über den App Store (StoreKit 2) — das ist bei einer App,
/// die Privatpersonen und Betriebe laden können, der Weg, den Apple
/// vorschreibt (3.1.1). Der Server glaubt dieser App dabei nichts: Was hier
/// als `signedTransactionInfo` an `/api/abo/apple` geht, prüft er gegen
/// Apples Wurzelzertifikat (`apple_abo.py`). Ein Fehler hier kann niemandem
/// Platz schenken.
///
/// Zwei Wege, und beide braucht es:
///   * `kaufen` — die Nutzerin tippt, und gleich darauf steht ihr Platz.
///   * `laufendeMelden` — bei jedem Start, was Apple an gültigen Belegen
///     führt (`Transaction.currentEntitlements`). Das fängt den Wechsel auf
///     ein neues Telefon, eine Wiederherstellung und den Fall, dass die
///     Meldung nach dem Kauf nicht ankam.
@MainActor
final class Kasse: ObservableObject {
    /// Was Apple zu unseren Kennungen sagt — Preis und Name in der Sprache
    /// und Währung des Landes.
    @Published private(set) var produkte: [String: Product] = [:]
    /// Woran das Laden der Preise ist — die Kaufseite zeigt es (24.10.2026).
    @Published private(set) var ladung: PreisLadung = .laedt
    @Published private(set) var laeuft = false
    @Published var fehler: String?

    private var horcher: Task<Void, Never>?
    /// Wohin gemeldet wird. Setzt die App beim Start (`BelegApp`).
    var melden: ((String) async -> Bool)?

    deinit { horcher?.cancel() }

    /// Apples Preise für die angebotenen Stufen holen — bis zu drei Versuche
    /// (Pause 1 s, dann 2 s), und die Kaufseite sieht jederzeit, woran es ist.
    ///
    /// Vorher gab es einen Versuch und bei Fehlschlag stumm `preisNotfalls`;
    /// Apple sah auf dem iPad genau dieses Blatt ohne Preise und lehnte ab
    /// (2.1(b), 24.10.2026). Gekauft wird nur bei `.geladen`.
    ///
    /// „Deine Ablage" und das Blatt rufen das gleichzeitig: es läuft nur EIN
    /// Ladelauf je Kennungssatz, weitere Aufrufer warten auf ihn, und ein
    /// vollständiger Stand fällt nicht zurück (Review 24.10.2026).
    func preiseLaden(_ stufen: [PlatzStufe]) async {
        let kennungen = stufen.map(\.apple)
        if ladung == .geladen && geladenFuer == kennungen { return }
        if let laufend, laufend.kennungen == kennungen {
            await laufend.task.value
            return
        }
        laufend?.task.cancel()
        geladenFuer = []
        ladung = .laedt
        let task = Task { await self.laden(kennungen) }
        laufend = (kennungen, task)
        await task.value
        if laufend?.kennungen == kennungen { laufend = nil }
    }

    /// „Nochmal" auf der Kaufseite: sofort wieder „lädt", der nächste
    /// `preiseLaden`-Aufruf beginnt von vorn.
    func nochmal() {
        laufend?.task.cancel()
        laufend = nil
        geladenFuer = []
        ladung = .laedt
    }

    private var laufend: (kennungen: [String], task: Task<Void, Never>)?
    private var geladenFuer: [String] = []

    private func laden(_ kennungen: [String]) async {
        let versuche = 3
        for versuch in 1...versuche {
            var geholt: [Product] = []
            if !kennungen.isEmpty {
                do {
                    geholt = try await Product.products(for: kennungen)
                } catch {
                    print("[kasse] Preise, Versuch \(versuch): \(error)")
                }
            }
            if Task.isCancelled { return }
            if !geholt.isEmpty {
                produkte = Dictionary(uniqueKeysWithValues: geholt.map { ($0.id, $0) })
            }
            let gefunden = kennungen.filter { produkte[$0] != nil }.count
            ladung = PlatzStand.preisLadungFortschreiben(
                bisher: geladenFuer == kennungen ? ladung : .laedt,
                gefunden: gefunden, erwartet: kennungen.count,
                versucheUebrig: versuche - versuch)
            if ladung == .geladen { geladenFuer = kennungen; return }
            if versuch < versuche { try? await Task.sleep(for: .seconds(versuch)) }
            if Task.isCancelled { return }
        }
        // Konsole, kein Nutzertext: welche Kennungen fehlen, sieht nur, wer
        // das Log liest.
        print("[kasse] Preise nicht vollständig — erwartet \(kennungen), "
              + "da \(produkte.keys.sorted())")
    }

    /// Den Kauf anstoßen. Rückgabe: ob jetzt Platz da ist.
    ///
    /// `kennung` ist die Kaufkennung des Betriebs (`appAccountToken`, seit
    /// 14.10.2026). Apple trägt sie in jeden Vorgang dieses Abos ein und
    /// schickt sie in jeder Server Notification zurück — damit findet der
    /// Server den Betrieb auch dann, wenn dieses Telefon nichts meldet, und
    /// ein Kauf landet nie beim falschen Betrieb, wenn auf einem iPhone
    /// zwei Zugänge benutzt werden. Fehlt sie (kein Netz beim Start, ein
    /// Konto aus dem Portal), wird wie vorher gekauft.
    func kaufen(_ stufe: PlatzStufe, kennung: UUID? = nil) async -> Bool {
        guard let produkt = produkte[stufe.apple] else {
            fehler = "Dieser Platz ist gerade nicht zu haben — später noch einmal."
            return false
        }
        laeuft = true
        fehler = nil
        defer { laeuft = false }
        var optionen: Set<Product.PurchaseOption> = []
        if let kennung { optionen.insert(.appAccountToken(kennung)) }
        do {
            switch try await produkt.purchase(options: optionen) {
            case .success(let beleg):
                return await uebernehmen(beleg)
            case .userCancelled:
                return false
            case .pending:
                // „Ask to Buy" und Bankfreigaben: Apple meldet sich später,
                // und `horchen()` nimmt es dann auf.
                fehler = "Der Kauf wartet noch auf eine Freigabe. Sobald sie "
                    + "da ist, hast du den Platz."
                return false
            @unknown default:
                return false
            }
        } catch {
            fehler = "Der Kauf hat gerade nicht geklappt — später noch einmal."
            return false
        }
    }

    /// Was Apple für dieses Konto an gültigen Belegen führt, dem Server
    /// melden. Beim Start und nach „Kauf wiederherstellen".
    func laufendeMelden() async -> Bool {
        var etwas = false
        for await beleg in Transaction.currentEntitlements {
            if await uebernehmen(beleg, stillschweigend: true) { etwas = true }
        }
        return etwas
    }

    /// „Käufe wiederherstellen" — der Knopf, den Apple bei Abos verlangt
    /// (3.1.1). Erst `StoreKit.AppStore.sync()`, dann melden.
    ///
    /// `laufendeMelden` allein reicht meistens: StoreKit 2 hält die Belege
    /// des angemeldeten Apple-Kontos ohnehin bereit. Nur manchmal nicht —
    /// nach einer Neuinstallation ohne Backup, nach einem Wechsel des
    /// Apple-Kontos, bei einem Kauf, der auf diesem Gerät nie lief.
    /// `StoreKit.AppStore.sync()` holt sie dann vom App Store nach; es fragt die
    /// Nutzerin nach ihrem Apple-Passwort, deshalb steht es hinter einem
    /// Knopf und läuft nie von selbst.
    ///
    /// Rückgabe: ob jetzt ein Platz steht. Schlägt `sync()` fehl (abgebrochen,
    /// kein Netz), wird trotzdem gemeldet — die Belege, die schon da sind,
    /// zählen weiter.
    func wiederherstellen() async -> Bool {
        laeuft = true
        defer { laeuft = false }
        do {
            // `StoreKit.` ist Pflicht, nicht Zierde: babus eigener Store
            // heisst auch `AppStore` und verdeckt Apples Typ sonst.
            try await StoreKit.AppStore.sync()
        } catch {
            // Abgebrochene Passwortabfrage ist kein Fehler, den man ihr
            // zeigt — darunter steht gleich, ob etwas gefunden wurde.
        }
        return await laufendeMelden()
    }

    /// Apples Meldungen mitlaufen lassen (Verlängerung, nachgereichte
    /// Freigabe, Kauf auf einem anderen Gerät desselben Kontos).
    func horchen() {
        guard horcher == nil else { return }
        horcher = Task { [weak self] in
            for await beleg in Transaction.updates {
                _ = await self?.uebernehmen(beleg, stillschweigend: true)
            }
        }
    }

    /// Einen Beleg von Apple annehmen und weitergeben.
    ///
    /// `jwsRepresentation` ist genau das, was der Server prüfen kann — die
    /// ausgepackte `Transaction` wäre nur die Behauptung dieser App.
    private func uebernehmen(_ ergebnis: VerificationResult<Transaction>,
                             stillschweigend: Bool = false) async -> Bool {
        guard case .verified(let vorgang) = ergebnis else {
            // Apple selbst hält den Beleg für nicht echt. Dann gar nicht
            // erst melden.
            if !stillschweigend {
                fehler = "Dieser Kaufbeleg lässt sich nicht prüfen."
            }
            return false
        }
        let ok = await melden?(ergebnis.jwsRepresentation) ?? false
        if ok {
            // Erst abschließen, wenn der Platz steht. Bleibt der Vorgang
            // offen, liefert Apple ihn beim nächsten Start wieder — besser
            // eine Wiederholung als ein bezahlter Platz, der nie ankommt.
            await vorgang.finish()
        } else if !stillschweigend {
            fehler = "Bezahlt ist bezahlt — der Platz kommt, sobald babu "
                + "wieder erreichbar ist."
        }
        return ok
    }
}
