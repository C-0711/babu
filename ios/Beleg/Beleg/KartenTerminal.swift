import Foundation
import ProximityReader

/// Die echte Kartenannahme über Apples ProximityReader.
///
/// Hier endet, was babu allein bauen kann. `PaymentCardReader.isSupported`
/// beantwortet die Gerätefrage ohne jede Freigabe — das ist der Test, der
/// heute schon läuft. `prepare(using:)` dagegen verlangt zweierlei, das
/// nicht aus diesem Repository kommt: Apples Berechtigung und ein Token
/// vom Zahlungsdienstleister.
///
/// Das Token wird pro Sitzung vom Anbieter ausgestellt, nachdem er den
/// Salon geprüft hat. Es gibt keinen Umweg und auch keinen Sandkasten ohne
/// Anbieter: wer Karten liest, ist in der Zahlungskette drin.
struct KartenTerminal: Kartenkasse {

    /// Kann dieses Gerät überhaupt Karten lesen?
    ///
    /// Auf dem Simulator liefert `isSupported` ein `true`, das nichts wert
    /// ist — dort gibt es keine Hardware, die eine Karte lesen könnte.
    /// Beim ersten Durchlauf stand deshalb ein grüner Haken, wo keiner
    /// hingehört. Die ehrliche Antwort im Simulator ist „weiß ich nicht".
    static var geraet: Huerdenstand {
        #if targetEnvironment(simulator)
        return .unbekannt
        #else
        return PaymentCardReader.isSupported ? .erfuellt : .offen
        #endif
    }

    /// Hat Apple die Berechtigung schon erteilt?
    ///
    /// iOS bietet keinen Weg, die eigenen Berechtigungen zur Laufzeit
    /// auszulesen — `SecTaskCopyValueForEntitlement` gibt es nur auf
    /// macOS. Beim Entwicklungs-Build steht die Antwort aber im
    /// mitgelieferten Provisioning-Profil, und genau das ist der Fall, den
    /// wir hier prüfen wollen: läuft die App auf Ninas Telefon mit oder
    /// ohne Freigabe? Fehlt das Profil (App Store), gilt die Berechtigung
    /// als erteilt — dort wäre die App sonst gar nicht erst durchgekommen.
    static var freigabe: Huerdenstand {
        guard let pfad = Bundle.main.path(forResource: "embedded",
                                          ofType: "mobileprovision"),
              let roh = try? Data(contentsOf: URL(fileURLWithPath: pfad)),
              let text = String(data: roh, encoding: .isoLatin1)
        else { return .unbekannt }   // ohne Profil nicht feststellbar
        // Das Profil ist CMS-signiert; die Nutzdaten sind eine Klartext-plist
        // darin. Für ein Ja/Nein genügt es, danach zu suchen.
        return text.contains(BERECHTIGUNG_TAPTOPAY) ? .erfuellt : .offen
    }

    /// Woher das Sitzungs-Token kommt. Nil heißt: kein Anbieter angebunden.
    let tokenHolen: (() async throws -> String)?

    var lage: Kartenlage {
        Kartenpruefung.lage(geraet: Self.geraet, freigabe: Self.freigabe,
                            anbieter: tokenHolen != nil ? .erfuellt : .offen)
    }

    func kassieren(_ betrag: Kartenbetrag) async throws -> Kartenbeleg {
        let jetzige = lage
        guard jetzige == .bereit, let tokenHolen else {
            throw Kartenfehler.nichtBereit(jetzige)
        }
        let leser = PaymentCardReader()
        let sitzung = try await leser.prepare(
            using: PaymentCardReader.Token(rawValue: try await tokenHolen()))

        let anfrage = PaymentCardTransactionRequest(
            amount: Decimal(betrag.cent) / 100,
            currencyCode: "EUR", for: .purchase)
        let ergebnis = try await sitzung.readPaymentCard(anfrage)

        // Eine gelesene Karte ist noch kein angenommenes Geld. Ohne diese
        // Unterscheidung stünde eine abgelehnte Zahlung im Kassenbuch.
        switch ergebnis.outcome {
        case .success:
            break
        case .cardDeclined:
            throw Kartenfehler.abgelehnt("Die Karte wurde abgelehnt. "
                                         + "Magst du eine andere versuchen?")
        case .failure:
            throw Kartenfehler.abgelehnt("Das Lesen hat nicht geklappt. "
                                         + "Noch einmal anhalten?")
        @unknown default:
            throw Kartenfehler.abgelehnt("Unklares Ergebnis — sicherheits"
                                         + "halber nichts gebucht.")
        }

        // Was babu behält: Betrag und die Nummer beim Anbieter, die
        // Kassenbuch und Kontoauszug verbindet. Kartendaten sieht die App
        // nie — die gehen verschlüsselt am Telefon vorbei zum Anbieter.
        return Kartenbeleg(betrag: betrag, referenz: ergebnis.id,
                           letzteVier: nil, probe: false)
    }
}
