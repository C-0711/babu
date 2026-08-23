import Foundation

/// Ein Name für die Sache. Für Nina ist die **Kasse** die Schublade und
/// das **Kassenbuch** das Buch darüber — die App führt das Buch. Vorher
/// stand mal das eine, mal das andere da; hier steht, welches Wort wann
/// gilt, damit es nicht wieder auseinanderläuft.
enum Kassenwort {
    static let buch = "Kassenbuch"
    static let schublade = "Kasse"
    /// Eingetragen wird immer ins Buch.
    static let eintragen = "Ins Kassenbuch eintragen"
    static let nachtragen = "Im Kassenbuch nachtragen"
    static let aendern = "Eintrag ändern"
    /// Gestimmt hat die Schublade — das ist der Abgleich mit dem, was
    /// abends wirklich drin liegt.
    static let stimmt = "Deine Kasse stimmt."
}

/// Wofür Geld die Kasse verlassen hat.
///
/// Bisher hieß alles „Entnahme". Steuerlich sind das drei völlig
/// verschiedene Dinge, und wer sie einmal in einen Topf geworfen hat,
/// kann sie später nicht mehr auseinandersortieren. Deshalb fragt die
/// App danach — mit drei festen Möglichkeiten statt eines Freitextes,
/// den hinterher niemand deuten kann.
enum Entnahmezweck: String, Codable, CaseIterable, Identifiable {
    /// Geld geht ins Private. Kein Aufwand.
    case privat
    /// Vorschuss ans Team: eine Forderung, die mit dem Lohn verrechnet
    /// wird. Weder Entnahme noch Aufwand.
    case vorschuss
    /// Nina hat privat für den Salon bezahlt und holt es sich zurück.
    /// Das ist Aufwand.
    case auslage

    var id: String { rawValue }

    /// Ninas Sprache — kein Wort aus dem Steuerrecht.
    var knopf: String {
        switch self {
        case .privat:    return "Für mich privat"
        case .vorschuss: return "Vorschuss fürs Team"
        case .auslage:   return "Ich hatte ausgelegt"
        }
    }

    var erklaerung: String {
        switch self {
        case .privat:
            return "Du nimmst Geld aus der Kasse für dich."
        case .vorschuss:
            return "Jemand aus dem Team bekommt Geld vorab — es wird "
                 + "später vom Lohn abgezogen."
        case .auslage:
            return "Du hast etwas für den Salon von deinem eigenen Geld "
                 + "bezahlt und holst es dir jetzt zurück."
        }
    }

    /// Nur die erstattete Auslage ist ein Betriebsausgabe-Posten. Der
    /// Vorschuss ist eine Forderung, die Privatentnahme gar nichts.
    var istAufwand: Bool { self == .auslage }

    var pfad: WritableKeyPath<Kassenbericht, Double> {
        switch self {
        case .privat:    return \.privatentnahmen
        case .vorschuss: return \.vorschussTeam
        case .auslage:   return \.auslagenErstattet
        }
    }
}

/// Wer wieviel Trinkgeld bekommen hat. Nicht für die Steuer der
/// Empfängerin — das ist steuerfrei (§ 3 Nr. 51 EStG) — sondern damit bei
/// einer Kassenprüfung erklärbar bleibt, warum Geld die Schublade
/// verlassen hat.
struct Trinkgeldanteil: Codable, Identifiable, Equatable {
    var id = UUID()
    var name: String
    var betrag: Double
}

