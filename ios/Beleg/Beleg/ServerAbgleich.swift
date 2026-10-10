import Foundation

/// Der Server ist die Wahrheit — die Belegliste der App kommt aus der
/// Belegbox (seit 10.10.2026).
///
/// Bis hierher kannte die App nur, was DIESES Telefon fotografiert hatte:
/// `belege` lag in einer Datei je Gerät, ohne Bezug zum Zugang. Daraus
/// folgten drei Meldungen auf einmal: ein zweites Telefon sah eine leere
/// Ablage, zwei Betriebe auf einem Telefon teilten sich eine Liste, und das
/// Blättern in frühere Monate (Ninas #85, #88) ging ins Leere, weil die
/// Monate aus derselben lokalen Liste entstanden.
///
/// Jetzt holt die App `GET /api/belege` und führt zusammen: was der Server
/// hat und hier fehlt, kommt dazu (ohne Foto — das lädt die Einzelansicht
/// nach); was hier als übertragen gilt und dort nicht mehr liegt, ist im
/// Portal gelöscht und geht; was hier noch auf seinen Upload wartet, bleibt
/// unangetastet. Dazu bekommt jeder Zugang seine eigene Zustandsdatei.
/// Reine Logik ohne UIKit — Harness `ios/Tests/serverabgleich`.
enum ServerAbgleich {
    /// Eine Zeile aus `GET /api/belege` — nur die Felder, die die App braucht.
    struct Zeile: Equatable {
        var stamm: String
        var datei: String
        var monat: String?
        var status: String
        var lieferant: String?
        var datum: String?          // ISO „2026-08-03"
        var brutto: Double?
        var netto: Double?
        var ust: Double?
        var ustSatz: Int?
        var konto: String?
        var belegart: String?
        var dokumentklasse: String?
        var hochgeladen: String?    // ISO-Zeit
    }

    static func zeile(aus json: [String: Any]) -> Zeile? {
        guard let stamm = json["stamm"] as? String, !stamm.isEmpty else { return nil }
        func zahl(_ k: String) -> Double? {
            if let d = json[k] as? Double { return d }
            if let i = json[k] as? Int { return Double(i) }
            if let s = json[k] as? String { return Double(s.replacingOccurrences(of: ",", with: ".")) }
            return nil
        }
        func text(_ k: String) -> String? {
            if let s = json[k] as? String { return s.isEmpty ? nil : s }
            if let i = json[k] as? Int { return String(i) }
            return nil
        }
        return Zeile(stamm: stamm,
                     datei: text("datei") ?? stamm,
                     monat: text("monat"),
                     status: text("status") ?? "erfasst",
                     lieferant: text("lieferant"),
                     datum: text("datum"),
                     brutto: zahl("brutto"), netto: zahl("netto"), ust: zahl("ust"),
                     ustSatz: zahl("ust_satz").map { Int($0) },
                     konto: text("konto_skr04"),
                     belegart: text("belegart"),
                     dokumentklasse: text("dokumentklasse"),
                     hochgeladen: text("hochgeladen"))
    }

    /// „2026-08-03" → „03.08.2026". Was schon deutsch ist, bleibt; alles
    /// andere wird leer — leer heißt in der Liste ehrlich „Ohne Datum".
    static func datumText(ausISO iso: String?) -> String {
        guard let iso, !iso.isEmpty else { return "" }
        if iso.contains(".") { return iso }
        let t = iso.prefix(10).split(separator: "-")
        guard t.count == 3, let j = Int(t[0]), let m = Int(t[1]), let d = Int(t[2]),
              (1...12).contains(m), (1...31).contains(d) else { return "" }
        return String(format: "%02d.%02d.%04d", d, m, j)
    }

    /// Letzter Pfadteil ohne Endung — der Schlüssel, unter dem der Server
    /// einen Beleg führt (`<zeit>-<hex>-beleg_<datum>_<slug>_<id8>`).
    static func stamm(ausDateiname name: String?) -> String? {
        guard let name, !name.isEmpty else { return nil }
        let letzter = name.split(separator: "/").last.map(String.init) ?? name
        if let punkt = letzter.lastIndex(of: "."), letzter.distance(from: punkt, to: letzter.endIndex) <= 5 {
            return String(letzter[..<punkt])
        }
        return letzter
    }

    /// Ein lokaler Name passt zum Server-Stamm, wenn er gleich ist — oder der
    /// Server ihm sein Präfix vorangestellt hat (der Upload-Name des Telefons
    /// ist das Suffix, dieselbe Regel wie in `GET /api/beleg/{stamm}`).
    static func passt(lokalerStamm: String, serverStamm: String) -> Bool {
        serverStamm == lokalerStamm || serverStamm.hasSuffix("-" + lokalerStamm)
    }

    static func status(aus server: String) -> BelegStatus {
        switch server {
        case "geprüft", "gebucht": return .bestaetigt
        case "exportiert": return .fixiert
        default: return .offen
        }
    }

    static func begruendung(aus server: String) -> String {
        switch server {
        case "geprüft", "gebucht": return "Von der Buchhaltung gebucht."
        case "exportiert": return "Liegt beim Steuerbüro."
        case "nachfrage": return "Die Buchhaltung hat noch eine Frage."
        case "unlesbar": return "Daraus war nichts zu lesen — bitte ansehen."
        default: return "Wird von der Buchhaltung gelesen."
        }
    }

    static func steuerschluessel(fuer satz: Int?) -> String {
        switch satz { case 19: return "9"; case 7: return "8"; default: return "0" }
    }

