import SwiftUI

/// Der Arbeitsplatz — nur in der breiten Größenklasse (iPad, aufgeklapptes
/// iPhone Duo, 27.10.2026): links die Belege, rechts der Chat. Tippt sie links
/// einen Beleg an, steht er links (Navigation in der Spalte); der Umschalter
/// oben rechts zeigt ihn stattdessen rechts groß, dann bleibt links das Archiv.
/// Auf dem iPhone gibt es diese Ansicht nicht — dort bleiben Dokumente und
/// Fragen zwei Reiter (`Ausbaustufe.reiter(fuer:ambassadorin:breit:)`).
struct ArbeitsplatzView: View {
    @EnvironmentObject var store: AppStore

    enum RechteSpalte { case fragen, beleg }
    @State private var rechts: RechteSpalte = .fragen

    var body: some View {
        GeometryReader { proxy in
            HStack(spacing: 0) {
                ListeView()
                    .environmentObject(store)
                    .frame(width: proxy.size.width * 0.45)
                Divider()
                VStack(spacing: 0) {
                    Picker("", selection: $rechts) {
                        Text("Fragen").tag(RechteSpalte.fragen)
                        Text("Beleg").tag(RechteSpalte.beleg)
                    }
                    .pickerStyle(.segmented)
                    .padding()
                    switch rechts {
                    case .fragen:
                        FragenTab().environmentObject(store)
                    case .beleg:
                        if let id = store.aufgeschlagen,
                           let b = store.belege.first(where: { $0.id == id }) {
                            BelegGrossView(beleg: b, fertig: { rechts = .fragen })
                                .environmentObject(store)
                        } else {
                            Spacer()
                            Text("Tipp links einen Beleg an.")
                                .foregroundStyle(GC.desc)
                            Spacer()
                        }
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
    }
}
