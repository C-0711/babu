import SwiftUI

/// Marketing: was der Salon nach außen zeigt. babu kennt Name, Farbe und
/// Zeichen — daraus macht es Aushang, Beitrag, Gutschein und Preisliste.
/// Was drauf steht, schreibt die Inhaberin; babu gestaltet es nur.
struct MarketingView: View {
    @EnvironmentObject var store: AppStore

    @State private var stuecke: [[String: Any]] = []
    @State private var gewaehlt: String?
    @State private var text = ""
    @State private var bild: UIImage?
    @State private var laeuft = false
    @State private var fehler: String?
    @State private var teilen: URL?

    var body: some View {
        List {
            if let fehler {
                Text(fehler).font(.footnote).foregroundStyle(GC.warn)
            }

            Section {
                ForEach(stuecke.indices, id: \.self) { i in
                    let s = stuecke[i]
                    let schluessel = s["schluessel"] as? String ?? ""
                    Button {
                        gewaehlt = schluessel
                        bild = nil
                        Task { await vorhandenesLaden(schluessel) }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(s["name"] as? String ?? "")
                                    .font(.body.weight(.medium)).foregroundStyle(GC.fg)
                                Text(s["dazu"] as? String ?? "")
                                    .font(.caption).foregroundStyle(GC.desc)
                            }
                            Spacer()
                            if s["fertig"] as? Bool == true {
                                Text("fertig").font(.caption2).foregroundStyle(GC.ok)
                            }
                            if gewaehlt == schluessel {
                                Image(systemName: "checkmark").foregroundStyle(GC.accent)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }
            } header: {
                Text("Was soll babu gestalten?")
            }

            if gewaehlt != nil {
                Section {
                    TextField("z. B. Vom 1. bis 14. September haben wir Urlaub.",
                              text: $text, axis: .vertical)
                        .lineLimit(2...5)
                } header: {
                    Text("Was soll drauf stehen?")
                } footer: {
                    Text("Genau dieser Text kommt aufs Bild. babu denkt sich "
                         + "nichts dazu aus — Angebote entscheidest du.")
                }

                Section {
                    Button {
                        Task { await gestalten() }
                    } label: {
                        HStack {
                            if laeuft { ProgressView().padding(.trailing, 6) }
                            Text(laeuft ? "babu gestaltet …" : "Gestalten")
                        }
                    }
                    .disabled(laeuft || text.trimmed.count < 3)
                }
            }

            if let bild {
                Section {
                    Image(uiImage: bild).resizable().scaledToFit()
                        .frame(maxWidth: .infinity)
                    Button {
                        sichern(bild)
                    } label: {
                        Label("Teilen oder sichern", systemImage: "square.and.arrow.up")
                    }
                }
            }
        }
        .navigationTitle("Marketing")
        .navigationBarTitleDisplayMode(.inline)
        .task { await laden() }
        .sheet(item: $teilen) { url in
            TeilenBlatt(datei: url) { teilen = nil }
        }
    }

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func laden() async {
        guard let (url, pat) = zugang() else {
            fehler = "Erst verbinden — dann gestaltet babu."
            return
        }
        stuecke = await AblageService.marketingStuecke(basis: url, pat: pat)
    }

    private func vorhandenesLaden(_ schluessel: String) async {
        guard let (url, pat) = zugang() else { return }
        if let daten = await AblageService.marketingBild(schluessel, basis: url, pat: pat) {
            bild = UIImage(data: daten)
        }
    }

    private func gestalten() async {
        guard let schluessel = gewaehlt, let (url, pat) = zugang() else { return }
        laeuft = true
        fehler = nil
        defer { laeuft = false }
        if let meldung = await AblageService.marketingEntwerfen(
            stueck: schluessel, text: text, basis: url, pat: pat) {
            fehler = meldung
            return
        }
        await vorhandenesLaden(schluessel)
        await laden()
    }

    private func sichern(_ bild: UIImage) {
        guard let daten = bild.jpegData(compressionQuality: 0.92) else { return }
        let ziel = FileManager.default.temporaryDirectory
            .appendingPathComponent("babu-\(gewaehlt ?? "bild").jpg")
        try? daten.write(to: ziel)
        teilen = ziel
    }
}
