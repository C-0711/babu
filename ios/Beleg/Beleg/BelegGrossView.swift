import SwiftUI

/// Einen Beleg groß ansehen — und, wenn er falsch gelesen wurde, gleich
/// noch einmal lesen lassen.
///
/// Beim Aufräumen entscheidet man in Sekunden über jeden Beleg. Genau dort
/// fällt auf, wenn eine Zahl nicht stimmt — und genau dort war bisher nichts
/// zu machen: das Bild war beschnitten und nicht vergrößerbar, und die
/// einzige Möglichkeit, eine neue Lesung zu bekommen, wäre gewesen, den
/// Beleg noch einmal zu fotografieren. Beides ist hier behoben.
struct BelegGrossView: View {
    let beleg: Beleg
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var neuGelesen = false
    @State private var meldung: String?
    @State private var laeuft = false

    private var stamm: String? {
        guard let name = beleg.ablageDateiname else { return nil }
        return (name as NSString).deletingPathExtension
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if let daten = beleg.bildJpeg, let bild = UIImage(data: daten) {
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

                    if let meldung {
                        Text(meldung)
                            .font(.footnote)
                            .foregroundStyle(neuGelesen ? GC.accent : GC.warn)
                    }

                    if let stamm {
                        HStack(spacing: 10) {
                            NavigationLink {
                                ProtokollView(stamm: stamm).environmentObject(store)
                            } label: {
                                Label("Was babu gelesen hat", systemImage: "text.magnifyingglass")
                                    .font(.footnote)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)

                            Button {
                                Task { await neuLesen(stamm) }
                            } label: {
                                if laeuft {
                                    ProgressView().controlSize(.mini)
                                } else {
                                    Label("Noch einmal lesen", systemImage: "arrow.clockwise")
                                        .font(.footnote)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .disabled(laeuft || neuGelesen)
                        }
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

    private func neuLesen(_ stamm: String) async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            meldung = "Dafür muss die Belegbox verbunden sein (Export → Zahnrad)."
            return
        }
        laeuft = true
        defer { laeuft = false }
        if await AblageService.neuLesenAnstossen(stamm: stamm, basis: url, pat: pat) {
            neuGelesen = true
            meldung = "babu liest den Beleg noch einmal — in etwa einer halben "
                + "Minute steht das Ergebnis hier."
        } else {
            meldung = "Das hat gerade nicht geklappt. Später noch einmal versuchen."
        }
    }
}
