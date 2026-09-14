import SwiftUI

/// Die Karte auf der Startseite — nur für den Anfang, nicht für die Dauer.
///
/// Eine leere App sagt nicht, was zu tun ist. Diese Karte sagt es, und dann
/// geht sie: zwei Zeilen, verbinden und einmal auslösen. Alles Weitere —
/// Betriebsangaben, Steuernummer, Kassenbuch — lernt babu aus dem, was
/// fotografiert wird, und steht im Profil. Eine Liste, die oben stehen
/// bleibt, bis ein Mensch sie abgearbeitet hat, ist eine Mahnung; sie
/// misst ihn an dem, was ihm fehlt, statt an dem, was schon da ist.
struct EinrichtungsKarte: View {
    let schritte: [Einrichtungsschritt]
    var wahl: (Einrichtungsziel) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Dein Anfang")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            Text("Zwei Dinge, dann läuft es. Tipp eine Zeile an, "
                 + "dann geht es dort weiter.")
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

            Text("Alles andere — deine Angaben, deine Steuernummer, deine "
                 + "Bankverbindung — liest babu nach und nach aus dem heraus, "
                 + "was du fotografierst.")
                .font(.caption2)
                .foregroundStyle(GC.muted)
                .padding(.top, 10)
                .fixedSize(horizontal: false, vertical: true)
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

/// „Deine Ablage wird noch eingerichtet" — der Zustand jedes neuen Betriebs
/// zwischen Anmeldung und dem Handgriff, der seine Ablage anlegt. Keine
/// Fehlermeldung: fotografieren geht, alles wartet sicher auf dem Telefon
/// und geht von selbst los, sobald die Ablage da ist.
struct AblageWartetKarte: View {
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "tray.and.arrow.down")
                .font(.title3)
                .foregroundStyle(GC.accent)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 4) {
                Text("Deine Ablage wird noch eingerichtet")
                    .font(.headline)
                    .fontDesign(.serif)
                    .foregroundStyle(GC.fg)
                Text("Fotografieren kannst du schon jetzt — deine Belege warten sicher auf dem Telefon und gehen von selbst los, sobald alles bereit ist. babu meldet sich.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 14))
        .accessibilityElement(children: .combine)
    }
}
