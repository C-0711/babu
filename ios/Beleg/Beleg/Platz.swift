import Foundation

/// Der Platz: wie viel die Ablage trägt und was noch frei ist.
///
/// Entschieden am 10.10.2026: **Funktionen trennen die Stufen nie, nur der
/// Speicher.** Jede Stufe kann alles. Die ersten zehn Belege sind frei,
/// danach wählt die Nutzerin einen Platz.
///
/// Gerechnet wird das auf dem Server (`paket.py`) — hier steht nur, was er
/// sagt. Zwei Gründe: Die Sperre entscheidet ohnehin dort, und eine zweite
/// Rechnung auf dem Telefon liefe irgendwann auseinander.
struct PlatzStand: Codable, Equatable {
    /// Die gebuchte Stufe („klein", „mittel", „gross") oder nil im
    /// Freikontingent.
    let stufe: String?
    /// Bytes, die zur Verfügung stehen — nil, solange keine Stufe gebucht ist.
    let grenze: Int?
    let verbraucht: Int
    let voll: Bool
    let knapp: Bool
    let belege: Int
    /// Wie viele der zehn freien Belege noch übrig sind — nil mit Stufe.
    let freiOffen: Int?

    enum CodingKeys: String, CodingKey {
        case stufe, grenze, verbraucht, voll, knapp, belege
        case freiOffen = "frei_offen"
    }

    /// Wie weit der Balken steht (0…1). Im Freikontingent zählen Belege,
    /// mit Stufe die Bytes — dieselbe Unterscheidung wie auf dem Server.
    var anteil: Double {
        if let frei = freiOffen {
            return min(1, Double(PlatzStand.belegeFrei - frei) / Double(PlatzStand.belegeFrei))
        }
        guard let grenze, grenze > 0 else { return 0 }
        return min(1, Double(verbraucht) / Double(grenze))
    }

    static let belegeFrei = 10

    /// Wie viele freie Belege noch bleiben — oder nil, wenn es nichts Freies
    /// mehr gibt (Stufe gebucht, voll). Gezählt wird auch, was schon auf dem
    /// Telefon liegt: direkt nach dem ersten Foto zählt der Server oft noch 0,
    /// weil der Beleg aufs Hochladen wartet, und „noch 10 frei" wäre falsch.
    func freiNoch(belegeAufTelefon: Int) -> Int? {
        guard stufe == nil, !voll, let frei = freiOffen else { return nil }
        let noch = min(frei, PlatzStand.belegeFrei - belegeAufTelefon)
        return noch > 0 ? noch : nil
    }

    /// Ob das Angebot nach dem ersten Beleg jetzt kommt (Wunsch vom
    /// 22.10.2026): einmal je Betrieb, sobald der erste Beleg aufgenommen
    /// ist — nur für die Inhaberin eines Betriebs aus dem App Store, der noch
    /// keine Stufe hat. Ist der Platz voll, übernimmt das Angebot, das es
    /// dafür schon gibt.
    static func angebotNachErstemBeleg(_ platz: PlatzStand?, belegeAufTelefon: Int,
                                       schonGezeigt: Bool, inhaberin: Bool) -> Bool {
        guard !schonGezeigt, inhaberin, belegeAufTelefon >= 1,
              let platz else { return false }
        return platz.stufe == nil && !platz.voll
    }

    /// Die Zeile auf dem Knopf, der statt eines kleinen „Später" unter den
    /// Stufen steht: kostenlos weitermachen ist ein gleichwertiger Weg, kein
    /// versteckter.
    static func kostenlosText(_ noch: Int) -> String {
        "Erst kostenlos weiter – noch \(noch) \(noch == 1 ? "Beleg" : "Belege") frei"
    }

    /// Was der Nutzerin dazu gesagt wird — oder nil, wenn alles Platz hat.
    /// Dieselben Sätze wie `paket.text()` auf dem Server; sie stehen hier
    /// noch einmal, weil die App sie auch ohne Netz zeigen können muss.
    var hinweis: String? {
        if stufe == nil {
            if voll {
                return "Deine \(PlatzStand.belegeFrei) freien Belege sind "
                     + "abgelegt. Such dir einen Platz aus, dann geht es "
                     + "weiter — deine Belege bleiben, wo sie sind."
            }
            if knapp, let frei = freiOffen {
                return "Noch \(frei) \(frei == 1 ? "Beleg" : "Belege") frei."
            }
            return nil
        }
        if voll {
            return "Deine Ablage ist voll. Mit der nächsten Stufe hast du "
                 + "sofort wieder Luft — alles Abgelegte bleibt, wo es ist."
        }
        return knapp ? "Deine Ablage wird knapp." : nil
    }
}

/// Eine Stufe, wie der Server sie anbietet.
struct PlatzStufe: Codable, Equatable, Identifiable {
    let stufe: String
    let gb: Int
    /// Endpreis in Cent, wie Apple ihn zeigt (inklusive Umsatzsteuer).
    let cent: Int
    /// Die Produkt-Kennung im App Store.
    let apple: String

    var id: String { stufe }

    /// Wie viele Belege hier hineinpassen.
    ///
    /// Gerechnet mit **550 KB je Beleg** — Foto, Lesung und Beiakten, am
    /// 10.10.2026 am Bestand gemessen (538 KB im Schnitt je Foto bei
    /// Qualität 0,6 in voller Auflösung, dazu ~13 KB Lesung). Grob
    /// gerundet, weil eine genaue Zahl eine Genauigkeit vorgäbe, die es
    /// nicht gibt: ein Bon mit vier Zeilen ist kleiner als ein
    /// zweiseitiger Vertrag.
    var belegeText: String {
        let belege = Double(gb) * 1024 * 1024 / 550
        if belege >= 100_000 { return "rund \(Int(belege / 1000)) Tausend Belege" }
        if belege >= 1000 { return "rund \(Int((belege / 500).rounded()) * 500) Belege" }
        return "rund \(Int(belege)) Belege"
    }

    /// „9,99 €" — die Fassung für den Fall, dass StoreKit den Preis nicht
    /// liefert (kein Netz, Produkt noch nicht freigegeben). Der Preis von
    /// Apple hat immer Vorrang: er steht in der Währung des Landes.
    var preisNotfalls: String {
        String(format: "%d,%02d €", cent / 100, cent % 100)
    }
}
