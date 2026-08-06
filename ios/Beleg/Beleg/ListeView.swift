import SwiftUI
import UIKit

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

    var body: some View {
        NavigationStack {
            List {
                if let d = store.durchsatzText {
                    Text(d)
                        .font(.caption.monospaced())
                        .foregroundStyle(GC.muted)
                        .listRowBackground(GC.canvas)
                }
                ForEach(gefiltert) { b in
                    NavigationLink(value: b.id) {
                        BelegZeile(beleg: b)
                    }
                }
                if gefiltert.isEmpty {
                    Text("Kein Beleg entspricht diesem Filter.")
                        .foregroundStyle(GC.muted)
                }
            }
            .navigationTitle("Belege")
            .navigationDestination(for: UUID.self) { id in
                DetailView(belegID: id)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Picker("Filter", selection: $filter) {
                        ForEach(Filter.allCases) { f in
                            Text(f.rawValue).tag(f)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }
        }
    }
}

struct BelegZeile: View {
    let beleg: Beleg

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: beleg.status == .offen ? "circle.dotted" :
                    beleg.status == .fixiert ? "checkmark.seal.fill" : "checkmark.seal")
                .foregroundStyle(beleg.status == .offen ? GC.muted : GC.accent)
            VStack(alignment: .leading, spacing: 2) {
                Text(beleg.lieferant)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text("\(beleg.belegNr) · \(beleg.status.label)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.muted)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(fmtEur(beleg.brutto))
                    .font(.subheadline.monospaced())
                Text(beleg.konto.map { "\($0) · \(beleg.ksLabel)" } ?? "ohne Konto")
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.muted)
            }
        }
    }
}

struct DetailView: View {
    @EnvironmentObject var store: AppStore
    let belegID: UUID

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    var body: some View {
        ScrollView {
            if let b = beleg {
                VStack(alignment: .leading, spacing: 14) {
                    if let data = b.bildJpeg, let img = UIImage(data: data) {
                        Image(uiImage: img)
                            .resizable()
                            .scaledToFit()
                            .frame(maxHeight: 320)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .shadow(color: Color(hex: 0x1F1E1A).opacity(0.25), radius: 12, y: 6)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                    }

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

                        provZeile("Quelle", b.bildJpeg == nil ? "Demo-Rendering" : "Kamera-Capture, entzerrt")
                        provZeile("Extraktion", "On-Device-OCR (Vision) · de-DE")
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
