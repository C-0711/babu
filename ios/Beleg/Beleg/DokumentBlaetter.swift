import SwiftUI

/// Die Dokumente als Blätter statt als Zeilen.
///
/// Wer einen bestimmten Betrag sucht, findet ihn in der Liste. Wer „den
/// grünen Zettel von neulich" sucht, findet ihn nur, wenn er ihn sieht.
/// Deshalb dieselben Dokumente noch einmal als Papier: Vorschaubild,
/// Lieferant, Betrag, und der Haken oben rechts, wenn alles stimmt.
///
/// Antippen öffnet den Beleg groß und zoombar — die Vorschau ist zu klein,
/// um etwas darauf zu lesen, und das soll sie auch sein.
struct DokumentBlaetter: View {
    let dokumente: [Beleg]
    @Binding var grossAnsehen: Grossansicht?
    /// Öffnen übernimmt der Aufrufer, indem er es auf seinen Stapel schiebt.
    /// Ein NavigationLink in einer Listenzeile bekäme vom System einen Pfeil
    /// daneben — bei einer Kachel sieht das aus wie ein Zeichenfehler.
    var oeffnen: (UUID) -> Void

    private let raster = [GridItem(.adaptive(minimum: 108, maximum: 170), spacing: 14)]

    var body: some View {
        LazyVGrid(columns: raster, spacing: 16) {
            ForEach(dokumente) { b in
                Button { oeffnen(b.id) } label: { Blatt(beleg: b) }
                .buttonStyle(.plain)
                // Lange drücken heißt „nur mal ansehen": das Bild groß und
                // zoombar, ohne den Umweg über die Detailansicht. Als
                // gleichzeitige Geste, damit der Link davon unberührt bleibt.
                .simultaneousGesture(
                    LongPressGesture(minimumDuration: 0.4).onEnded { _ in
                        grossAnsehen = Grossansicht(id: b.id)
                    })
                .accessibilityHint("Tippen zum Öffnen, halten zum Vergrößern")
            }
        }
        .padding(.horizontal, 2)
        .padding(.vertical, 6)
    }
}

private struct Blatt: View {
    let beleg: Beleg

    private var fertig: Bool { beleg.archivBestaetigt || beleg.status == .fixiert }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ZStack(alignment: .topTrailing) {
                bild
                if fertig {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 19))
                        .foregroundStyle(.white, GC.ok)
                        .padding(5)
                        .accessibilityHidden(true)
                } else if beleg.reviewStatus == "fehlgeschlagen" {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 19))
                        .foregroundStyle(.white, GC.warn)
                        .padding(5)
                        .accessibilityHidden(true)
                }
            }
            Text(beleg.lieferant)
                .font(.footnote.weight(.medium))
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
                .lineLimit(1)
            Text(fmtEur(beleg.brutto))
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(GC.desc)
        }
    }

    @ViewBuilder
    private var bild: some View {
        // Erst der Rahmen im Papierformat, DANN das Bild als Füllung DARIN.
        // Ein scaledToFill-Bild direkt zu rahmen lässt sehr hohe Bon-Fotos
        // (900 × 4300 px sind normal) über die Kachel hinauswachsen und das
        // ganze Raster übermalen. Ausrichtung oben: der Kopf mit dem Laden
        // ist das, woran man einen Bon wiedererkennt.
        Color.clear
            .aspectRatio(1 / 1.35, contentMode: .fit)
            .frame(maxWidth: .infinity)
            .overlay(alignment: .top) {
                if let daten = beleg.bildJpeg, let ui = UIImage(data: daten) {
                    Image(uiImage: ui)
                        .resizable()
                        .scaledToFill()
                } else {
                    GC.desk.overlay(
                        Image(systemName: Dokumentart.von(beleg).symbol)
                            .font(.system(size: 26, weight: .light))
                            .foregroundStyle(GC.muted))
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 9))
            .overlay(RoundedRectangle(cornerRadius: 9).stroke(GC.linie, lineWidth: 1))
            .shadow(color: Color(hex: 0x1F1E1A).opacity(0.10), radius: 5, y: 3)
    }
}
