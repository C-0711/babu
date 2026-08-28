import SwiftUI
import UIKit

struct ListeView: View {
    @EnvironmentObject var store: AppStore
    @State private var filter: Filter = .alle
    @State private var zeigeAufraeumen = false
    @State private var loeschKandidat: UUID?
    /// Welche Art gerade gezeigt wird. Belege sind die Voreinstellung —
    /// das ist der häufigste Fall und der Grund, warum es die App gibt.
    @State private var art: Dokumentart = .beleg
    // Server-Ablage des gewählten Fachs (Portal-Uploads, Kanzlei-Post).
    @State private var serverStuecke: [AblageService.AblageStueck] = []
    @State private var serverLaedt = false
    @State private var grossAnsehen: Grossansicht?
    /// Der Weg des Stapels. Die Liste schiebt über NavigationLink, die
    /// Blätter schieben selbst — ein Link in einer Listenzeile bekommt vom
    /// System einen Pfeil, und der stand neben jeder Kachel.
    @State private var pfad = NavigationPath()
    /// Die Wahl zwischen Liste und Blättern bleibt bestehen. Wer einmal
    /// entschieden hat, wie er sucht, will nicht bei jedem Start neu wählen.
    @AppStorage("dokumentansicht") private var ansichtRoh = Dokumentansicht.liste.rawValue
    private var ansicht: Dokumentansicht {
        Dokumentansicht(rawValue: ansichtRoh) ?? .liste
    }

    /// Wie viele Dokumente je Art da sind — für die Zahl am Reiter.
    private var anzahlJeArt: [Dokumentart: Int] {
        Dictionary(grouping: store.belege, by: Dokumentart.von).mapValues(\.count)
    }

    private var offeneAnzahl: Int {
        store.belege.filter { $0.status == .offen }.count
    }

    /// Belege, bei denen die Buchhaltung auf Ninas Antwort wartet.
    private var fragenBelege: [Beleg] {
        store.belege.filter { $0.status == .offen && $0.offeneFrage != nil }
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
        store.belege.filter { Dokumentart.von($0) == art }.filter { b in
            switch filter {
            case .alle: return true
            case .automatisch: return b.status == .automatisch
            case .bestaetigt: return b.status == .bestaetigt
            case .korrigiert: return b.status == .korrigiert
            case .offen: return b.status == .offen
            }
        }
    }

    /// Die Server-Ablage des Fachs holen — lokale Aufnahmen, die schon
    /// übertragen sind, stehen dort ebenfalls; die lokale Liste oben zeigt
    /// sie mit Status, hier geht es um das, was NUR auf dem Server liegt.
    private func serverStueckeLaden() async {
        serverStuecke = []
        // Auch die BELEGE: sie lagen bisher nur lokal auf dem Telefon, das
        // sie fotografiert hat. Auf einem zweiten Gerät — oder wenn eine
        // Kollegin dieselbe Belegbox öffnet — war der Reiter leer, während
        // im Portal alles stand. Doppelt gezeigt wird nichts; die Prüfung
        // gegen `lokaleNamen` unten gab es längst.
        guard store.ablageAktiv,
              let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        serverLaedt = true
        defer { serverLaedt = false }
        let alle = await AblageService.ablageStuecke(art: art.rawValue, basis: url, pat: pat)
        // Was die App selbst hochgeladen hat, steht schon oben in der
        // lokalen Liste — nicht doppelt zeigen.
        let lokaleNamen = Set(store.belege.compactMap(\.ablageDateiname))
        serverStuecke = alle.filter { s in
            !lokaleNamen.contains((s.pfad as NSString).lastPathComponent)
        }
    }

