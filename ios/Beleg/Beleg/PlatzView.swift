import SwiftUI
import StoreKit

/// „Deine Ablage" — wie viel Platz gebucht ist und wie voll sie ist.
///
/// Nach dem Muster von iCloud, und aus demselben Grund: **der Kauf findet
/// außerhalb statt.** Apple nimmt das Geld, Apple verlängert, Apple kündigt.
/// Die App kann deshalb nur zweierlei tun, und beides muss sie tun:
///
///   1. **Zeigen, was gilt** — welche Stufe, wie viel davon belegt ist.
///      Wer bei Apple bucht, sieht dort eine Produktkennung und einen
///      Preis; was er davon tatsächlich hat, weiß nur babu.
///   2. **Weiterreichen** — „Platz ändern" öffnet die Auswahl (ein Kauf bei
///      Apple), „Abo verwalten" öffnet Apples eigenes Blatt. Beides verlangt
///      Apple ausdrücklich (App Store Review 3.1.2): ein Abo muss sich aus
///      der App heraus verwalten lassen.
///
/// Gezählt wird in **Belegen, nicht in Gigabyte**. iCloud redet von GB, weil
/// ein Foto beliebig groß sein kann; hier ist die Einheit immer dasselbe —
/// ein abfotografierter Beleg. „Noch rund 8.300 Belege" beantwortet die
/// Frage, die jemand wirklich hat; „3,7 GB frei" beantwortet sie nicht.
struct PlatzView: View {
    @EnvironmentObject var store: AppStore
    @EnvironmentObject var kasse: Kasse
    @State private var zeigeVerwalten = false
    // Eigener Schalter für dieses Blatt. Hinge es an `store.zeigePlatz`,
    // hinge dasselbe Flag an ZWEI Blättern (hier und an der Wurzel in
    // BelegApp) — UIKit versucht dann beide zugleich zu zeigen, bricht ab
    // und das Flag bleibt wahr (Apple-Ablehnung 24.10.2026, iPad).
    @State private var zeigePlatzHier = false

    private var platz: PlatzStand? { store.platz }

    var body: some View {
        List {
            if let p = platz {
                stand(p)
                womit(p)
                wege(p)
            } else {
                Text("Für diesen Zugang gibt es keine Stufen.")
                    .foregroundStyle(GC.desc)
            }
        }
        .warmerGrund()
        .navigationTitle("Deine Ablage")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await store.kontoNachfragen()
            await kasse.preiseLaden(store.stufen)
        }
        .sheet(isPresented: $zeigePlatzHier) { PlatzSheet() }
        // Apples eigenes Blatt: kündigen, wechseln, Rechnung ansehen. Das
        // kann die App nicht selbst, und sie soll es auch nicht nachbauen.
        .manageSubscriptionsSheet(isPresented: $zeigeVerwalten)
    }

    // MARK: - Was gilt

    @ViewBuilder
    private func stand(_ p: PlatzStand) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    Text(stufenName(p))
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(GC.fg)
                    Spacer()
                    if let s = gebucht(p) {
                        Text(preis(s)).font(.subheadline)
                            .foregroundStyle(GC.desc)
                    }
                }
                balken(p)
                Text(belegt(p)).font(.footnote).foregroundStyle(GC.desc)
            }
            .padding(.vertical, 6)
        } footer: {
            if let satz = p.hinweis {
                Text(satz)
            } else if p.stufe == nil {
                Text("Die ersten \(PlatzStand.belegeFrei) Belege sind frei. "
                     + "Danach suchst du dir einen Platz aus — deine Belege "
                     + "bleiben in jedem Fall, wo sie sind.")
            }
        }
    }

    private func balken(_ p: PlatzStand) -> some View {
        GeometryReader { raum in
            ZStack(alignment: .leading) {
                Capsule().fill(GC.linie)
                Capsule()
                    .fill(p.voll ? GC.warn : GC.accent)
                    .frame(width: max(4, raum.size.width * p.anteil))
            }
        }
        .frame(height: 8)
    }

    // MARK: - Was drinliegt

    /// Dieselben Fächer wie unter „Dokumente" — gezählt aus der Liste, die
    /// das Telefon ohnehin führt. Keine Bytes: die Einheit ist der Beleg.
    /// Leere Fächer bleiben weg; eine Zeile „Verträge 0" sagt nichts.
    @ViewBuilder
    private func womit(_ p: PlatzStand) -> some View {
        let je = Dictionary(grouping: store.belege, by: Dokumentart.von)
            .mapValues(\.count)
        let gefuellt = Dokumentart.allCases.filter { (je[$0] ?? 0) > 0 }
        if !gefuellt.isEmpty {
            Section("Was drinliegt") {
                ForEach(gefuellt) { art in
                    HStack {
                        Label(art.name, systemImage: art.symbol)
                            .foregroundStyle(GC.fg)
                        Spacer()
                        Text("\(je[art] ?? 0)").monospacedDigit()
                            .foregroundStyle(GC.desc)
                    }
                }
            }
        }
    }

    // MARK: - Die zwei Wege nach draußen

    @ViewBuilder
    private func wege(_ p: PlatzStand) -> some View {
        Section {
            Button(p.stufe == nil ? "Platz buchen" : "Platz ändern") {
                zeigePlatzHier = true
            }
            if p.stufe != nil {
                Button("Abo verwalten") { zeigeVerwalten = true }
            }
        } footer: {
            Text(p.stufe == nil
                 ? "Gebucht wird über den App Store."
                 : "Kündigen und wechseln gehen über den App Store — "
                   + "babu sieht deine Zahlungsdaten nie. Nach einer "
                   + "Kündigung bleiben deine Belege lesbar; es kommt nur "
                   + "nichts Neues dazu.")
        }
    }

    // MARK: - Worte

    private func gebucht(_ p: PlatzStand) -> PlatzStufe? {
        store.stufen.first { $0.stufe == p.stufe }
    }

    private func stufenName(_ p: PlatzStand) -> String {
        gebucht(p).map { "\($0.gb) GB" } ?? "Noch keine Stufe"
    }

    private func preis(_ s: PlatzStufe) -> String {
        (kasse.produkte[s.apple]?.displayPrice ?? s.preisNotfalls) + " / Monat"
    }

    private func belegt(_ p: PlatzStand) -> String {
        if let frei = p.freiOffen {
            let eins = frei == 1
            return frei == 0
                ? "Alle \(PlatzStand.belegeFrei) freien Belege abgelegt"
                : "\(p.belege) von \(PlatzStand.belegeFrei) frei — noch "
                  + "\(frei) \(eins ? "Beleg" : "Belege")"
        }
        guard let s = gebucht(p) else { return "\(p.belege) Belege abgelegt" }
        return "\(p.belege) Belege abgelegt · Platz für \(s.belegeText)"
    }
}
