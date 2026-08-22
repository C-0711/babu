import Foundation

/// Kartenzahlung mit dem Telefon — „Tap to Pay on iPhone".
///
/// Das Telefon wird zum Kartenlesegerät: die Kundin hält ihre Karte oder
/// Uhr an die Rückseite, fertig. Kein Terminal, keine Miete, kein Kabel.
///
/// Drei Dinge müssen dafür zusammenkommen, und nur eines davon ist Code:
///
/// 1. **Das Gerät** muss es können — iPhone XS oder neuer, aktuelles iOS,
///    unterstütztes Land. Das prüft `PaymentCardReader.isSupported`, und
///    zwar ehrlich: auf dem Simulator ist es immer `false`.
/// 2. **Apple** muss die Berechtigung erteilen
///    (`com.apple.developer.proximity-reader.payment.acceptance`). Die gibt
///    es auf Antrag, nicht auf Knopfdruck.
/// 3. **Ein Zahlungsdienstleister** muss den Salon aufnehmen und pro
///    Sitzung ein Token ausstellen. Ohne dieses Token startet keine
///    Lesesitzung — auch keine im Testbetrieb. Geld bewegen darf nur, wer
///    dafür zugelassen ist; babu ist das nicht und wird es nicht.
///
/// Was hier steht, ist deshalb die vollständige Strecke bis an diese Grenze:
/// eine ehrliche Prüfung, was fehlt, und ein Prüfstand, mit dem sich der
/// ganze Ablauf schon durchspielen lässt. Kommt der Dienstleister dazu,
/// wird genau eine Sache ausgetauscht — `KartenTerminal`.

// MARK: - Was fehlt noch?

/// Die Berechtigung, die Apple erteilen muss.
let BERECHTIGUNG_TAPTOPAY = "com.apple.developer.proximity-reader.payment.acceptance"

/// Wie eine einzelne Hürde steht.
///
/// Der dritte Fall ist der wichtige. Eine Diagnose, die „unbekannt" zu
/// „erfüllt" rundet, ist schlimmer als gar keine: sie schickt Nina mit
/// einem grünen Haken zur Kundin und lässt sie dort auflaufen. Beim ersten
/// Durchlauf im Simulator stand genau deshalb „Apples Freigabe ist
/// erteilt" — sie war es nicht, es ließ sich nur nicht feststellen.
enum Huerdenstand: Equatable {
    case erfuellt
    case offen
    case unbekannt
}

/// Wie weit babu auf diesem Gerät mit Kartenzahlung kommt.
enum Kartenlage: Equatable {
    /// Alles da — es kann kassiert werden.
    case bereit
    /// Dieses Gerät kann kein Tap to Pay (zu alt, Simulator, falsches Land).
    case geraetKannNicht
    /// Apple hat die Berechtigung noch nicht erteilt.
    case freigabeFehlt
    /// Kein Zahlungsdienstleister hinterlegt — ohne den gibt es kein Token.
    case anbieterFehlt
    /// Hier lässt sich nichts feststellen — auf dem Simulator gibt es
    /// keine Hardware, die eine Karte lesen könnte.
    case unklar

    /// Was Nina davon wissen muss. Kein Fachchinesisch, keine Ausrede.
    var satz: String {
        switch self {
        case .bereit:
            return "Dieses iPhone kann Karten annehmen."
        case .geraetKannNicht:
            return "Dieses Gerät kann kein Tap to Pay. Dafür braucht es ein "
                 + "iPhone XS oder neuer mit aktuellem iOS — und auf dem "
                 + "Simulator geht es grundsätzlich nicht."
        case .freigabeFehlt:
            return "Apple muss die Kartenannahme für babu noch freischalten. "
                 + "Das ist beantragt und dauert; am Gerät liegt es nicht."
        case .anbieterFehlt:
            return "Es fehlt noch ein Zahlungsdienstleister. Nur ein "
                 + "zugelassener Anbieter darf das Geld abwickeln — babu "
                 + "reicht die Zahlung durch, hält sie aber nie."
        case .unklar:
            return "Auf dem Simulator lässt sich das nicht beantworten. "
                 + "Tap to Pay läuft nur auf einem echten iPhone — dort "
                 + "steht hier eine belastbare Antwort."
        }
    }

    /// Der nächste Schritt, falls es einen gibt.
    var naechstes: String? {
        switch self {
        case .bereit:          return nil
        case .geraetKannNicht: return "Auf einem neueren iPhone probieren."
        case .freigabeFehlt:   return "Auf Apples Freigabe warten."
        case .anbieterFehlt:   return "Anbieter aussuchen und Salon anmelden."
        case .unklar:          return "Auf einem echten iPhone öffnen."
        }
    }

    /// Solange nicht kassiert werden kann, hilft der Prüfstand.
    var probeMoeglich: Bool { self != .bereit }
}

