import SwiftUI
import UIKit

/// Ruhige Bestätigung nach der Aufnahme: das Beleg-Foto mit grün markierten
/// Feldern und einem großen grünen Haken darüber. Alles Weitere (Buchungssatz,
/// Einordnung, Hinweise) liegt hinter dem ⓘ oben rechts — die Nutzerin soll
/// auf einen Blick sehen: hat funktioniert.
struct ErgebnisUebersicht: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    let belegID: UUID
    let bild: UIImage?
    let markierungen: [CGRect]   // Vision-normiert, Ursprung unten links
    let startZeit: Date
    var fertig: () -> Void

    @State private var hakenDa = false
    @State private var markierungenDa = false
    @State private var zeigeInfo = false
    @State private var zeigeBewirtung = false

    private var aktuell: Beleg? { store.belege.first { $0.id == belegID } }

    private var hatHinweis: Bool {
        guard let b = aktuell else { return false }
        return !b.summenprobeOK || b.gutschriftSignal == true || b.brauchtBewirtungsangaben
    }

    var body: some View {
        if let b = aktuell {
            ZStack(alignment: .topTrailing) {
                VStack(spacing: 16) {
                    Spacer(minLength: 4)
                    belegAnsicht
                    VStack(spacing: 2) {
                        Text(b.lieferant)
                            .font(.title3.weight(.semibold))
                            .fontDesign(.serif)
                            .foregroundStyle(GC.fg)
                            .lineLimit(1)
                        Text(fmtEur(b.brutto))
                            .font(.system(size: 30, weight: .medium, design: .monospaced))
                            .foregroundStyle(GC.fg)
                    }
                    if hatHinweis {
                        // Sanfter Fingerzeig statt Warntafel — Details unterm ⓘ.
                        Button {
                            zeigeInfo = true
                        } label: {
                            Label("Ein Hinweis dazu", systemImage: "info.circle")
                                .font(.footnote)
                                .foregroundStyle(GC.muted)
                        }
                    }
                    Spacer()
                    aktionen(b)
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 14)

                Button {
                    zeigeInfo = true
                } label: {
                    Image(systemName: "info.circle")
                        .font(.system(size: 20))
                        .foregroundStyle(GC.muted)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Alle Angaben zum Beleg")
                .padding(.trailing, 6)
            }
            .onAppear(perform: einblenden)
            .sheet(isPresented: $zeigeInfo) { infoSheet(b) }
            .sheet(isPresented: $zeigeBewirtung) {
                BewirtungsangabenSheet(belegID: b.id) {
                    store.buchen(id: b.id, konto: nil, steuerschluessel: nil,
                                 dauer: Date().timeIntervalSince(startZeit))
                }
            }
        }
    }

    // MARK: - Beleg mit Markierungen + Haken

    @ViewBuilder
    private var belegAnsicht: some View {
        Group {
            if let bild {
                Image(uiImage: bild)
                    .resizable()
                    .scaledToFit()
                    .overlay {
                        GeometryReader { geo in
                            ZStack {
                                ForEach(Array(markierungen.enumerated()), id: \.offset) { _, r in
                                    RoundedRectangle(cornerRadius: 5)
                                        .fill(GC.ok.opacity(0.16))
                                        .overlay(RoundedRectangle(cornerRadius: 5)
                                            .stroke(GC.ok, lineWidth: 1.6))
                                        .frame(width: r.width * geo.size.width + 10,
                                               height: r.height * geo.size.height + 8)
                                        .position(x: r.midX * geo.size.width,
                                                  y: (1 - r.midY) * geo.size.height)
                                }
                            }
                            .opacity(markierungenDa ? 1 : 0)
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .shadow(color: Color(hex: 0x1F1E1A).opacity(0.22), radius: 14, y: 7)
            } else {
                RoundedRectangle(cornerRadius: 14)
                    .fill(GC.accentSubtle)
                    .frame(height: 260)
            }
        }
        .frame(maxHeight: 380)
        .overlay { grosserHaken }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Beleg erfolgreich gelesen — die erkannten Angaben sind markiert")
    }

    private var grosserHaken: some View {
        ZStack {
            Circle()
                .fill(.white)
                .frame(width: 96, height: 96)
                .shadow(color: Color(hex: 0x1F1E1A).opacity(0.25), radius: 12, y: 5)
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 92))
                .foregroundStyle(GC.ok)
        }
        .scaleEffect(hakenDa ? 1 : 0.4)
        .opacity(hakenDa ? 1 : 0)
    }

    private func einblenden() {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        if reduceMotion {
            hakenDa = true
            markierungenDa = true
            return
        }
        withAnimation(.spring(response: 0.45, dampingFraction: 0.62).delay(0.05)) {
            hakenDa = true
        }
        withAnimation(.easeIn(duration: 0.35).delay(0.3)) {
            markierungenDa = true
        }
    }

    // MARK: - Aktionen

    @ViewBuilder
    private func aktionen(_ b: Beleg) -> some View {
        if b.status == .offen {
            if b.confidence >= 80 {
                Button {
                    if b.brauchtBewirtungsangaben {
                        zeigeBewirtung = true
                    } else {
                        store.buchen(id: b.id, konto: nil, steuerschluessel: nil,
                                     dauer: Date().timeIntervalSince(startZeit))
                    }
                } label: {
                    Text("Passt so").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            } else {
                Button {
                    zeigeInfo = true
                } label: {
                    Text("Kurz ansehen").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
        }
        HStack(spacing: 10) {
            Button {
                fertig()
            } label: {
                Text("Weiter erfassen").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            Button {
                fertig()
                store.tab = .belege
            } label: {
                Text("Zur Belegliste").frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
    }

    // MARK: - ⓘ: alle Angaben (die bisherige Ergebnis-Karte)

    private func infoSheet(_ b: Beleg) -> some View {
        NavigationStack {
            ScrollView {
                ErgebnisKarte(beleg: b, startZeit: startZeit) {
                    zeigeInfo = false
                    fertig()
                }
                .padding(16)
            }
            .background(GC.canvas)
            .navigationTitle("Alle Angaben")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { zeigeInfo = false }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
