import Foundation

/// Empfehlen: eine Friseurin wirbt einen Salon und bekommt dafür Geld.
///
/// Hier steht, was die App über die Ambassadorin weiß (`GET
/// /api/ambassador/me`) und nach welchen Regeln es auf dem Bildschirm
/// erscheint — welche Farbe ein Salon bekommt, wie der Betrag aussieht, was
/// unter dem Betrag steht. Absichtlich ohne SwiftUI und UIKit, damit
/// `ios/Tests/empfehlen` die Regeln ohne App-Ziel prüfen kann.
///
/// Jedes Feld ist optional und wird nachsichtig gelesen: der Server wächst
/// schneller als die App, und ein Feld, das fehlt oder anders aussieht,
/// darf den Reiter nicht leer machen.
struct EmpfehlenStand: Equatable {
    /// Ihr Code — nur als Schlüssel für das, was dieses Telefon schon gesehen
    /// hat (Ka-ching). Gezeigt wird er nie.
    var code: String?
    var name: String?
    /// `false`: ihr Zugang zum Einladen ist gerade abgeschaltet — Geld und
    /// Salons bleiben sichtbar, neue Einladungen gehen nicht.
    var aktiv: Bool
    /// Der allgemeine Link für alle (QR-Code, Flyer, Instagram).
    var link: String?
    var geld: Geld
    var salons: [Salonzeile]
    var profilVollstaendig: Bool
    /// Alles, was sie je verdient hat (ganze Euro). Steigt es, ist eine
    /// Provision gebucht — der Ka-ching-Moment.
    var verdient: Double
    /// Für wen die jüngste Provision war („Provision Kims Haarstudio,
    /// gezeichnet" → „Kims Haarstudio"); `nil`, wenn das nicht eindeutig ist.
    var letzteProvisionSalon: String?

    struct Geld: Equatable {
        /// Verdient, aber noch nicht ausgezahlt — in ganzen Euro, so wie der
        /// Server rechnet (`kern_ambassador._geld`, Provision in Euro).
        var offen: Double
        /// Schon an eine Überweisung gehängt, aber noch nicht bestätigt.
        var unterwegs: Double
        /// Die Überweisung, die das Geld wirklich bringt (Stichtag und
        /// Mindestsumme schon berücksichtigt) — `nil`, solange keine absehbar ist.
        var erwartet: Erwartet?
    }

    struct Erwartet: Equatable {
        var datum: String       // ISO, „2026-10-15"
        var betrag: Double
    }

    /// Eine Zeile unter „Deine Salons".
    struct Salonzeile: Identifiable, Equatable {
        var id: String
        /// Woran dieser Salon über Ladevorgänge hinweg zu erkennen ist
        /// (Salonname, sonst Name; klein geschrieben).
        var schluessel: String
        var name: String
        var ampel: Ampel
        var wort: String
        /// Die Zeile darunter („Noch kein Beleg").
        var aktiv: String?
        /// Was heute für diesen Salon zu tun ist — nur dann gibt es einen Knopf.
        var aufgabe: Aufgabe?
    }

    /// Der Auftrag, den der Server für einen Salon vorschlägt: wann
    /// Nachfragen sinnvoll ist, entscheidet er, nicht die App.
    struct Aufgabe: Equatable {
        var nr: Int
        var art: String
        var knopf: String
        var grund: String?
        var whatsapp: String?
    }

    /// Grau = eingeladen, gelb = probiert aus, grün = zahlt.
    enum Ampel: Equatable { case grau, gelb, gruen }

    /// Was `POST /api/ambassador/link` zurückgibt.
    struct Einladung: Equatable {
        var link: String
        var text: String?
        var whatsapp: String?
    }
}

// MARK: - Lesen

extension EmpfehlenStand {