/// Die Prüfung selbst — reine Rechnung, damit sie ohne Gerät testbar ist.
///
/// Die Reihenfolge ist Absicht: erst das Gerät, dann Apple, dann der
/// Anbieter. So sieht Nina immer die Hürde, die als Nächstes dran ist,
/// statt drei auf einmal.
enum Kartenpruefung {
    static func lage(geraet: Huerdenstand, freigabe: Huerdenstand,
                     anbieter: Huerdenstand) -> Kartenlage {
        // „Nein" schlägt „weiß nicht": eine feststehende Hürde ist die
        // nützlichere Auskunft. Aber „weiß nicht" wird nie zu „ja".
        if geraet == .offen { return .geraetKannNicht }
        if geraet == .unbekannt { return .unklar }
        if freigabe == .offen { return .freigabeFehlt }
        if freigabe == .unbekannt { return .unklar }
        if anbieter != .erfuellt { return .anbieterFehlt }
        return .bereit
    }
}

// MARK: - Was kassiert wird

/// Ein Betrag in Cent — nie als Double.
///
/// 0,1 + 0,2 ergibt in Fließkomma nicht 0,3. Bei Geld ist das kein
/// Schönheitsfehler, sondern ein Kassensturz, der nicht aufgeht.
struct Kartenbetrag: Equatable {
    let cent: Int

    /// „42,00", „42.00", „1.250,00", „42 €" — alles derselbe Gedanke.
    ///
    /// Der Punkt ist die Falle. Wer ihn immer als Tausendertrennung
    /// wegwirft, macht aus 42.00 € vierteltausend Euro — genau dieser
    /// Fehler stand schon einmal im Server und hat aus 12,50 € Trinkgeld
    /// 125 € gemacht. Die Regel: Ist ein Komma da, sind Punkte
    /// Tausendertrennung. Sonst ist ein einzelner Punkt mit genau zwei
    /// Nachkommastellen ein Dezimalpunkt.
    init?(euro text: String) {
        var roh = text.replacingOccurrences(of: "€", with: "")
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "\u{00A0}", with: "")
        guard !roh.isEmpty else { return nil }

        if roh.contains(",") {
            roh = roh.replacingOccurrences(of: ".", with: "")
                     .replacingOccurrences(of: ",", with: ".")
        } else {
            let teile = roh.split(separator: ".", omittingEmptySubsequences: false)
            // Ein Punkt mit zwei Stellen dahinter: Dezimalpunkt, bleibt.
            // Alles andere (1.250, 1.250.000): Tausendertrennung, fliegt raus.
            if !(teile.count == 2 && teile[1].count == 2) {
                roh = roh.replacingOccurrences(of: ".", with: "")
            }
        }
        guard let wert = Double(roh), wert > 0, wert < 100_000 else { return nil }
        self.cent = Int((wert * 100).rounded())
    }

    init(cent: Int) { self.cent = cent }

    var text: String {
        String(format: "%d,%02d €", cent / 100, abs(cent % 100))
    }
}

/// Was nach einer Zahlung zurückkommt.
struct Kartenbeleg: Equatable {
    let betrag: Kartenbetrag
    /// Die Nummer beim Zahlungsdienstleister — sie verbindet Kassenbuch
    /// und Kontoauszug. Ohne sie ist die Zahlung später nicht auffindbar.
    let referenz: String
    /// Die letzten vier Ziffern, mehr sieht babu nie und will es auch nicht.
    let letzteVier: String?
    let probe: Bool
}

enum Kartenfehler: LocalizedError, Equatable {
    case nichtBereit(Kartenlage)
    case abgebrochen
    case abgelehnt(String)
    case betragUnklar

    var errorDescription: String? {
        switch self {
        case .nichtBereit(let lage): return lage.satz
        case .abgebrochen:           return "Abgebrochen."
        case .abgelehnt(let grund):  return grund
        case .betragUnklar:          return "Wie hoch ist der Betrag?"
        }
    }
}

/// Wer das Geld einzieht. Genau diese Schnittstelle tauscht ein
/// Zahlungsdienstleister später aus — alles darüber bleibt, wie es ist.
protocol Kartenkasse {
    var lage: Kartenlage { get }
    func kassieren(_ betrag: Kartenbetrag) async throws -> Kartenbeleg
}

/// Der Prüfstand: derselbe Ablauf, nur ohne Karte und ohne Geld.
///
/// Damit lässt sich alles testen, was babu selbst verantwortet — dass der
/// Betrag stimmt, dass er im Kassenbuch landet, dass ein Abbruch nichts
/// bucht. Nur das Stück, das ohnehin dem Anbieter gehört, fehlt.
struct ProbeKasse: Kartenkasse {
    let lage: Kartenlage
    var verzoegerung: UInt64 = 1_200_000_000      // damit es sich echt anfühlt
    var lehntAb: String?                          // für den Fehlerfall

    func kassieren(_ betrag: Kartenbetrag) async throws -> Kartenbeleg {
        guard betrag.cent > 0 else { throw Kartenfehler.betragUnklar }
        try? await Task.sleep(nanoseconds: verzoegerung)
        if let grund = lehntAb { throw Kartenfehler.abgelehnt(grund) }
        return Kartenbeleg(betrag: betrag,
                           referenz: "probe-" + String(UUID().uuidString.prefix(8)),
                           letzteVier: "4242", probe: true)
    }
}