    static func zeit(ausISO iso: String?) -> Date? {
        guard let iso, !iso.isEmpty else { return nil }
        let f = ISO8601DateFormatter()
        return f.date(from: iso) ?? {
            f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return f.date(from: iso)
        }()
    }

    /// Ein Beleg, den dieses Telefon nie gesehen hat — vom Server, ohne Foto.
    static func beleg(aus z: Zeile) -> Beleg {
        var b = Beleg(lieferant: z.lieferant ?? "Beleg",
                      belegNr: "ohne Nr.",
                      datumText: datumText(ausISO: z.datum),
                      netto: z.netto ?? 0, ust: z.ust ?? 0, brutto: z.brutto ?? 0,
                      ustSatz: z.ustSatz ?? 0,
                      konto: z.konto,
                      steuerschluessel: steuerschluessel(fuer: z.ustSatz),
                      kreditor: "70000",
                      herkunft: .historie,
                      confidence: status(aus: z.status) == .bestaetigt ? 100 : 0,
                      status: status(aus: z.status),
                      begruendung: begruendung(aus: z.status),
                      summenprobeOK: status(aus: z.status) == .bestaetigt)
        b.ablageStatus = .uebertragen
        b.ablageDateiname = z.datei.split(separator: "/").last.map(String.init) ?? z.datei
        b.ablageZeit = zeit(ausISO: z.hochgeladen)
        b.dokumentklasse = z.dokumentklasse
        b.abgelegtAls = z.dokumentklasse ?? "beleg"
        return b
    }

    /// Was der Server über einen Beleg weiß, den das Telefon selbst
    /// hochgeladen hat: nur Lücken füllen, nie die eigene Buchung überschreiben.
    static func nachtragen(_ b: inout Beleg, aus z: Zeile) {
        guard b.ablageStatus == .uebertragen else { return }
        if b.datumText.isEmpty { b.datumText = datumText(ausISO: z.datum) }
        if b.lieferant.isEmpty || b.lieferant == "Beleg", let l = z.lieferant { b.lieferant = l }
        if b.brutto == 0, let brutto = z.brutto, brutto != 0 {
            b.brutto = brutto
            b.netto = z.netto ?? b.netto
            b.ust = z.ust ?? b.ust
            if let s = z.ustSatz { b.ustSatz = s; b.steuerschluessel = steuerschluessel(fuer: s) }
        }
        if b.konto == nil { b.konto = z.konto }
        if b.dokumentklasse == nil { b.dokumentklasse = z.dokumentklasse }
        // Der Servername ist der Schlüssel zu Review und Bild — ab jetzt exakt.
        if stamm(ausDateiname: b.ablageDateiname) != z.stamm {
            b.ablageDateiname = z.datei.split(separator: "/").last.map(String.init) ?? z.datei
        }
    }

    /// Darf das Fehlen auf dem Server bedeuten „im Portal gelöscht"? Nur für
    /// Belege im Belegfach: Verträge, Briefe und Kontoauszüge liegen in
    /// anderen Fächern und tauchen in `/api/belege` nie auf.
    static func gehoertInsBelegfach(_ b: Beleg) -> Bool {
        (b.abgelegtAls ?? "beleg") == "beleg" && (b.dokumentklasse ?? "beleg") == "beleg"
    }

    /// Die eine Regel: lokal + Server → die Liste, die die App zeigt.
    ///
    /// `vollstaendig` sagt, ob die Serverliste ganz da ist. Nur dann darf
    /// ein fehlender Beleg als gelöscht gelten — eine halbe Seite ist kein
    /// Beweis für gar nichts.
    static func zusammenfuehren(lokal: [Beleg], server: [Zeile], vollstaendig: Bool) -> [Beleg] {
        var ergebnis = lokal
        var getroffen = Set<Int>()
        var neue: [Beleg] = []
        for z in server {
            let treffer = ergebnis.indices.first { i in
                guard !getroffen.contains(i),
                      let s = stamm(ausDateiname: ergebnis[i].ablageDateiname) else { return false }
                return passt(lokalerStamm: s, serverStamm: z.stamm)
            }
            if let i = treffer {
                getroffen.insert(i)
                nachtragen(&ergebnis[i], aus: z)
            } else {
                neue.append(beleg(aus: z))
            }
        }
        if vollstaendig {
            ergebnis = ergebnis.enumerated().filter { i, b in
                getroffen.contains(i)
                    || b.ablageStatus != .uebertragen
                    || b.istDemo == true
                    || !gehoertInsBelegfach(b)
            }.map(\.element)
        }
        neue.sort { ($0.ablageZeit ?? .distantPast) > ($1.ablageZeit ?? .distantPast) }
        return ergebnis + neue
    }

    /// Eine Zustandsdatei je Zugang: der Geräteschlüssel entscheidet, nicht
    /// das Telefon. Zwei Betriebe auf einem iPhone bekommen so zwei Listen.
    /// Ohne Schlüssel die alte `zustand.json` (und der Umzug beim Start).
    static func zustandsDateiName(zugang: String?) -> String {
        guard let z = zugang, !z.isEmpty else { return "zustand.json" }
        var h: UInt64 = 0xcbf2_9ce4_8422_2325          // FNV-1a, 64 Bit
        for b in z.utf8 { h ^= UInt64(b); h = h &* 0x0000_0100_0000_01b3 }
        return "zustand-" + String(h, radix: 16) + ".json"
    }
}
