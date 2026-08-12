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
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if b.status != .fixiert {
                            Button(role: .destructive) {
                                store.loeschen(id: b.id)
                            } label: {
                                Label("Löschen", systemImage: "trash")
                            }
                        }
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

    @State private var review: BelegReviewDaten?
    @State private var reviewLaedt = false
    @State private var reviewHinweis: String?

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
                        if let ablage = b.ablageStatus {
                            switch ablage {
                            case .uebertragen:
                                provZeile("Belegbox", "übertragen ✓" + (b.ablageZeit.map {
                                    " · " + DateFormatter.siegel.string(from: $0)
                                } ?? ""))
                            case .ausstehend:
                                provZeile("Belegbox", "Übertragung ausstehend")
                            case .fehlgeschlagen:
                                provZeile("Belegbox", "Übertragung fehlgeschlagen")
                            }
                            if ablage != .uebertragen {
                                Button {
                                    Task { await store.uebertrage(b.id) }
                                } label: {
                                    Label("Jetzt übertragen", systemImage: "arrow.up.doc")
                                        .font(.caption)
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }
                        }

                        if b.ablageStatus == .uebertragen {
                            reviewBereich(fuer: b)
                        }

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
        .task {
            if let b = beleg, b.ablageStatus == .uebertragen {
                await reviewLaden(fuer: b)
            }
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

    // MARK: - BelegReview (Server-Lane)

    @ViewBuilder
    private func reviewBereich(fuer b: Beleg) -> some View {
        Divider().padding(.vertical, 2)
        HStack {
            Text("BELEGREVIEW · SERVER")
                .font(.caption2.monospaced())
                .kerning(1)
                .foregroundStyle(GC.muted)
            Spacer()
            Button {
                Task { await reviewLaden(fuer: b) }
            } label: {
                if reviewLaedt {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: "arrow.clockwise")
                        .font(.caption2)
                }
            }
            .accessibilityLabel("Review aktualisieren")
        }

        if let r = review {
            let f = r.felder
            provZeile("Engine", "\(r.engine ?? "Server-OCR") · \(r.zeilen ?? 0) Zeilen · ø \(Int((r.ocrKonfidenz ?? 0) * 100)) %")
            if let art = r.einschaetzung.belegart {
                provZeile("Belegart", art)
            }
            vergleich("Brutto", lokal: fmtEur(b.brutto), server: f.brutto.map(fmtEur),
                      gleich: f.brutto.map { abs($0 - b.brutto) < 0.011 })
            vergleich("Netto", lokal: fmtEur(b.netto), server: f.netto.map(fmtEur),
                      gleich: f.netto.map { abs($0 - b.netto) < 0.011 })
            vergleich("USt", lokal: fmtEur(b.ust), server: f.ust.map(fmtEur),
                      gleich: f.ust.map { abs($0 - b.ust) < 0.011 })
            vergleich("Datum", lokal: b.datumText, server: f.datum,
                      gleich: f.datum.map { $0 == b.datumText })
            vergleich("Beleg-Nr.", lokal: b.belegNr, server: f.belegNr,
                      gleich: f.belegNr.map { $0 == b.belegNr })
            if let konto = r.einschaetzung.kontoSkr04 {
                let gleich = konto == b.konto
                provZeile("Konto", "\(konto) \(Kontenplan.bezeichnung(konto))" + (gleich ? " ✓" : " · Gerät: \(b.konto ?? "—")"))
            }
            ForEach(r.einschaetzung.hinweise ?? [], id: \.self) { hinweis in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "info.circle")
                        .font(.caption2)
                        .foregroundStyle(GC.accent)
                    Text(hinweis)
                        .font(.caption)
                        .foregroundStyle(GC.desc)
                }
            }
            ForEach(f.offen ?? [], id: \.self) { punkt in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "questionmark.circle")
                        .font(.caption2)
                        .foregroundStyle(GC.warn)
                    Text(punkt)
                        .font(.caption)
                        .foregroundStyle(GC.desc)
                }
            }
        } else if let hinweis = reviewHinweis {
            Text(hinweis)
                .font(.caption)
                .foregroundStyle(GC.muted)
        }
    }

    /// Abgleich Gerät ↔ Server: ✓ bei Übereinstimmung, sonst beide Werte.
    private func vergleich(_ key: String, lokal: String, server: String?, gleich: Bool?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(key)
                .font(.caption2.monospaced())
                .foregroundStyle(GC.muted)
                .frame(width: 88, alignment: .leading)
            if let server {
                if gleich == true {
                    Text("\(server) ✓")
                        .font(.caption.monospaced())
                        .foregroundStyle(GC.ok)
                } else {
                    Text("Server: \(server) · Gerät: \(lokal)")
                        .font(.caption.monospaced())
                        .foregroundStyle(GC.warn)
                }
            } else {
                Text("Server: — · Gerät: \(lokal)")
                    .font(.caption.monospaced())
                    .foregroundStyle(GC.muted)
            }
        }
    }

    private func reviewLaden(fuer b: Beleg) async {
        guard let dateiname = b.ablageDateiname,
              let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            reviewHinweis = "Review braucht Server-URL und PAT (Einstellungen)."
            return
        }
        reviewLaedt = true
        defer { reviewLaedt = false }
        let stamm = (dateiname as NSString).deletingPathExtension
        if let r = await AblageService.reviewAbrufen(stamm: stamm, basis: url, pat: pat) {
            review = r
            reviewHinweis = nil
        } else if review == nil {
            reviewHinweis = "Noch kein Review — der Server liest gerade (↻ zum Aktualisieren)."
        }
    }
}
