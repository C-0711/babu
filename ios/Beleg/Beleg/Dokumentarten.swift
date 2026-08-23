import SwiftUI

/// Was für ein Papier ist das — und wo gehört es hin?
///
/// Der Reiter hieß „Belege", und alles, was fotografiert wurde, hieß Beleg.
/// Tatsächlich fotografiert die Nutzerin auch Kontoauszüge, den Mietvertrag
/// und Post vom Amt. Der Server erkennt das längst beim Einreichen
/// (`einsortieren.py`) und legt jede Art in ihren eigenen Ordner; die App
/// bekommt die Art in der Antwort zurück und merkt sie sich als
/// `abgelegtAls`. Angezeigt wurde sie nur nie.
///
/// Hier steht die Übersetzung: derselbe Schlüssel wie auf dem Server, dazu
/// ein Name, den man liest, und ein Symbol in der Strichsprache der App.
enum Dokumentart: String, CaseIterable, Identifiable {
    case beleg
    case kontoauszug
    case vertrag
    case behoerde

    var id: String { rawValue }

    /// Wie es im Reiter steht — Mehrzahl, weil es eine Sammlung ist.
    var name: String {
        switch self {
        case .beleg:       return "Belege"
        case .kontoauszug: return "Kontoauszüge"
        case .vertrag:     return "Verträge"
        case .behoerde:    return "Post vom Amt"
        }
    }

    /// Einzahl — für Sätze über ein einzelnes Stück.
    var einzahl: String {
        switch self {
        case .beleg:       return "Beleg"
        case .kontoauszug: return "Kontoauszug"
        case .vertrag:     return "Vertrag"
        case .behoerde:    return "Brief vom Amt"
        }
    }

    var symbol: String {
        switch self {
        case .beleg:       return "doc.text"
        case .kontoauszug: return "building.columns"
        case .vertrag:     return "doc.plaintext"
        case .behoerde:    return "envelope"
        }
    }

    /// Was dasteht, wenn in dieser Art noch nichts liegt.
    var leerSatz: String {
        switch self {
        case .beleg:
            return "Noch keine Belege. Halt einfach drauf — den Rest macht babu."
        case .kontoauszug:
            return "Noch keine Kontoauszüge. Fotografier oder lade einen hoch, "
                 + "dann gleicht babu deine Zahlungen mit den Belegen ab."
        case .vertrag:
            return "Noch keine Verträge. Miete, Versicherung, Leasing — babu "
                 + "merkt sich Laufzeit und Kündigungsfrist."
        case .behoerde:
            return "Noch keine Post vom Amt. Bescheide und Schreiben landen "
                 + "hier, sobald du sie fotografierst."
        }
    }

    /// Die Art, die der Server einem Dokument gegeben hat.
    ///
    /// Was noch nicht abgelegt ist, kennt seine Art noch nicht — dann gilt
    /// Beleg. Das ist auch die Voreinstellung des Servers und der häufigste
    /// Fall; ein Bon, der kurz unter „Belege" steht und später umzieht, ist
    /// harmloser als einer, der nirgends auftaucht.
    static func von(_ beleg: Beleg) -> Dokumentart {
        Dokumentart(rawValue: beleg.abgelegtAls ?? "") ?? .beleg
    }
}

/// Liste oder Vorschaubilder — die Nutzerin entscheidet.
///
/// Eine Liste zeigt Zahlen und Zustand, ein Blätterfeld zeigt das Papier.
/// Wer einen bestimmten Betrag sucht, will die Liste; wer „den grünen
/// Zettel von neulich" sucht, will das Bild. Beides ist richtig, deshalb
/// bleibt die Wahl gespeichert.
enum Dokumentansicht: String {
    case liste
    case blaetter

    var symbol: String { self == .liste ? "square.grid.2x2" : "list.bullet" }
    var name: String { self == .liste ? "Als Bilder" : "Als Liste" }
    var andere: Dokumentansicht { self == .liste ? .blaetter : .liste }
}
