import Foundation

/// Ein Tages-Kassenbericht — bewusst NUR Tagessummen, exakt wie das
/// Papier-Formular der offenen Ladenkasse (Bestand Vortag, Einnahmen,
/// Ausgaben, gezählter Bestand). Es werden KEINE einzelnen Zahlvorgänge
/// erfasst und keine Zahlung abgewickelt — die App bleibt damit
/// Kassenbuch-Unterstützung und wird kein elektronisches
/// Aufzeichnungssystem mit Kassenfunktion (KassenSichV/§146a-AO-Grenze).
struct Kassenbericht: Codable, Identifiable, Equatable {
    var id = UUID()
    var datum: String              // "2026-08-17" — genau ein Bericht pro Tag
    var bestandVortag = 0.0
    var einnahmenBar = 0.0
    var privateinlagen = 0.0
    var barabhebungBank = 0.0
    var ecZahlungen = 0.0
    // Eingelöste Gutscheine: KEINE neue Einnahme — das Geld kam schon beim
    // Verkauf des Gutscheins in die Kasse. Wird nur für den Tagesumsatz
    // ausgewiesen, nicht in den Kassenbestand gerechnet.
    var gutscheineEingeloest = 0.0
    var trinkgeldTeamEC = 0.0
    var sonstigeAusgaben = 0.0
    var privatentnahmen = 0.0
    var einzahlungBank = 0.0
    var gezaehltSchluss = 0.0
    var erstellt = Date()
    // Optional, damit ältere zustand.json weiter dekodiert (Migration).
    var differenzGrund: String?    // z. B. „10 € Wechselgeld verzählt"
    var sonstigeNotiz: String?     // wofür die sonstige Ausgabe war
    var uebermittelt: Date?        // Tagesblatt liegt in der Belegbox

    /// Korrekturen, die nach dem Festschreiben nötig waren. Nichts wird
    /// überschrieben — was geändert wurde, steht hier mit Grund und Zeitpunkt.
    /// Optional, damit ältere zustand.json weiter dekodiert (Migration).
    var korrekturen: [Kassenkorrektur]?

    var summeEinnahmen: Double { bestandVortag + einnahmenBar + privateinlagen + barabhebungBank }
    var summeAusgaben: Double { trinkgeldTeamEC + sonstigeAusgaben + privatentnahmen + einzahlungBank }
    var rechnerischerBestand: Double { summeEinnahmen - summeAusgaben }
    var differenz: Double { gezaehltSchluss - rechnerischerBestand }
    var tagesumsatz: Double { einnahmenBar + ecZahlungen }
    var kasseStimmt: Bool { abs(differenz) < 0.01 }

    /// Festgeschrieben ist ein Tag, sobald sein Blatt in der Belegbox liegt.
    /// Ab da ist er ein Beleg, kein Entwurf mehr.
    var festgeschrieben: Bool { uebermittelt != nil }
}

// ── Unveränderbarkeit ────────────────────────────────────────────────────────
//
// Nina, 22.08.2026: „Im Kassenbuch darf nichts einfach verschwinden."
//
// Sie hat recht, und es ist nicht Geschmack. Die GoBD verlangen
// Unveränderbarkeit und Nachvollziehbarkeit (§ 146 Abs. 4 AO: eine
// Aufzeichnung darf nicht so verändert werden, dass der ursprüngliche Inhalt
// nicht mehr feststellbar ist). Eine Kasse, in der ein Eintrag spurlos
// überschrieben werden kann, ist bei einer Prüfung formell nicht
// ordnungsgemäß — das kann eine Schätzung nach sich ziehen.
//
// Bis 23.08.2026 tat `kassenberichteSpeichern` genau das: `berichte[i] = neu`,
// ohne Grund, ohne Spur. Die Belegbox hätte die alte Fassung zwar noch in der
// Versionsgeschichte, aber in der App war sie weg — und niemand musste sagen,
// warum.

/// Ein geändertes Feld, in Klartext: was stand da, was steht jetzt da.
struct Feldaenderung: Codable, Equatable {
    var feld: String
    var vorher: String
    var nachher: String
}

/// Eine Korrektur an einem festgeschriebenen Tag — mit Grund, wie es sein muss.
struct Kassenkorrektur: Codable, Equatable, Identifiable {
    var id = UUID()
    var zeitpunkt = Date()
    var grund: String
    var aenderungen: [Feldaenderung]
}

