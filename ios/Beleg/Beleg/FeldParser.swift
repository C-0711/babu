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

        // Belegnummer: RE-…, Bon 1234, Rechnung Nr. …
        if let m = ersterTreffer(gesamt, #"(?:RE[-\s]?[\w/]{3,}|Rechnungs?-?\s?(?:Nr\.?|nummer)[:\s]*([\w/-]+)|Bon\s*(\d{3,})|Beleg\s*(\d{3,}))"#, caseInsensitive: true) {
            f.belegNr = m.trimmingCharacters(in: .whitespaces)
        }

        // Steuersatz
        if matcht(gesamt, #"7\s*%"#), !matcht(gesamt, #"19\s*%"#) { f.ustSatz = 7 }

        // Beträge (deutsches Format)
        let betraege = alleTreffer(gesamt, #"\b\d{1,3}(?:\.\d{3})*,\d{2}\b"#)
            .compactMap { parseBetrag($0) }
        if let max = betraege.max() {
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
        // Kein Treffer: unsicherer KI-Fallback → Review
        let basis = 40 + felder.felderZahl * 5 + Int(felder.ocrKonfidenz * 10)
        return Vorschlag(konto: "6850", kreditor: "70099", herkunft: .ki,
                         confidence: min(basis, 74),
                         begruendung: "Kein Historien- oder Regeltreffer — Leistungsart bitte prüfen.",
                         steuerschluessel: ksDefault)
    }
}