    init?(daten: Data) {
        guard let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any]
        else { return nil }
        self.init(json: json)
    }

    init(json: [String: Any]) {
        code = Self.text(json["code"])
        name = Self.text(json["name"])
        aktiv = json["aktiv"] as? Bool ?? true
        link = Self.text(json["link"])
        let g = json["geld"] as? [String: Any] ?? [:]
        let erwartet: Erwartet? = {
            guard let e = g["erwartet"] as? [String: Any],
                  let datum = Self.text(e["datum"]),
                  let betrag = Self.zahl(e["betrag"]) else { return nil }
            return Erwartet(datum: datum, betrag: betrag)
        }()
        geld = Geld(offen: Self.zahl(g["offen"]) ?? Self.zahl(json["offen"]) ?? 0,
                    unterwegs: Self.zahl(g["unterwegs"]) ?? 0,
                    erwartet: erwartet)
        salons = Self.salonzeilen(kontakte: json["kontakte"] as? [[String: Any]],
                                  salons: json["salons"] as? [[String: Any]] ?? [])
        // Fehlt die Angabe, wird nicht gemahnt — lieber eine Zeile zu wenig
        // als ein falscher Alarm über ihr Geld.
        profilVollstaendig = json["profil_vollstaendig"] as? Bool ?? true
        verdient = Self.zahl(json["verdient"]) ?? Self.zahl(g["verdient"]) ?? 0
        letzteProvisionSalon = Self.provisionSalon(
            (g["bewegungen"] as? [[String: Any]])?.first)
    }

    /// „Provision Kims Haarstudio, gezeichnet" → „Kims Haarstudio". Steht
    /// dort nur der Platzhalter „Salon" oder sieht der Text anders aus,
    /// lieber gar keinen Namen als einen falschen.
    static func provisionSalon(_ bewegung: [String: Any]?) -> String? {
        guard let b = bewegung, text(b["art"]) == "provision",
              let t = text(b["text"]), t.hasPrefix("Provision "),
              let komma = t.range(of: ", ", options: .backwards) else { return nil }
        let salon = t[t.index(t.startIndex, offsetBy: 10)..<komma.lowerBound]
            .trimmingCharacters(in: .whitespaces)
        return salon.isEmpty || salon == "Salon" ? nil : salon
    }

    /// Die Kontakte so, wie der Server sie führt — dazu Salons, die keine
    /// Kontaktzeile haben (z. B. über den allgemeinen Link gekommen). Der
    /// Server führt die heute schon mit; die Liste hier ist das Netz für
    /// einen Stand, der es nicht tut.
    static func salonzeilen(kontakte: [[String: Any]]?,
                            salons: [[String: Any]]) -> [Salonzeile] {
        var zeilen: [Salonzeile] = []
        var bekannt = Set<String>()
        for (i, k) in (kontakte ?? []).enumerated() {
            let salon = text(k["salon"])
            let name = text(k["name"]) ?? salon ?? "Salon"
            let (ampel, wort) = ampel(stand: text(k["stand"]),
                                      meilenstein: text(k["meilenstein"]))
            zeilen.append(Salonzeile(id: "k\(i)", schluessel: (salon ?? name).lowercased(),
                                     name: name, ampel: ampel, wort: wort,
                                     aktiv: text(k["aktiv"]),
                                     aufgabe: aufgabe(k["aufgabe"])))
            for wer in [salon, text(k["name"])].compactMap({ $0 }) {
                bekannt.insert(wer.lowercased())
            }
        }
        for (i, s) in salons.enumerated() {
            let salon = text(s["salon"])
            if let salon, bekannt.contains(salon.lowercased()) { continue }
            if kontakte != nil, salon == nil { continue }   // nichts, woran man ihn erkennt
            let (ampel, wort) = ampel(stand: nil, meilenstein: text(s["meilenstein"]))
            zeilen.append(Salonzeile(id: "s\(i)",
                                     schluessel: (salon ?? text(s["email"]) ?? "salon \(i)")
                                         .lowercased(),
                                     name: salon ?? "Salon", ampel: ampel,
                                     wort: wort, aktiv: text(s["naechster_schritt"]),
                                     aufgabe: nil))
        }
        return zeilen
    }

    static func aufgabe(_ roh: Any?) -> Aufgabe? {
        guard let a = roh as? [String: Any],
              let nr = zahl(a["nr"]).map({ Int($0) }),
              let art = text(a["art"]),
              let knopf = text(a["knopf"]) else { return nil }
        return Aufgabe(nr: nr, art: art, knopf: knopf, grund: text(a["grund"]),
                       whatsapp: text(a["whatsapp"]))
    }

    static func einladung(_ daten: Data?) -> Einladung? {
        guard let daten,
              let json = (try? JSONSerialization.jsonObject(with: daten)) as? [String: Any],
              let link = text(json["link"]) else { return nil }
        return Einladung(link: link, text: text(json["text"]),
                         whatsapp: text(json["whatsapp"]))
    }

    /// Farbe und Wort zu einem Salon. Das Wort des Servers bleibt stehen,
    /// wo es mehr sagt als die drei Grundwörter („Test vorbei", „gekündigt").
    static func ampel(stand: String?, meilenstein: String?) -> (Ampel, String) {
        if let stand, !stand.isEmpty {
            switch stand.lowercased() {
            case "macht mit", "hat abgeschlossen":        return (.gruen, "zahlt")
            case "probiert aus":                          return (.gelb, "probiert aus")
            case "will weitermachen", "zahlung offen":    return (.gelb, stand)
            case "noch nicht gestartet":                  return (.grau, "eingeladen")
            default:                                      return (.grau, stand)
            }
        }
        switch meilenstein {
        case "gezeichnet", "gehalten": return (.gruen, "zahlt")
        case "testet":                 return (.gelb, "probiert aus")
        default:                       return (.grau, "eingeladen")
        }
    }

    // Nachsichtig lesen: Zahlen dürfen als Zahl oder Text kommen, leere
    // Texte zählen als fehlend.
    static func zahl(_ x: Any?) -> Double? {
        // `is Bool` taugt hier nicht: Swift hält jede 0 und 1 aus JSON für
        // ein Bool. Ob es wirklich eins war, sagt nur der Typ dahinter.
        if let n = x as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() {
            return n.doubleValue
        }
        if let s = x as? String { return Double(s.replacingOccurrences(of: ",", with: ".")) }
        return nil
    }

    static func text(_ x: Any?) -> String? {
        guard let s = x as? String else { return nil }
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? nil : t
    }
}

