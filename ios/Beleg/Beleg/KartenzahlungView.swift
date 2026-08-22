import SwiftUI

/// Was dieses iPhone in Sachen Kartenzahlung kann — und was noch fehlt.
///
/// Der Bildschirm ist bewusst als Diagnose gebaut, nicht als Werbung: er
/// sagt zuerst, woran es hakt, und erst danach, was schon geht. Solange
/// nicht wirklich kassiert werden kann, steht das an jeder Stelle dran.
struct KartenzahlungView: View {
    @EnvironmentObject var store: AppStore

    @State private var probebetrag = "42,00"
    @State private var laeuft = false
    @State private var beleg: Kartenbeleg?
    @State private var fehler: String?
    @State private var lehntAb = false

    private var lage: Kartenlage {
        Kartenpruefung.lage(geraet: KartenTerminal.geraet,
                            freigabe: KartenTerminal.freigabe,
                            anbieter: .offen)   // noch kein Anbieter angebunden
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) {
                        Image(systemName: lage == .bereit
                              ? "checkmark.circle.fill" : "hourglass")
                            .foregroundStyle(lage == .bereit ? GC.ok : GC.accent)
                        Text(lage == .bereit ? "Bereit" : "Noch nicht bereit")
                            .font(.body.weight(.semibold))
                    }
                    Text(lage.satz).font(.callout).foregroundStyle(GC.desc)
                    if let weiter = lage.naechstes {
                        Text("Als Nächstes: \(weiter)")
                            .font(.caption).foregroundStyle(GC.muted)
                    }
                }
                .padding(.vertical, 4)
            } header: {
                Text("Karte mit dem Telefon")
            }

            Section("Die drei Hürden") {
                huerde("Dieses iPhone", KartenTerminal.geraet,
                       ja: "kann Karten lesen",
                       nein: "kann es nicht — dafür braucht es ein "
                           + "iPhone XS oder neuer",
                       weissNicht: "nicht feststellbar — der Simulator "
                           + "meldet Bereitschaft, ohne welche zu haben")
                huerde("Apples Freigabe", KartenTerminal.freigabe,
                       ja: "ist erteilt",
                       nein: "steht noch aus",
                       weissNicht: "nicht feststellbar — dieser Build hat "
                           + "kein Provisioning-Profil")
                huerde("Zahlungsdienstleister", .offen,
                       ja: "angebunden",
                       nein: "fehlt — nur ein zugelassener Anbieter darf "
                           + "das Geld abwickeln",
                       weissNicht: "")
            }

            Section {
                TextField("Betrag", text: $probebetrag)
                    .keyboardType(.decimalPad)
                Toggle("Karte wird abgelehnt", isOn: $lehntAb)
                Button {
                    Task { await probieren() }
                } label: {
                    HStack {
                        if laeuft { ProgressView().padding(.trailing, 6) }
                        Text(laeuft ? "Karte anhalten …" : "Prüfstand starten")
                    }
                }
                .disabled(laeuft)

                if let beleg {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("\(beleg.betrag.text) angenommen",
                              systemImage: "checkmark.circle")
                            .foregroundStyle(GC.ok)
                        Text("Beleg \(beleg.referenz)"
                             + (beleg.letzteVier.map { " · Karte …\($0)" } ?? ""))
                            .font(.caption).foregroundStyle(GC.muted)
                        if beleg.probe {
                            Text("Prüfstand — es ist kein Geld geflossen.")
                                .font(.caption).foregroundStyle(GC.accent)
                        }
                    }
                }
                if let fehler {
                    Text(fehler).font(.footnote).foregroundStyle(GC.warn)
                }
            } header: {
                Text("Prüfstand")
            } footer: {
                Text("Spielt den ganzen Ablauf durch, ohne dass Geld fließt. "
                     + "So lässt sich prüfen, ob der Betrag stimmt und im "
                     + "Kassenbuch richtig ankommt — der Rest gehört ohnehin "
                     + "dem Zahlungsdienstleister.")
            }

            Section {
                EmptyView()
            } footer: {
                Text("babu hält niemals Geld und wickelt keine Zahlung ab. "
                     + "Es reicht den Betrag an einen zugelassenen Anbieter "
                     + "durch und schreibt hinterher auf, was angekommen ist.")
            }
        }
        .navigationTitle("Kartenzahlung")
        .toolbarTitleDisplayMode(.inline)
        .warmerGrund()
    }

    /// Ein Haken nur, wo es wirklich feststeht. „Weiß nicht" bekommt ein
    /// Fragezeichen — nicht wortlos einen leeren Kreis wie ein klares Nein.
    private func huerde(_ titel: String, _ stand: Huerdenstand,
                        ja: String, nein: String,
                        weissNicht: String) -> some View {
        let (bild, farbe, text): (String, Color, String) = {
            switch stand {
            case .erfuellt:  return ("checkmark.circle.fill", GC.ok, ja)
            case .offen:     return ("circle", GC.muted, nein)
            case .unbekannt: return ("questionmark.circle", GC.accent, weissNicht)
            }
        }()
        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: bild).foregroundStyle(farbe)
            VStack(alignment: .leading, spacing: 2) {
                Text(titel).font(.callout.weight(.medium))
                Text(text).font(.caption).foregroundStyle(GC.desc)
            }
        }
        .padding(.vertical, 2)
    }

    private func probieren() async {
        guard let betrag = Kartenbetrag(euro: probebetrag) else {
            fehler = Kartenfehler.betragUnklar.errorDescription
            return
        }
        laeuft = true; fehler = nil; beleg = nil
        defer { laeuft = false }
        let kasse = ProbeKasse(lage: lage,
                               lehntAb: lehntAb ? "Karte abgelehnt — bitte "
                                                + "andere Karte versuchen." : nil)
        do {
            beleg = try await kasse.kassieren(betrag)
        } catch {
            fehler = (error as? Kartenfehler)?.errorDescription
                  ?? error.localizedDescription
        }
    }
}
