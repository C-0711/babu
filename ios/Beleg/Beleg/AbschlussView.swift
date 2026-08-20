import SwiftUI

/// Monatsabschluss auf dem Telefon: was reinkam, was rausging — und was
/// ans Finanzamt geht. Ein Entwurf; geprüft wird er vom Steuer-Backend.
struct AbschlussView: View {
    @EnvironmentObject var store: AppStore

    @State private var monat = AbschlussView.monatJetzt()
    @State private var daten: Monatsabschluss?
    @State private var laedt = true
    @State private var fehler: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                monatsSchalter

                if laedt {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("Wird gerechnet …").foregroundStyle(GC.muted)
                    }
                    .padding(.top, 30)
                } else if let fehler {
                    Text(fehler)
                        .font(.footnote)
                        .foregroundStyle(GC.warn)
                } else if let d = daten {
                    if d.tageErfasst == 0 {
                        hinweisKarte
                    }
                    zahlenKarte(d)
                    if !d.gruppen.isEmpty { kostenKarte(d) }
                    steuerKarte(d)
                    if !d.offenePunkte.isEmpty { pruefKarte(d) }
                }
            }
            .padding(18)
        }
        .background(GC.canvas)
        .navigationTitle("Monatsabschluss")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: monat) { await laden() }
    }

    private var monatsSchalter: some View {
        HStack {
            Button { schiebe(-1) } label: {
                Image(systemName: "chevron.left").frame(width: 44, height: 44)
            }
            Spacer()
            Text(AbschlussView.monatsName(monat))
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
            Spacer()
            Button { schiebe(1) } label: {
                Image(systemName: "chevron.right").frame(width: 44, height: 44)
            }
        }
        .foregroundStyle(GC.fg)
    }

    private var hinweisKarte: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Für diesen Monat fehlt dein Kassenbuch")
                .font(.headline)
                .fontDesign(.serif)
            Text("Ohne die Tageseinnahmen können wir weder deine Zahlen noch die Umsatzsteuer rechnen. Trag sie im Kassenbuch ein — eine Zahl pro Frage.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    private func zahlenKarte(_ d: Monatsabschluss) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Deine Zahlen").font(.headline).fontDesign(.serif)
            zeile("Eingenommen (ohne Steuer)", fmtEur(d.umsatzNetto))
            zeile("Ausgegeben (ohne Steuer)", fmtEur(d.kostenNetto))
            Divider()
            HStack {
                Text("Bleibt dir").font(.body.weight(.semibold))
                Spacer()
                Text(fmtEur(d.ergebnis))
                    .font(.body.weight(.semibold).monospaced())
                    .foregroundStyle(d.ergebnis >= 0 ? GC.ok : GC.warn)
            }
            if let anteil = d.ergebnisAnteil {
                Text("Von 100 € Umsatz bleiben dir \(Int(anteil.rounded())) €.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
            }
            ForEach(d.fehlt, id: \.self) { satz in
                Label(satz, systemImage: "exclamationmark.circle")
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    private func kostenKarte(_ d: Monatsabschluss) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Text("Wohin das Geld ging").font(.headline).fontDesign(.serif)
            ForEach(d.gruppen) { g in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(g.name).font(.subheadline)
                        if let quelle = g.ausVertrag {
                            Text("aus deinem Vertrag mit \(quelle)")
                                .font(.caption2).foregroundStyle(GC.muted)
                        } else if g.geschaetzt {
                            Text("aus deinem Team")
                                .font(.caption2).foregroundStyle(GC.muted)
                        }
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(fmtEur(g.netto)).font(.subheadline.monospaced())
                        if let anteil = g.anteil {
                            Text("\(Int(anteil.rounded())) %")
                                .font(.caption2).foregroundStyle(GC.muted)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    private func steuerKarte(_ d: Monatsabschluss) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Umsatzsteuer").font(.headline).fontDesign(.serif)
            if d.steuerStand == "keine" {
                Text("Keine Voranmeldung nötig").font(.body.weight(.medium))
                Text(d.steuerHinweis).font(.footnote).foregroundStyle(GC.desc)
            } else {
                Text(d.steuerSatz)
                    .font(.system(size: 24, weight: .semibold, design: .serif))
                    .foregroundStyle(GC.fg)
                ForEach(d.steuerZeilen) { z in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(z.name).font(.subheadline)
                            Text("Kennzahl \(z.kz)")
                                .font(.caption2).foregroundStyle(GC.muted)
                        }
                        Spacer()
                        Text(fmtEur(z.wert)).font(.subheadline.monospaced())
                    }
                }
                Text(d.steuerHinweis)
                    .font(.caption)
                    .foregroundStyle(GC.muted)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    private func pruefKarte(_ d: Monatsabschluss) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Das fehlt noch").font(.headline).fontDesign(.serif)
            Text("Diese Belege haben wir nicht mitgerechnet — sie würden die Zahlen verfälschen.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
            ForEach(d.offenePunkte) { p in
                HStack(spacing: 8) {
                    Image(systemName: "questionmark.circle").foregroundStyle(GC.warn)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(p.lieferant).font(.subheadline)
                        Text(p.hinweis).font(.caption2).foregroundStyle(GC.muted)
                    }
                }
            }
            Button {
                store.tab = .belege
            } label: {
                Text("Zur Belegliste").font(.footnote)
            }
            .padding(.top, 2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    private func zeile(_ text: String, _ wert: String) -> some View {
        HStack {
            Text(text).font(.subheadline).foregroundStyle(GC.desc)
            Spacer()
            Text(wert).font(.subheadline.monospaced()).foregroundStyle(GC.fg)
        }
    }

    // MARK: - Laden

    private func laden() async {
        guard let url = URL(string: store.ablageURL), let pat = KeychainHelfer.ladePAT() else {
            fehler = "Dafür braucht die App die Belegbox — einmal in den Einstellungen verbinden."
            laedt = false
            return
        }
        laedt = true
        daten = await AblageService.monatsabschluss(monat: monat, basis: url, pat: pat)
        fehler = daten == nil ? "Gerade keine Verbindung." : nil
        laedt = false
    }

    private func schiebe(_ um: Int) {
        let teile = monat.split(separator: "-").compactMap { Int($0) }
        guard teile.count == 2 else { return }
        var jahr = teile[0], m = teile[1] + um
        if m < 1 { m = 12; jahr -= 1 }
        if m > 12 { m = 1; jahr += 1 }
        monat = String(format: "%04d-%02d", jahr, m)
    }

    static func monatJetzt() -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM"
        return f.string(from: Date())
    }

    static func monatsName(_ monat: String) -> String {
        let ein = DateFormatter(); ein.dateFormat = "yyyy-MM"
        let aus = DateFormatter()
        aus.locale = Locale(identifier: "de_DE"); aus.dateFormat = "LLLL yyyy"
        return ein.date(from: monat).map { aus.string(from: $0) } ?? monat
    }
}
