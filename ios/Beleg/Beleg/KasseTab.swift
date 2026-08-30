import SwiftUI

/// Kassenbuch: ein Kalender zeigt auf einen Blick, an welchen Tagen es
/// geführt wurde (grüner Punkt), und für jeden Tag gibt es den
/// Frage-Ablauf — eine Zahl pro Schritt, groß und in einfacher Sprache.
///
/// Ein Name für die Sache: die App führt das **Kassenbuch**. Das Wort
/// „Kasse" bleibt der Schublade vorbehalten — sie ist es, die abends
/// stimmt oder nicht. Die Wörter stehen in `Kassenwort`.
struct KasseTab: View {
    @EnvironmentObject var store: AppStore

    @State private var monat = Date()
    @State private var gewaehlt = KassenTag.schluessel(Date())
    @State private var workflow: TagRef?
    @State private var ausgaben: AusgabenStand = .laedt

    private struct TagRef: Identifiable { let id: String }

    /// Vier unterscheidbare Lagen — „keine Verbindung" ist etwas anderes als
    /// „noch nie verbunden", und beides ist etwas anderes als „rechnet noch".
    private enum AusgabenStand {
        case laedt
        case nichtVerbunden
        case keineVerbindung
        case da(Monatsabschluss)
    }

    private var kal: Calendar { KassenTag.kalender }
    private var heute: String { KassenTag.schluessel(Date()) }
    private var gepflegteTage: Set<String> { Set(store.kassenberichte.map(\.datum)) }

    private var monatSchluessel: String {
        let f = DateFormatter()
        f.calendar = kal
        f.dateFormat = "yyyy-MM"
        return f.string(from: monat)
    }

