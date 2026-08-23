import Foundation

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

/// Ein Gespräch, das FRÜHER auf dem Server mitgeschrieben wurde. Neue kommen
/// keine mehr dazu (BABU-25) — was liegt, muss Nina sehen und löschen können.
struct ServerGespraech: Identifiable, Equatable {
    let id: Int
    let titel: String
    let zuletzt: String
    let nachrichten: Int
}

/// Die Textarbeit des Fragen-Bereichs — ohne SwiftUI, damit sie im Harness
/// geprüft werden kann (`ios/Tests/chat`). Was hier steht, liest Nina.
enum Chattexte {

    /// So viele Züge reisen mit der Frage zum Server. Derselbe Wert wie
    /// `VERLAUF_ZUEGE` dort — mehr hilft selten und drängt das Fallwissen
    /// aus dem Fenster.
    static let zuege = 6

    /// Der Verlauf für den Server. Er liegt in der App, nicht auf dem
    /// Server (BABU-25): dort ist er sichtbar, löschbar und gehört ihr.
    /// Leere Blasen (die noch laufende Antwort) bleiben draußen.
    static func verlaufFuerServer(_ nachrichten: [ChatNachricht],
                                  zuege: Int = Chattexte.zuege) -> [[String: String]] {
        nachrichten
            .filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .suffix(zuege * 2)
            .map { ["rolle": $0.vonMir ? "user" : "assistant", "text": $0.text] }
    }

    /// „2026-09-15" → „15.09.2026". Nina liest kein ISO.
    static func datumDeutsch(_ iso: String) -> String? {
        let teile = iso.prefix(10).split(separator: "-")
        guard teile.count == 3, teile[0].count == 4,
              teile.allSatisfy({ $0.allSatisfy(\.isNumber) }) else { return nil }
        return "\(teile[2]).\(teile[1]).\(teile[0])"
    }

    /// Was nach dem Fotografieren eines Amtsbriefs im Chat steht: worum es
    /// geht, was zu tun ist, bis wann — und wo Auskunft aufhört.
    static func briefAntwort(einfach: String, wasTun: String?, bisWann: String?,
                             hinweis: String?) -> String {
        var teile = [einfach.trimmingCharacters(in: .whitespacesAndNewlines)]
        if let tun = wasTun?.trimmingCharacters(in: .whitespacesAndNewlines),
           !tun.isEmpty {
            teile.append("Was du tun musst: \(tun)")
        }
        if let bis = bisWann?.trimmingCharacters(in: .whitespacesAndNewlines),
           !bis.isEmpty {
            // Steht dort etwas, das kein Datum ist, geben wir es unverändert
            // weiter — lieber die Formulierung aus dem Brief als gar nichts.
            teile.append("Zeit hast du bis: \(datumDeutsch(bis) ?? bis)")
        } else {
            teile.append("Eine Frist steht in dem Brief nicht — trotzdem: "
                         + "leg ihn nicht auf den Stapel.")
        }
        teile.append("Der Brief liegt jetzt sicher in deiner Belegbox.")
        if let h = hinweis?.trimmingCharacters(in: .whitespacesAndNewlines), !h.isEmpty {
            teile.append(h)
        }
        return teile.filter { !$0.isEmpty }.joined(separator: "\n\n")
    }
}
