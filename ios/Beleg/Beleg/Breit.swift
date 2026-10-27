import SwiftUI

/// Breite Größenklasse (iPad, aufgeklapptes iPhone Duo, 27.10.2026): Formulare
/// stehen mittig mit Höchstbreite, Blätter kommen in Formulargröße statt
/// bildschirmfüllend. Auf dem iPhone (compact) ändert beides nichts — jede
/// breite Variante ist ein zusätzlicher Zweig, kein Umbau.
private struct BreiteSpalte: ViewModifier {
    @Environment(\.horizontalSizeClass) private var sizeClass
    let max: CGFloat

    func body(content: Content) -> some View {
        if sizeClass == .regular {
            content
                .frame(maxWidth: max)
                .frame(maxWidth: .infinity)
        } else {
            content
        }
    }
}

extension View {
    /// Mittig, höchstens `max` Punkte breit — nur in der breiten Größenklasse.
    /// Vor `warmerGrund()` setzen, damit der Grund die ganze Breite füllt.
    func breiteSpalte(max: CGFloat = 640) -> some View {
        modifier(BreiteSpalte(max: max))
    }

    /// Ein Blatt in Formulargröße (iPad) statt bildschirmfüllend; auf dem
    /// iPhone wirkungslos. Vor iOS 18 gibt es die Größe nicht — dann wie bisher.
    @ViewBuilder
    func formblatt() -> some View {
        if #available(iOS 18, *) {
            presentationSizing(.form)
        } else {
            self
        }
    }
}
