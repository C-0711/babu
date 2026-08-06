import SwiftUI
import UIKit

// MARK: - Belegliste im Unlimited-OCR-Design

struct ListeView: View {
    @EnvironmentObject var store: AppStore
    @State private var filter: Filter = .alle

    enum Filter: String, CaseIterable, Identifiable {
        case alle = "Alle"
        case automatisch = "Automatisch"
        case bestaetigt = "Bestätigt"
        case korrigiert = "Korrigiert"
        case offen = "Offen"
        var id: String { rawValue }
    }

    private var gefiltert: [Beleg] {
        store.belege.filter { b in
            switch filter {
            case .alle: return true
            case .automatisch: return b.status == .automatisch
            case .bestaetigt: return b.status == .bestaetigt
            case .korrigiert: return b.status == .korrigiert
            case .offen: return b.status == .offen
            }
        }
    }

    private var heute: [Beleg] { gefiltert.filter { Calendar.current.isDateInToday($0.erfasstAm) } }
    private var archiv: [Beleg] { gefiltert.filter { !Calendar.current.isDateInToday($0.erfasstAm) } }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    filterChips
                        .padding(.vertical, 10)

                    if let d = store.durchsatzText {
                        Text(d)
                            .font(.caption2.monospaced())
                            .foregroundStyle(GC.muted)
                            .padding(.horizontal, 18)
                            .padding(.bottom, 4)
                    }

                    if gefiltert.isEmpty {
                        Text("Kein Beleg entspricht diesem Filter.")
                            .font(.footnote)
                            .foregroundStyle(GC.muted)
                            .padding(18)
                    }

                    if !heute.isEmpty {
                        sektionsLabel("Heute erfasst")
                        ForEach(heute) { belegZeile($0) }
                    }
                    if !archiv.isEmpty {
                        sektionsLabel("Bereits archiviert")
                        ForEach(archiv) { belegZeile($0) }
                    }
                }
            }
            .background(GC.canvas)
            .navigationTitle("Belege")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: UUID.self) { id in
                DetailView(belegID: id)
            }
        }
    }

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Filter.allCases) { f in
                    Button {
                        filter = f
                    } label: {
                        Text(f.rawValue)
                            .font(.footnote.weight(.semibold))
                            .padding(.horizontal, 13).padding(.vertical, 7)
                            .background(filter == f ? GC.accentSubtle : GC.bg, in: Capsule())
                            .overlay(Capsule().stroke(filter == f ? GC.accent : Color(hex: 0xEFEFEF)))
                            .foregroundStyle(filter == f ? GC.accentHover : GC.desc)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func sektionsLabel(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.system(size: 10, design: .monospaced))
            .kerning(1)
            .foregroundStyle(GC.muted)
            .padding(.horizontal, 18)
            .padding(.top, 14)
            .padding(.bottom, 4)
    }

    private func belegZeile(_ b: Beleg) -> some View {
        NavigationLink(value: b.id) {
            BelegZeile(beleg: b)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Zeile mit Thumbnail + Siegel-Ring

struct BelegZeile: View {
    let beleg: Beleg

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                BelegThumbnail(beleg: beleg)
                VStack(alignment: .leading, spacing: 3) {
                    Text(beleg.lieferant)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(GC.fg)
                        .lineLimit(1)
                    HStack(spacing: 0) {
                        Text("\(beleg.belegNr) · ")
                        statusText
                    }
                    .font(.system(size: 10.5, design: .monospaced))
                    .foregroundStyle(GC.muted)
                    .lineLimit(1)
                }
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 3) {
                    Text(fmtEur(beleg.brutto))
                        .font(.subheadline.monospaced())
                        .foregroundStyle(GC.fg)
                    Text(beleg.konto.map { "\($0) · \(beleg.ksLabel)" } ?? "ohne Konto")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(GC.muted)
                }
                Image(systemName: "chevron.right")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(GC.muted.opacity(0.6))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            Divider().overlay(Color(hex: 0xEFEFEF)).padding(.leading, 68)
        }
        .contentShape(Rectangle())
    }

    @ViewBuilder
    private var statusText: some View {
        switch beleg.status {
        case .korrigiert: Text("korrigiert → lernt").foregroundStyle(GC.warn)
        case .bestaetigt: Text("bestätigt").foregroundStyle(GC.ok)
        case .offen: Text("offen").foregroundStyle(GC.warn)
        case .fixiert: Text("fixiert")
        case .automatisch:
            Text(beleg.herkunft.rawValue)
                .foregroundStyle(beleg.herkunft == .historie ? GC.accent :
                                 beleg.herkunft == .regel ? GC.ok : GC.warn)
        }
    }
}

struct BelegThumbnail: View {
    let beleg: Beleg

    var body: some View {
        Group {
            if let data = beleg.bildAufbereitetJpeg ?? beleg.bildJpeg,
               let img = UIImage(data: data) {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFill()
            } else {
                // Platzhalter-Papier für Demo-Archivbelege ohne Bild
                VStack(alignment: .leading, spacing: 3) {
                    RoundedRectangle(cornerRadius: 1).frame(width: 22, height: 3)
                    RoundedRectangle(cornerRadius: 1).frame(width: 26, height: 2)
                    RoundedRectangle(cornerRadius: 1).frame(width: 18, height: 2)
                    Spacer()
                    RoundedRectangle(cornerRadius: 1).frame(width: 14, height: 2)
                }
                .foregroundStyle(Color(hex: 0xD9D2C4))
                .padding(6)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(Color.white)
            }
        }
        .frame(width: 40, height: 52)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color(hex: 0xE5E7EB)))
        .shadow(color: Color(hex: 0x1F1E1A).opacity(0.12), radius: 3, y: 2)
        .overlay(alignment: .bottomTrailing) {
            SiegelRing(status: beleg.status)
                .offset(x: 5, y: 5)
        }
    }
}

