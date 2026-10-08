import SwiftUI
import UIKit

/// Konzept „Ein Knopf": die eine Seite.
///
/// Eine Zahl, ein Satz, ein Knopf — sonst nichts. Keine Reiter, kein Menü,
/// keine Liste. Knopf = tun, Wischen nach unten = später. Welche Seite dran
/// ist, entscheidet die Regie (`EinKnopfLage`); nach jeder Aktion neu.
/// Raus geht es nur über das kleine „Konzept" oben rechts — das ist Chrome,
/// kein Seitenknopf.
struct EinKnopfView: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var lage = EinKnopfLage()

    @State private var versatz: CGFloat = 0
    @State private var antwortBlatt = false
    @State private var fragenBeleg: Kennung?
    @State private var zeigeScanner = false
    @State private var spaeterDialog = false
    @State private var grundDialog = false
    @State private var konzeptDialog = false
    @State private var stumm = Katsching.stumm

    /// `fullScreenCover(item:)` will etwas Identifizierbares — eine UUID allein ist es nicht.
    private struct Kennung: Identifiable, Equatable { let id: UUID }

    var body: some View {
        ZStack {
            GC.canvas.ignoresSafeArea()
            if let m = lage.moment {
                momentAnsicht(m)
                    .transition(.opacity)
            } else {
                seite
                    .id(lage.seite.kennung)
                    .transition(reduceMotion
                                ? .opacity
                                : .asymmetric(
                                    insertion: .move(edge: .bottom).combined(with: .opacity),
                                    removal: .move(edge: .bottom).combined(with: .opacity)))
                    .offset(y: max(0, versatz))
                    .gesture(wischen)
            }
        }
        .overlay(alignment: .topTrailing) { konzeptAbzeichen }
        .task { await lage.starten(store: store) }
        .onChange(of: lage.moment) { _, neu in
            guard let neu else { return }
            Task {
                try? await Task.sleep(nanoseconds: 1_800_000_000)
                // Nur den eigenen Moment beenden — kommt in der Zwischenzeit
                // ein neuer, gehört die Uhr ihm.
                guard lage.moment?.id == neu.id else { return }
                await lage.momentVorbei(store: store)
            }
        }
        // „Teilen → In babu öffnen": ein Bild landet direkt im Reinwerfen.
        // PDFs bleiben im Prototyp der gewohnten Ansicht vorbehalten.
        .onOpenURL { url in
            let zugriff = url.startAccessingSecurityScopedResource()
            defer { if zugriff { url.stopAccessingSecurityScopedResource() } }
            guard let daten = try? Data(contentsOf: url),
                  let bild = UIImage(data: daten) else { return }
            Task { await reinwerfen(bild) }
        }
        .sheet(isPresented: $antwortBlatt) {
            antwortOptionen
                .presentationDetents([.medium])
                .presentationBackground(GC.canvas)
        }
        .fullScreenCover(item: $fragenBeleg) { k in
            BuchungsfragenView(belegID: k.id).environmentObject(store)
        }
        .onChange(of: fragenBeleg) { alt, neu in
            if let alt, neu == nil {
                Task { await lage.nachFragen(id: alt.id, store: store) }
            }
        }
        .fullScreenCover(isPresented: $zeigeScanner) {
            ScannerView(
                onScan: { bild in
                    zeigeScanner = false
                    Task { await reinwerfen(bild) }
                },
                onCancel: { zeigeScanner = false })
        }
        .confirmationDialog("Und der Beleg?", isPresented: $spaeterDialog) {
            Button("Später") { Task { await lage.spaeter(store: store) } }
            Button("Dazu gibt es keinen Beleg") { grundDialog = true }
            Button("Abbrechen", role: .cancel) { }
        }
        .confirmationDialog("Warum gibt es keinen Beleg?", isPresented: $grundDialog) {
            ForEach(lage.gruende) { g in
                Button(g.name) { Task { await lage.klaeren(grund: g.schluessel, store: store) } }
            }
            Button("Abbrechen", role: .cancel) { }
        }
        .confirmationDialog("Konzept „Ein Knopf“", isPresented: $konzeptDialog) {
            Button("Zurück zur gewohnten Ansicht") { store.einKnopf = false }
            if lage.rundgang {
                Button("Rundgang von vorn") { Task { await lage.vonVorn(store: store) } }
            }
            Button(stumm ? "Katsching wieder an" : "Katsching stumm") {
                stumm.toggle()
                Katsching.stumm = stumm
            }
            Button("Abbrechen", role: .cancel) { }
        }
    }

    // MARK: - Die Seite

    private var seite: some View {
        VStack(spacing: 0) {
            Spacer()

            if case .monatFertig = lage.seite {
                // Der eine grüne Haken — die einzige Zierde auf irgendeiner Seite.
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 40))
                    .foregroundStyle(GC.ok)
                    .padding(.bottom, 18)
            }

            if let label = lage.blatt.label {
                Text(label.uppercased())
                    .font(.system(size: 11, design: .monospaced))
                    .kerning(1.2)
                    .foregroundStyle(GC.desc)
                    .padding(.bottom, 8)
            }

            Text(lage.blatt.zahl)
                .font(.system(size: 64, weight: .semibold, design: .serif))
                .monospacedDigit()
                .foregroundStyle(GC.fg)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .contentTransition(.numericText())

            Text(lage.hinweis ?? lage.blatt.satz)
                .font(.title3)
                .fontDesign(.serif)
                .foregroundStyle(lage.hinweis == nil ? GC.body : GC.warn)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 22)

            Spacer()

            Button {
                knopfGedrueckt()
            } label: {
                HStack(spacing: 10) {
                    if lage.laedt { ProgressView().tint(.white) }
                    Text(lage.blatt.knopf)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .tint(farbe(lage.blatt.stimmung))
            .disabled(lage.laedt)
            .padding(.bottom, 36)
        }
        .padding(.horizontal, 28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
    }

    private func farbe(_ s: Regie.Stimmung) -> Color {
        switch s {
        case .ruhig: return GC.accent
        case .mahnend: return GC.warn
        case .dringend: return GC.danger
        case .fertig: return GC.ok
        }
    }

    private func knopfGedrueckt() {
        switch lage.seite {
        case .fristNaht:
            Task { await lage.loslegen(store: store) }
        case .frage(let f):
            if let id = f.belegID { fragenBeleg = Kennung(id: id) } else { antwortBlatt = true }
        case .belegFehlt, .heim:
            kameraOeffnen()
        case .monatFertig:
            Task { await lage.abschicken(store: store) }
        }
    }

    /// Im Simulator gibt es keine Kamera — dort liest der Demo-Beleg.
    private func kameraOeffnen() {
        #if targetEnvironment(simulator)
        Task { await reinwerfen(DemoBeleg.bild()) }
        #else
        if ScannerView.verfuegbar {
            zeigeScanner = true
        } else {
            Task { await reinwerfen(DemoBeleg.bild()) }
        }
        #endif
    }

    private func reinwerfen(_ bild: UIImage) async {
        if let id = await lage.reingeworfen(bild, store: store) {
            fragenBeleg = Kennung(id: id)
        }
    }

    // MARK: - Wischen = später

    private var wischen: some Gesture {
        DragGesture()
            .onChanged { wert in
                versatz = wert.translation.height
            }
            .onEnded { wert in
                guard wert.translation.height > 120 else {
                    withAnimation(.spring(duration: 0.3)) { versatz = 0 }
                    return
                }
                switch lage.seite {
                case .belegFehlt:
                    withAnimation(.spring(duration: 0.3)) { versatz = 0 }
                    spaeterDialog = true
                case .heim:
                    // Nichts aufzuschieben — die Seite federt zurück.
                    withAnimation(.spring(duration: 0.3)) { versatz = 0 }
                default:
                    withAnimation(.easeIn(duration: 0.22)) { versatz = 700 }
                    Task {
                        await lage.spaeter(store: store)
                        versatz = 0
                    }
                }
            }
    }

    // MARK: - Halbblatt mit Antworten

    private var antwortOptionen: some View {
        VStack(alignment: .leading, spacing: 14) {
            if case .frage(let f) = lage.seite {
                Text(f.text)
                    .font(.title3)
                    .fontDesign(.serif)
                    .foregroundStyle(GC.fg)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.bottom, 6)
                ForEach(f.optionen, id: \.self) { option in
                    Button {
                        antwortBlatt = false
                        Task {
                            // Erst geht das Blatt zu, dann kommt der Moment —
                            // sonst überlagern sich beide Bewegungen.
                            try? await Task.sleep(nanoseconds: 350_000_000)
                            await lage.antworten(option, store: store)
                        }
                    } label: {
                        Text(option).frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .tint(GC.accent)
                }
            }
            Spacer()
        }
        .padding(24)
    }

    // MARK: - Momente

    @ViewBuilder
    private func momentAnsicht(_ m: EinKnopfLage.Moment) -> some View {
        switch m {
        case .katsching(let a):
            KatschingMoment(anlass: a).id(a.id)
        case .unterwegs(let id, let satz):
            UnterwegsMoment(satz: satz).id(id)
        }
    }

    // MARK: - Chrome

    private var konzeptAbzeichen: some View {
        Button {
            konzeptDialog = true
        } label: {
            BadgeView(text: "Konzept", color: GC.muted)
                .padding(8)
        }
        .buttonStyle(.plain)
        .padding(.top, 6)
        .padding(.trailing, 12)
        .accessibilityLabel("Konzept-Einstellungen")
    }
}