// MARK: - Was auf dem Bildschirm steht

extension EmpfehlenStand {

    /// Ab dieser Summe wird überwiesen (`kern_ambassador.MINDEST_AUSZAHLUNG`).
    static let mindestsumme: Double = 100

    /// Geld liegt bereit, aber es fehlt das Konto, auf das es soll.
    var kontoFehlt: Bool { !profilVollstaendig && geld.offen > 0 }

    /// Die Zeile unter dem Betrag: wann das Geld kommt.
    var geldSatz: String {
        let g = geld
        if g.offen <= 0 { return "Sobald ein Salon mitmacht, steht dein Geld hier." }
        if kontoFehlt { return "Liegt für dich bereit — sobald dein Konto da ist, überweisen wir." }
        if g.unterwegs > 0, g.unterwegs >= g.offen { return "Ist schon auf dem Weg zu dir." }
        guard let e = g.erwartet, let tag = Self.datumLang(e.datum) else {
            if g.unterwegs > 0 {
                return "Davon sind \(Self.euro(g.unterwegs)) schon auf dem Weg zu dir."
            }
            return "Überwiesen wird, sobald \(Self.euro(Self.mindestsumme)) zusammen sind."
        }
        if e.betrag >= g.offen { return "Kommt am \(tag) auf dein Konto." }
        return "Davon kommen \(Self.euro(e.betrag)) am \(tag), der Rest später."
    }

    /// „79 €", „1.234 €", „79,50 €" — ohne Nachkommastellen, wenn es keine gibt.
    static func euro(_ wert: Double) -> String {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "de_DE")
        f.numberStyle = .decimal
        let ganz = wert.rounded() == wert
        f.minimumFractionDigits = ganz ? 0 : 2
        f.maximumFractionDigits = ganz ? 0 : 2
        return (f.string(from: NSNumber(value: wert)) ?? "\(Int(wert))") + " €"
    }

    /// „2026-01-15" → „15. Januar"; im nächsten Jahr mit Jahreszahl.
    static func datumLang(_ iso: String, heute: Date = Date()) -> String? {
        let teile = iso.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard teile.count == 3, (1...12).contains(teile[1]), (1...31).contains(teile[2])
        else { return nil }
        let monate = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                      "August", "September", "Oktober", "November", "Dezember"]
        let jahr = Calendar(identifier: .gregorian).component(.year, from: heute)
        let ohneJahr = "\(teile[2]). \(monate[teile[1] - 1])"
        return teile[0] == jahr ? ohneJahr : "\(ohneJahr) \(teile[0])"
    }

    /// Der Text, wenn der Server keinen schreibt (Kontakt ohne Handynummer).
    static func einladungstext(vorname: String, link: String) -> String {
        let anrede = vorname.isEmpty ? "Hallo" : "Hallo \(vorname)"
        return "\(anrede), ich mache meine Belege jetzt mit babu: Foto machen, fertig. "
            + "Probier es 30 Tage kostenlos aus: \(link)"
    }

    /// Die Handynummer eines Kontakts: zuerst, was als Mobil/iPhone
    /// gespeichert ist, sonst eine Nummer, die wie ein Handy aussieht.
    /// Festnetz taugt nicht für WhatsApp — dann lieber gar keine.
    static func handynummer(_ nummern: [(mobil: Bool, nummer: String)]) -> String? {
        let brauchbar = nummern.filter { ziffern($0.nummer).count >= 6 }
        if let m = brauchbar.first(where: { $0.mobil }) { return m.nummer }
        return brauchbar.first(where: { siehtNachHandyAus($0.nummer) })?.nummer
    }

    /// Deutsche (015x/016x/017x), österreichische (06xx) und Schweizer
    /// (075–079) Handynummern, mit oder ohne Ländervorwahl.
    static func siehtNachHandyAus(_ roh: String) -> Bool {
        var z = ziffern(roh)
        let international = roh.trimmingCharacters(in: .whitespaces).hasPrefix("+")
        if !international {
            if z.hasPrefix("00") { z = String(z.dropFirst(2)) }
            else if z.hasPrefix("0") { z = "49" + z.dropFirst() }
        }
        guard z.count >= 10, z.count <= 15 else { return false }
        return ["4915", "4916", "4917", "436", "4175", "4176", "4177", "4178", "4179"]
            .contains { z.hasPrefix($0) }
    }

    private static func ziffern(_ s: String) -> String {
        s.filter(\.isNumber)
    }
}