/// Das Siegel als gestaltetes Element: gestrichelt = wartet,
/// Ring = gesiegelt, gefüllt = exportiert-fixiert.
struct SiegelRing: View {
    let status: BelegStatus

    var body: some View {
        ZStack {
            Circle().fill(GC.bg)
            switch status {
            case .offen:
                Circle().stroke(GC.muted, style: StrokeStyle(lineWidth: 1.3, dash: [2.5, 2]))
                Text("·").foregroundStyle(GC.muted)
            case .fixiert:
                Circle().fill(GC.accent)
                Text("✓").foregroundStyle(.white)
            default:
                Circle().stroke(GC.accent, lineWidth: 1.3)
                Text("✓").foregroundStyle(GC.accent)
            }
        }
        .font(.system(size: 8, weight: .bold))
        .frame(width: 16, height: 16)
    }
}

// MARK: - Detail: aufbereitetes Bild + Instant-Reading-Overlay

struct DetailView: View {
    @EnvironmentObject var store: AppStore
    let belegID: UUID

    @State private var zeigeOriginal = false
    @State private var aktiveBox: FeldBox?

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    var body: some View {
        ScrollView {
            if let b = beleg {
                VStack(alignment: .leading, spacing: 14) {
                    belegBild(b)

                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(b.lieferant).font(.headline).fontDesign(.serif)
                            Spacer()
                            Text(fmtEur(b.brutto)).font(.subheadline.monospaced())
                        }
                        BuchsatzView(beleg: b)

                        Text("PROVENANCE")
                            .font(.caption2.monospaced())
                            .kerning(1)
                            .foregroundStyle(GC.muted)

                        provZeile("Quelle", b.bildJpeg == nil ? "Demo-Rendering" : "Kamera-Capture · Original + aufbereitet")
                        provZeile("Extraktion", "On-Device-OCR (Vision) · de-DE · \(b.boxen.count) Felder verortet")
                        provZeile("Kontierung", "\(b.herkunft.rawValue) · Conf \(b.confidence) %")
                        provZeile("Summenprobe", b.summenprobeOK ? "bestanden ✓" : "nicht bestanden")
                        provZeile("Status", b.status.label)

                        if let s = b.siegel, let z = b.siegelZeit {
                            Button {
                                UIPasteboard.general.string = "\(s) · \(DateFormatter.siegel.string(from: z))"
                            } label: {
                                HStack {
                                    Text("\(s) · \(DateFormatter.siegel.string(from: z))")
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(GC.accentHover)
                                    Spacer()
                                    Text("KOPIEREN")
                                        .font(.system(size: 9, design: .monospaced))
                                        .foregroundStyle(GC.muted)
                                }
                                .padding(10)
                                .background(GC.canvas, in: RoundedRectangle(cornerRadius: 8))
                            }
                        }
                    }
                    .gcCard()
                }
                .padding(20)
            }
        }
        .background(GC.canvas)
        .navigationTitle(beleg?.belegNr ?? "Beleg")
        .navigationBarTitleDisplayMode(.inline)
    }

    // Belegbild auf der "Ablage" (Desk), mit antippbaren Feld-Boxen.
    @ViewBuilder
    private func belegBild(_ b: Beleg) -> some View {
        let daten = zeigeOriginal ? b.bildJpeg : (b.bildAufbereitetJpeg ?? b.bildJpeg)
        if let data = daten, let img = UIImage(data: data) {
            VStack(spacing: 10) {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFit()
                    .overlay {
                        if !zeigeOriginal {
                            GeometryReader { geo in
                                ForEach(b.boxen) { box in
                                    feldBox(box, in: geo.size)
                                }
                            }
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .shadow(color: Color(hex: 0x1F1E1A).opacity(0.3), radius: 14, y: 8)
                    .frame(maxHeight: 380)
                    .frame(maxWidth: .infinity)

                if let a = aktiveBox {
                    Text("\(a.label) · \(a.wert)")
                        .font(.caption.monospaced())
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(GC.accent, in: Capsule())
                        .foregroundStyle(.white)
                } else if !b.boxen.isEmpty, !zeigeOriginal {
                    Text("Feld antippen — gelesener Wert wird angezeigt")
                        .font(.caption2)
                        .foregroundStyle(GC.muted)
                }

                if b.bildAufbereitetJpeg != nil, b.bildJpeg != nil {
                    Picker("Fassung", selection: $zeigeOriginal) {
                        Text("Aufbereitet").tag(false)
                        Text("Original").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 240)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(GC.desk, in: RoundedRectangle(cornerRadius: 14))
        }
    }

    private func feldBox(_ box: FeldBox, in size: CGSize) -> some View {
        // Vision-Koordinaten: normiert, Ursprung unten links → SwiftUI oben links.
        let r = box.rect
        let w = max(r.width * size.width, 26)
        let h = max(r.height * size.height, 12)
        let sel = aktiveBox?.id == box.id
        return Rectangle()
            .fill(GC.accent.opacity(sel ? 0.2 : 0.08))
            .overlay(Rectangle().stroke(GC.accent, lineWidth: sel ? 2 : 1.2))
            .frame(width: w, height: h)
            .position(x: r.midX * size.width, y: (1 - r.midY) * size.height)
            .onTapGesture {
                aktiveBox = sel ? nil : box
            }
    }

    private func provZeile(_ key: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(key)
                .font(.caption2.monospaced())
                .foregroundStyle(GC.muted)
                .frame(width: 88, alignment: .leading)
            Text(value)
                .font(.caption.monospaced())
                .foregroundStyle(GC.body)
        }
    }
}
