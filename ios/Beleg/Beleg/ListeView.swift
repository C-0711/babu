import SwiftUI
import UIKit

struct ListeView: View {
    @EnvironmentObject var store: AppStore
    @State private var filter: Filter = .alle
    @State private var zeigeAufraeumen = false
    @State private var loeschKandidat: UUID?

    private var offeneAnzahl: Int {
        store.belege.filter { $0.status == .offen }.count
    }

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
                if offeneAnzahl > 0 {
                    Button {
                        zeigeAufraeumen = true
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "rectangle.stack")
                                .font(.title3)
                                .foregroundStyle(GC.accent)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Aufräumen")
                                    .font(.headline)
                                    .fontDesign(.serif)
                                    .foregroundStyle(GC.fg)
                                Text("\(offeneAnzahl) \(offeneAnzahl == 1 ? "offener Beleg wartet" : "offene Belege warten") — wisch dich durch")
                                    .font(.footnote)
                                    .foregroundStyle(GC.desc)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundStyle(GC.muted)
                        }
                        .padding(.vertical, 4)
                    }
                    .listRowBackground(GC.accentSubtle)
                }
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
                                // Erst nachfragen — gelöscht ist gelöscht,
                                // es gibt keinen Papierkorb.
                                loeschKandidat = b.id
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
            .fullScreenCover(isPresented: $zeigeAufraeumen) {
                AufraeumenView()
            }
            .confirmationDialog("Diesen Beleg endgültig löschen?",
                                isPresented: Binding(get: { loeschKandidat != nil },
                                                     set: { if !$0 { loeschKandidat = nil } }),
                                titleVisibility: .visible) {
                Button("Endgültig löschen", role: .destructive) {
                    if let id = loeschKandidat { store.loeschen(id: id) }
                    loeschKandidat = nil
                }
                Button("Behalten", role: .cancel) { loeschKandidat = nil }
            } message: {
                Text("Foto und alle Angaben sind danach weg.")
            }
        }
    }
}

struct BelegZeile: View {
    let beleg: Beleg

