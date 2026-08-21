import SwiftUI
import UserNotifications

/// Was babu von sich aus sagt: Fristen, Kündigungen, offene Rechnungen,
/// der fertige Monat. Bisher musste die Inhaberin die App öffnen, um davon
/// zu erfahren — jetzt kommt es zu ihr.
struct Meldung: Identifiable, Equatable {
    var schluessel: String
    var art: String          // frist · vertrag · rechnung · abschluss
    var titel: String
    var text: String
    var dringend: Bool

    var id: String { schluessel }

    var symbol: String {
        switch art {
        case "frist": return "calendar.badge.exclamationmark"
        case "vertrag": return "shippingbox"
        case "rechnung": return "eurosign.circle"
        default: return "chart.bar.doc.horizontal"
        }
    }

    init?(json: [String: Any]) {
        guard let schluessel = json["schluessel"] as? String,
              let titel = json["titel"] as? String else { return nil }
        self.schluessel = schluessel
        self.titel = titel
        art = json["art"] as? String ?? "frist"
        text = json["text"] as? String ?? ""
        dringend = json["dringend"] as? Bool ?? false
    }
}

/// Erinnerungen auf dem Gerät. Bewusst LOKAL und nicht über einen
/// Push-Dienst: dafür bräuchte es ein Zertifikat und eine Geräte-Verwaltung,
/// die es nicht gibt. Der Preis dafür steht in `hinweis`.
enum Erinnerungen {

    static let hinweis = "Erinnerungen legt babu auf deinem Telefon an, "
        + "während du die App benutzt."

    /// Einmal fragen — und nie wieder, wenn sie Nein gesagt hat.
    static func erlaubnisHolen() async -> Bool {
        let zentrale = UNUserNotificationCenter.current()
        let stand = await zentrale.notificationSettings()
        switch stand.authorizationStatus {
        case .authorized, .provisional: return true
        case .denied: return false
        default:
            return (try? await zentrale.requestAuthorization(
                options: [.alert, .sound])) ?? false
        }
    }

    /// Aus den Meldungen Erinnerungen machen. Der Schlüssel ist die Kennung —
    /// dieselbe Meldung kommt dadurch nie zweimal aufs Telefon.
    static func planen(_ meldungen: [Meldung]) async {
        // Erst fragen, wenn es wirklich etwas zu erinnern gibt. Wer beim
        // ersten Öffnen nach Mitteilungen gefragt wird, ohne dass etwas
        // ansteht, sagt Nein — und hört dann auch nichts, wenn es zählt.
        guard !meldungen.isEmpty, await erlaubnisHolen() else { return }
        let zentrale = UNUserNotificationCenter.current()
        let offen = await zentrale.pendingNotificationRequests()
        let schonGeplant = Set(offen.map(\.identifier))

        for meldung in meldungen where !schonGeplant.contains(meldung.schluessel) {
            let inhalt = UNMutableNotificationContent()
            inhalt.title = meldung.titel
            inhalt.body = meldung.text
            inhalt.sound = meldung.dringend ? .default : nil
            // Nicht sofort: um 9 Uhr, wenn der Salon aufmacht — mitten in
            // einer Behandlung will niemand ans Telefon.
            var wann = DateComponents()
            wann.hour = 9
            wann.minute = 0
            let ausloeser = UNCalendarNotificationTrigger(dateMatching: wann,
                                                          repeats: false)
            try? await zentrale.add(UNNotificationRequest(
                identifier: meldung.schluessel, content: inhalt,
                trigger: ausloeser))
        }
    }
}

/// Die Meldungen als Karten — dort, wo die Inhaberin ohnehin hinschaut.
struct MeldungenAbschnitt: View {
    @EnvironmentObject var store: AppStore
    @State private var meldungen: [Meldung] = []

    var body: some View {
        Group {
            if !meldungen.isEmpty {
                Section {
                    ForEach(meldungen) { m in
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: m.symbol)
                                .font(.body)
                                .foregroundStyle(m.dringend ? GC.warn : GC.accent)
                                .frame(width: 24)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(m.titel)
                                    .font(.body.weight(.medium))
                                    .foregroundStyle(GC.fg)
                                Text(m.text)
                                    .font(.caption)
                                    .foregroundStyle(GC.desc)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .padding(.vertical, 3)
                    }
                } header: {
                    Text("Das steht an")
                }
            }
        }
        .task { await laden() }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        meldungen = await AblageService.meldungenLaden(basis: url, pat: pat)
        await Erinnerungen.planen(meldungen)
    }
}
