import SwiftUI
import StoreKit

/// Die Stufenauswahl: „Such dir einen Platz aus."
///
/// Was hier NICHT steht, ist das Wichtigste: keine Funktionsliste je Stufe,
/// kein „ab Stufe 2 auch…". Jede Stufe kann alles (Entscheidung vom
/// 10.10.2026) — verglichen wird nur Platz gegen Preis. Eine Tabelle mit
/// Häkchen hätte genau den Eindruck erzeugt, den es nicht geben soll.
///
/// Die vier Sätze oben sind die, die der Auftraggeber genannt hat: der Chat
/// versteht alle hochgeladenen Unterlagen, das Profil legt sich selbst an,
/// babu wird mit jedem Dokument schlauer, und die Auslagen lassen sich
/// abrechnen.
struct PlatzSheet: View {
    @EnvironmentObject var store: AppStore
    @EnvironmentObject var kasse: Kasse
    @Environment(\.dismiss) private var dismiss

    /// Welche Stufe gerade hervorgehoben ist. Die mittlere zuerst: sie ist
    /// die, mit der die meisten auskommen (9.500 Belege).
    @State private var gewaehlt: String?
    @State private var gekauft = false

    private var stufen: [PlatzStufe] { store.stufen }

    /// Wie viele freie Belege noch bleiben — nil, wenn es keinen kostenlosen
    /// Weg mehr gibt. Dann steht oben wieder das kleine „Später".
    private var kostenlosNoch: Int? {
        store.platz?.freiNoch(belegeAufTelefon: store.belege.count)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    kopf
                    koennen
                    auswahl
                    kleingedrucktes
                }
                .padding(20)
            }
            .warmerGrund()
            .navigationTitle(gekauft ? "Mehr Platz" : "Deine Ablage")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                // Solange es Freies gibt, steht das kostenlose Weiter als
                // eigener Knopf unter den Stufen (22.10.2026) — ein kleines
                // „Später" daneben wäre derselbe Weg noch einmal, nur
                // versteckter.
                if gekauft || kostenlosNoch == nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button(gekauft ? "Weiter" : "Später") { dismiss() }
                    }
                }
            }
            // `id`: kommen die Stufen erst nach dem Öffnen (Server noch
            // unterwegs), lädt das Blatt die Preise dann noch einmal.
            .task(id: stufen.map(\.apple)) {
                await kasse.preiseLaden(stufen)
                if gewaehlt == nil {
                    gewaehlt = stufen.first(where: { $0.stufe == "mittel" })?.stufe
                        ?? stufen.first?.stufe
                }
            }
            .alert("", isPresented: .init(get: { kasse.fehler != nil },
                                          set: { if !$0 { kasse.fehler = nil } })) {
                Button("Verstanden") { kasse.fehler = nil }
            } message: {
                Text(kasse.fehler ?? "")
            }
        }
    }

    // MARK: - Kopf

    @ViewBuilder private var kopf: some View {
        if gekauft {
            VStack(alignment: .leading, spacing: 8) {
                Label("Der Platz steht", systemImage: "checkmark.circle.fill")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(GC.ok)
                Text("Es geht weiter, wo du aufgehört hast.")
                    .foregroundStyle(GC.desc)
            }
        } else if let p = store.platz, p.voll {
            VStack(alignment: .leading, spacing: 8) {
                Text(p.stufe == nil
                     ? "Deine zehn freien Belege sind abgelegt."
                     : "Deine Ablage ist voll.")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(GC.fg)
                Text("Deine Belege bleiben, wo sie sind — such dir einen "
                     + "Platz aus, dann geht es weiter.")
                    .foregroundStyle(GC.desc)
            }
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("So viel Platz, wie du brauchst")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(GC.fg)
                Text("Alle Stufen können alles. Du wählst nur, wie viel "
                     + "hineinpasst.")
                    .foregroundStyle(GC.desc)
            }
        }
    }

    // MARK: - Was babu kann

    private static let punkte: [(String, String, String)] = [
        ("text.magnifyingglass", "Fragen statt suchen",
         "Der Chat kennt jede Unterlage, die du hochgeladen hast — Verträge, "
         + "Post vom Amt, Rechnungen."),
        ("person.text.rectangle", "Das Profil legt sich selbst an",
         "Was in deinen Belegen steht, trägt babu für dich ein. Du musst kein "
         + "Formular ausfüllen."),
        ("brain", "Mit jedem Dokument schlauer",
         "Je mehr da liegt, desto besser bucht und antwortet babu — für "
         + "deinen Betrieb, nicht für irgendeinen."),
        ("arrow.left.arrow.right", "Auslagen abrechnen",
         "Was deine Leute vorgelegt haben, geht als Erstattung zurück — mit "
         + "Beleg und Überweisung.")
    ]

    private var koennen: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Self.punkte, id: \.1) { bild, titel, text in
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: bild)
                        .font(.system(size: 17))
                        .foregroundStyle(GC.accent)
                        .frame(width: 24)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(titel).font(.subheadline.weight(.semibold))
                            .foregroundStyle(GC.fg)
                        Text(text).font(.caption).foregroundStyle(GC.desc)
                    }
                }
            }
        }
        .padding(16)
        .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 14))
    }

    // MARK: - Die Stufen

    @ViewBuilder private var auswahl: some View {
        // Drei Zustände, sichtbar (24.10.2026): laden, da, nicht erreichbar.
        // Vorher stand bei fehlenden Preisen stumm der Notfallpreis daneben.
        switch kasse.ladung {
        case .laedt:
            HStack(spacing: 10) {
                ProgressView()
                Text("Preise werden geladen …").foregroundStyle(GC.muted)
            }
        case .fehler:
            VStack(alignment: .leading, spacing: 10) {
                Text("Preise gerade nicht erreichbar.").foregroundStyle(GC.muted)
                Button("Nochmal") {
                    kasse.nochmal()
                    Task {
                        await store.kontoNachfragen()
                        await kasse.preiseLaden(store.stufen)
                    }
                }
                .font(.body.weight(.semibold))
                .foregroundStyle(GC.accent)
            }
        case .geladen:
            EmptyView()
        }
        if !stufen.isEmpty {
            VStack(spacing: 10) {
                ForEach(stufen) { stufe in
                    stufenZeile(stufe)
                }
            }
            Button {
                guard let s = stufen.first(where: { $0.stufe == gewaehlt }) else { return }
                Task {
                    if await kaufen(s) { gekauft = true }
                }
            } label: {
                HStack {
                    if kasse.laeuft { ProgressView().tint(.white) }
                    Text(kasse.laeuft ? "Einen Moment …" : "Platz buchen")
                        .font(.body.weight(.semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(GC.accent, in: RoundedRectangle(cornerRadius: 12))
                .foregroundStyle(.white)
            }
            .disabled(kasse.laeuft || gewaehlt == nil || gekauft || kasse.ladung != .geladen)
            .opacity(gekauft ? 0.4 : 1)

            // Kostenlos weitermachen ist ein gleichwertiger Weg, kein
            // versteckter (Auftraggeber 22.10.2026): gleich breit wie
            // „Platz buchen", nur ohne Fläche.
            if let noch = kostenlosNoch, !gekauft {
                Button { dismiss() } label: {
                    Text(PlatzStand.kostenlosText(noch))
                        .font(.body.weight(.semibold))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .foregroundStyle(GC.accent)
                        .background(GC.bg, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12)
                            .stroke(GC.accent, lineWidth: 1.5))
                }
                .buttonStyle(.plain)
            }

            Button("Schon bezahlt? Käufe wiederherstellen") {
                Task {
                    if await kasse.wiederherstellen() {
                        await store.kontoNachfragen()
                        gekauft = true
                    } else {
                        kasse.fehler = "Auf diesem Apple-Konto liegt gerade "
                            + "kein Platz, den babu übernehmen könnte."
                    }
                }
            }
            .font(.footnote)
            .foregroundStyle(GC.accent)
            .frame(maxWidth: .infinity)
        }
    }

    private func stufenZeile(_ stufe: PlatzStufe) -> some View {
        let ist = gewaehlt == stufe.stufe
        let laeuft = store.platz?.stufe == stufe.stufe
        return Button {
            gewaehlt = stufe.stufe
        } label: {
            HStack(spacing: 14) {
                Image(systemName: ist ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(ist ? GC.accent : GC.muted)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("\(stufe.gb) GB").font(.body.weight(.semibold))
                            .foregroundStyle(GC.fg)
                        if laeuft {
                            Text("dein Platz").font(.caption2)
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(GC.ok.opacity(0.15),
                                            in: Capsule())
                                .foregroundStyle(GC.ok)
                        }
                    }
                    Text(stufe.belegeText).font(.caption)
                        .foregroundStyle(GC.desc)
                }
                Spacer()
                Text(preis(stufe)).font(.body.weight(.semibold))
                    .foregroundStyle(GC.fg)
                    + Text(" / Monat").font(.caption)
                    .foregroundStyle(GC.desc)
            }
            .padding(14)
            .background(ist ? GC.accentSubtle : GC.bg,
                        in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(ist ? GC.accent : GC.linie, lineWidth: ist ? 1.5 : 1))
        }
        .buttonStyle(.plain)
    }

    /// Nur Apples Preis — er steht in der Währung des Landes. Solange er fehlt,
    /// steht ein Strich da, kein Euro-Ersatzwert neben „Preise werden geladen".
    private func preis(_ stufe: PlatzStufe) -> String {
        kasse.produkte[stufe.apple]?.displayPrice ?? "–"
    }

    private func kaufen(_ stufe: PlatzStufe) async -> Bool {
        // Die Kaufkennung geht als `appAccountToken` mit: damit gehört der
        // Kauf dem Betrieb, nicht dem Telefon (14.10.2026).
        let ok = await kasse.kaufen(stufe, kennung: store.kaufKennung)
        if ok { await store.kontoNachfragen() }
        return ok
    }

    // MARK: - Das Kleingedruckte

    private var kleingedrucktes: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Jede Stufe läuft einen Monat und verlängert sich von "
                  + "selbst, bis du kündigst.", systemImage: "arrow.clockwise")
            Label("Deine Belege liegen in Deutschland.",
                  systemImage: "lock.shield")
            Label("Monatlich kündbar — in den Einstellungen deines "
                  + "Apple-Kontos.", systemImage: "calendar")
            Label("Kündigst du, bleiben deine Belege lesbar. Es kommt nur "
                  + "nichts Neues dazu.", systemImage: "tray.full")
            Label("ERiC und der Anschluss an die Buchhaltung kommen dazu, "
                  + "sobald sie fertig sind — für alle, ohne Aufpreis.",
                  systemImage: "gift")
            rechtliches
        }
        .font(.caption)
        .foregroundStyle(GC.desc)
        .labelStyle(.titleAndIcon)
    }

    /// Nutzungsbedingungen und Datenschutz — hier, am Ort des Kaufs.
    ///
    /// Sie standen schon in den Einstellungen. Apple verlangt sie aber dort,
    /// wo abgeschlossen wird (3.1.2): wer kauft, muss die Bedingungen lesen
    /// können, ohne die Auswahl zu verlassen und sie zu suchen.
    @ViewBuilder private var rechtliches: some View {
        HStack(spacing: 14) {
            if let ab = URL(string: store.ablageURL + "/agb") {
                Link("Nutzungsbedingungen", destination: ab)
            }
            if let ds = URL(string: store.ablageURL + "/datenschutz") {
                Link("Datenschutz", destination: ds)
            }
            Spacer(minLength: 0)
        }
        .font(.caption)
        .foregroundStyle(GC.accent)
        .padding(.top, 2)
    }
}
