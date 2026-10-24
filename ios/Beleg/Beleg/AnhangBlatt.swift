import SwiftUI

/// Was an den Chat gehängt werden soll — ein Brief vom Amt oder ein Vertrag,
/// als Foto oder als Datei.
enum AnhangWahl {
    case briefFoto, briefDatei, vertragFoto, vertragDatei
}

/// Das Anhang-Blatt für iPad und breite Fenster (seit 24.10.2026).
///
/// Auf dem iPhone bleibt die Büroklammer ein `Menu` mit einem `PhotosPicker`
/// darin — das funktioniert dort. Auf dem iPad (auch im
/// iPhone-Kompatibilitätsfenster) schließt sich das Menü, und der Picker
/// erscheint nie: Apple hat genau das am 24.10.2026 abgelehnt (2.1(a)). Hier
/// wählt die Nutzerin nur; den Picker öffnet `FragenTab` erst, wenn dieses
/// Blatt weg ist — dann will UIKit nichts mehr gleichzeitig zeigen.
struct AnhangBlatt: View {
    let wahl: (AnhangWahl) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Brief vom Amt") {
                    knopf("Fotografieren oder aus Fotos", bild: "camera", .briefFoto)
                    knopf("Aus Dateien (PDF)", bild: "folder", .briefDatei)
                }
                Section("Vertrag") {
                    knopf("Mietvertrag & Co. fotografieren", bild: "doc.text", .vertragFoto)
                    knopf("Vertrag aus Dateien (PDF)", bild: "folder", .vertragDatei)
                }
            }
            .warmerGrund()
            .navigationTitle("Anhang")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Abbrechen") { dismiss() }
                }
            }
        }
    }

    private func knopf(_ titel: String, bild: String, _ was: AnhangWahl) -> some View {
        Button {
            wahl(was)
            dismiss()
        } label: {
            Label(titel, systemImage: bild)
        }
        .foregroundStyle(GC.body)
    }
}
