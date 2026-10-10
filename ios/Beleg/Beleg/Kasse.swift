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
    @Published private(set) var laeuft = false
    @Published var fehler: String?

    private var horcher: Task<Void, Never>?
    /// Wohin gemeldet wird. Setzt die App beim Start (`BelegApp`).
    var melden: ((String) async -> Bool)?

    deinit { horcher?.cancel() }

    /// Apples Preise für die angebotenen Stufen holen.
    func preiseLaden(_ stufen: [PlatzStufe]) async {
        guard !stufen.isEmpty else { return }
        do {
            let geholt = try await Product.products(for: stufen.map(\.apple))
            produkte = Dictionary(uniqueKeysWithValues: geholt.map { ($0.id, $0) })
        } catch {
            // Kein Netz oder die Produkte sind noch nicht freigegeben: die
            // Ansicht zeigt dann `preisNotfalls`. Keine Fehlermeldung — die
            // Nutzerin hat nichts falsch gemacht.
            produkte = [:]
        }
    }

    /// Den Kauf anstoßen. Rückgabe: ob jetzt Platz da ist.
    func kaufen(_ stufe: PlatzStufe) async -> Bool {
        guard let produkt = produkte[stufe.apple] else {
            fehler = "Dieser Platz ist gerade nicht zu haben — später noch einmal."
            return false
        }
        laeuft = true
        fehler = nil
        defer { laeuft = false }
        do {
            switch try await produkt.purchase() {
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