/// Anmelden per Link: `babu://anmelden/<token>` (babu Pro: `babupro://…`).
/// Die Seite hinter dem Link in der Mail schickt genau diese Adresse.
enum Anmeldelink {
    static let schemata: Set<String> = ["babu", "babupro"]

    /// Der Token, wenn die Adresse ein Anmelde-Link ist — sonst `nil`
    /// (dann ist es eine geteilte Datei oder etwas anderes).
    static func token(aus url: URL) -> String? {
        guard let schema = url.scheme?.lowercased(), schemata.contains(schema),
              url.host?.lowercased() == "anmelden" else { return nil }
        let token = url.pathComponents.filter { $0 != "/" }.last ?? ""
        return token.isEmpty ? nil : token
    }
}

// MARK: - Ka-ching

/// Was dieses Telefon zuletzt von ihrem Geld und ihren Salons gesehen hat.
/// Liegt je Code in den UserDefaults — eine Kleinigkeit fürs Gefühl, kein
/// Bestand, der in `zustand.json` gehört.
struct Merkstand: Codable, Equatable {
    var verdient: Double
    /// Die Salons, die schon zahlen (`Salonzeile.schluessel`).
    var gruene: [String]
}

/// Ein Salon ist zahlende Kundin geworden: Geld kam dazu, ein Salon wurde
/// grün — oder beides. Ein Ereignis je Öffnen, auch wenn mehrere zugleich.
struct KachingEreignis: Equatable, Identifiable {
    var id = UUID()
    /// Wie viel dazukam (0: nur ein Salon wurde grün, das Geld kommt noch).
    var plus: Double
    /// Wer neu dabei ist — so, wie die Liste die Salons nennt.
    var namen: [String]
    var satz: String
    /// Der offene Betrag vorher und jetzt — dazwischen zählt die Zahl.
    var offenVorher: Double
    var offenJetzt: Double

    var geldGeaendert: Bool { plus > 0 }
}

extension EmpfehlenStand {

    var merkstand: Merkstand {
        Merkstand(verdient: verdient,
                  gruene: salons.filter { $0.ampel == .gruen }.map(\.schluessel).sorted())
    }

    /// Gibt es seit dem gemerkten Stand etwas zu feiern? Beim allerersten
    /// Mal (nichts gemerkt) nie — dann wird nur gemerkt. Sinkt `verdient`
    /// (Storno), ist das kein Ereignis.
    func kaching(seit gemerkt: Merkstand?) -> KachingEreignis? {
        guard let gemerkt else { return nil }
        let plus = max(0, verdient - gemerkt.verdient)
        let schonGruen = Set(gemerkt.gruene)
        let neu = salons.filter { $0.ampel == .gruen && !schonGruen.contains($0.schluessel) }
        var namen: [String] = []
        for z in neu where !namen.contains(z.name) { namen.append(z.name) }
        guard plus > 0 || !namen.isEmpty else { return nil }

        var wer = namen
        if wer.isEmpty, let salon = letzteProvisionSalon { wer = [salon] }
        let wie = wer.isEmpty ? nil
            : Self.aufzaehlen(wer) + (wer.count == 1 ? " macht mit!" : " machen mit!")
        let satz: String
        switch (plus > 0, wie) {
        case (true, let wie?): satz = "+\(Self.euro(plus)) — \(wie)"
        case (true, nil):      satz = "+\(Self.euro(plus))"
        case (false, let wie?): satz = wie
        case (false, nil):     satz = ""   // kommt nicht vor: oben ausgeschlossen
        }
        return KachingEreignis(plus: plus, namen: namen, satz: satz,
                               offenVorher: max(0, geld.offen - plus),
                               offenJetzt: geld.offen)
    }

    /// „Kim", „Kim und Mara", „Kim, Mara und Sabine".
    static func aufzaehlen(_ namen: [String]) -> String {
        guard namen.count > 1 else { return namen.first ?? "" }
        return namen.dropLast().joined(separator: ", ") + " und " + namen.last!
    }

    /// Wie voll der Topf ist: Bezug ist die Summe, ab der überwiesen wird.
    static func fuellung(_ offen: Double) -> Double {
        min(max(offen / mindestsumme, 0), 1)
    }
}
