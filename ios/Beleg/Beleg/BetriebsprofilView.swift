import SwiftUI

/// Dein Betrieb — an einer Stelle, und sie wächst.
///
/// Bisher lag das an zwei Orten: die Angaben im Formular „Dein Betrieb", und
/// was aus den hochgeladenen Unterlagen herausgelesen wurde, nur im Browser.
/// Wer wissen wollte, was babu über den Salon weiß, musste beides kennen.
///
/// Seit dem 08.09.2026 zeigt diese Ansicht nicht mehr, was fehlt, sondern was
/// da ist — und woher es kommt. Das ist keine Kosmetik: die Karte „Dein
/// Anfang" auf der Startseite verschwindet jetzt, sobald verbunden ist und
/// der erste Beleg liegt, und alles Weitere wächst hier nach. Wo babu eine
/// Angabe aus einer Unterlage gelesen hat, steht die Unterlage dabei. Wo
/// nicht, steht nichts dabei — Herkunft wird nicht erfunden.
///
/// Kein Balken, keine Prozente, kein „5 von 7". Das Profil ist keine Prüfung.
struct BetriebsprofilView: View {
    @EnvironmentObject var store: AppStore

    @State private var angaben: [String: String]?
    @State private var laedt = true
    @State private var karten: [Betriebskarte] = []
    @State private var quellen: [String] = []
    @State private var wachstum = Profilwachstum()
    @State private var vertraege = 0

    private var bekannt: [(feld: Profilfeld, wert: String)] {
        Einrichtung.bekannteFelder(angaben ?? [:])
    }

    private var naechstes: [(quelle: Lernquelle, satz: String)] {
        Einrichtung.naechstes(angaben ?? [:])
    }

    /// Wie viele Unterlagen zu diesem Bild beigetragen haben. Belege auf dem
    /// Gerät zählen mit — sie sind der häufigste Weg, auf dem etwas dazukommt.
    private var beitraege: Int {
        wachstum.unterlagen.count + vertraege
            + store.belege.filter { $0.istDemo != true }.count
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
                if !naechstes.isEmpty { naechstesAbschnitt }
                if !karten.isEmpty { ausUnterlagenAbschnitt }
                aendernAbschnitt
            }
        }
        .warmerGrund()
        .navigationTitle("Dein Betrieb")
        .navigationBarTitleDisplayMode(.inline)
        .task { await laden() }
    }

    // MARK: - Was babu schon weiß

    private var bekanntAbschnitt: some View {
        Section {
            if bekannt.isEmpty {
                Text("Noch nichts. Fotografier einen Brief vom Finanzamt — "
                     + "babu holt sich heraus, was es braucht. Oder trag die "
                     + "Angaben unten selbst ein.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
            } else {
                ForEach(bekannt, id: \.feld.schluessel) { eintrag in
                    angabe(eintrag.feld, eintrag.wert)
                }
            }
        } header: {
            Text("Das weiß babu über deinen Betrieb")
        } footer: {
            if beitraege > 0 {
                Text(wachstumssatz)
            }
        }
    }

    /// Der leise Satz darunter: das Bild wächst mit jedem Dokument. Ohne
    /// Zahl, die etwas verlangt — die Zahl sagt, was schon da ist.
    private var wachstumssatz: String {
        var teile = ["\(beitraege) "
                     + (beitraege == 1 ? "Unterlage hat" : "Unterlagen haben")
                     + " zu diesem Bild beigetragen."]
        if !wachstum.herkunft.isEmpty {
            teile.append("Mit jeder weiteren wird es vollständiger.")
        } else {
            teile.append("Je mehr du fotografierst, desto mehr steht hier "
                         + "von selbst.")
        }
        return teile.joined(separator: " ")
    }

    private func angabe(_ feld: Profilfeld, _ wert: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 15))
                .foregroundStyle(GC.ok)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(feld.name)
                    .font(.caption)
                    .foregroundStyle(GC.muted)
                Text(wert)
                    .font(.subheadline)
                    .foregroundStyle(GC.fg)
                    .fixedSize(horizontal: false, vertical: true)
                // Nur wo babu die Unterlage wirklich kennt. Was von Hand
                // eingetragen wurde, steht ohne Zusatz da — eine erfundene
                // Herkunft wäre schlimmer als gar keine.
                if let woher = herkunft(feld) {
                    Text(woher)
                        .font(.caption2)
                        .foregroundStyle(GC.accent)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 1)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func herkunft(_ feld: Profilfeld) -> String? {
        for schluessel in [feld.schluessel, feld.ersatz].compactMap({ $0 }) {
            if let h = wachstum.herkunft[schluessel] {
                return "Kennt babu aus deiner Unterlage „\(h.unterlage)“."
            }
        }
        return nil
    }

    // MARK: - Was als Nächstes dazukommt

    private var naechstesAbschnitt: some View {
        Section {
            ForEach(naechstes, id: \.quelle) { eintrag in
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: eintrag.quelle.symbol)
                        .font(.system(size: 14))
                        .foregroundStyle(eintrag.quelle == .nurSelbst
                                         ? GC.muted : GC.accent)
                        .frame(width: 20)
                        .padding(.top, 1)
                    Text(eintrag.satz)
                        .font(.subheadline)
                        .foregroundStyle(GC.body)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.vertical, 3)
            }
        } header: {
            Text("Das kommt als Nächstes dazu")
        } footer: {
            Text("Nichts davon musst du heute erledigen. Es kommt von selbst, "
                 + "sobald die Unterlage einmal durch die Kamera geht.")
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
        if let gewachsen = await AblageService.profilwachstumLaden(basis: url,
                                                                   pat: pat) {
            wachstum = gewachsen
        }
        // Verträge zählen als Beitrag zum Bild: jeder bringt einen Partner,
        // einen Betrag und eine Kündigungsfrist mit.
        if let geld = await AblageService.vertraegeLaden(basis: url, pat: pat) {
            vertraege = geld.vertraege.count
        }
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