enum Kassenfehler: Error, Equatable {
    /// Ein festgeschriebener Tag wird nicht ohne Begründung geändert.
    case grundFehlt
    /// Es hat sich nichts geändert — dann gibt es auch nichts zu begründen.
    case keineAenderung
}

extension Kassenbericht {
    /// Die Felder, die den Tag ausmachen — Name für Menschen, Wert als Text.
    /// Bewusst hier und nicht per Reflection: was im Kassenbuch steht, soll
    /// jemand lesen können, der den Code nicht kennt.
    var felderFuerSpur: [(String, String)] {
        func g(_ w: Double) -> String { String(format: "%.2f", w) }
        return [
            ("Bestand Vortag", g(bestandVortag)),
            ("Bareinnahmen", g(einnahmenBar)),
            ("Privateinlagen", g(privateinlagen)),
            ("Barabhebung Bank", g(barabhebungBank)),
            ("Kartenzahlungen", g(ecZahlungen)),
            ("Gutscheine eingelöst", g(gutscheineEingeloest)),
            ("Trinkgeld Team (Karte)", g(trinkgeldTeamEC)),
            ("Sonstige Ausgaben", g(sonstigeAusgaben)),
            ("Privatentnahmen", g(privatentnahmen)),
            ("Einzahlung Bank", g(einzahlungBank)),
            ("Gezählter Bestand", g(gezaehltSchluss)),
            ("Grund der Differenz", differenzGrund ?? ""),
            ("Notiz", sonstigeNotiz ?? ""),
        ]
    }

    /// Was sich gegenüber der alten Fassung geändert hat.
    func aenderungenGegen(_ alt: Kassenbericht) -> [Feldaenderung] {
        zip(alt.felderFuerSpur, felderFuerSpur).compactMap { a, n in
            a.1 == n.1 ? nil : Feldaenderung(feld: n.0, vorher: a.1, nachher: n.1)
        }
    }
}

/// Einen Tag ändern — und die alte Fassung dabei behalten.
///
/// Solange der Tag noch nicht festgeschrieben ist, ist er ein Entwurf: ändern
/// ohne Grund ist in Ordnung. Danach ist jede Änderung eine Korrektur und
/// braucht eine Begründung, die stehen bleibt.
func kassenberichtKorrigieren(alt: Kassenbericht, neu: Kassenbericht,
                              grund: String) throws -> Kassenbericht {
    var ergebnis = neu
    ergebnis.id = alt.id                  // derselbe Tag bleibt derselbe Vorgang
    ergebnis.erstellt = alt.erstellt
    ergebnis.korrekturen = alt.korrekturen

    guard alt.festgeschrieben else {
        ergebnis.uebermittelt = nil       // Entwurf: frisch übermitteln
        return ergebnis
    }

    let aenderungen = neu.aenderungenGegen(alt)
    guard !aenderungen.isEmpty else { throw Kassenfehler.keineAenderung }
    let sauber = grund.trimmingCharacters(in: .whitespacesAndNewlines)
    guard sauber.count >= 3 else { throw Kassenfehler.grundFehlt }

    var spur = alt.korrekturen ?? []
    spur.append(Kassenkorrektur(grund: sauber, aenderungen: aenderungen))
    ergebnis.korrekturen = spur
    ergebnis.uebermittelt = nil           // korrigiertes Blatt geht neu raus
    return ergebnis
}

/// Tag-Schlüssel fürs Kassenbuch: sortierbar und zeitzonenfest.
enum KassenTag {
    static let kalender: Calendar = {
        var k = Calendar(identifier: .gregorian)
        k.locale = Locale(identifier: "de_DE")
        k.firstWeekday = 2   // Montag
        return k
    }()

    private static let schluesselFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = kalender
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static let anzeigeFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = kalender
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "EEEE, d. MMMM"
        return f
    }()

    static func schluessel(_ datum: Date) -> String {
        schluesselFormat.string(from: datum)
    }

    static func datum(_ schluessel: String) -> Date? {
        schluesselFormat.date(from: schluessel)
    }

    /// „Sonntag, 17. August" — für Überschriften.
    static func anzeige(_ schluessel: String) -> String {
        datum(schluessel).map { anzeigeFormat.string(from: $0) } ?? schluessel
    }
}
