import SwiftUI

/// Kontoauszug abgeben — vom Telefon aus, nicht vom Schreibtisch.
///
/// Bisher gab es das nur im Portal. Nina arbeitet aber am Telefon, und das
/// PDF der Bank liegt dort ohnehin: die Banking-App teilt es direkt hierher.
/// babu liest die Umsätze und sagt sofort, zu welcher Abbuchung noch der
/// Beleg fehlt — das ist der Moment, in dem man ihn noch findet.
struct KontoauszugView: View {
    @EnvironmentObject var store: AppStore

    @State private var zeigeDateien = false
    @State private var laedtHoch = false
    @State private var meldung: String?
    /// Der zuletzt betroffene Monat ("JJJJ-MM") und was der Abgleich dazu sagt.
    @State private var monat: String?
    @State private var umsaetze = 0
    @State private var abgleich: (auszugDa: Bool, gedeckt: Int, fehlend: Int,
                                  fehlendSumme: Double, bankgebuehren: Int,
                                  einnahmenSumme: Double,
                                  positionen: [AbgleichPosition])?
    /// Der lokale Beleg zu einer gedeckten Position, falls er auf DIESEM
    /// Gerät liegt — dann öffnet der Tipp die Beleg-Ansicht.
    @State private var zeigeBeleg: Beleg?

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Das PDF deiner Bank — babu liest jede Abbuchung "
                         + "und prüft, ob der Beleg dazu schon da ist.")
                        .font(.body)
                    Text("Original-PDF aus dem Online-Banking, kein Foto und "
                         + "kein Scan — nur das PDF trägt die Umsätze lesbar "
                         + "in sich.")
                        .font(.caption).foregroundStyle(GC.desc)
                }
                .padding(.vertical, 4)

                Button {
                    zeigeDateien = true
                } label: {
                    if laedtHoch {
                        HStack { ProgressView(); Text("babu liest den Auszug …") }
                    } else {
                        Label("Kontoauszug wählen (PDF)", systemImage: "doc.badge.arrow.up")
                    }
                }
                .disabled(laedtHoch)

                if let meldung {
                    Text(meldung).font(.footnote).foregroundStyle(GC.warn)
                }
            }

            if let monat, let a = abgleich, a.auszugDa {
                Section {
                    if umsaetze > 0 {
                        HStack {
                            Text("Umsätze gelesen")
                            Spacer()
                            Text("\(umsaetze)").font(.body.monospacedDigit())
                        }
                    }
                    HStack {
                        Label("Beleg ist da", systemImage: "checkmark.circle")
                            .foregroundStyle(GC.ok)
                        Spacer()
                        Text("\(a.gedeckt)").font(.body.monospacedDigit())
                    }
                    if a.fehlend > 0 {
                        HStack {
                            Label("Beleg fehlt noch", systemImage: "questionmark.circle")
                                .foregroundStyle(GC.warn)
                            Spacer()
                            Text("\(a.fehlend) · \(fmtEur(a.fehlendSumme))")
                                .font(.body.monospacedDigit())
                        }
                    }
                    if a.bankgebuehren > 0 {
                        Text("\(a.bankgebuehren) Bankentgelte — dafür ist der "
                             + "Auszug selbst der Beleg.")
                            .font(.caption).foregroundStyle(GC.desc)
                    }
                } header: {
                    Text(monatsName(monat))
                } footer: {
                    if a.fehlend > 0 {
                        Text("Zu jeder fehlenden Abbuchung gibt es irgendwo "
                             + "einen Beleg — fotografier ihn, dann geht die "
                             + "Zahl runter.")
                    }
                }

                if !a.positionen.isEmpty {
                    Section("Alle Positionen") {
                        ForEach(a.positionen) { p in
                            positionsZeile(p)
                        }
                    }
                }
            }
        }
        .warmerGrund()
        .sheet(item: $zeigeBeleg) { b in
            BelegGrossView(beleg: b).environmentObject(store)
        }
        .navigationTitle("Kontoauszug")
        .navigationBarTitleDisplayMode(.inline)
        .fileImporter(isPresented: $zeigeDateien,
                      allowedContentTypes: [.pdf]) { ergebnis in
            guard case .success(let url) = ergebnis else { return }
            let zugriff = url.startAccessingSecurityScopedResource()
            defer { if zugriff { url.stopAccessingSecurityScopedResource() } }
            if let daten = try? Data(contentsOf: url) {
                hochladen(daten, name: url.lastPathComponent)
            } else {
                meldung = "Die Datei ließ sich nicht öffnen."
            }
        }
        .task { await letztenMonatZeigen() }
    }

    private func hochladen(_ daten: Data, name: String) {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else {
            meldung = "Erst verbinden — dann kann babu den Auszug lesen."
            return
        }
        laedtHoch = true
        meldung = nil
        Task {
            let antwort = await AblageService.kontoauszugAbgeben(
                daten: daten, dateiname: name, basis: url, pat: pat)
            if let gelesen = antwort.gelesen {
                monat = gelesen.monat
                umsaetze = gelesen.umsaetze
                abgleich = await AblageService.abgleichLaden(
                    monat: gelesen.monat, basis: url, pat: pat)
            } else {
                meldung = antwort.meldung
            }
            laedtHoch = false
        }
    }

    /// Beim Öffnen den jüngsten Monat zeigen, für den schon ein Auszug da ist —
    /// diesen oder den davor. Sonst bleibt die Seite leer, obwohl es etwas gäbe.
    private func letztenMonatZeigen() async {
        guard monat == nil, let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        let kal = Calendar.current
        for zurueck in 0...1 {
            guard let tag = kal.date(byAdding: .month, value: -zurueck, to: Date())
            else { continue }
            let k = kal.dateComponents([.year, .month], from: tag)
            let m = String(format: "%04d-%02d", k.year ?? 0, k.month ?? 0)
            if let a = await AblageService.abgleichLaden(monat: m, basis: url,
                                                         pat: pat), a.auszugDa {
                monat = m
                umsaetze = 0
                abgleich = a
                return
            }
        }
    }

    /// Eine Zeile der Checkliste: Haken für gedeckte, offener Kreis für
    /// fehlende, dezenter Punkt für Bankentgelte und Eingänge.
    @ViewBuilder
    private func positionsZeile(_ p: AbgleichPosition) -> some View {
        let inhalt = HStack(spacing: 10) {
            Image(systemName: p.status == "gedeckt" ? "checkmark.circle.fill"
                  : p.status == "fehlt" ? "circle" : "minus.circle")
                .foregroundStyle(p.status == "gedeckt" ? GC.ok
                                 : p.status == "fehlt" ? GC.warn : GC.muted)
            VStack(alignment: .leading, spacing: 2) {
                Text(p.gegenpartei).font(.subheadline).lineLimit(1)
                Text(p.status == "gedeckt" ? "Beleg liegt vor"
                     : p.status == "fehlt" ? "Beleg fehlt — einfach fotografieren"
                     : p.status == "bank" ? "Bankentgelt — der Auszug ist der Beleg"
                     : "Eingang")
                    .font(.caption)
                    .foregroundStyle(p.status == "fehlt" ? GC.warn : GC.desc)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(fmtEur(abs(p.betrag))).font(.subheadline.monospacedDigit())
                Text(p.datum).font(.caption2).foregroundStyle(GC.muted)
            }
        }
        if p.status == "gedeckt", let stamm = p.stamm,
           let beleg = store.belege.first(where: {
               $0.ablageDateiname?.contains(stamm) == true }) {
            Button { zeigeBeleg = beleg } label: { inhalt }
                .buttonStyle(.plain)
        } else {
            inhalt
        }
    }

    private func monatsName(_ m: String) -> String {
        let t = m.split(separator: "-")
        guard t.count == 2, let nr = Int(t[1]), (1...12).contains(nr)
        else { return m }
        let namen = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                     "August", "September", "Oktober", "November", "Dezember"]
        return "\(namen[nr - 1]) \(t[0])"
    }
}
