import SwiftUI

/// „Aufräumen" — der Belege-Stapel: ein offener Beleg pro Karte, eine
/// Entscheidung pro Wisch. Rechts = buchen (Karte fliegt mit Bronze-Haken
/// davon), links = später (sanft — nichts ist „falsch"). Bewirtungsbelege
/// ohne Angaben fragen beim Buchen freundlich nach. Am Ende: Abschluss-
/// Moment mit Tagessumme.
/// Welcher Beleg gerade groß offen ist — nur ein Träger, damit `sheet(item:)`
/// etwas Identifizierbares bekommt.
struct Grossansicht: Identifiable {
    let id: UUID
}

struct AufraeumenView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var stapel: [UUID] = []
    @State private var gebucht = 0
    @State private var gebuchtSumme = 0.0
    @State private var versatz: CGSize = .zero
    @State private var fliegt = false
    @State private var zeigeBewirtung = false
    @State private var zeigeKontierung = false
    @State private var startZeit = Date()
    /// Welcher Beleg gerade groß angesehen wird. Im Wischstapel geht Zoomen
    /// nicht an Ort und Stelle — zwei Finger auf der Karte wären dieselbe
    /// Geste wie das Wischen. Also aufs Bild tippen und in Ruhe hineinsehen.
    @State private var grossAnsehen: Grossansicht?
    /// War beim Öffnen schon nichts offen? Dann ist „Alles aufgeräumt" gelogen
    /// — es wurde ja nichts aufgeräumt. Seit das Aufräumen auch im Konto-Menü
    /// steht, kommt man hier an, ohne dass etwas wartet; dann muss die Ansicht
    /// das sagen, statt einen Erfolg zu feiern, den es nicht gab.
    @State private var vonAnfangAnLeer = false

    private var oberster: Beleg? {
        guard let id = stapel.first else { return nil }
        return store.belege.first { $0.id == id }
    }

    private var naechster: Beleg? {
        guard stapel.count > 1 else { return nil }
        return store.belege.first { $0.id == stapel[1] }
    }

    var body: some View {
        ZStack {
            GC.canvas.ignoresSafeArea()
            VStack(spacing: 0) {
                kopf
                Spacer()
                if let beleg = oberster {
                    kartenBereich(beleg)
                    Spacer()
                    knoepfe(beleg)
                        .padding(.bottom, 26)
                } else {
                    finale
                    Spacer()
                }
            }
        }
        .onAppear {
            stapel = store.belege.filter { $0.status == .offen }.map(\.id)
            vonAnfangAnLeer = stapel.isEmpty
            startZeit = Date()
        }
        .sheet(isPresented: $zeigeBewirtung) {
            if let beleg = oberster {
                BewirtungsangabenSheet(belegID: beleg.id) {
                    buchen(beleg)
                }
            }
        }
        .sheet(isPresented: $zeigeKontierung, onDismiss: kontierungAbgeschlossen) {
            if let beleg = oberster {
                ReviewSheet(belegID: beleg.id, startZeit: startZeit)
            }
        }
        .sheet(item: $grossAnsehen) { auswahl in
            if let beleg = store.belege.first(where: { $0.id == auswahl.id }) {
                BelegGrossView(beleg: beleg).environmentObject(store)
            }
        }
    }

    // MARK: - Kopf

    private var kopf: some View {
        HStack {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(GC.desc)
                    .frame(width: 44, height: 44)
                    .background(GC.chrome, in: Circle())
            }
            .accessibilityLabel("Schließen")
            Spacer()
            if !stapel.isEmpty {
                Text("Noch \(stapel.count)")
                    .font(.caption.monospaced())
                    .foregroundStyle(GC.muted)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
    }

    // MARK: - Karten

    private func kartenBereich(_ beleg: Beleg) -> some View {
        ZStack {
            if let dahinter = naechster {
                karte(dahinter)
                    .scaleEffect(0.94)
                    .offset(y: 12)
                    .opacity(0.6)
            }
            karte(beleg)
                .offset(versatz)
                .rotationEffect(.degrees(Double(versatz.width) / 18))
                .overlay(wischHinweis)
                .gesture(
                    DragGesture()
                        .onChanged { wert in
                            guard !fliegt else { return }
                            versatz = wert.translation
                        }
                        .onEnded { wert in
                            guard !fliegt else { return }
                            if wert.translation.width > 110 {
                                buchenAnstossen(beleg)
                            } else if wert.translation.width < -110 {
                                spaeter()
                            } else {
                                withAnimation(.spring(duration: 0.3)) { versatz = .zero }
                            }
                        }
                )
        }
        .padding(.horizontal, 28)
    }

    private func karte(_ beleg: Beleg) -> some View {
        VStack(spacing: 0) {
            if let daten = beleg.bildJpeg, let bild = UIImage(data: daten) {
                Image(uiImage: bild)
                    .resizable()
                    .scaledToFill()
                    .frame(height: 220)
                    .clipped()
                    .overlay(alignment: .topTrailing) {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(GC.fg)
                            .frame(width: 32, height: 32)
                            .background(.ultraThinMaterial, in: Circle())
                            .padding(10)
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { grossAnsehen = Grossansicht(id: beleg.id) }
                    .accessibilityAddTraits(.isButton)
                    .accessibilityLabel("Beleg groß ansehen")
            } else {
                GC.accentSubtle.frame(height: 120)
                    .overlay(Image(systemName: "doc.text")
                        .font(.system(size: 34, weight: .light))
                        .foregroundStyle(GC.accent))
            }
            VStack(alignment: .leading, spacing: 8) {
                Text(beleg.lieferant)
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                    .lineLimit(1)
                Text(fmtEur(beleg.brutto))
                    .font(.system(size: 34, weight: .medium, design: .monospaced))
                    .foregroundStyle(GC.fg)
                HStack(spacing: 8) {
                    if let konto = beleg.konto {
                        BadgeView(text: Kontenplan.bezeichnung(konto), color: GC.accent)
                    }
                    BadgeView(text: beleg.herkunft.kurz,
                              color: herkunftsFarbe(beleg.herkunft))
                    Text("\(beleg.confidence) %")
                        .font(.caption.monospaced())
                        .foregroundStyle(GC.muted)
                }
                if beleg.konto == nil {
                    Label("Noch keine Kategorie — beim Buchen wählst du kurz eine aus.",
                          systemImage: "tray")
                        .font(.footnote)
                        .foregroundStyle(GC.warn)
                }
                if beleg.brauchtBewirtungsangaben {
                    Label("Beim Buchen wird kurz nachgefragt: Mit wem warst du essen?",
                          systemImage: "person.2")
                        .font(.footnote)
                        .foregroundStyle(GC.warn)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .background(GC.bg)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .shadow(color: Color(hex: 0x1F1E1A).opacity(0.14), radius: 16, y: 8)
    }

    /// Beim Ziehen: rechts kündigt der Bronze-Haken das Buchen an,
    /// links ein ruhiges „Später" — bewusst kein Rot.
    @ViewBuilder
    private var wischHinweis: some View {
        if versatz.width > 40 {
            wischMarke("checkmark.seal.fill", "Buchen", GC.accent,
                       staerke: min(1, Double(versatz.width - 40) / 80))
        } else if versatz.width < -40 {
            wischMarke("clock", "Später", GC.muted,
                       staerke: min(1, Double(-versatz.width - 40) / 80))
        }
    }

    private func wischMarke(_ symbol: String, _ text: String, _ farbe: Color,
                            staerke: Double) -> some View {
        VStack(spacing: 6) {
            Image(systemName: symbol).font(.system(size: 44))
            Text(text).font(.headline)
        }
        .foregroundStyle(farbe)
        .opacity(staerke)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(GC.bg.opacity(0.55 * staerke))
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .allowsHitTesting(false)
    }

    // MARK: - Aktionen

    private func knoepfe(_ beleg: Beleg) -> some View {
        HStack(spacing: 14) {
            Button {
                spaeter()
            } label: {
                Label("Später", systemImage: "clock")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            Button {
                buchenAnstossen(beleg)
            } label: {
                Label("Buchen", systemImage: "checkmark.seal")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding(.horizontal, 28)
    }

    private func buchenAnstossen(_ beleg: Beleg) {
        if beleg.konto == nil || beleg.brauchtBetrag {
            // Ohne Kategorie oder ohne Betrag wird nichts gebucht und nichts
            // gesiegelt — im Kontierungs-Sheet lässt sich beides klären
            // (dort wohnt auch „Angaben korrigieren" für den Betrag).
            withAnimation(.spring(duration: 0.3)) { versatz = .zero }
            zeigeKontierung = true
        } else if beleg.brauchtBewirtungsangaben {
            withAnimation(.spring(duration: 0.3)) { versatz = .zero }
            zeigeBewirtung = true
        } else {
            buchen(beleg)
        }
    }

    /// Nach dem Kontierungs-Sheet: wurde gebucht, fliegt die Karte davon;
    /// bei Abbruch bleibt der Beleg einfach oben liegen.
    private func kontierungAbgeschlossen() {
        guard let beleg = oberster, beleg.status != .offen else { return }
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        gebucht += 1
        gebuchtSumme += beleg.brutto
        flieg(richtung: 620)
    }

    private func buchen(_ beleg: Beleg) {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        gebucht += 1
        gebuchtSumme += beleg.brutto
        store.buchen(id: beleg.id, konto: nil, steuerschluessel: nil,
                     dauer: Date().timeIntervalSince(startZeit))
        flieg(richtung: 620)
    }

    private func spaeter() {
        flieg(richtung: -620)   // Beleg bleibt offen in der Liste
    }

    private func flieg(richtung: CGFloat) {
        guard !fliegt else { return }
        fliegt = true
        if reduceMotion {
            versatz = .zero
            if !stapel.isEmpty { stapel.removeFirst() }
            fliegt = false
            return
        }
        withAnimation(.easeIn(duration: 0.28)) {
            versatz = CGSize(width: richtung, height: -40)
        }
        Task {
            try? await Task.sleep(nanoseconds: 290_000_000)
            versatz = .zero
            if !stapel.isEmpty { stapel.removeFirst() }
            fliegt = false
        }
    }

    // MARK: - Finale

    @ViewBuilder
    private var finale: some View {
        if vonAnfangAnLeer { nichtsOffen } else { geschafft }
    }

    /// Hier war nichts zu tun. Kein Konfetti, kein „geschafft" — nur die
    /// Auskunft, warum der Stapel leer ist und wie er sich füllt.
    private var nichtsOffen: some View {
        VStack(spacing: 14) {
            Image(systemName: "rectangle.stack")
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(GC.accent)
            Text("Gerade ist nichts offen")
                .font(.system(size: 28, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)
                .multilineTextAlignment(.center)
            Text("Sobald ein Beleg auf eine Entscheidung wartet, liegt er "
                 + "hier — und du wischst dich in Ruhe durch.")
                .font(.subheadline)
                .foregroundStyle(GC.desc)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 36)
            Button {
                dismiss()
            } label: {
                Text("Fertig").frame(maxWidth: 200)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.top, 10)
        }
        .padding(.top, 70)
    }

    private var geschafft: some View {
        VStack(spacing: 14) {
            HStack(spacing: 10) {
                Text("Alles aufgeräumt")
                    .font(.system(size: 30, weight: .semibold, design: .serif))
                    .foregroundStyle(GC.fg)
                Text("✨")
                    .font(.system(size: 26))
            }
            if gebucht > 0 {
                Text("\(gebucht) \(gebucht == 1 ? "Beleg" : "Belege") gebucht · \(fmtEur(gebuchtSumme))")
                    .font(.subheadline.monospaced())
                    .foregroundStyle(GC.desc)
            } else {
                Text("Keine offenen Belege — schön.")
                    .font(.subheadline)
                    .foregroundStyle(GC.desc)
            }
            Button {
                dismiss()
            } label: {
                Text("Fertig").frame(maxWidth: 200)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.top, 10)
        }
        .padding(.top, 80)
    }
}