/// Ein Tages-Kassenbericht — bewusst NUR Tagessummen, exakt wie das
/// Papier-Formular der offenen Ladenkasse (Bestand Vortag, Einnahmen,
/// Ausgaben, gezählter Bestand). Es werden KEINE einzelnen Zahlvorgänge
/// erfasst und keine Zahlung abgewickelt — die App bleibt damit
/// Kassenbuch-Unterstützung und wird kein elektronisches
/// Aufzeichnungssystem mit Kassenfunktion (KassenSichV/§146a-AO-Grenze).
/// Auch die Zahlart „Gutschein" ist deshalb eine Tagessumme und kein
/// einzelner Verkaufsvorgang.
struct Kassenbericht: Codable, Identifiable, Equatable {
    var id = UUID()
    var datum: String              // "2026-08-17" — genau ein Bericht pro Tag
    var bestandVortag = 0.0
    var einnahmenBar = 0.0
    // Verkaufte Gutscheine: Geld kommt in die Schublade UND der Erlös ist
    // realisiert (Einzweck-Gutschein — der Steuersatz steht schon fest).
    // Zählt getrennt von `einnahmenBar`, damit das Monatsende beides
    // auseinanderhalten kann.
    var gutscheinVerkauf = 0.0
    var privateinlagen = 0.0
    var barabhebungBank = 0.0
    var ecZahlungen = 0.0
    // Trinkgeld, das mit dem Kartenumsatz aufs Geschäftskonto kam. Kein
    // Umsatz — es gehört dem Salon nicht. Liegt auch nicht in der Kasse.
    var trinkgeldKarte = 0.0
    // Eingelöste Gutscheine: KEINE neue Einnahme — das Geld kam schon beim
    // Verkauf des Gutscheins in die Kasse. Wird nur für den Tagesumsatz
    // ausgewiesen, nicht in den Kassenbestand gerechnet.
    var gutscheineEingeloest = 0.0
    // Team-Trinkgeld, bar aus der Schublade ausgezahlt: mindert den
    // Bestand, ist aber kein Aufwand — durchlaufender Posten.
    var trinkgeldTeamEC = 0.0
    var trinkgeldVerteilt: [Trinkgeldanteil] = []
    var sonstigeAusgaben = 0.0
    var privatentnahmen = 0.0
    var vorschussTeam = 0.0        // Forderung, wird mit dem Lohn verrechnet
    var auslagenErstattet = 0.0    // Nina hatte ausgelegt — Aufwand
    var einzahlungBank = 0.0
    var gezaehltSchluss = 0.0
    var erstellt = Date()
    // Optional, damit ältere zustand.json weiter dekodiert (Migration).
    var differenzGrund: String?    // z. B. „10 € Wechselgeld verzählt"
    var sonstigeNotiz: String?     // wofür die sonstige Ausgabe war
    var uebermittelt: Date?        // Tagesblatt liegt in der Belegbox
    /// Korrekturen, die nach dem Festschreiben nötig waren. Nichts wird
    /// überschrieben — was geändert wurde, steht hier mit Grund und Zeitpunkt.
    var korrekturen: [Kassenkorrektur]?

    var summeEinnahmen: Double {
        bestandVortag + einnahmenBar + gutscheinVerkauf
            + privateinlagen + barabhebungBank
    }
    var summeAusgaben: Double {
        trinkgeldTeamEC + sonstigeAusgaben + summeEntnahmen + einzahlungBank
    }
    /// Alles, was aus einem der drei Entnahmegründe die Kasse verlässt.
    var summeEntnahmen: Double {
        Entnahmezweck.allCases.reduce(0) { $0 + self[keyPath: $1.pfad] }
    }
    /// Was der Salon heute bar verbraucht hat. Vorschuss und
    /// Privatentnahme gehören ausdrücklich NICHT dazu.
    var barAufwand: Double {
        sonstigeAusgaben
            + Entnahmezweck.allCases.filter(\.istAufwand)
                .reduce(0) { $0 + self[keyPath: $1.pfad] }
    }
    var rechnerischerBestand: Double { summeEinnahmen - summeAusgaben }
    var differenz: Double { gezaehltSchluss - rechnerischerBestand }
    /// Umsatz des Tages. Eingelöste Gutscheine fehlen hier mit Absicht —
    /// dieser Erlös wurde beim Verkauf gebucht. Trinkgeld fehlt, weil es
    /// kein Umsatz ist.
    var tagesumsatz: Double { einnahmenBar + ecZahlungen + gutscheinVerkauf }
    /// Was auf dem Tagesabschluss des Kartenlesers steht — Umsatz und
    /// Trinkgeld zusammen. Nur zum Vergleichen, nicht zum Buchen.
    var kartenterminalSumme: Double { ecZahlungen + trinkgeldKarte }
    /// Weitergegebenes Trinkgeld — durchlaufender Posten, kein Umsatz.
    var trinkgeldTeam: Double { trinkgeldTeamEC }
    /// Was von dem Karten-Trinkgeld bei Nina bleibt: Betriebseinnahme.
    /// Wird nie negativ — an manchen Tagen wird mehr ausgezahlt, als
    /// hereinkam, weil gestriges Trinkgeld nachgereicht wird.
    var trinkgeldInhaberin: Double { max(0, trinkgeldKarte - trinkgeldTeamEC) }
    var summeTrinkgeldVerteilt: Double {
        trinkgeldVerteilt.reduce(0) { $0 + $1.betrag }
    }
    /// Ist belegt, wohin das ausgezahlte Trinkgeld gegangen ist?
    var trinkgeldSpurVollstaendig: Bool {
        abs(summeTrinkgeldVerteilt - trinkgeldTeamEC) < 0.01
    }
    var kasseStimmt: Bool { abs(differenz) < 0.01 }

