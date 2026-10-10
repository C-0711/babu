import SwiftUI

/// Ein Streifen, der sagt, wie viel Platz noch ist — und sonst schweigt.
///
/// Sichtbar wird er nur, wenn es etwas zu sagen gibt: in den letzten drei
/// freien Belegen, über der Warnschwelle (90 %) oder wenn der Platz voll
/// ist. Solange reichlich Platz da ist, zeigt die App nichts davon — ein
/// Balken, der immer zu sehen ist, erzieht zum Wegsehen.
///
/// Bei jedem Konto, das nicht über den App Store gekommen ist, ist
/// `store.platz` nil und der Streifen gibt nichts zurück.
struct PlatzStreifen: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        if let p = store.platz, p.voll || p.knapp {
            Button {
                store.zeigePlatz = true
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: p.voll ? "tray.full.fill" : "tray.fill")
                        .foregroundStyle(p.voll ? GC.warn : GC.accent)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(satz(p))
                            .font(.footnote.weight(.medium))
                            .foregroundStyle(GC.fg)
                            .multilineTextAlignment(.leading)
                        balken(p)
                    }
                    Spacer(minLength: 4)
                    Text(p.voll ? "Platz nehmen" : "Mehr")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(GC.accent)
                }
                .padding(12)
                .background(p.voll ? GC.warn.opacity(0.08) : GC.accentSubtle,
                            in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
        }
    }

    /// Im Freikontingent zählen Belege, mit Stufe die Bytes — dieselbe
    /// Unterscheidung wie auf dem Server. „Noch 3 Belege frei" versteht
    /// jeder; „noch 50 MB" niemand.
    private func satz(_ p: PlatzStand) -> String {
        if let frei = p.freiOffen {
            if frei == 0 {
                return "Deine \(PlatzStand.belegeFrei) freien Belege sind abgelegt."
            }
            return "Noch \(frei) \(frei == 1 ? "Beleg" : "Belege") frei."
        }
        if p.voll { return "Dein Platz ist voll." }
        return "Dein Platz wird knapp."
    }

    private func balken(_ p: PlatzStand) -> some View {
        GeometryReader { raum in
            ZStack(alignment: .leading) {
                Capsule().fill(GC.linie)
                Capsule()
                    .fill(p.voll ? GC.warn : GC.accent)
                    .frame(width: max(3, raum.size.width * p.anteil))
            }
        }
        .frame(height: 4)
    }
}