    /// Die Arten als Reiter. Belege stehen vorn und sind voreingestellt —
    /// alles andere ist die Ausnahme, auch wenn es wichtig ist.
    private var artenLeiste: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Dokumentart.allCases) { a in
                    let anzahl = anzahlJeArt[a] ?? 0
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) { art = a }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: a.symbol).font(.system(size: 12))
                            Text(a.name).font(.subheadline)
                            if anzahl > 0 {
                                Text("\(anzahl)")
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(art == a ? GC.fg : GC.muted)
                            }
                        }
                        .padding(.horizontal, 13).padding(.vertical, 8)
                        .background(art == a ? GC.accentSubtle : GC.bg,
                                    in: Capsule())
                        .overlay(Capsule().stroke(art == a ? GC.accent : GC.linie,
                                                  lineWidth: 1))
                        .foregroundStyle(art == a ? GC.fg : GC.desc)
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(art == a ? [.isSelected] : [])
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 2)
        }
    }

    var body: some View {
        NavigationStack(path: $pfad) {
            List {
                // Was ansteht, steht oben — dort schaut sie ohnehin hin.
                MonatslaufKarte()
                MeldungenAbschnitt()
                BelegjagdAbschnitt()
                if let erster = fragenBelege.first {
                    // Die Fragen sind der schnellste Weg zum grünen Haken —
                    // deshalb ganz oben und so groß wie der Kassenbuch-Knopf.
                    Button {
                        pfad.append(erster.id)
                    } label: {
                        Label(fragenBelege.count == 1
                              ? "babu hat Fragen zu einem Beleg"
                              : "babu hat Fragen zu \(fragenBelege.count) Belegen",
                              systemImage: "questionmark.bubble")
                            .font(.title3.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .listRowBackground(GC.canvas)
                    .listRowSeparator(.hidden)
                }
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
                artenLeiste
                    .listRowInsets(EdgeInsets(top: 6, leading: 0, bottom: 6, trailing: 0))
                    .listRowBackground(GC.canvas)

                if ansicht == .blaetter {
                    DokumentBlaetter(dokumente: gefiltert,
                                     grossAnsehen: $grossAnsehen) { pfad.append($0) }
                        .listRowInsets(EdgeInsets(top: 0, leading: 12, bottom: 8, trailing: 12))
                        .listRowBackground(GC.canvas)
                        .listRowSeparator(.hidden)
                } else {
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
                }
                if gefiltert.isEmpty && serverStuecke.isEmpty {
                    Text(filter == .alle ? art.leerSatz
                                         : "Kein \(art.einzahl) entspricht diesem Filter.")
                        .font(.footnote)
                        .foregroundStyle(GC.muted)
                        .listRowBackground(GC.canvas)
                }
                // Kontoauszüge, Verträge und Post kommen oft übers Portal
                // herein und liegen dann NUR in der Server-Ablage — bis
                // 27.08.2026 zeigte die App sie gar nicht („warum kommen
                // die Kontoauszüge nicht in der App?"). Seit dem 28.08.
                // gilt dasselbe für die Belege: was auf einem anderen Gerät
                // fotografiert wurde, gehört auch hierher.
                Group {
                    if serverLaedt && serverStuecke.isEmpty {
                        HStack { ProgressView(); Text("Deine Ablage wird geholt …") }
                            .font(.footnote)
                            .foregroundStyle(GC.muted)
                            .listRowBackground(GC.canvas)
                    }
                    if !serverStuecke.isEmpty {
                        Section("In deiner Ablage") {
                            ForEach(serverStuecke) { s in
                                AblageStueckZeile(stueck: s)
                            }
                        }
                    }
                }
            }
            .task(id: art) { await serverStueckeLaden() }
            .warmerGrund()
            .navigationTitle("Dokumente")
            .mitMeldenKnopf("Dokumente")
            .mitKontoMenu()
            .navigationDestination(for: UUID.self) { id in
                DetailView(belegID: id)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            ansichtRoh = ansicht.andere.rawValue
                        }
                    } label: {
                        Image(systemName: ansicht.symbol)
                    }
                    .accessibilityLabel(ansicht.andere.name)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Picker("Filter", selection: $filter) {
                        ForEach(Filter.allCases) { f in
                            Text(f.rawValue).tag(f)
                        }
                    }
                    .pickerStyle(.menu)
                }
            }
            .sheet(item: $grossAnsehen) { auswahl in
                if let b = store.belege.first(where: { $0.id == auswahl.id }) {
                    BelegGrossView(beleg: b).environmentObject(store)
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
            // Grüner Haken = alles gut (gebucht + abgelegt + Archiv bestätigt).
            Image(systemName: beleg.status == .offen ? "circle.dotted" :
                    (beleg.archivBestaetigt || beleg.status == .fixiert)
                    ? "checkmark.seal.fill" : "checkmark.seal")
                .foregroundStyle(beleg.status == .offen ? GC.muted :
                    beleg.archivBestaetigt ? GC.ok : GC.accent)
            VStack(alignment: .leading, spacing: 2) {
                Text(beleg.lieferant)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text("\(beleg.belegNr) · \(beleg.status.label)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.muted)
                if beleg.status == .offen, beleg.offeneFrage != nil {
                    Text("Noch nicht fertig — babu hat Fragen")
                        .font(.caption2)
                        .foregroundStyle(GC.warn)
                }
                if beleg.istDemo == true {
                    Text("BEISPIEL · GEHT NICHT AN DATEV")
                        .font(.system(size: 9, design: .monospaced))
                        .kerning(0.5)
                        .foregroundStyle(GC.muted)
                }
                if beleg.reviewStatus == "fehlgeschlagen" {
                    Text("NICHT LESBAR — FOTO PRÜFEN")
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
    @Environment(\.dismiss) private var zurueck
    let belegID: UUID

    @State private var review: BelegReviewDaten?
    @State private var reviewLaedt = false
    @State private var reviewHinweis: String?
    @State private var zeigeAlle = false
    @State private var zeigeBewirtung = false
    @State private var zeigeFeldEditor = false
    @State private var zeigeKontierung = false
    @State private var detailBild: UIImage?
    @State private var zeigeLoeschen = false
    @State private var zeigeBuchungsfragen = false

    /// Der Name, unter dem der Beleg in der Belegbox liegt — ohne ihn gibt
    /// es kein Protokoll abzuholen.
    private var protokollStamm: String? {
        guard let name = beleg?.ablageDateiname else { return nil }
        return (name as NSString).deletingPathExtension
    }

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
                            if b.archivBestaetigt || b.status == .fixiert {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.system(size: 22))
                                    .foregroundStyle(GC.ok)
                                    .accessibilityLabel("Alles in Ordnung")
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 1) {
                                Text(fmtEur(b.brutto))
                                    .font(.system(size: 22, weight: .medium, design: .monospaced))
                                    .foregroundStyle(GC.fg)
                                if let w = b.fremdWaehrung, let orig = b.fremdBetrag {
                                    Text("\(orig, format: .number.precision(.fractionLength(2))) \(w) umgerechnet")
                                        .font(.caption2.monospacedDigit())
                                        .foregroundStyle(GC.desc)
                                }
                            }
                            .layoutPriority(1)
                        }
                        if let satz = review?.zusammenfassung, !satz.isEmpty {
                            // Was auf dem Beleg los war, in einer Zeile —
                            // damit man ihn wiedererkennt, ohne ihn zu öffnen.
                            Text(satz)
                                .font(.footnote)
                                .foregroundStyle(GC.desc)
                                .frame(maxWidth: .infinity, alignment: .leading)
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
        .sheet(isPresented: $zeigeBuchungsfragen) {
            BuchungsfragenView(belegID: belegID)
                .environmentObject(store)
        }
        .sheet(isPresented: $zeigeAlle) { alleAngabenSheet }
        .confirmationDialog("Diesen Beleg endgültig löschen?",
                            isPresented: $zeigeLoeschen, titleVisibility: .visible) {
            Button("Endgültig löschen", role: .destructive) {
                zeigeAlle = false
                store.loeschen(id: belegID)
                zurueck()
            }
            Button("Behalten", role: .cancel) {}
        } message: {
            Text("Foto und alle Angaben sind danach weg. Richtig so, wenn der Beleg gar nicht zu dir gehört.")
        }
    }

    // MARK: - Beleg groß, Markierungen, Haken

    @ViewBuilder
    private func belegAnsicht(_ b: Beleg) -> some View {
        Group {
            if let bild = detailBild {
                // Belege sind klein gedruckt — hineinzoomen können reicht.
                // Die grünen Fundstellen-Kästen sind raus (24.08.2026,
                // Christoph): sie verdeckten den Beleg mehr, als sie halfen;
                // was gelesen wurde, steht hinterm ⓘ.
                ZoombaresBild(bild: bild) { _ in EmptyView() }
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
        } else if b.status == .offen, store.ablageAktiv, !b.ocrText.isEmpty {
            // Die Buchhaltung hat Fragen — der wichtigste Knopf der Seite,
            // deshalb so groß wie „Ins Kassenbuch eintragen".
            Button {
                zeigeBuchungsfragen = true
            } label: {
                Label("babu hat Fragen — jetzt beantworten",
                      systemImage: "questionmark.bubble")
                    .font(.title3.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        } else if !b.archivBestaetigt, b.ablageStatus == .uebertragen, b.status != .fixiert {
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
                        if let satz = review?.zusammenfassung, !satz.isEmpty {
                            Text(satz)
                                .font(.footnote)
                                .foregroundStyle(GC.desc)
                        }

                        // Zuoberst, weil es die Frage beantwortet, mit der man
                        // das ⓘ überhaupt öffnet: was hat babu da gelesen?
                        if let stamm = protokollStamm {
                            NavigationLink {
                                ProtokollView(stamm: stamm).environmentObject(store)
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "text.magnifyingglass")
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text("Was babu gelesen hat")
                                            .font(.subheadline.weight(.medium))
                                        Text("Jede Zeile, und zu jedem Wert die Stelle "
                                             + "auf dem Beleg")
                                            .font(.caption2)
                                            .foregroundStyle(GC.muted)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right")
                                        .font(.caption2)
                                        .foregroundStyle(GC.muted)
                                }
                                .foregroundStyle(GC.fg)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(GC.accentSubtle,
                                            in: RoundedRectangle(cornerRadius: 10))
                            }
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
                                if b.status != .fixiert, store.ablageAktiv,
                                   !b.ocrText.isEmpty {
                                    // Die Buchhaltung noch einmal ranlassen —
                                    // heilt Altfälle (Fremdwährung, falsches
                                    // Konto) mit einer frischen Einschätzung.
                                    Button {
                                        zeigeAlle = false
                                        zeigeBuchungsfragen = true
                                    } label: {
                                        Label("Neu einschätzen & buchen",
                                              systemImage: "questionmark.bubble")
                                            .font(.caption)
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                                }
                            }

                            // Fremder Beleg im Stapel? Muss ohne Wischgeste
                            // wegzubekommen sein — Rückfrage kommt danach.
                            Button(role: .destructive) {
                                zeigeLoeschen = true
                            } label: {
                                Label("Gehört nicht zu mir — löschen", systemImage: "trash")
                                    .font(.caption)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .tint(GC.warn)
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
            Text("PRÜFUNG")
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
            .accessibilityLabel("Prüfung aktualisieren")
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
            gelesen("Brutto", f.brutto.map(fmtEur))
            gelesen("Netto", f.netto.map(fmtEur))
            gelesen("USt", f.ust.map(fmtEur))
            gelesen("Datum", f.datum)
            gelesen("Beleg-Nr.", f.belegNr)
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
            ForEach(f.widerspruch ?? [], id: \.self) { abweichung in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "arrow.triangle.branch")
                        .font(.caption2)
                        .foregroundStyle(GC.warn)
                    Text(abweichung)
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
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(GC.linie, lineWidth: 1))
    }

    /// Ein Wert aus dem archivierten Ergebnis.
    ///
    /// Hier stand einmal „Prüfung: X · Aufnahme: Y" — ein Vergleich zwischen
    /// dem, was das Gerät gelesen hatte, und dem, was der Server las. Seit
    /// die App den Serverwert übernimmt, stimmen beide immer überein, und
    /// aus dem Vergleich würde ein Haken, den sich niemand verdient hat:
    /// zwei Lesungen, die sich einig sind, obwohl es nur eine ist.
    ///
    /// Der echte Gegencheck steht weiter unten als „Widerspruch" — dort
    /// vergleicht der Server seine eigene Lesung mit der des Bildmodells.
    private func gelesen(_ key: String, _ wert: String?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(key)
                .font(.caption2.monospaced())
                .foregroundStyle(GC.muted)
                .frame(width: 88, alignment: .leading)
            Text(wert?.isEmpty == false ? wert! : "nicht gelesen")
                .font(.caption.monospaced())
                .foregroundStyle(wert?.isEmpty == false ? GC.body : GC.muted)
        }
    }

    private func reviewLaden(fuer b: Beleg) async {
        guard let dateiname = b.ablageDateiname,
              let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            reviewHinweis = "Für die Prüfung bitte die Belegbox verbinden (Export → Zahnrad)."
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
            reviewHinweis = "Wird noch gelesen — gleich verfügbar (↻ zum Aktualisieren)."
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

/// Eine Zeile der Server-Ablage: Vorschau, Name, Datum, Seitenzahl.
/// Tippen öffnet das Blatt groß (Seite 1 — mehr Seiten zeigt das Portal).
private struct AblageStueckZeile: View {
    @EnvironmentObject var store: AppStore
    let stueck: AblageService.AblageStueck

    @State private var vorschau: UIImage?
    @State private var gross = false

    private var datumText: String {
        guard let zeit = stueck.zeit, zeit.count >= 10 else { return "" }
        let teile = zeit.prefix(10).split(separator: "-")
        guard teile.count == 3 else { return String(zeit.prefix(10)) }
        return "\(teile[2]).\(teile[1]).\(teile[0])"
    }

    var body: some View {
        Button {
            gross = true
        } label: {
            HStack(spacing: 12) {
                Group {
                    if let vorschau {
                        Image(uiImage: vorschau)
                            .resizable()
                            .scaledToFill()
                    } else {
                        GC.desk.overlay(
                            Image(systemName: "doc.text")
                                .font(.system(size: 16, weight: .light))
                                .foregroundStyle(GC.muted))
                    }
                }
                .frame(width: 42, height: 54)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                VStack(alignment: .leading, spacing: 2) {
                    Text(stueck.name)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(GC.fg)
                        .lineLimit(1)
                    HStack(spacing: 6) {
                        if !datumText.isEmpty {
                            Text(datumText)
                                .font(.caption.monospaced())
                                .foregroundStyle(GC.muted)
                        }
                        if let seiten = stueck.seiten, seiten > 1 {
                            Text("\(seiten) Seiten")
                                .font(.caption.monospaced())
                                .foregroundStyle(GC.accent)
                        }
                    }
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(GC.muted)
            }
        }
        .task {
            guard vorschau == nil, store.ablageAktiv,
                  let url = URL(string: store.ablageURL),
                  let pat = KeychainHelfer.ladePAT() else { return }
            vorschau = await AblageService.vorschauLaden(pfad: stueck.pfad,
                                                         basis: url, pat: pat)
        }
        .sheet(isPresented: $gross) {
            NavigationStack {
                Group {
                    if let vorschau {
                        ZoombaresBild(bild: vorschau)
                    } else {
                        ProgressView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(GC.canvas)
                .navigationTitle(stueck.name)
                .toolbarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Fertig") { gross = false }
                    }
                }
            }
        }
    }
}
