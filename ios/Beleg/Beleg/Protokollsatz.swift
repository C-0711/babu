import Foundation

/// Zerlegt das Markdown des Servers in Blöcke, die sich anzeigen lassen.
/// Bewusst klein gehalten: es muss genau das können, was das Protokoll
/// benutzt — nicht Markdown im Allgemeinen.
enum Protokollsatz {
    enum Block {
        case titel(String)
        case abschnitt(String)
        case hervorgehoben(String)
        case absatz(String)
        case punkt(String)
        case zitat(String)
        case rechnung([String])
        case tabelle(kopf: [String], zeilen: [[String]])
    }

    static func bloecke(aus text: String) -> [Block] {
        var raus: [Block] = []
        var absatz: [String] = []
        var rechnung: [String] = []
        var tabelle: [[String]] = []

        func absatzSchliessen() {
            guard !absatz.isEmpty else { return }
            let t = absatz.joined(separator: " ")
            absatz = []
            if t.hasPrefix("**"), t.hasSuffix("**") {
                raus.append(.hervorgehoben(ohneAuszeichnung(t)))
            } else {
                raus.append(.absatz(ohneAuszeichnung(t)))
            }
        }
        func rechnungSchliessen() {
            guard !rechnung.isEmpty else { return }
            raus.append(.rechnung(rechnung))
            rechnung = []
        }
        func tabelleSchliessen() {
            guard let kopf = tabelle.first else { return }
            let zeilen = Array(tabelle.dropFirst())
            tabelle = []
            guard !zeilen.isEmpty else { return }
            raus.append(.tabelle(kopf: kopf, zeilen: zeilen))
        }

        for rohzeile in text.components(separatedBy: .newlines) {
            let zeile = rohzeile.trimmingCharacters(in: .whitespaces)

            // Eingerückte Zeilen sind die Steuerrechnung — dort trägt die
            // Ausrichtung die Bedeutung, also bleibt sie stehen. Zwei
            // Leerzeichen genügen: die Rechenzeichen stehen links vom
            // Zahlenblock („  + Steuer"), und ein Block, der daran
            // auseinanderfiele, wäre keine Rechnung mehr.
            if rohzeile.hasPrefix("  ") && !zeile.isEmpty {
                absatzSchliessen(); tabelleSchliessen()
                rechnung.append(String(rohzeile.dropFirst(2)))
                continue
            }
            rechnungSchliessen()

            if zeile.isEmpty {
                absatzSchliessen(); tabelleSchliessen()
                continue
            }
            if zeile.hasPrefix("|") {
                absatzSchliessen()
                let felder = zellen(zeile)
                // Die Trennzeile (|---|---|) trägt nichts.
                if felder.allSatisfy({ $0.allSatisfy { "-: ".contains($0) } }) { continue }
                tabelle.append(felder)
                continue
            }
            tabelleSchliessen()

            if zeile.hasPrefix("## ") {
                absatzSchliessen()
                raus.append(.abschnitt(String(zeile.dropFirst(3))))
            } else if zeile.hasPrefix("# ") {
                absatzSchliessen()
                raus.append(.titel(String(zeile.dropFirst(2))))
            } else if zeile.hasPrefix("- ") {
                absatzSchliessen()
                raus.append(.punkt(ohneAuszeichnung(String(zeile.dropFirst(2)))))
            } else if zeile.hasPrefix("> ") {
                absatzSchliessen()
                raus.append(.zitat(ohneAuszeichnung(String(zeile.dropFirst(2)))))
            } else {
                absatz.append(zeile)
            }
        }
        absatzSchliessen(); rechnungSchliessen(); tabelleSchliessen()
        return raus
    }

    static func zellen(_ zeile: String) -> [String] {
        var felder: [String] = []
        var aktuell = ""
        var maskiert = false
        for zeichen in zeile.dropFirst() {          // führendes | weg
            if maskiert {
                aktuell.append(zeichen)
                maskiert = false
            } else if zeichen == "\\" {
                maskiert = true
            } else if zeichen == "|" {
                felder.append(aktuell.trimmingCharacters(in: .whitespaces))
                aktuell = ""
            } else {
                aktuell.append(zeichen)
            }
        }
        let rest = aktuell.trimmingCharacters(in: .whitespaces)
        if !rest.isEmpty { felder.append(rest) }
        return felder.map(ohneAuszeichnung)
    }

    /// Sternchen und Backticks entfernen — die Auszeichnung übernimmt hier
    /// die Schrift, nicht das Zeichen.
    static func ohneAuszeichnung(_ text: String) -> String {
        text.replacingOccurrences(of: "**", with: "")
            .replacingOccurrences(of: "`", with: "")
            .replacingOccurrences(of: "&nbsp;", with: "")
            .replacingOccurrences(of: "\\|", with: "|")
            .trimmingCharacters(in: .whitespaces)
    }
}
