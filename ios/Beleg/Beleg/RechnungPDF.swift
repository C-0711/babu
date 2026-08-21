import UIKit

/// Das PDF, das die Kundin bekommt. Gebaut wird es auf dem Telefon — mit der
/// Nummer, die der Server vorher vergeben hat. Bewusst schlicht: eine
/// Rechnung muss lesbar und vollständig sein, nicht hübsch.
enum RechnungPDF {

    private static let rand: CGFloat = 56
    private static let seite = CGRect(x: 0, y: 0, width: 595, height: 842)  // A4

    /// - Parameter kopf: Stammdaten des Salons (aus den Einstellungen).
    static func bauen(nummer: String, datum: String, leistungszeitpunkt: String,
                      kopf: [String: String], empfaenger: Empfaenger,
                      positionen: [RechnungPosition], summe: RechnungsSumme,
                      kleinunternehmer: Bool, hinweis: String = "",
                      akzent: UIColor = .black, logo: UIImage? = nil) -> Data {
        let renderer = UIGraphicsPDFRenderer(bounds: seite)
        return renderer.pdfData { ctx in
            ctx.beginPage()
            var y: CGFloat = rand

            // Das Logo oben rechts — so groß, dass man es erkennt, so klein,
            // dass es die Rechnung nicht zur Werbung macht.
            if let logo {
                let breite: CGFloat = 96
                let hoehe = min(breite, breite * logo.size.height / max(logo.size.width, 1))
                logo.draw(in: CGRect(x: seite.width - rand - breite, y: rand,
                                     width: breite, height: hoehe))
            }

            // Absender klein über der Anschrift — wie im Fensterumschlag.
            let absender = [kopf["betrieb_name"], kopf["anschrift"]]
                .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
            y = zeichne(absender, at: y, groesse: 8, farbe: .darkGray)
            y += 14

            // Empfängerin
            y = zeichne(empfaenger.name, at: y, groesse: 11, fett: true)
            for zeile in empfaenger.anschrift.split(separator: ",") {
                y = zeichne(String(zeile).trimmed, at: y, groesse: 11)
            }
            if !empfaenger.ustId.isEmpty {
                y = zeichne("USt-IdNr.: " + empfaenger.ustId, at: y, groesse: 9,
                            farbe: .darkGray)
            }
            y += 40

            // Überschrift und Eckdaten
            y = zeichne("Rechnung \(nummer)", at: y, groesse: 18, fett: true,
                        farbe: akzent)
            y += 6
            y = zeichne("Rechnungsdatum: " + tagKurz(datum), at: y, groesse: 10)
            y = zeichne("Leistungszeitpunkt: " + tagKurz(leistungszeitpunkt),
                        at: y, groesse: 10)
            y += 22

            // Positionen
            y = zeile(links: "Beschreibung", rechts: "Betrag", at: y, fett: true)
            y = linie(at: y + 4, ctx: ctx, farbe: akzent, staerke: 1.2)
            for p in positionen {
                let text = p.menge == 1 ? p.text
                                        : "\(mengeText(p.menge)) × \(p.text)"
                let satz = kleinunternehmer ? "" : "  (\(p.ustSatz) %)"
                y = zeile(links: text + satz, rechts: fmtEur(p.gesamt), at: y + 6)
            }
            y = linie(at: y + 8, ctx: ctx)

            // Summen
            y = zeile(links: "Netto", rechts: fmtEur(summe.netto), at: y + 8)
            for s in summe.jeSatz {
                y = zeile(links: "Umsatzsteuer \(s.satz) %", rechts: fmtEur(s.ust),
                          at: y + 4)
            }
            y = zeile(links: "Gesamtbetrag", rechts: fmtEur(summe.brutto),
                      at: y + 8, fett: true)

            // Pflichthinweis der Kleinunternehmerin
            if kleinunternehmer {
                y += 22
                y = zeichne("Kein Ausweis von Umsatzsteuer nach § 19 UStG "
                            + "(Kleinunternehmerregelung).", at: y, groesse: 9)
            }
            if !hinweis.isEmpty {
                y += 14
                y = zeichne(hinweis, at: y, groesse: 9)
            }

            // Fuß: Steuernummer ist Pflicht, Bankdaten sind Höflichkeit.
            var fuss = [kopf["betrieb_name"], kopf["anschrift"]]
                .compactMap { $0 }.filter { !$0.isEmpty }
            if let st = kopf["steuernummer"], !st.isEmpty { fuss.append("Steuernummer " + st) }
            if let uid = kopf["ust_id"], !uid.isEmpty { fuss.append("USt-IdNr. " + uid) }
            if let iban = kopf["iban"], !iban.isEmpty { fuss.append("IBAN " + iban) }
            if let bank = kopf["bank"], !bank.isEmpty { fuss.append(bank) }
            var fy = seite.height - rand - CGFloat(fuss.count) * 12
            for zeile in fuss {
                fy = zeichne(zeile, at: fy, groesse: 8, farbe: .darkGray)
            }
        }
    }

