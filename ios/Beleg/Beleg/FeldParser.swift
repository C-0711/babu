import Foundation

/// Vom OCR extrahierte Felder eines Belegs.
struct Felder {
    var lieferant: String?
    var belegNr: String?
    var datumText: String?
    var netto: Double?
    var ust: Double?
    var brutto: Double?
    var ustSatz: Int = 19
    var summenprobeOK = false
    var felderZahl = 0
    var ocrKonfidenz: Double = 0
    var bewirtungsSignal = false
}

/// Heuristischer Parser über den erkannten Textzeilen — die On-Device-Lane
/// des Dual-Lane-Konzepts. Deutsch formatierte Beträge (1.234,56).
enum FeldParser {

    static func parse(zeilen: [(text: String, conf: Double)]) -> Felder {
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

        // Datum: dd.MM.yyyy bzw. dd.MM.yy
        if let m = ersterTreffer(gesamt, #"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b"#) {
            f.datumText = m
        }

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

        // Steuersatz-Heuristik (Fallback; eine Steuertabelle überstimmt sie unten)
        if matcht(gesamt, #"7\s*%"#), !matcht(gesamt, #"19\s*%"#) { f.ustSatz = 7 }

        // Bewirtungssignal aus dem Volltext — nicht nur aus dem Lieferantennamen.
        // „inkgeld" fängt links beschnittene Thermobon-Zeilen („Trinkgeld") ab.
        let klein = gesamt.lowercased()
        let bewirtungsWorte = ["trinkgeld", "inkgeld", "bewirtung", "restaurant",
                               "gasthaus", "gaststätte", "gastronovi", "speisekarte"]
        f.bewirtungsSignal = bewirtungsWorte.contains { klein.contains($0) }
            || matcht(klein, #"\btisch\b"#)

        // Beträge (deutsches Format)
        let betraege = alleTreffer(gesamt, #"\b\d{1,3}(?:\.\d{3})*,\d{2}\b"#)
            .compactMap { parseBetrag($0) }
        let tabelle = steuerTabelle(gesamt)
        let tabellenBrutto = tabelle.reduce(0) { $0 + $1.brutto }

        if !tabelle.isEmpty, tabellenBrutto >= (betraege.max() ?? 0) * 0.5 {
            // Steuertabelle gefunden (Netto/USt/Brutto je Satz): präziser als
            // Paar-Raten — und Trinkgeld bleibt automatisch außen vor.
            f.netto = runde2(tabelle.reduce(0) { $0 + $1.netto })
            f.ust = runde2(tabelle.reduce(0) { $0 + $1.ust })
            f.brutto = runde2(tabellenBrutto)
            f.summenprobeOK = true
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
            if f.netto == nil, f.ustSatz > 0 {
                // Rückrechnung aus Brutto, falls Netto/USt nicht einzeln lesbar
                let satz = Double(f.ustSatz) / 100.0
                let netto = (max / (1 + satz) * 100).rounded() / 100
                f.netto = netto
                f.ust = ((max - netto) * 100).rounded() / 100
            }
        }

        f.felderZahl = [f.lieferant != nil, f.belegNr != nil, f.datumText != nil,
                        f.netto != nil, f.ust != nil, f.brutto != nil].filter { $0 }.count
        return f
    }

    static func parseBetrag(_ s: String) -> Double? {
        Double(s.replacingOccurrences(of: ".", with: "").replacingOccurrences(of: ",", with: "."))
    }

    // MARK: - Steuertabelle

    private struct SteuerZeile {
        let satz: Int
        let netto: Double
        let ust: Double
        let brutto: Double
    }

    /// Liest die Steuersatz-Tabelle eines Bons (Netto/USt/Brutto je Satz) aus
    /// einem Token-Strom von Raten und Beträgen. Funktioniert für zeilenweise
    /// Tabellen („A 19% 15,97 3,03 19,00") UND für spaltenweise zerlegte OCR
    /// („85,40 · 79,81 · 5,59 · 7%"), weil pro Rate beide Nachbarschafts-Fenster
    /// geprüft werden: drei Beträge müssen die Summenprobe UND die
    /// Satz-Plausibilität (USt ≈ Netto × Satz) bestehen.
    private static func steuerTabelle(_ text: String) -> [SteuerZeile] {
        enum Token { case satz(Int); case betrag(Double) }
        let muster = #"\b(\d{1,2})(?:[.,]0{1,2})?\s*%|\b(\d{1,3}(?:\.\d{3})*,\d{2})\b"#
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

        var zeilen: [SteuerZeile] = []
        for (i, token) in tokens.enumerated() {
            guard case .satz(let satz) = token else { continue }

            // Bis zu drei Beträge vor bzw. nach der Rate — begrenzt durch die
            // nächste Rate, damit sich Zeilen nicht vermischen.
            func fenster(_ richtung: Int) -> [Double] {
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
            func aufloesen(_ werte: [Double]) -> SteuerZeile? {
                guard werte.count == 3 else { return nil }
                let s = werte.sorted(by: >)
                let (brutto, netto, ust) = (s[0], s[1], s[2])
                guard abs(netto + ust - brutto) < 0.011 else { return nil }
                let erwartet = netto * Double(satz) / 100
                guard abs(ust - erwartet) <= Swift.max(0.03, erwartet * 0.02) else { return nil }
                return SteuerZeile(satz: satz, netto: netto, ust: ust, brutto: brutto)
            }

            if let z = aufloesen(fenster(1)) ?? aufloesen(fenster(-1)),
               !zeilen.contains(where: {
                   $0.satz == z.satz && abs($0.brutto - z.brutto) < 0.011 && abs($0.ust - z.ust) < 0.011
               }) {
                zeilen.append(z)
            }
        }
        return zeilen
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
