import SwiftUI

/// „Aufräumen" — der Belege-Stapel: ein offener Beleg pro Karte, eine
/// Entscheidung pro Wisch. Rechts = buchen (Karte fliegt mit Bronze-Haken
/// davon), links = später (sanft — nichts ist „falsch"). Bewirtungsbelege
/// ohne Angaben fragen beim Buchen freundlich nach. Am Ende: Abschluss-
/// Moment mit Tagessumme.
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
                              color: beleg.herkunft == .historie ? GC.accent :
                                     beleg.herkunft == .regel ? GC.ok : GC.warn)
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
        if beleg.konto == nil {
            // Ohne Kategorie wird nichts gebucht und nichts gesiegelt —
            // erst kurz eine wählen (sonst leeres Kontofeld im Stapel).
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

    private var finale: some View {
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
