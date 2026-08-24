import Foundation

/// Vom OCR extrahierte Felder eines Belegs.
struct Felder {
    var lieferant: String?
    var belegNr: String?
    var datumText: String?
    var netto: Double?
    var ust: Double?
    var brutto: Double?
    /// 19, 7 oder 0 — immer das, was auf dem Beleg steht. Steht dort nichts,
    /// bleibt es bei 0: „nicht gefunden" wurde früher stillschweigend zu
    /// 19 %, und das war Vorsteuer, die kein Beleg auswies.
    var ustSatz: Int = 0
    var summenprobeOK = false
    var felderZahl = 0
    var ocrKonfidenz: Double = 0
    var bewirtungsSignal = false
    var gutschriftSignal = false
    /// Steuertabelle je Satz (7 % und 19 % getrennt) — bleibt am Beleg,
    /// damit der Export Mehrsatz-Belege aufteilen kann.
    var steuerPositionen: [SteuerPosition] = []
    /// Erkannte Fremdwährung (AED, CHF, USD …) — nil heißt Euro. Steht sie,
    /// sind ALLE Beträge dieses Belegs in dieser Währung, nicht in Euro.
    var waehrung: String?
}

/// Heuristischer Parser über den erkannten Textzeilen — die On-Device-Lane
/// des Dual-Lane-Konzepts. Deutsch formatierte Beträge (1.234,56).
enum FeldParser {

    /// Deutsche Beträge: mit Tausenderpunkt (1.234,56) ODER ohne (1234,56) —
    /// viele Kassen drucken vierstellig ohne Punkt; das alte Muster verlor
    /// dadurch jeden Betrag ab 1.000 €.
    static let betragMuster = #"\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,6},\d{2}"#