    /// Festgeschrieben ist ein Tag, sobald sein Blatt in der Belegbox liegt.
    /// Ab da ist er ein Beleg, kein Entwurf mehr.
    var festgeschrieben: Bool { uebermittelt != nil }

    init(datum: String) {
        self.datum = datum
    }

    /// Von Hand, weil Swift beim erzeugten Decoder die Vorgabewerte NICHT
    /// verwendet: ein fehlender Schlüssel wirft. `zustand.json` wird mit
    /// `try?` gelesen — ein einziges neues Pflichtfeld hätte also den
    /// GANZEN gespeicherten Zustand gelöscht, Belege inbegriffen. Jedes
    /// Feld muss deshalb fehlen dürfen.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func zahl(_ k: CodingKeys) throws -> Double {
            try c.decodeIfPresent(Double.self, forKey: k) ?? 0
        }
        id = try c.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        datum = try c.decodeIfPresent(String.self, forKey: .datum) ?? ""
        bestandVortag = try zahl(.bestandVortag)
        einnahmenBar = try zahl(.einnahmenBar)
        gutscheinVerkauf = try zahl(.gutscheinVerkauf)
        privateinlagen = try zahl(.privateinlagen)
        barabhebungBank = try zahl(.barabhebungBank)
        ecZahlungen = try zahl(.ecZahlungen)
        trinkgeldKarte = try zahl(.trinkgeldKarte)
        gutscheineEingeloest = try zahl(.gutscheineEingeloest)
        trinkgeldTeamEC = try zahl(.trinkgeldTeamEC)
        trinkgeldVerteilt = try c.decodeIfPresent([Trinkgeldanteil].self,
                                                  forKey: .trinkgeldVerteilt) ?? []
        sonstigeAusgaben = try zahl(.sonstigeAusgaben)
        privatentnahmen = try zahl(.privatentnahmen)
        vorschussTeam = try zahl(.vorschussTeam)
        auslagenErstattet = try zahl(.auslagenErstattet)
        einzahlungBank = try zahl(.einzahlungBank)
        gezaehltSchluss = try zahl(.gezaehltSchluss)
        erstellt = try c.decodeIfPresent(Date.self, forKey: .erstellt) ?? Date()
        differenzGrund = try c.decodeIfPresent(String.self, forKey: .differenzGrund)
        sonstigeNotiz = try c.decodeIfPresent(String.self, forKey: .sonstigeNotiz)
        uebermittelt = try c.decodeIfPresent(Date.self, forKey: .uebermittelt)
        korrekturen = try c.decodeIfPresent([Kassenkorrektur].self,
                                            forKey: .korrekturen)
    }
}

/// Wo das Tagesblatt gerade liegt — und was als Nächstes damit passiert.
///
/// „Wie wird die Kasse übermittelt?" war bisher nirgends beantwortet;
/// sichtbar war nur ein Haken. Ein Haken sagt nicht, wohin etwas gegangen
/// ist und wann.
enum Uebermittlung: Equatable {
    /// Liegt nur auf dem Telefon — es fehlt die Verbindung.
    case offen
    /// Liegt seit diesem Zeitpunkt in der Belegbox.
    case inBelegbox(Date)

    static func fuer(_ bericht: Kassenbericht) -> Uebermittlung {
        bericht.uebermittelt.map { .inBelegbox($0) } ?? .offen
    }

    private static let zeitpunkt: DateFormatter = {
        let f = DateFormatter()
        f.calendar = KassenTag.kalender
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "d. MMMM yyyy, HH:mm"
        return f
    }()

    var satz: String {
        switch self {
        case .offen:
            return "Liegt noch auf deinem Telefon. Sobald du Verbindung "
                 + "hast, geht das Tagesblatt von allein in deine Belegbox."
        case .inBelegbox(let wann):
            return "Am \(Uebermittlung.zeitpunkt.string(from: wann)) in "
                 + "deiner Belegbox abgelegt — dort liegt es sicher."
        }
    }

    var erledigt: Bool {
        if case .inBelegbox = self { return true }
        return false
    }

    /// Was danach kommt. Steht neben dem Satz oben, damit klar ist, dass
    /// mit dem Ablegen noch nicht Schluss ist.
    static let monatsende = "Am Monatsende zählt babu die Tagesblätter "
        + "zusammen — daraus wird die Auswertung für deine Steuerberatung."
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
