import SwiftUI

/// Einen Beleg groß ansehen — das Bild war zuvor beschnitten und nicht
/// vergrößerbar; hier ist das behoben.
struct BelegGrossView: View {
    let beleg: Beleg
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    private var stamm: String? {
        guard let name = beleg.ablageDateiname else { return nil }
        return (name as NSString).deletingPathExtension
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if let seiten = beleg.seitenJpeg, seiten.count > 1 {
                    // Mehrseitiger Beleg: durch die Seiten blättern.
                    TabView {
                        ForEach(Array(seiten.enumerated()), id: \.offset) { paar in
                            if let bild = UIImage(data: paar.element) {
                                ZoombaresBild(bild: bild)
                                    .padding(12)
                                    .accessibilityLabel("Seite \(paar.offset + 1) von \(seiten.count)")
                            }
                        }
                    }
                    .tabViewStyle(.page)
                    .indexViewStyle(.page(backgroundDisplayMode: .always))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let daten = beleg.bildJpeg, let bild = UIImage(data: daten) {
                    ZoombaresBild(bild: bild)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding(12)
                } else {
                    Spacer()
                    Image(systemName: "doc.text")
                        .font(.system(size: 44, weight: .light))
                        .foregroundStyle(GC.accent)
                    Spacer()
                }

                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(beleg.lieferant)
                            .font(.headline)
                            .fontDesign(.serif)
                            .lineLimit(1)
                        Spacer()
                        Text(fmtEur(beleg.brutto))
                            .font(.system(size: 20, weight: .medium, design: .monospaced))
                    }
                    .foregroundStyle(GC.fg)

                    if let stamm {
                        NavigationLink {
                            ProtokollView(stamm: stamm).environmentObject(store)
                        } label: {
                            Label("Was babu gelesen hat", systemImage: "text.magnifyingglass")
                                .font(.footnote)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    } else {
                        Text("Dieser Beleg ist noch nicht in der Belegbox — sobald er "
                             + "abgelegt ist, kann babu ihn lesen.")
                            .font(.footnote)
                            .foregroundStyle(GC.muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
                .background(GC.bg)
            }
            .background(GC.canvas)
            .navigationTitle("Beleg")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { dismiss() }
                }
            }
        }
    }
}
