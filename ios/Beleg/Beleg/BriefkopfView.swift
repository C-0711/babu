import SwiftUI
import PhotosUI

/// In vier Schritten zum eigenen Briefkopf: Farbe, Stil, Zeichen, fertig.
/// Kein einziger Hex-Code, keine Schriftnamen — eine Rechnung ist oft das
/// Einzige, was eine Kundin schriftlich vom Salon in die Hand bekommt.
struct BriefkopfView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    @State private var schritt = 0
    @State private var vorschlaege: [[String: Any]] = []
    @State private var vorschlagBilder: [Int: UIImage] = [:]
    @State private var saat = 0
    @State private var gewaehlt: String?
    @State private var farben: [[String: Any]] = []
    @State private var stile: [[String: Any]] = []
    @State private var gewaehlteFarbe: String?
    @State private var gewaehlterStil = "schlicht"
    @State private var logo: UIImage?
    @State private var laeuft = false
    @State private var fehler: String?
    @State private var auswahl: PhotosPickerItem?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                fortschritt
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let fehler {
                            Text(fehler).font(.footnote).foregroundStyle(GC.warn)
                        }
                        switch schritt {
                        case 0: schrittZehn
                        case 1: schrittFarbe
                        case 2: schrittStil
                        case 3: schrittZeichen
                        default: schrittFertig
                        }
                    }
                    .padding(20)
                }
                fussleiste
            }
            .warmerGrund()
            .navigationTitle("Dein Briefkopf")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fertig") { dismiss() }
                }
            }
            .task { await laden() }
        }
    }

    // MARK: - Die vier Schritte oben

    private var fortschritt: some View {
        HStack(spacing: 6) {
            ForEach(1...4, id: \.self) { n in
                Capsule()
                    .fill(n <= schritt ? GC.accent : GC.desk)
                    .frame(height: 3)
            }
            .opacity(schritt == 0 ? 0 : 1)
        }
        .padding(.horizontal, 20)
        .padding(.top, 4)
    }

    // MARK: - Der Schnellweg: ein Knopf, zehn Zeichen

    private var schrittZehn: some View {
        VStack(alignment: .leading, spacing: 16) {
            titel("Dein Auftritt",
                  "babu entwirft zehn Zeichen für deinen Salon. Eines antippen — "
                  + "Farbe, Schrift und Briefkopf stehen dann von selbst.")
            Button {
                Task { await zehnHolen() }
            } label: {
                HStack {
                    if laeuft { ProgressView().tint(.white).padding(.trailing, 6) }
                    Text(laeuft ? "babu entwirft zehn Zeichen …"
                         : (vorschlaege.isEmpty ? "Zeig mir zehn" : "Zehn andere"))
                }
                .frame(maxWidth: .infinity).padding(14)
                .background(GC.fg, in: RoundedRectangle(cornerRadius: 12))
                .foregroundStyle(.white)
            }
            .disabled(laeuft)

            if !vorschlaege.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 104), spacing: 12)],
                          spacing: 12) {
                    ForEach(vorschlaege.indices, id: \.self) { i in
                        let v = vorschlaege[i]
                        let nummer = v["nummer"] as? Int ?? i
                        Button {
                            Task { await annehmen(nummer) }
                        } label: {
                            VStack(spacing: 6) {
                                if let bild = vorschlagBilder[nummer] {
                                    Image(uiImage: bild).resizable().scaledToFit()
                                        .frame(height: 96)
                                } else {
                                    ProgressView().frame(height: 96)
                                }
                                Text(v["farbe_name"] as? String ?? "")
                                    .font(.caption2).foregroundStyle(GC.desc)
                            }
                            .padding(8)
                            .gcCard()
                        }
                    }
                }
            }

            if let gewaehlt {
                Text("Übernommen: \(gewaehlt)")
                    .font(.footnote).foregroundStyle(GC.ok)
            }

            Button("Lieber selbst aussuchen") { schritt = 1 }
                .font(.footnote).foregroundStyle(GC.desc)

            Text("Zum Entwerfen geht der Name deines Salons an einen Dienst "
                 + "außerhalb — sonst bleibt alles hier.")
                .font(.caption2).foregroundStyle(GC.muted)
        }
    }

    private func zehnHolen() async {
        guard let (url, pat) = zugang() else {
            fehler = "Erst verbinden — dann entwirft babu."
            return
        }
        laeuft = true
        fehler = nil
        vorschlagBilder = [:]
        defer { laeuft = false }
        let (liste, meldung) = await AblageService.logoVorschlaege(
            saat: saat, basis: url, pat: pat)
        if let meldung { fehler = meldung; return }
        vorschlaege = liste
        saat += 1
        for v in liste {
            let nummer = v["nummer"] as? Int ?? 0
            if let daten = await AblageService.logoVorschlagBild(nummer, basis: url,
                                                                 pat: pat) {
                vorschlagBilder[nummer] = UIImage(data: daten)
            }
        }
    }

    private func annehmen(_ nummer: Int) async {
        guard let (url, pat) = zugang() else { return }
        logo = vorschlagBilder[nummer]
        gewaehlt = await AblageService.logoWaehlen(nummer: nummer, saat: saat - 1,
                                                    basis: url, pat: pat)
        if gewaehlt == nil { fehler = "Das ließ sich gerade nicht übernehmen." }
        else { schritt = 4 }
    }

    // MARK: - Schritt 1: Farbe

    private var schrittFarbe: some View {
        VStack(alignment: .leading, spacing: 14) {
            titel("Welche Farbe passt zu deinem Salon?",
                  "Sie taucht auf jeder Rechnung auf. Alle hier lassen sich gut drucken.")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 104), spacing: 12)],
                      spacing: 12) {
                ForEach(farben.indices, id: \.self) { i in
                    let f = farben[i]
                    let schluessel = f["schluessel"] as? String ?? ""
                    Button {
                        gewaehlteFarbe = schluessel
                    } label: {
                        VStack(spacing: 8) {
                            RoundedRectangle(cornerRadius: 10)
                                .fill(Color(hexText: f["hex"] as? String ?? "#000000"))
                                .frame(height: 54)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(GC.fg, lineWidth: gewaehlteFarbe == schluessel ? 2.5 : 0)
                                )
                            Text(f["name"] as? String ?? "")
                                .font(.footnote.weight(.medium)).foregroundStyle(GC.fg)
                            Text(f["dazu"] as? String ?? "")
                                .font(.caption2).foregroundStyle(GC.desc)
                                .multilineTextAlignment(.center)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Schritt 2: Stil

    private var schrittStil: some View {
        VStack(alignment: .leading, spacing: 14) {
            titel("Wie soll es wirken?", "Das gibt dem Zeichen seine Handschrift.")
            ForEach(stile.indices, id: \.self) { i in
                let s = stile[i]
                let schluessel = s["schluessel"] as? String ?? ""
                Button {
                    gewaehlterStil = schluessel
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(s["name"] as? String ?? "")
                                .font(.body.weight(.medium)).foregroundStyle(GC.fg)
                            Text(s["dazu"] as? String ?? "")
                                .font(.caption).foregroundStyle(GC.desc)
                        }
                        Spacer()
                        if gewaehlterStil == schluessel {
                            Image(systemName: "checkmark").foregroundStyle(GC.accent)
                        }
                    }
                    .padding(14)
                    .gcCard()
                }
            }
        }
    }

    // MARK: - Schritt 3: Das Zeichen

    private var schrittZeichen: some View {
        VStack(alignment: .leading, spacing: 14) {
            titel("Dein Zeichen", "babu entwirft eines — oder du lädst dein eigenes hoch.")
            if let logo {
                Image(uiImage: logo)
                    .resizable().scaledToFit()
                    .frame(maxHeight: 190)
                    .frame(maxWidth: .infinity)
                    .padding(14)
                    .gcCard()
            }
            Button {
                Task { await entwerfen() }
            } label: {
                HStack {
                    if laeuft { ProgressView().padding(.trailing, 6) }
                    Text(laeuft ? "babu entwirft …"
                         : (logo == nil ? "Logo entwerfen lassen" : "Nochmal versuchen"))
                }
                .frame(maxWidth: .infinity)
                .padding(13)
                .background(GC.fg, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
            }
            .disabled(laeuft)

            PhotosPicker(selection: $auswahl, matching: .images) {
                Label("Eigenes Bild hochladen", systemImage: "photo")
                    .frame(maxWidth: .infinity).padding(12)
                    .gcCard()
            }
            .onChange(of: auswahl) { _, neu in
                Task { await eigenesBild(neu) }
            }

            Text("Zum Entwerfen geht der Name deines Salons an einen Dienst "
                 + "außerhalb — sonst bleibt alles hier.")
                .font(.caption2).foregroundStyle(GC.muted)
        }
    }

    // MARK: - Schritt 4: Fertig

    private var schrittFertig: some View {
        VStack(alignment: .leading, spacing: 14) {
            titel("So sieht deine Rechnung aus.", "Fertig — du kannst es jederzeit ändern.")
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top) {
                    if let logo {
                        Image(uiImage: logo).resizable().scaledToFit()
                            .frame(width: 54, height: 54)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Rechnung 2026-0001")
                            .font(.title3.weight(.semibold)).fontDesign(.serif)
                            .foregroundStyle(farbeJetzt)
                        Text("Rechnungsdatum: heute").font(.caption2)
                            .foregroundStyle(GC.desc)
                    }
                }
                Rectangle().fill(farbeJetzt).frame(height: 1.5)
                HStack {
                    Text("Stuhlmiete August").font(.footnote)
                    Spacer()
                    Text("450,00 €").font(.footnote.monospacedDigit())
                }
                HStack {
                    Text("Gesamt").font(.footnote.weight(.semibold))
                    Spacer()
                    Text("535,50 €").font(.footnote.monospacedDigit().weight(.semibold))
                }
            }
            .padding(16)
            .gcCard()
        }
    }

    private var farbeJetzt: Color {
        guard let schluessel = gewaehlteFarbe,
              let f = farben.first(where: { $0["schluessel"] as? String == schluessel }),
              let hex = f["hex"] as? String else { return GC.fg }
        return Color(hexText: hex)
    }

    // MARK: - Unten

    @ViewBuilder
    private var fussleiste: some View {
        if schritt == 0 {
            EmptyView()
        } else {
        HStack {
            if schritt > 1 {
                Button("Zurück") { schritt -= 1 }
                    .foregroundStyle(GC.desc)
            }
            Spacer()
            Button(schritt == 4 ? "Fertig" : "Weiter") {
                if schritt == 4 { dismiss(); return }
                Task { await weiter() }
            }
            .disabled(schritt == 1 && gewaehlteFarbe == nil)
            .padding(.horizontal, 22).padding(.vertical, 11)
            .background(GC.fg, in: Capsule())
            .foregroundStyle(.white)
            .opacity(schritt == 1 && gewaehlteFarbe == nil ? 0.4 : 1)
        }
        .padding(.horizontal, 20).padding(.vertical, 12)
        }
    }

    private func titel(_ gross: String, _ klein: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(gross).font(.title3.weight(.semibold)).fontDesign(.serif)
            Text(klein).font(.footnote).foregroundStyle(GC.desc)
        }
    }

    // MARK: - Server

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    /// Farben und Stile stehen auch ohne Verbindung zur Verfügung: sie sind
    /// fest, und wer seinen Briefkopf ansehen will, soll nicht erst online
    /// gehen müssen. Der Server bestätigt die Wahl, sobald es ihn gibt.
    private static let farbenLokal: [[String: Any]] = [
        ["schluessel": "kupfer", "name": "Kupfer", "hex": "#8A4B2A", "dazu": "warm und handwerklich"],
        ["schluessel": "mahagoni", "name": "Mahagoni", "hex": "#6E2C2C", "dazu": "kräftig, klassisch"],
        ["schluessel": "aubergine", "name": "Aubergine", "hex": "#4A2545", "dazu": "eigen, modern"],
        ["schluessel": "nachtblau", "name": "Nachtblau", "hex": "#1F3A5F", "dazu": "ruhig und seriös"],
        ["schluessel": "salbei", "name": "Salbei", "hex": "#3F5D4B", "dazu": "natürlich, frisch"],
        ["schluessel": "tanne", "name": "Tannengrün", "hex": "#1F3D30", "dazu": "tief und wertig"],
        ["schluessel": "terrakotta", "name": "Terrakotta", "hex": "#9A4A34", "dazu": "südlich, warm"],
        ["schluessel": "graphit", "name": "Graphit", "hex": "#33383D", "dazu": "zurückhaltend, edel"],
        ["schluessel": "schwarz", "name": "Tiefschwarz", "hex": "#1F1D1B", "dazu": "immer richtig"],
    ]

    private static let stileLokal: [[String: Any]] = [
        ["schluessel": "schlicht", "name": "Schlicht", "dazu": "zeitlos, ein klares Zeichen"],
        ["schluessel": "verspielt", "name": "Verspielt", "dazu": "freundlich, weiche Formen"],
        ["schluessel": "edel", "name": "Edel", "dazu": "reduziert, feine Linien"],
    ]

    private func laden() async {
        farben = Self.farbenLokal
        stile = Self.stileLokal
        guard let (url, pat) = zugang() else {
            // Aussuchen geht trotzdem — nur sichern braucht die Verbindung.
            fehler = "Ohne Verbindung kannst du schon aussuchen; gesichert "
                   + "wird es, sobald du verbunden bist."
            return
        }
        if let k = await AblageService.markeKatalog(basis: url, pat: pat),
           !k.farben.isEmpty {
            farben = k.farben
            stile = k.stile.isEmpty ? Self.stileLokal : k.stile
        }
        if let daten = await AblageService.logoLaden(basis: url, pat: pat) {
            logo = UIImage(data: daten)
        }
    }

    private func weiter() async {
        if schritt == 1, let farbe = gewaehlteFarbe, let (url, pat) = zugang() {
            _ = await AblageService.markeFarbeWaehlen(farbe, basis: url, pat: pat)
        }
        schritt += 1
    }

    private func entwerfen() async {
        guard let (url, pat) = zugang() else { return }
        laeuft = true
        fehler = nil
        defer { laeuft = false }
        if let meldung = await AblageService.logoEntwerfen(stil: gewaehlterStil,
                                                           basis: url, pat: pat) {
            fehler = meldung
            return
        }
        if let daten = await AblageService.logoLaden(basis: url, pat: pat) {
            logo = UIImage(data: daten)
        }
    }

    private func eigenesBild(_ eintrag: PhotosPickerItem?) async {
        guard let eintrag, let (url, pat) = zugang() else { return }
        guard let daten = try? await eintrag.loadTransferable(type: Data.self),
              let bild = UIImage(data: daten),
              let png = bild.pngData() else {
            fehler = "Das Bild ließ sich nicht lesen."
            return
        }
        if await AblageService.logoSenden(png, basis: url, pat: pat) {
            logo = bild
            fehler = nil
        } else {
            fehler = "Das Bild ließ sich nicht ablegen."
        }
    }
}

extension Color {
    /// „#8A4B2A" → Farbe. Unbrauchbares wird schwarz, nie ein Absturz.
    init(hexText: String) {
        let roh = hexText.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var wert: UInt64 = 0
        Scanner(string: roh).scanHexInt64(&wert)
        self.init(.sRGB,
                  red: Double((wert >> 16) & 0xFF) / 255,
                  green: Double((wert >> 8) & 0xFF) / 255,
                  blue: Double(wert & 0xFF) / 255)
    }
}
