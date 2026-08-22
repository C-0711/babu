import SwiftUI

/// Ein Beleg, in den man hineinsehen kann.
///
/// Belege sind klein gedruckt. Ein Kassenbon auf einem Telefonbildschirm ist
/// an der Stelle, auf die es ankommt — die Summe, der Steuersatz, die
/// Belegnummer —, oft nur ein paar Pixel hoch. Wer prüfen soll, ob babu
/// richtig gelesen hat, muss das Original lesen können; sonst bleibt nur
/// Glauben.
///
/// Deshalb: zwei Finger zum Vergrößern, Doppeltippen für schnell hin und
/// zurück, ziehen zum Verschieben. Beim Loslassen federt es in die Grenzen
/// zurück, damit der Beleg nie aus dem Bild rutscht und verloren wirkt.
struct ZoombaresBild<Auflage: View>: View {
    let bild: UIImage
    var maxFaktor: CGFloat = 6
    /// Wird über dem Bild gezeichnet und mitvergrößert — z. B. die grünen
    /// Markierungen der erkannten Felder.
    @ViewBuilder var auflage: (CGSize) -> Auflage

    @State private var faktor: CGFloat = 1
    @State private var faktorBeimGriff: CGFloat = 1
    @State private var versatz: CGSize = .zero
    @State private var versatzBeimGriff: CGSize = .zero

    var body: some View {
        GeometryReader { aussen in
            let rahmen = passenderRahmen(in: aussen.size)
            ZStack {
                Image(uiImage: bild)
                    .resizable()
                    .scaledToFit()
                    .overlay { auflage(rahmen) }
                    .frame(width: rahmen.width, height: rahmen.height)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .shadow(color: Color(hex: 0x1F1E1A).opacity(0.22), radius: 14, y: 7)
                    .scaleEffect(faktor)
                    .offset(versatz)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(
                SimultaneousGesture(
                    MagnificationGesture()
                        .onChanged { wert in
                            faktor = min(max(faktorBeimGriff * wert, 1), maxFaktor)
                        }
                        .onEnded { _ in
                            faktorBeimGriff = faktor
                            einrasten(rahmen: rahmen)
                        },
                    DragGesture()
                        .onChanged { wert in
                            guard faktor > 1 else { return }
                            versatz = CGSize(
                                width: versatzBeimGriff.width + wert.translation.width,
                                height: versatzBeimGriff.height + wert.translation.height)
                        }
                        .onEnded { _ in
                            versatzBeimGriff = versatz
                            einrasten(rahmen: rahmen)
                        }
                )
            )
            .onTapGesture(count: 2) {
                withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                    if faktor > 1.05 {
                        faktor = 1
                        versatz = .zero
                    } else {
                        faktor = 3
                    }
                    faktorBeimGriff = faktor
                    versatzBeimGriff = versatz
                }
            }
            .accessibilityLabel("Beleg-Foto")
            .accessibilityHint("Doppeltippen zum Vergrößern, zwei Finger zum Zoomen")
            .overlay(alignment: .bottomTrailing) {
                if faktor > 1.05 {
                    Button {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.82)) {
                            faktor = 1
                            versatz = .zero
                            faktorBeimGriff = 1
                            versatzBeimGriff = .zero
                        }
                    } label: {
                        Image(systemName: "arrow.down.right.and.arrow.up.left")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(GC.fg)
                            .frame(width: 38, height: 38)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                    .accessibilityLabel("Wieder ganz zeigen")
                    .padding(10)
                    .transition(.scale.combined(with: .opacity))
                }
            }
        }
    }

    /// Die Größe, die das Bild ohne Zoom einnimmt — Grundlage fürs Einrasten.
    private func passenderRahmen(in raum: CGSize) -> CGSize {
        let seiten = bild.size
        guard seiten.width > 0, seiten.height > 0, raum.width > 0, raum.height > 0 else {
            return raum
        }
        let f = min(raum.width / seiten.width, raum.height / seiten.height)
        return CGSize(width: seiten.width * f, height: seiten.height * f)
    }

    /// Zurück in die Grenzen: verschoben werden darf nur, was über den Rand
    /// hinausragt. Ohne das ließe sich der Beleg aus dem Bild schieben.
    private func einrasten(rahmen: CGSize) {
        let luftX = max(0, (rahmen.width * faktor - rahmen.width) / 2)
        let luftY = max(0, (rahmen.height * faktor - rahmen.height) / 2)
        let gezaehmt = CGSize(width: min(max(versatz.width, -luftX), luftX),
                              height: min(max(versatz.height, -luftY), luftY))
        if gezaehmt != versatz {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                versatz = gezaehmt
            }
        }
        versatzBeimGriff = gezaehmt
    }
}

extension ZoombaresBild where Auflage == EmptyView {
    init(bild: UIImage, maxFaktor: CGFloat = 6) {
        self.init(bild: bild, maxFaktor: maxFaktor) { _ in EmptyView() }
    }
}