    /// Die Zahlen des Monats sieht nur die Inhaberin — der Server antwortet
    /// einer Mitarbeiterin mit 403. Ohne diese Prüfung stünde bei ihr
    /// dauerhaft „keine Verbindung", was schlicht nicht stimmt.
    private var darfZahlenSehen: Bool { store.verbundenRolle != "mitarbeit" }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    kalenderKarte
                    tagesKarte
                    if darfZahlenSehen { ausgabenKarte }
                }
                .padding(16)
            }
            .background(GC.canvas)
            .warmerGrund()
            .navigationTitle(Kassenwort.buch)
            .mitMeldenKnopf(Kassenwort.buch)
            .toolbarTitleDisplayMode(.inline)
            .mitKontoMenu()
            .fullScreenCover(item: $workflow) { ref in
                KassenberichtWorkflow(tag: ref.id)
            }
            .task(id: monatSchluessel) {
                await ausgabenLaden(fuer: monatSchluessel)
            }
        }
    }

    // MARK: - Kalender

    private var kalenderKarte: some View {
        VStack(spacing: 12) {
            HStack {
                Button {
                    monat = kal.date(byAdding: .month, value: -1, to: monat) ?? monat
                } label: {
                    Image(systemName: "chevron.left")
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Voriger Monat")
                Spacer()
                Text(monatsTitel)
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                Spacer()
                Button {
                    monat = kal.date(byAdding: .month, value: 1, to: monat) ?? monat
                } label: {
                    Image(systemName: "chevron.right")
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Nächster Monat")
            }
            .foregroundStyle(GC.fg)

            HStack {
                ForEach(["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], id: \.self) { w in
                    Text(w)
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                        .frame(maxWidth: .infinity)
                }
            }

            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 8) {
                ForEach(Array(tageDesMonats.enumerated()), id: \.offset) { _, tag in
                    if let tag {
                        tagZelle(tag)
                    } else {
                        Color.clear.frame(height: 44)
                    }
                }
            }
        }
        .gcCard()
    }

    private func tagZelle(_ tag: String) -> some View {
        let gepflegt = gepflegteTage.contains(tag)
        let istHeute = tag == heute
        let zukunft = tag > heute
        let nummer = String(Int(tag.suffix(2)) ?? 0)
        return Button {
            gewaehlt = tag
        } label: {
            ZStack {
                if gepflegt {
                    Circle().fill(GC.ok)
                } else if tag == gewaehlt {
                    Circle().fill(GC.accentSubtle)
                }
                if istHeute && !gepflegt {
                    Circle().stroke(GC.accent, lineWidth: 1.5)
                }
                if tag == gewaehlt {
                    Circle().stroke(GC.fg.opacity(0.55), lineWidth: 1.5)
                }
                Text(nummer)
                    .font(.system(size: 17, weight: gepflegt ? .semibold : .regular))
                    .foregroundStyle(gepflegt ? .white : zukunft ? GC.muted : GC.body)
            }
            .frame(height: 44)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(KassenTag.anzeige(tag))"
                            + (gepflegt ? ", im \(Kassenwort.buch) eingetragen" : ""))
    }

    private var monatsTitel: String {
        let f = DateFormatter()
        f.calendar = kal
        f.locale = Locale(identifier: "de_DE")
        f.dateFormat = "LLLL yyyy"
        return f.string(from: monat)
    }

    /// Zellen des Monats: führende nil-Zellen bis zum Wochentag des 1.,
    /// dann die Tag-Schlüssel.
    private var tageDesMonats: [String?] {
        guard let erster = kal.date(from: kal.dateComponents([.year, .month], from: monat)),
              let bereich = kal.range(of: .day, in: .month, for: erster) else { return [] }
        let wochentag = kal.component(.weekday, from: erster)          // 1 = So
        let fuehrend = (wochentag - kal.firstWeekday + 7) % 7
        var zellen: [String?] = Array(repeating: nil, count: fuehrend)
        for tag in bereich {
            if let datum = kal.date(byAdding: .day, value: tag - 1, to: erster) {
                zellen.append(KassenTag.schluessel(datum))
            }
        }
        return zellen
    }

    // MARK: - Tageskarte

    @ViewBuilder
    private var tagesKarte: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(KassenTag.anzeige(gewaehlt))
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)

            if let b = store.kassenbericht(fuer: gewaehlt) {
                HStack(spacing: 10) {
                    Image(systemName: b.kasseStimmt ? "checkmark.circle.fill" : "info.circle")
                        .font(.system(size: 28))
                        .foregroundStyle(b.kasseStimmt ? GC.ok : GC.warn)
                    Text(b.kasseStimmt ? Kassenwort.stimmt
                         : "Unterschied: \(fmtEur(b.differenz)) — ist notiert.")
                        .font(.body.weight(.medium))
                        .foregroundStyle(GC.fg)
                }
                if let grund = b.differenzGrund, !grund.isEmpty {
                    Text("Grund: \(grund)")
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                }
                zeile("Bargeld eingenommen", fmtEur(b.einnahmenBar))
                zeile("Mit Karte bezahlt", fmtEur(b.ecZahlungen))
                if b.gutscheinVerkauf > 0 {
                    zeile("Gutscheine verkauft", fmtEur(b.gutscheinVerkauf))
                }
                if b.gutscheineEingeloest > 0 {
                    zeile("Mit Gutschein bezahlt", fmtEur(b.gutscheineEingeloest))
                }
                zeile("Tagesumsatz gesamt", fmtEur(b.tagesumsatz))
                if b.trinkgeldKarte > 0 {
                    zeile("Trinkgeld auf der Karte", fmtEur(b.trinkgeldKarte))
                }
                zeile("Abends gezählt", fmtEur(b.gezaehltSchluss))
                uebermittlungsKarte(b)
                Button {
                    workflow = TagRef(id: gewaehlt)
                } label: {
                    Text(Kassenwort.aendern).frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            } else if gewaehlt > heute {
                Text("Der Tag ist noch nicht da.")
                    .font(.body)
                    .foregroundStyle(GC.muted)
            } else {
                Text("Für diesen Tag ist noch nichts eingetragen.")
                    .font(.body)
                    .foregroundStyle(GC.desc)
                Button {
                    workflow = TagRef(id: gewaehlt)
                } label: {
                    Text(gewaehlt == heute ? Kassenwort.eintragen : Kassenwort.nachtragen)
                        .font(.title3.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    /// „Wie wird die Kasse übermittelt?" — Ninas Frage, bisher nirgends
    /// beantwortet. Sichtbar war nur ein Haken; der sagt weder wohin noch
    /// wann, und schon gar nicht, was am Monatsende daraus wird.
    private func uebermittlungsKarte(_ b: Kassenbericht) -> some View {
        let stand = Uebermittlung.fuer(b)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: stand.erledigt ? "checkmark.seal" : "clock")
                    .font(.footnote)
                    .foregroundStyle(stand.erledigt ? GC.ok : GC.muted)
                Text(stand.satz)
                    .font(.footnote)
                    .foregroundStyle(stand.erledigt ? GC.body : GC.desc)
            }
            Text(Uebermittlung.monatsende)
                .font(.caption)
                .foregroundStyle(GC.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(GC.desk, in: RoundedRectangle(cornerRadius: 12))
    }

    private func zeile(_ label: String, _ wert: String) -> some View {
        HStack {
            Text(label)
                .font(.body)
                .foregroundStyle(GC.desc)
            Spacer()
            Text(wert)
                .font(.body.monospaced().weight(.medium))
                .foregroundStyle(GC.fg)
        }
    }

    // MARK: - Ausgaben des Monats

    private var ausgabenKarte: some View {
        NavigationLink {
            AbschlussView(monat: monatSchluessel)
        } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Ausgaben \(monatsTitel)")
                            .font(.headline)
                            .fontDesign(.serif)
                            .foregroundStyle(GC.fg)
                        ausgabenInhalt
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(GC.muted.opacity(0.6))
                }
                if case .da(let a) = ausgaben, !a.groessteGruppen().isEmpty {
                    Divider()
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Größte Posten")
                            .font(.caption)
                            .foregroundStyle(GC.muted)
                        ForEach(a.groessteGruppen()) { g in
                            HStack {
                                Text(g.name)
                                    .font(.footnote)
                                    .foregroundStyle(GC.body)
                                Spacer()
                                Text(fmtEur(g.netto))
                                    .font(.footnote.monospaced())
                                    .foregroundStyle(GC.desc)
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .gcCard()
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var ausgabenInhalt: some View {
        switch ausgaben {
        case .laedt:
            HStack(spacing: 6) {
                ProgressView().controlSize(.small)
                Text("Wird gerechnet …")
                    .font(.footnote)
                    .foregroundStyle(GC.muted)
            }
        case .nichtVerbunden:
            Text("Dafür musst du dich einmal in den Einstellungen verbinden.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
        case .keineVerbindung:
            Text("Gerade keine Verbindung")
                .font(.footnote)
                .foregroundStyle(GC.warn)
        case .da(let a):
            if a.tageErfasst == 0 {
                // Ein leerer Monat sieht sonst aus wie ein Monat ohne
                // Ausgaben — das ist nicht dasselbe.
                Text("Für diesen Monat ist noch nichts erfasst.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
            } else {
                Text(fmtEur(a.kostenNetto))
                    .font(.system(size: 32, weight: .semibold, design: .serif))
                    .foregroundStyle(GC.fg)
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                Text("ohne Steuer")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                // Die große Zahl ohne ihre Vorbehalte zu zeigen, wäre eine
                // Behauptung: die Löhne fehlen hier meistens noch.
                ForEach(a.fehlt, id: \.self) { satz in
                    Text(satz)
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func ausgabenLaden(fuer schluessel: String) async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else {
            ausgaben = .nichtVerbunden
            return
        }
        ausgaben = .laedt
        let ergebnis = await AblageService.monatsabschluss(monat: schluessel, basis: url, pat: pat)
        // Beim Blättern bricht `.task(id:)` den alten Lauf ab — dessen späte
        // Antwort darf den neuen Monat nicht überschreiben.
        guard schluessel == monatSchluessel else { return }
        ausgaben = ergebnis.map(AusgabenStand.da) ?? .keineVerbindung
    }
}