    static func parse(zeilen: [(text: String, conf: Double)]) -> Felder {
        // Fremdwährung zuerst: steht auf dem Beleg AED/CHF/USD & Co. neben
        // den Beträgen, sind die Zahlen KEINE Euro — der Euro-Wert kommt
        // später von der Buchhaltung (Kontoauszug-Abgleich oder Kurs).
        let fremd = fremdwaehrung(zeilen.map(\.text))
        var f = Felder()
        let alleZeilen = zeilen.map { $0.text }
        let gesamt = alleZeilen.joined(separator: "\n")
        f.ocrKonfidenz = zeilen.isEmpty ? 0 : zeilen.map { $0.conf }.reduce(0, +) / Double(zeilen.count)

        // Lieferant: erste "wortartige" Zeile ohne Datum/Betrag.
        for z in alleZeilen.prefix(5) {
            let t = z.trimmingCharacters(in: .whitespaces)
            guard t.count > 3 else { continue }
            guard t.rangeOfCharacter(from: .letters) != nil else { continue }
            if matcht(t, #"\d{1,2}\.\d{1,2}\.\d{2,4}"#) { continue }
            if matcht(t, #"^\s*(rechnung|quittung|bon|beleg|kassenbon)\b"#, caseInsensitive: true) { continue }
            f.lieferant = t
            break
        }

        // Datum: dd.MM.yyyy bzw. dd.MM.yy — nur plausible Werte (Tag 1–31,
        // Monat 1–12); eine Zeile mit „Datum"-Label gewinnt vor dem ersten
        // Treffer im Volltext (der oft „gültig bis" oder Lieferdatum ist).
        let datumMuster = #"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b"#
        let datumsKandidaten = alleZeilen.filter { matcht($0, #"datum"#, caseInsensitive: true) }
            .compactMap { ersterTreffer($0, datumMuster) }
            + alleTreffer(gesamt, datumMuster)
        f.datumText = datumsKandidaten.first(where: datumPlausibel)

        // Belegnummer: erst explizite Labels (Rechnungs-Nr., Bon-Nr. …), dann
        // ein nacktes „-Nr.:" (Thermobons schneiden das Label oft links ab),
        // dann RE-Token — immer mit erzwungener Ziffer, damit das bloße Wort
        // „Rechnung" nie als Nummer durchgeht.
        f.belegNr = (
            ersteGruppe(gesamt, #"\b(?:re(?:chn(?:ung)?)?s?|beleg|bon|quittungs?)[-.\s]*(?:nr|nummer)\.?\s*[:.]?\s*([\w/-]*\d[\w/-]*)"#)
            ?? ersteGruppe(gesamt, #"\bnr\.?\s*:\s*([\w/-]*\d[\w/-]*)"#)
            ?? ersterTreffer(gesamt, #"\bRE(?=[-\s]?[\w/]*\d)[-\s]?[\w/-]{3,}"#, caseInsensitive: true)
            ?? ersteGruppe(gesamt, #"\b(?:bon|beleg)\s*(\d{3,})"#)
        )?.trimmingCharacters(in: .whitespaces)

        // Steuersatz: aus dem Beleg gelesen, nie angenommen. Die alte Regel
        // („7 %, wenn nirgends 19 % steht") ließ 19 % als Normalfall stehen —
        // und im Salon stimmt das oft nicht: Porto, Versicherung, Miete,
        // Beiträge und Bankgebühren tragen gar keine Umsatzsteuer. Steht
        // nichts da, sind es 0 %; was sonst herauskäme, wäre Vorsteuer, die
        // auf keinem Beleg stand. Eine Steuertabelle überstimmt das unten.
        f.ustSatz = gesetzlicheSaetze(gesamt).max() ?? 0

        // Kein Steuerausweis (§19 UStG, Porto, steuerfrei): dann wird unten
        // KEINE Vorsteuer aus dem Brutto zurückgerechnet — erfundene 19 %
        // wären unberechtigter Vorsteuerabzug.
        if matcht(gesamt, #"kleinunternehmer|§\s*19\s*ustg|kein(e|en)?\s+(ausweis|umsatzsteuer)|ohne\s+umsatzsteuer|steuerfrei|umsatzsteuerbefreit|nicht\s+umsatzsteuerpflichtig"#,
                  caseInsensitive: true) {
            f.ustSatz = 0
        }

        // Bewirtungssignal aus dem Volltext — nicht nur aus dem Lieferantennamen.
        // „inkgeld" fängt links beschnittene Thermobon-Zeilen („Trinkgeld") ab.
        let klein = gesamt.lowercased()
        let bewirtungsWorte = ["trinkgeld", "inkgeld", "bewirtung", "restaurant",
                               "gasthaus", "gaststätte", "gastronovi", "speisekarte"]
        f.bewirtungsSignal = bewirtungsWorte.contains { klein.contains($0) }
            || matcht(klein, #"\btisch\b"#)

        // Gutschrift/Storno: Betrag mit Vorzeichen oder klare Wortsignale —
        // so ein Beleg wird nie automatisch als Aufwand gesiegelt.
        f.gutschriftSignal = matcht(klein, #"gutschrift|storno|retoure|erstattung"#)
            || matcht(gesamt, #"(^|\s)[-−]\d{1,6},\d{2}\b"#)

        // Beträge (deutsches Format). Zeilen mit Gegeben/Rückgeld sind
        // Zahlungsverkehr, kein Rechnungsbetrag — sonst „besteht" auf einem
        // Barbon 44,50 + 5,50 = 50,00 fälschlich die Summenprobe.
        let zahlungsZeile = #"gegeben|r(ü|ue)ckgeld|wechselgeld|zur(ü|ue)ck\b"#
        let betragRegex = #"\b(?:"# + betragMuster + #")\b"#
        let betraege = alleZeilen
            .filter { !matcht($0, zahlungsZeile, caseInsensitive: true) }
            .flatMap { alleTreffer($0, betragRegex) }
            .compactMap { parseBetrag($0) }
        let tabelle = steuerTabelle(gesamt)
        let tabellenBrutto = tabelle.reduce(0) { $0 + $1.brutto }

        // Guard 0.75: eine unvollständig aufgelöste Tabelle (fehlende Satz-Zeile)
        // liegt typisch weit unter dem Zahlbetrag — dann lieber Fallback als
        // ein zu kleiner Brutto. Trinkgeld-Differenzen (< 25 %) passieren.
        if !tabelle.isEmpty, tabellenBrutto >= (betraege.max() ?? 0) * 0.75 {
            // Steuertabelle gefunden (Netto/USt/Brutto je Satz): präziser als
            // Paar-Raten — und Trinkgeld bleibt automatisch außen vor.
            f.netto = runde2(tabelle.reduce(0) { $0 + $1.netto })
            f.ust = runde2(tabelle.reduce(0) { $0 + $1.ust })
            f.brutto = runde2(tabellenBrutto)
            f.summenprobeOK = true
            f.steuerPositionen = tabelle
            if let dominant = tabelle.max(by: { $0.netto < $1.netto }) {
                f.ustSatz = dominant.satz
            }
        } else if let max = betraege.max() {
            f.brutto = max
            // Summenprobe: Paar suchen mit netto + ust == brutto
            let rest = betraege.filter { $0 < max }
            außen: for n in rest {
                for u in rest where u != n {
                    if abs(n + u - max) < 0.011, n > u {
                        f.netto = n
                        f.ust = u
                        f.summenprobeOK = true
                        break außen
                    }
                }
            }
            if f.netto == nil {
                if f.ustSatz > 0 {
                    // Rückrechnung aus Brutto, falls Netto/USt nicht einzeln lesbar
                    let satz = Double(f.ustSatz) / 100.0
                    let netto = (max / (1 + satz) * 100).rounded() / 100
                    f.netto = netto
                    f.ust = ((max - netto) * 100).rounded() / 100
                } else {
                    // Ohne Steuerausweis gibt es nichts zurückzurechnen.
                    f.netto = max
                    f.ust = 0
                }
            }
        }

        // Gegenprobe am Bargeld: Gegeben minus Rückgeld muss der Betrag sein.
        // Ein Barbon trägt seine Kontrolle unten mit sich — wer 50 hinlegt
        // und 5,50 zurückbekommt, hat 44,50 bezahlt. Steht oben etwas
        // anderes, ist eine der drei Zahlen falsch gelesen, und dann darf
        // der Beleg nicht mit grünem Haken durchlaufen.
        //
        // Nur nach unten: mehr gegeben als nötig ist Trinkgeld, kein Fehler.
        if let brutto = f.brutto,
           let gegeben = betragAusZeile(alleZeilen, #"gegeben|barzahlung|bar bezahlt"#),
           let rueckgeld = betragAusZeile(alleZeilen, #"r(ü|ue)ckgeld|wechselgeld|zur(ü|ue)ck"#),
           runde2(gegeben - rueckgeld) < brutto - 0.005 {
            f.summenprobeOK = false
        }

        f.felderZahl = [f.lieferant != nil, f.belegNr != nil, f.datumText != nil,
                        f.netto != nil, f.ust != nil, f.brutto != nil].filter { $0 }.count
        f.waehrung = fremd
        return f
    }

    /// Alle Prozentangaben im Text, die ein gesetzlicher Steuersatz sein
    /// können. „7,00 %" gehört dazu — die alte Textsuche fand nur „7 %" und
    /// buchte den Bäckerbon mit 19 %.
    static func gesetzlicheSaetze(_ text: String) -> [Int] {
        alleGruppen(text, #"\b(\d{1,2})(?:[.,]0{1,2})?\s*%"#)
            .compactMap { Int($0) }
            .filter { [0, 5, 7, 16, 19].contains($0) }
    }

    /// Der größte Betrag in der letzten Zeile, die auf das Muster passt.
    /// Barbelege drucken Gegeben und Rückgeld ganz unten.
    static func betragAusZeile(_ zeilen: [String], _ muster: String) -> Double? {
        for z in zeilen.reversed() where matcht(z, muster, caseInsensitive: true) {
            let betraege = alleTreffer(z, #"\b(?:"# + betragMuster + #")\b"#)
                .compactMap { parseBetrag($0) }
            if let groesster = betraege.max() { return groesster }
        }
        return nil
    }

    static func parseBetrag(_ s: String) -> Double? {
        Double(s.replacingOccurrences(of: ".", with: "").replacingOccurrences(of: ",", with: "."))
    }

    /// Tag 1–31, Monat 1–12 — sonst ist es kein Belegdatum (32.13. kommt
    /// aus Artikelnummern und OCR-Fehllesungen).
    static func datumPlausibel(_ s: String) -> Bool {
        let t = s.split(separator: ".")
        guard t.count == 3, let tag = Int(t[0]), let monat = Int(t[1]) else { return false }
        return (1...31).contains(tag) && (1...12).contains(monat)
    }

    // MARK: - Steuertabelle

    /// Liest die Steuersatz-Tabelle eines Bons (Netto/USt/Brutto je Satz) aus
    /// einem Token-Strom von Raten und Beträgen. Funktioniert für zeilenweise
    /// Tabellen („A 19% 15,97 3,03 19,00") UND für spaltenweise zerlegte OCR
    /// („85,40 · 79,81 · 5,59 · 7%"), weil pro Rate beide Nachbarschafts-Fenster
    /// geprüft werden: drei Beträge müssen die Summenprobe UND die
    /// Satz-Plausibilität (USt ≈ Netto × Satz) bestehen.
    static func steuerTabelle(_ text: String) -> [SteuerPosition] {
        enum Token { case satz(Int); case betrag(Double) }
        let muster = #"\b(\d{1,2})(?:[.,]0{1,2})?\s*%|\b("# + betragMuster + #")\b"#
        guard let re = try? NSRegularExpression(pattern: muster) else { return [] }

        let ns = text as NSString
        var tokens: [Token] = []
        re.enumerateMatches(in: text, range: NSRange(location: 0, length: ns.length)) { m, _, _ in
            guard let m else { return }
            if m.range(at: 1).location != NSNotFound,
               let satz = Int(ns.substring(with: m.range(at: 1))),
               [0, 5, 7, 16, 19].contains(satz) {
                tokens.append(.satz(satz))
            } else if m.range(at: 2).location != NSNotFound,
                      let betrag = parseBetrag(ns.substring(with: m.range(at: 2))) {
                tokens.append(.betrag(betrag))
            }
        }

        var zeilen: [SteuerPosition] = []
        for (i, token) in tokens.enumerated() {
            guard case .satz(let satz) = token else { continue }

            // Kandidaten: bis zu drei Beträge VOR und NACH der Rate, jeweils
            // begrenzt durch die Nachbar-Rate. OCR verteilt Tabellenzeilen
            // teils ÜBER den Satz-Token (Brutto/Netto davor, USt danach) —
            // deshalb alle 3er-Kombinationen aus beiden Seiten prüfen und nur
            // ein EINDEUTIG gültiges Tripel übernehmen (nichts raten).
            func seite(_ richtung: Int) -> [Double] {
                var werte: [Double] = []
                var j = i + richtung
                while j >= 0, j < tokens.count, werte.count < 3 {
                    switch tokens[j] {
                    case .satz: return werte
                    case .betrag(let b): werte.append(b)
                    }
                    j += richtung
                }
                return werte
            }
            let pool = seite(-1) + seite(1)
            guard pool.count >= 3 else { continue }

            var treffer: [SteuerPosition] = []
            for a in 0..<pool.count {
                for b in (a + 1)..<pool.count {
                    for c in (b + 1)..<pool.count {
                        guard let z = pruefeTripel([pool[a], pool[b], pool[c]], satz: satz) else { continue }
                        if !treffer.contains(where: { gleich($0, z) }) { treffer.append(z) }
                    }
                }
            }
            guard treffer.count == 1, let z = treffer.first else { continue }  // mehrdeutig → auslassen
            if !zeilen.contains(where: { $0.satz == z.satz && gleich($0, z) }) {
                zeilen.append(z)
            }
        }
        return zeilen
    }

    /// Tripel gültig, wenn Summenprobe hält UND die USt zum Satz passt.
    private static func pruefeTripel(_ werte: [Double], satz: Int) -> SteuerPosition? {
        let s = werte.sorted(by: >)
        let (brutto, netto, ust) = (s[0], s[1], s[2])
        guard abs(netto + ust - brutto) < 0.011 else { return nil }
        let erwartet = netto * Double(satz) / 100
        guard abs(ust - erwartet) <= Swift.max(0.03, erwartet * 0.02) else { return nil }
        return SteuerPosition(satz: satz, netto: netto, ust: ust, brutto: brutto)
    }

    private static func gleich(_ a: SteuerPosition, _ b: SteuerPosition) -> Bool {
        abs(a.brutto - b.brutto) < 0.011 && abs(a.netto - b.netto) < 0.011 && abs(a.ust - b.ust) < 0.011
    }

    private static func runde2(_ x: Double) -> Double { (x * 100).rounded() / 100 }

    private static func matcht(_ text: String, _ pattern: String, caseInsensitive: Bool = false) -> Bool {
        ersterTreffer(text, pattern, caseInsensitive: caseInsensitive) != nil
    }

    private static func ersterTreffer(_ text: String, _ pattern: String, caseInsensitive: Bool = false) -> String? {
        let opts: NSRegularExpression.Options = caseInsensitive ? [.caseInsensitive] : []
        guard let re = try? NSRegularExpression(pattern: pattern, options: opts) else { return nil }
        let range = NSRange(text.startIndex..., in: text)
        guard let m = re.firstMatch(in: text, range: range),
              let r = Range(m.range, in: text) else { return nil }
        return String(text[r])
    }

    /// Wie `ersterTreffer`, liefert aber die erste Capture-Gruppe.
    private static func ersteGruppe(_ text: String, _ pattern: String) -> String? {
        guard let re = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return nil }
        let range = NSRange(text.startIndex..., in: text)
        guard let m = re.firstMatch(in: text, range: range), m.numberOfRanges > 1,
              let r = Range(m.range(at: 1), in: text) else { return nil }
        return String(text[r])
    }

    /// Wie `alleTreffer`, liefert aber je Treffer die erste Capture-Gruppe.
    private static func alleGruppen(_ text: String, _ pattern: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return re.matches(in: text, range: range).compactMap {
            $0.numberOfRanges > 1 ? Range($0.range(at: 1), in: text).map { r in String(text[r]) } : nil
        }
    }

    private static func alleTreffer(_ text: String, _ pattern: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return re.matches(in: text, range: range).compactMap {
            Range($0.range, in: text).map { String(text[$0]) }
        }
    }
}

/// Kontierungs-Engine: Historie → Regeln → Fallback (deterministisch vor generativ).
struct Vorschlag {
    var konto: String
    var kreditor: String
    var herkunft: Herkunft
    var confidence: Int
    var begruendung: String
    var steuerschluessel: String
}

enum Kontierung {
    /// Kreditor-Historie des Demo-Mandanten (Lieferant-Schlüsselwort → Konto).
    static let historie: [(key: String, konto: String, kreditor: String, anzahl: Int)] = [
        ("müller", "6815", "70001", 14),
        ("hetzner", "6837", "70003", 9),
        ("telekom", "6805", "70005", 23),
        ("shell", "6530", "70019", 11)
    ]

    static let regeln: [(keys: [String], konto: String, ks: String, name: String)] = [
        (["gasthaus", "restaurant", "gaststätte"], "6640", "9", "Bewirtungsbeleg"),
        (["tankstelle", "aral", "esso", "jet ", "total"], "6530", "9", "Kfz-Kosten"),
        (["fernverkehr", "deutsche bahn", "db ag"], "6673", "8", "Bahnfahrt"),
        (["stadtwerke", "energie", "strom"], "6325", "9", "Energie-Abschlag"),
        (["bürobedarf", "papier", "toner"], "6815", "9", "Bürobedarf"),
        (["blumen"], "6610", "8", "Geschenk/Aufmerksamkeit"),
        (["buchhandlung", "verlag"], "6820", "9", "Fachliteratur")
    ]

    static func vorschlag(felder: Felder) -> Vorschlag {
        var v = basisVorschlag(felder: felder)
        // Gutschrift/Storno nie automatisch als Aufwand siegeln — Vorzeichen
        // und Buchungsrichtung muss ein Mensch bestätigen.
        if felder.gutschriftSignal {
            v.confidence = min(v.confidence, 70)
            v.begruendung += " Sieht nach Gutschrift/Erstattung aus — bitte prüfen."
        }
        return v
    }

    private static func basisVorschlag(felder: Felder) -> Vorschlag {
        let name = (felder.lieferant ?? "").lowercased()
        let ksDefault = felder.ustSatz == 7 ? "8" : (felder.ustSatz == 0 ? "0" : "9")

        if let h = historie.first(where: { name.contains($0.key) }) {
            var conf = 94 + min(4, h.anzahl / 5)
            if !felder.summenprobeOK { conf = min(conf, 90) }
            return Vorschlag(konto: h.konto, kreditor: h.kreditor, herkunft: .historie,
                             confidence: conf,
                             begruendung: "Lieferant \(h.anzahl)× zuvor auf \(h.konto) gebucht.",
                             steuerschluessel: ksDefault)
        }
        if let r = regeln.first(where: { r in r.keys.contains(where: { name.contains($0) }) }) {
            var conf = 85 + (felder.summenprobeOK ? 4 : -6)
            conf = min(conf, 93)
            return Vorschlag(konto: r.konto, kreditor: "70099", herkunft: .regel,
                             confidence: conf,
                             begruendung: "Regel „\(r.name)“ griff — ein Tap genügt.",
                             steuerschluessel: r.ks)
        }
        // Bewirtungssignale aus dem Belegtext (Trinkgeld, Tisch-Nr., Gastro-Kasse):
        // greift, wenn der Lieferantenname nichts hergibt — z. B. verstümmelte
        // Logo-Lesung. Etwas vorsichtiger als eine Namensregel.
        if felder.bewirtungsSignal {
            let conf = min(83 + (felder.summenprobeOK ? 4 : -6), 90)
            return Vorschlag(konto: "6640", kreditor: "70099", herkunft: .regel,
                             confidence: conf,
                             begruendung: "Bewirtungssignale im Belegtext (Trinkgeld/Tisch) — Bewirtungsangaben nach §4 Abs. 5 EStG ergänzen.",
                             steuerschluessel: ksDefault)
        }

        // Kein Treffer: unsicherer KI-Fallback → Review
        let basis = 40 + felder.felderZahl * 5 + Int(felder.ocrKonfidenz * 10)
        return Vorschlag(konto: "6850", kreditor: "70099", herkunft: .ki,
                         confidence: min(basis, 74),
                         begruendung: "Kein Historien- oder Regeltreffer — Leistungsart bitte prüfen.",
                         steuerschluessel: ksDefault)
    }
}


extension FeldParser {
    /// Welche Nicht-Euro-Währung der Beleg trägt — die erste, die neben
    /// einer Zahl auftaucht. € gewinnt: Belege mit Euro-Zeichen (auch
    /// Kartenzettel mit Umrechnung) gelten als Euro.
    static func fremdwaehrung(_ zeilen: [String]) -> String? {
        let muster = ["AED", "CHF", "USD", "GBP", "CZK", "PLN", "TRY",
                      "SEK", "DKK", "NOK", "HUF"]
        var treffer: String?
        for z in zeilen {
            if z.contains("€") || z.uppercased().contains(" EUR") { return nil }
            guard treffer == nil else { continue }
            let gross = z.uppercased()
            for w in muster where gross.contains(w) {
                // Nur zählen, wenn eine Zahl in der Nähe steht — sonst ist
                // es Text („USD-Konto") und kein Betrag.
                if z.rangeOfCharacter(from: .decimalDigits) != nil {
                    treffer = w
                }
            }
        }
        return treffer
    }
}