    var body: some View {
        HStack(spacing: 12) {
            // Grüner Haken = alles gut (gebucht + abgelegt + Zweitprüfung OK).
            Image(systemName: beleg.status == .offen ? "circle.dotted" :
                    (beleg.zweitgeprueft || beleg.status == .fixiert)
                    ? "checkmark.seal.fill" : "checkmark.seal")
                .foregroundStyle(beleg.status == .offen ? GC.muted :
                    beleg.zweitgeprueft ? GC.ok : GC.accent)
            VStack(alignment: .leading, spacing: 2) {
                Text(beleg.lieferant)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text("\(beleg.belegNr) · \(beleg.status.label)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.muted)
                if beleg.istDemo == true {
                    Text("BEISPIEL · GEHT NICHT AN DATEV")
                        .font(.system(size: 9, design: .monospaced))
                        .kerning(0.5)
                        .foregroundStyle(GC.muted)
                }
                if beleg.reviewStatus == "fehlgeschlagen" {
                    Text("ZWEITPRÜFUNG NICHT MÖGLICH — FOTO PRÜFEN")
                        .font(.system(size: 9, design: .monospaced))
                        .kerning(0.5)
                        .foregroundStyle(GC.warn)
                } else if beleg.ablageStatus == .fehlgeschlagen {
                    Text("NOCH NICHT ABGELEGT — WIRD ERNEUT VERSUCHT")
                        .font(.system(size: 9, design: .monospaced))
                        .kerning(0.5)
                        .foregroundStyle(GC.warn)
                }
                if beleg.brauchtBewirtungsangaben {
                    HStack(spacing: 4) {
                        Image(systemName: "person.2")
                            .font(.system(size: 9))
                        Text("BEWIRTUNGSANGABEN FEHLEN")
                            .font(.system(size: 9, design: .monospaced))
                            .kerning(0.5)
                    }
                    .foregroundStyle(GC.warn)
                }
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
    @State private var zeigeAlle = false
    @State private var zeigeBewirtung = false
    @State private var zeigeFeldEditor = false
    @State private var zeigeKontierung = false
    @State private var detailBild: UIImage?
    @State private var markierungen: [CGRect] = []

    private var beleg: Beleg? { store.belege.first { $0.id == belegID } }

    // Wie die Ergebnis-Ansicht nach der Aufnahme: das Beleg-Foto groß, die
    // erkannten Felder grün markiert, der grüne Haken als EINZIGES Signal —
    // alles Weitere liegt hinter dem ⓘ oben rechts.
    var body: some View {
        Group {
            if let b = beleg {
                ZStack(alignment: .topTrailing) {
                    VStack(spacing: 12) {
                        belegAnsicht(b)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(b.lieferant)
                                .font(.title3.weight(.semibold))
                                .fontDesign(.serif)
                                .foregroundStyle(GC.fg)
                                .lineLimit(1)
                                .minimumScaleFactor(0.7)
                            // Haken an der Seite — bestätigt, ohne den Beleg zu verdecken.
                            if b.zweitgeprueft || b.status == .fixiert {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 22))
                                    .foregroundStyle(GC.ok)
                                    .accessibilityLabel("Alles in Ordnung")
                            }
                            Spacer()
                            Text(fmtEur(b.brutto))
                                .font(.system(size: 22, weight: .medium, design: .monospaced))
                                .foregroundStyle(GC.fg)
                                .layoutPriority(1)
                        }
                        statusZeile(b)
                    }
                    .padding(.horizontal, 14)
                    .padding(.top, 4)
                    .padding(.bottom, 12)

                    Button {
                        zeigeAlle = true
                    } label: {
                        Image(systemName: "info.circle")
                            .font(.system(size: 20))
                            .foregroundStyle(GC.desc)
                            .frame(width: 40, height: 40)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                    .accessibilityLabel("Alle Angaben zum Beleg")
                    .padding(.trailing, 18)
                    .padding(.top, 6)
                }
            }
        }
        .background(GC.canvas)
        .navigationTitle(beleg?.belegNr ?? "Beleg")
        .navigationBarTitleDisplayMode(.inline)
        .task { await laden() }
        .sheet(isPresented: $zeigeAlle) { alleAngabenSheet }
    }

    // MARK: - Beleg groß, Markierungen, Haken

    @ViewBuilder
    private func belegAnsicht(_ b: Beleg) -> some View {
        Group {
            if let bild = detailBild {
                Image(uiImage: bild)
                    .resizable()
                    .scaledToFit()
                    .overlay {
                        GeometryReader { geo in
                            ZStack {
                                ForEach(Array(markierungen.enumerated()), id: \.offset) { _, r in
                                    RoundedRectangle(cornerRadius: 5)
                                        .fill(GC.ok.opacity(0.16))
                                        .overlay(RoundedRectangle(cornerRadius: 5)
                                            .stroke(GC.ok, lineWidth: 1.6))
                                        .frame(width: r.width * geo.size.width + 10,
                                               height: r.height * geo.size.height + 8)
                                        .position(x: r.midX * geo.size.width,
                                                  y: (1 - r.midY) * geo.size.height)
                                }
                            }
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .shadow(color: Color(hex: 0x1F1E1A).opacity(0.22), radius: 14, y: 7)
            } else {
                RoundedRectangle(cornerRadius: 14)
                    .fill(GC.accentSubtle)
                    .overlay(Image(systemName: "doc.text")
                        .font(.system(size: 34, weight: .light))
                        .foregroundStyle(GC.accent))
            }
        }
    }

    /// Eine leise Zeile statt Warntafeln — Details stehen unterm ⓘ.
    @ViewBuilder
    private func statusZeile(_ b: Beleg) -> some View {
        if b.reviewStatus == "fehlgeschlagen" {
            Text("Der Beleg war schwer zu lesen — am besten neu fotografieren.")
                .font(.footnote)
                .foregroundStyle(GC.warn)
        } else if b.brauchtBewirtungsangaben || b.ablageStatus == .fehlgeschlagen {
            Button {
                zeigeAlle = true
            } label: {
                Label("Ein Hinweis dazu", systemImage: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(GC.muted)
            }
        } else if !b.zweitgeprueft, b.ablageStatus == .uebertragen, b.status != .fixiert {
            Text("Wird gerade noch einmal geprüft …")
                .font(.footnote)
                .foregroundStyle(GC.muted)
        }
    }

    private func laden() async {
        guard let b = beleg else { return }
        if detailBild == nil, let daten = b.bildJpeg {
            detailBild = UIImage(data: daten)
        }
        if markierungen.isEmpty, let bild = detailBild {
            let ocr = await OCRService.erkenne(bild)
            markierungen = FeldMarker.markierungen(zeilen: ocr.zeilen, beleg: b)
        }
        if b.ablageStatus == .uebertragen {
            await reviewLaden(fuer: b)
        }
    }

    // MARK: - ⓘ: alle Angaben (der bisherige Detail-Inhalt)

    private var alleAngabenSheet: some View {
        NavigationStack {
            ScrollView {
                if let b = beleg {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 8) {
                            Text(b.lieferant).font(.headline).fontDesign(.serif)
                            Spacer()
                            Text(fmtEur(b.brutto)).font(.subheadline.monospaced())
                        }
                        BuchsatzView(beleg: b)

                        // Korrektur-Wege: bis zur Fixierung änderbar.
                        if b.status != .fixiert {
                            HStack(spacing: 10) {
                                Button {
                                    zeigeFeldEditor = true
                                } label: {
                                    Label("Angaben korrigieren", systemImage: "pencil")
                                        .font(.caption)
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                                Button {
                                    zeigeKontierung = true
                                } label: {
                                    Label("Kategorie ändern", systemImage: "tray")
                                        .font(.caption)
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            }
                        }

                        if let ablage = b.ablageStatus, ablage != .uebertragen {
                            Button {
                                Task { await store.uebertrage(b.id) }
                            } label: {
                                Label("Jetzt ablegen", systemImage: "arrow.up.doc")
                                    .font(.caption)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }

                        // Bewirtungsangaben (§4 Abs. 5): erfasst zeigen, fehlende nachfragen.
                        if b.konto == "6640" {
                            if b.brauchtBewirtungsangaben {
                                Button {
                                    zeigeBewirtung = true
                                } label: {
                                    Label("Bewirtungsangaben ergänzen (§4 Abs. 5 EStG)",
                                          systemImage: "person.2")
                                        .font(.footnote)
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .tint(GC.warn)
                            } else {
                                provZeile("Anlass", b.bewirtungAnlass ?? "—")
                                provZeile("Personen", (b.bewirtungPersonen ?? "—") + " ✓")
                            }
                        }

                        if b.ablageStatus == .uebertragen {
                            reviewBereich(fuer: b)
                        }

                        if b.siegel != nil, let z = b.siegelZeit {
                            Text("Festgehalten am \(DateFormatter.siegel.string(from: z)) — bleibt unverändert")
                                .font(.caption2)
                                .foregroundStyle(GC.muted)
                        }
                    }
                    .gcCard()
                    .padding(16)
                }
            }
            .background(GC.canvas)
            .navigationTitle("Alle Angaben")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { zeigeAlle = false }
                }
            }
            .sheet(isPresented: $zeigeBewirtung) {
                BewirtungsangabenSheet(belegID: belegID)
            }
            .sheet(isPresented: $zeigeFeldEditor) {
                FeldEditorSheet(belegID: belegID)
            }
            .sheet(isPresented: $zeigeKontierung) {
                ReviewSheet(belegID: belegID, startZeit: Date())
            }
        }
        .presentationDetents([.medium, .large])
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
            Text("ZWEITPRÜFUNG")
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
            .accessibilityLabel("Zweitprüfung aktualisieren")
        }

        if let r = review, r.fehlgeschlagen {
            // Ehrlich statt „läuft noch": die Prüfung hat es versucht und ist
            // an diesem Foto gescheitert.
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.caption2)
                    .foregroundStyle(GC.warn)
                Text("Dieser Beleg konnte nicht gelesen werden. Am besten neu fotografieren und noch einmal ablegen.")
                    .font(.caption)
                    .foregroundStyle(GC.desc)
            }
        } else if let r = review {
            let f = r.felder ?? BelegReviewDaten.Felder()
            if let art = r.einschaetzung?.belegart {
                // Ohne Methoden-Zusatz („semantisch, 30 %") — nur die Einordnung.
                provZeile("Eingeordnet", String(art.split(separator: "(").first ?? "").trimmingCharacters(in: .whitespaces))
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
            if let konto = r.einschaetzung?.kontoSkr04 {
                let gleich = konto == b.konto
                provZeile("Konto", "\(konto) \(Kontenplan.bezeichnung(konto))" + (gleich ? " ✓" : " · Gerät: \(b.konto ?? "—")"))
            }

            // Bild-Lane: direkt aus dem Foto gelesen (ohne Systemnamen).
            if let vlm = r.vlm {
                Text("AUS DEM FOTO")
                    .font(.caption2.monospaced())
                    .kerning(1)
                    .foregroundStyle(GC.muted)
                    .padding(.top, 4)
                if let lieferant = vlm.lieferant {
                    provZeile("Lieferant", lieferant)
                }
                if let trinkgeld = vlm.trinkgeld, trinkgeld > 0 {
                    provZeile("Trinkgeld", fmtEur(trinkgeld))
                }
                if let zahlungsart = vlm.zahlungsart {
                    provZeile("Zahlung", zahlungsart)
                }
                if let positionen = vlm.positionenAnzahl {
                    provZeile("Positionen", "\(positionen)")
                }
            }

            // Das geht an DATEV — jedes Feld als eigene Box, so wie es
            // beim Steuerberater ankommt.
            if let satz = r.buchungssatz, let umsatz = satz.umsatz, let konto = satz.konto {
                Text("DAS GEHT AN DATEV")
                    .font(.caption2.monospaced())
                    .kerning(1)
                    .foregroundStyle(GC.muted)
                    .padding(.top, 4)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()),
                                    GridItem(.flexible())], spacing: 8) {
                    datevBox("Umsatz", "\(umsatz) \(satz.sollHaben ?? "S")")
                    datevBox("Konto", konto)
                    datevBox("Gegenkonto", satz.gegenkonto ?? "—")
                    datevBox("Steuer (BU)", satz.buSchluessel ?? "—")
                    datevBox("Belegdatum", satz.belegdatum ?? "—")
                    datevBox("Belegfeld 1", satz.belegfeld1 ?? "—")
                }
                if let text = satz.buchungstext {
                    datevBox("Buchungstext", text)
                }
            }
            ForEach(r.einschaetzung?.hinweise ?? [], id: \.self) { hinweis in
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

    /// Ein DATEV-Feld als Box: kleines Label, Mono-Wert.
    private func datevBox(_ label: String, _ wert: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label.uppercased())
                .font(.system(size: 8, design: .monospaced))
                .kerning(0.5)
                .foregroundStyle(GC.muted)
            Text(wert)
                .font(.caption.monospaced())
                .foregroundStyle(GC.fg)
                .lineLimit(2)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color(hex: 0xE8E4DC), lineWidth: 1))
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
                    Text("Prüfung: \(server) · Aufnahme: \(lokal)")
                        .font(.caption.monospaced())
                        .foregroundStyle(GC.warn)
                }
            } else {
                Text("Prüfung: — · Aufnahme: \(lokal)")
                    .font(.caption.monospaced())
                    .foregroundStyle(GC.muted)
            }
        }
    }

    private func reviewLaden(fuer b: Beleg) async {
        guard let dateiname = b.ablageDateiname,
              let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            reviewHinweis = "Für die Zweitprüfung bitte die Belegbox verbinden (Export → Zahnrad)."
            return
        }
        reviewLaedt = true
        defer { reviewLaedt = false }
        let stamm = (dateiname as NSString).deletingPathExtension
        switch await AblageService.reviewAbrufen(stamm: stamm, basis: url, pat: pat) {
        case .fertig(let r):
            review = r
            reviewHinweis = nil
            // Audit-Stempel am Beleg persistieren — sichtbar in der Belegliste.
            if let audit = r.audit {
                store.auditSetzen(id: b.id, aufnahme: audit.aufnahme?.commit,
                                  review: audit.review?.commit,
                                  status: r.fehlgeschlagen ? "fehlgeschlagen" : "ok")
            }
        case .nochNicht where review == nil:
            reviewHinweis = "Zweitprüfung läuft — gleich verfügbar (↻ zum Aktualisieren)."
        case .zugangFehlt:
            reviewHinweis = "Der Zugang zur Belegbox ist abgelaufen — einmal neu verbinden (Export → Zahnrad)."
        case .keineVerbindung where review == nil:
            reviewHinweis = "Gerade keine Verbindung — später noch einmal versuchen."
        case .serverProblem where review == nil:
            reviewHinweis = "Die Belegbox meldet einen Fehler — später noch einmal versuchen."
        default:
            break   // Es gibt schon ein Ergebnis — das behalten wir.
        }
    }
}
