import Foundation

// Abgleich: was auf dem Telefon geändert wird, kommt auch in der Belegbox an.
//
// Ninas Fund vom 14.09.2026: sie hat in der App einen Beleg gelöscht und
// einen anderen korrigiert — beides blieb auf dem Telefon. Die Kanzlei sah
// im Portal den alten Stand, und zwei Wahrheiten sind keine. Seither wird
// jede Änderung am Bestand als Auftrag in eine Warteschlange gelegt, die
// zustand.json überlebt, und beim nächsten Sichtbarwerden abgearbeitet —
// derselbe Weg wie die Uploads: ohne Netz bleibt der Auftrag liegen, mit
// Netz geht er raus, und was der Server endgültig ablehnt, wird verworfen
// statt ewig wiederholt.
//
// Diese Datei ist UIKit-frei und hält nur die Regeln; der Harness in
// ios/Tests/abgleich prüft sie ohne Simulator.

/// Ein Auftrag an den Server. `stamm` ist der serverseitige Name des
/// Belegs (ohne Endung) — er kann beim Anlegen noch fehlen, wenn der Upload
/// gerade läuft, und wird dann nachgetragen, sobald der Server ihn nennt.
struct AbgleichAuftrag: Codable, Identifiable, Equatable {
    enum Art: String, Codable { case loeschen, angaben, bewirtung }

    var id = UUID()
    var belegID: UUID
    var art: Art
    var stamm: String?
    var felder: [String: String]
    var erstellt: Date = Date()
    var versuche: Int = 0
}

enum Abgleich {

    /// Der Pfad am Server, relativ zur Ablage-Basis — dieselben Routen, die
    /// das Portal ruft. Ohne Stamm gibt es keinen Pfad.
    static func pfad(_ a: AbgleichAuftrag) -> String? {
        guard let stamm = a.stamm, !stamm.isEmpty else { return nil }
        switch a.art {
        case .loeschen:   return "api/beleg/\(stamm)/loeschen"
        case .angaben:    return "api/angaben/\(stamm)"
        case .bewirtung:  return "api/bewirtung/\(stamm)"
        }
    }

    /// Der Rumpf, so wie der Server ihn erwartet. Bewirtung will die
    /// Teilnehmer als Liste; die App führt sie als eine Zeile.
    static func rumpf(_ a: AbgleichAuftrag) -> [String: Any] {
        switch a.art {
        case .loeschen:
            return [:]
        case .angaben:
            return a.felder
        case .bewirtung:
            let personen = a.felder["personen"] ?? ""
            let teilnehmer = personen
                .split(whereSeparator: { $0 == "," || $0 == "\n" || $0 == ";" })
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
            return ["anlass": a.felder["anlass"] ?? "", "teilnehmer": teilnehmer]
        }
    }

    /// Einen neuen Auftrag einreihen — und die Schlange dabei klein halten.
    ///
    /// Ein Löschen macht alles andere zu diesem Beleg gegenstandslos. Zwei
    /// Angaben zum selben Beleg werden zu einer (spätere Felder gewinnen),
    /// damit nicht fünf Aufrufe rausgehen, wo einer reicht — der Server
    /// mischt ohnehin. Bewirtung ebenso.
    static func einreihen(_ neu: AbgleichAuftrag, in schlange: [AbgleichAuftrag]) -> [AbgleichAuftrag] {
        var s = schlange
        if neu.art == .loeschen {
            s.removeAll { $0.belegID == neu.belegID }
            s.append(neu)
            return s
        }
        // Nach einem Löschen kommt nichts mehr — der Beleg ist weg.
        if s.contains(where: { $0.belegID == neu.belegID && $0.art == .loeschen }) {
            return s
        }
        if let i = s.firstIndex(where: { $0.belegID == neu.belegID && $0.art == neu.art }) {
            var zusammen = s[i]
            zusammen.felder.merge(neu.felder) { _, spaeter in spaeter }
            zusammen.stamm = neu.stamm ?? zusammen.stamm
            zusammen.versuche = 0
            s[i] = zusammen
            return s
        }
        s.append(neu)
        return s
    }

    /// Der Upload ist durch, der Server hat den Beleg benannt: alle Aufträge
    /// zu diesem Beleg bekommen den Namen, sofern sie noch keinen haben.
    static func stammNachtragen(_ schlange: [AbgleichAuftrag], belegID: UUID,
                                stamm: String) -> [AbgleichAuftrag] {
        schlange.map { a in
            guard a.belegID == belegID, a.stamm == nil || a.stamm!.isEmpty else { return a }
            var b = a
            b.stamm = stamm
            return b
        }
    }

    /// Wartezeit nach `versuche` Fehlschlägen — verdoppelt sich wie beim
    /// Upload (30 s … 30 min).
    static func pause(nachVersuchen n: Int) -> TimeInterval {
        guard n > 0 else { return 0 }
        return min(30.0 * pow(2.0, Double(n - 1)), 1800)
    }

    /// Das deutsche Datum der App (05.03.2026) in die ISO-Form des Servers.
    /// Unlesbares wird nicht geschickt — lieber gar kein Datum als ein
    /// falsches im Monatsabschluss.
    static func isoDatum(_ deutsch: String) -> String? {
        let t = deutsch.trimmingCharacters(in: .whitespaces).split(separator: ".")
        guard t.count == 3, let tag = Int(t[0]), let monat = Int(t[1]), let jahr = Int(t[2]),
              (1...31).contains(tag), (1...12).contains(monat), jahr > 1999 else { return nil }
        return String(format: "%04d-%02d-%02d", jahr, monat, tag)
    }

    /// Betrag im Format, das der Server liest („4,20").
    static func betragText(_ wert: Double) -> String {
        String(format: "%.2f", wert).replacingOccurrences(of: ".", with: ",")
    }
}
