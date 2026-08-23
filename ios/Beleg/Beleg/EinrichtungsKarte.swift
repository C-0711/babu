import SwiftUI

/// Die Karte auf der Startseite, solange beim Einrichten noch etwas fehlt.
///
/// Eine leere App mit fünf Reitern sagt nicht, was zu tun ist. Diese Karte
/// sagt es — in fünf Zeilen, jede mit ihrem echten Stand dahinter, und jede
/// führt an die Stelle, an der es weitergeht. Ist alles erledigt, ist sie weg.
struct EinrichtungsKarte: View {
    let schritte: [Einrichtungsschritt]
    /// Ohne Verbindung lässt sich über zwei Zeilen nichts sagen — dann gehört
    /// ein Satz darunter, der das erklärt, statt eines geratenen „offen".
    let kontoVerbunden: Bool
    var wahl: (Einrichtungsziel) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Dein Anfang")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            Text("Das steht noch an. Tipp eine Zeile an, dann geht es dort weiter.")
                .font(.caption)
                .foregroundStyle(GC.desc)
                .padding(.top, 3)
                .padding(.bottom, 6)

            ForEach(schritte) { schritt in
                zeile(schritt)
                if schritt.id != schritte.last?.id {
                    Rectangle().fill(GC.linie).frame(height: 1)
                }
            }

            if !kontoVerbunden {
                Text("Was zu deinem Betrieb gehört, liegt in deinem babu-Konto. "
                     + "Sobald du verbunden bist, steht es hier.")
                    .font(.caption2)
                    .foregroundStyle(GC.muted)
                    .padding(.top, 10)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .gcCard()
    }

    private func farbe(_ stand: Einrichtungsschritt.Stand) -> Color {
        switch stand {
        case .erledigt: return GC.ok
        case .teilweise: return GC.warn
        case .offen, .unbekannt: return GC.muted
        }
    }

    private func zeile(_ schritt: Einrichtungsschritt) -> some View {
        Button {
            wahl(schritt.ziel)
        } label: {
            HStack(spacing: 10) {
                Text(schritt.titel)
                    .font(.subheadline)
                    .foregroundStyle(schritt.istErledigt ? GC.desc : GC.fg)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                Spacer(minLength: 8)
                Text(schritt.standText)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(farbe(schritt.stand))
                // Der Pfeil steht nur da, wo es wirklich weitergeht — sonst
                // sähen fünf erledigte Zeilen aus wie fünf Aufgaben.
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(GC.muted)
                    .opacity(schritt.istErledigt ? 0 : 1)
            }
            .contentShape(Rectangle())
            .padding(.vertical, 10)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(schritt.titel), \(gesprochen(schritt.stand))")
    }

    /// „✓" und „—" liest die Sprachausgabe nicht vor — hier steht es in Worten.
    private func gesprochen(_ stand: Einrichtungsschritt.Stand) -> String {
        switch stand {
        case .erledigt: return "erledigt"
        case .offen: return "offen"
        case .teilweise(let fertig, let gesamt): return "\(fertig) von \(gesamt)"
        case .unbekannt: return "noch nicht bekannt"
        }
    }
}
