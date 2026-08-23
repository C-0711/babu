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

    private struct TagRef: Identifiable { let id: String }

    private var kal: Calendar { KassenTag.kalender }
    private var heute: String { KassenTag.schluessel(Date()) }
    private var gepflegteTage: Set<String> { Set(store.kassenberichte.map(\.datum)) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    kalenderKarte
                    tagesKarte
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
}