    // MARK: - Zeichnen

    @discardableResult
    private static func zeichne(_ text: String, at y: CGFloat, groesse: CGFloat,
                                fett: Bool = false,
                                farbe: UIColor = .black) -> CGFloat {
        let schrift = fett ? UIFont.boldSystemFont(ofSize: groesse)
                           : UIFont.systemFont(ofSize: groesse)
        let breite = seite.width - 2 * rand
        let rechteck = CGRect(x: rand, y: y, width: breite, height: 400)
        let hoehe = (text as NSString).boundingRect(
            with: CGSize(width: breite, height: .greatestFiniteMagnitude),
            options: .usesLineFragmentOrigin,
            attributes: [.font: schrift], context: nil).height
        (text as NSString).draw(with: rechteck, options: .usesLineFragmentOrigin,
                                attributes: [.font: schrift, .foregroundColor: farbe],
                                context: nil)
        return y + max(hoehe, groesse + 3)
    }

    private static func zeile(links: String, rechts: String, at y: CGFloat,
                              fett: Bool = false) -> CGFloat {
        let schrift = fett ? UIFont.boldSystemFont(ofSize: 11)
                           : UIFont.systemFont(ofSize: 11)
        let breite = seite.width - 2 * rand
        (links as NSString).draw(
            with: CGRect(x: rand, y: y, width: breite - 110, height: 40),
            options: .usesLineFragmentOrigin, attributes: [.font: schrift], context: nil)
        let absatz = NSMutableParagraphStyle()
        absatz.alignment = .right
        (rechts as NSString).draw(
            with: CGRect(x: rand + breite - 110, y: y, width: 110, height: 40),
            options: .usesLineFragmentOrigin,
            attributes: [.font: schrift, .paragraphStyle: absatz], context: nil)
        let hoehe = (links as NSString).boundingRect(
            with: CGSize(width: breite - 110, height: .greatestFiniteMagnitude),
            options: .usesLineFragmentOrigin,
            attributes: [.font: schrift], context: nil).height
        return y + max(hoehe, 14)
    }

    private static func linie(at y: CGFloat, ctx: UIGraphicsPDFRendererContext,
                              farbe: UIColor = .lightGray,
                              staerke: CGFloat = 0.5) -> CGFloat {
        ctx.cgContext.setStrokeColor(farbe.cgColor)
        ctx.cgContext.setLineWidth(staerke)
        ctx.cgContext.move(to: CGPoint(x: rand, y: y))
        ctx.cgContext.addLine(to: CGPoint(x: seite.width - rand, y: y))
        ctx.cgContext.strokePath()
        return y + 2
    }

    private static func mengeText(_ menge: Double) -> String {
        menge == menge.rounded() ? String(Int(menge))
                                 : String(format: "%.2f", menge).replacingOccurrences(
                                     of: ".", with: ",")
    }
}
