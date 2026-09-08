import SwiftUI

/// Dein Betrieb — an einer Stelle.
///
/// Bisher lag das an zwei Orten: die Angaben im Formular „Dein Betrieb", und
/// was aus den hochgeladenen Unterlagen herausgelesen wurde, nur im Browser.
/// Wer wissen wollte, was babu über den Salon weiß, musste beides kennen.
///
/// Hier steht es zusammen: was schon feststeht, was noch fehlt — und dass
/// beides aus dem wächst, was fotografiert und eingereicht wird. Geändert
/// wird weiter im Formular darunter; eine zweite Ablage gibt es nicht.
struct BetriebsprofilView: View {
    @EnvironmentObject var store: AppStore

    @State private var angaben: [String: String]?
    @State private var laedt = true
    @State private var karten: [Betriebskarte] = []
    @State private var quellen: [String] = []

    private var fehlend: [String] {
        Einrichtung.fehlendeBetriebsfelder(angaben ?? [:])
    }

    private var bekannt: [(name: String, wert: String)] {
        guard let angaben else { return [] }
        return Einrichtung.betriebsfelder.compactMap { feld in
            let wert = (angaben[feld.schluessel] ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return wert.isEmpty ? nil : (feld.name, wert)
        }
    }

    private var steuernummer: String? {
        guard let angaben else { return nil }
        for schluessel in ["steuernummer", "ust_id"] {
            let wert = (angaben[schluessel] ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !wert.isEmpty { return wert }
        }
        return nil
    }

    var body: some View {
        List {
            if store.verbundenAls == nil {
                Section {
                    Text("Das Bild deines Betriebs liegt in deinem babu-Konto. "
                         + "Verbinde dich zuerst mit E-Mail und Passwort.")
                        .font(.footnote)
                        .foregroundStyle(GC.desc)
                }
            } else if laedt {
                Section {
                    HStack {
                        ProgressView()
                        Text("Einen Moment …")
                            .font(.footnote).foregroundStyle(GC.muted)
                    }
                }
            } else {
                bekanntAbschnitt
                if !fehlend.isEmpty || steuernummer == nil { fehltAbschnitt }
                if !karten.isEmpty { ausUnterlagenAbschnitt }
                herkunftAbschnitt
                aendernAbschnitt
            }
        }
        .warmerGrund()
        .navigationTitle("Dein Betrieb")
        .navigationBarTitleDisplayMode(.inline)
        .task { await laden() }
    }

    // MARK: - Was feststeht

    private var bekanntAbschnitt: some View {
        Section {
            if bekannt.isEmpty && steuernummer == nil {
                Text("Noch nichts. Fotografiere einen Brief vom Finanzamt oder "
                     + "trag die Angaben unten selbst ein — dann steht es hier.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
            } else {
                ForEach(bekannt, id: \.name) { eintrag in
                    angabe(eintrag.name, eintrag.wert)
                }
                if let steuernummer {
                    angabe("Steuernummer", steuernummer)
                }
            }
        } header: {
            Text("Das weiß babu über deinen Betrieb")
        }
    }

    private func angabe(_ name: String, _ wert: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 15))
                .foregroundStyle(GC.ok)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.caption)
                    .foregroundStyle(GC.muted)
                Text(wert)
                    .font(.subheadline)
                    .foregroundStyle(GC.fg)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Was fehlt

    private var fehltAbschnitt: some View {
        Section {
            ForEach(fehlend, id: \.self) { name in
                HStack(spacing: 10) {
                    Image(systemName: "circle.dashed")
                        .font(.system(size: 15))
                        .foregroundStyle(GC.warn)
                    Text(name)
                        .font(.subheadline)
                        .foregroundStyle(GC.fg)
                }
                .padding(.vertical, 2)
            }
            if steuernummer == nil {
                HStack(spacing: 10) {
                    Image(systemName: "circle.dashed")
                        .font(.system(size: 15))
                        .foregroundStyle(GC.warn)
                    Text("Steuernummer")
                        .font(.subheadline)
                        .foregroundStyle(GC.fg)
                }
                .padding(.vertical, 2)
            }
        } header: {
            Text("Das fehlt noch")
        } footer: {
            Text("Meist steht es auf einem Brief vom Finanzamt. Fotografier ihn "
                 + "einfach — babu holt sich heraus, was es braucht.")
        }
    }

    // MARK: - Was aus den Unterlagen kam

    private var ausUnterlagenAbschnitt: some View {
        Section {
            ForEach(karten) { karte in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(ampelfarbe(karte.ampel))
                            .frame(width: 8, height: 8)
                        Text(karte.titel)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(GC.fg)
                        Spacer(minLength: 8)
                        if let wert = karte.wert {
                            Text(wert)
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(GC.desc)
                        }
                    }
                    Text(karte.satz)
                        .font(.caption)
                        .foregroundStyle(GC.desc)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.vertical, 3)
            }
        } header: {
            Text("Aus deinen Unterlagen gelesen")
        } footer: {
            if quellen.isEmpty {
                Text("Das steht nicht in einem Formular — babu hat es aus dem "
                     + "gelesen, was du eingereicht hast.")
            } else {
                Text("Gelesen aus: " + quellen.joined(separator: ", ") + ".")
            }
        }
    }

    private func ampelfarbe(_ ampel: String) -> Color {
        switch ampel {
        case "gruen": return GC.ok
        case "gelb":  return GC.warn
        case "rot":   return GC.danger
        default:      return GC.muted
        }
    }

    // MARK: - Woher das kommt

    private var herkunftAbschnitt: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                Text("Du fotografierst, babu baut daraus das Bild deines Betriebs.")
                    .font(.subheadline)
                    .foregroundStyle(GC.fg)
                herkunftZeile("doc.text.viewfinder",
                              "Briefe vom Finanzamt — Steuernummer, Finanzamt, "
                              + "wie du angemeldet bist")
                herkunftZeile("shippingbox",
                              "Verträge — Miete, Strom, Leasing")
                herkunftZeile("building.columns",
                              "Kontoauszüge — was regelmäßig abgeht")
                herkunftZeile("rectangle.stack",
                              "Belege — woran du verdienst und was du ausgibst")
            }
            .padding(.vertical, 2)
        } header: {
            Text("Woher babu das hat")
        } footer: {
            Text("Je mehr du einreichst, desto vollständiger wird dieses Bild — "
                 + "und desto weniger musst du selbst eintippen.")
        }
    }

    private func herkunftZeile(_ symbol: String, _ satz: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: symbol)
                .font(.system(size: 13))
                .foregroundStyle(GC.accent)
                .frame(width: 20)
                .padding(.top, 2)
            Text(satz)
                .font(.caption)
                .foregroundStyle(GC.desc)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Selbst ändern

    private var aendernAbschnitt: some View {
        Section {
            NavigationLink {
                BetriebsangabenView()
            } label: {
                Label("Angaben ergänzen oder ändern", systemImage: "square.and.pencil")
            }
        } footer: {
            Text("Alles, was hier steht, kannst du selbst überschreiben.")
        }
    }

    // MARK: - Laden

    private func laden() async {
        defer { laedt = false }
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        angaben = await AblageService.stammdatenLaden(basis: url, pat: pat)
        // Der Salon-Check läuft über ein abgeschlossenes Jahr. Gibt es dafür
        // noch nichts, kommt eine leere Liste — dann bleibt der Abschnitt weg,
        // statt eine leere Überschrift zu zeigen.
        if let bild = await AblageService.betriebsbildLaden(jahr: nil, basis: url,
                                                            pat: pat) {
            karten = bild.karten
            quellen = bild.quellen
        }
    }
}
