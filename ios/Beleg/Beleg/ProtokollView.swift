import SwiftUI

/// Das Leseprotokoll — was babu auf dem Beleg gelesen hat, vollständig.
///
/// Der Server schreibt zu jedem Beleg eine Markdown-Datei: jede erkannte
/// Zeile mit ihrer Erkennungsgüte, jeder Wert mit der Zeile, aus der er
/// stammt, die Steuerrechnung als Rechnung. Hier wird sie gesetzt.
///
/// Warum nicht `AttributedString(markdown:)`: das kann Fett und Kursiv, aber
/// keine Tabellen — und das Protokoll besteht zur Hälfte aus Tabellen. Ein
/// eigener kleiner Setzer ist hier weniger Aufwand als der Umweg über eine
/// Webansicht, und er sieht aus wie der Rest der App.
struct ProtokollView: View {
    let stamm: String
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var text: String?
    @State private var hinweis: String?
    @State private var laedt = false
    @State private var neuGelesen = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let text {
                        ForEach(Array(Protokollsatz.bloecke(aus: text).enumerated()),
                                id: \.offset) { _, block in
                            blockAnsicht(block)
                        }
                    } else if laedt {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("Protokoll wird geholt …")
                                .font(.footnote)
                                .foregroundStyle(GC.muted)
                        }
                    } else if let hinweis {
                        Text(hinweis)
                            .font(.footnote)
                            .foregroundStyle(GC.desc)
                    }

                    if neuGelesen {
                        Label("babu liest den Beleg gerade noch einmal. In etwa "
                              + "einer halben Minute ist das neue Protokoll da.",
                              systemImage: "arrow.clockwise")
                            .font(.footnote)
                            .foregroundStyle(GC.accent)
                    } else if text != nil || hinweis != nil {
                        Button {
                            Task { await neuLesen() }
                        } label: {
                            Label("Noch einmal lesen lassen", systemImage: "arrow.clockwise")
                                .font(.footnote)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .padding(.top, 4)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
            }
            .background(GC.canvas)
            .navigationTitle("Was babu gelesen hat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { dismiss() }
                }
            }
            .task { await laden() }
        }
    }

    // MARK: - Die einzelnen Blöcke

    @ViewBuilder
    private func blockAnsicht(_ block: Protokollsatz.Block) -> some View {
        switch block {
        case .titel(let t):
            Text(t)
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
        case .abschnitt(let t):
            Text(t.uppercased())
                .font(.caption2.monospaced())
                .kerning(1)
                .foregroundStyle(GC.muted)
                .padding(.top, 6)
        case .hervorgehoben(let t):
            Text(t)
                .font(.callout.weight(.medium))
                .foregroundStyle(GC.fg)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 10))
        case .absatz(let t):
            Text(t)
                .font(.footnote)
                .foregroundStyle(GC.desc)
        case .punkt(let t):
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Text("·").foregroundStyle(GC.muted)
                Text(t).font(.footnote).foregroundStyle(GC.desc)
            }
        case .zitat(let t):
            Text(t)
                .font(.footnote)
                .foregroundStyle(GC.warn)
                .padding(.leading, 10)
                .overlay(alignment: .leading) {
                    Rectangle().fill(GC.warn.opacity(0.5)).frame(width: 2)
                }
        case .rechnung(let zeilen):
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(zeilen.enumerated()), id: \.offset) { _, z in
                    Text(z).font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(GC.body)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(GC.desk, in: RoundedRectangle(cornerRadius: 10))
        case .tabelle(let kopf, let zeilen):
            tabelle(kopf: kopf, zeilen: zeilen)
        }
    }

    /// Tabellen werden zu Zeilen gesetzt, nicht zu Spalten: auf einem Telefon
    /// wird eine vierspaltige Tabelle sonst zu Konfetti.
    @ViewBuilder
    private func tabelle(kopf: [String], zeilen: [[String]]) -> some View {
        VStack(spacing: 0) {
            ForEach(Array(zeilen.enumerated()), id: \.offset) { i, zeile in
                let felder = zip(kopf, zeile).filter {
                    !$0.1.isEmpty && $0.1 != "&nbsp;"
                }
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(Array(felder.enumerated()), id: \.offset) { j, paar in
                        if j == 0 {
                            Text(paar.1)
                                .font(.footnote.weight(.medium))
                                .foregroundStyle(GC.fg)
                        } else {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                if !paar.0.isEmpty {
                                    Text(paar.0)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(GC.muted)
                                        .frame(width: 62, alignment: .leading)
                                }
                                Text(paar.1)
                                    .font(.caption)
                                    .foregroundStyle(GC.body)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 7)
                .padding(.horizontal, 10)
                .background(i.isMultiple(of: 2) ? GC.desk : Color.clear)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Holen

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            hinweis = "Für das Protokoll bitte die Belegbox verbinden (Export → Zahnrad)."
            return
        }
        laedt = true
        defer { laedt = false }
        switch await AblageService.protokollAbrufen(stamm: stamm, basis: url, pat: pat) {
        case .fertig(let t):
            text = t
            hinweis = nil
        case .nochNicht:
            hinweis = "Zu diesem Beleg gibt es noch kein Protokoll — er wurde "
                + "gelesen, bevor es das gab. Einmal neu lesen lassen legt eines an."
        case .zugangFehlt:
            hinweis = "Der Zugang zur Belegbox ist abgelaufen — einmal neu verbinden."
        default:
            hinweis = "Gerade keine Verbindung — später noch einmal versuchen."
        }
    }

    private func neuLesen() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        laedt = true
        defer { laedt = false }
        if await AblageService.neuLesenAnstossen(stamm: stamm, basis: url, pat: pat) {
            neuGelesen = true
            text = nil
            hinweis = nil
        } else {
            hinweis = "Das hat gerade nicht geklappt — später noch einmal versuchen."
        }
    }
}
