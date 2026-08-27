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
    let startZeit: Date
    var fertig: () -> Void

    @State private var hakenDa = false
    @State private var hakenGeparkt = false   // nach dem Moment: klein neben den Namen
    @State private var zeigeInfo = false
    @State private var zeigeBewirtung = false
    @Namespace private var hakenNS

    private var aktuell: Beleg? { store.belege.first { $0.id == belegID } }

    private var hatHinweis: Bool {
        guard let b = aktuell else { return false }
        return !b.summenprobeOK || b.brauchtBewirtungsangaben
    }

    var body: some View {
        if let b = aktuell {
            ZStack(alignment: .topTrailing) {
                VStack(spacing: 12) {
                    // Der Beleg bekommt allen verfügbaren Platz.
                    belegAnsicht
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(b.lieferant)
                            .font(.title3.weight(.semibold))
                            .fontDesign(.serif)
                            .foregroundStyle(GC.fg)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        if let n = b.seitenJpeg?.count, n > 1 {
                            Text("\(n) Seiten — ein Beleg")
                                .font(.footnote)
                                .foregroundStyle(GC.muted)
                        }
                        if hakenGeparkt {
                            // Der Haken landet hier — bestätigt, ohne zu verdecken.
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 22))
                                .foregroundStyle(GC.ok)
                                .matchedGeometryEffect(id: "haken", in: hakenNS)
                        }
                        Spacer()
                        Text(fmtEur(b.brutto))
                            .font(.system(size: 22, weight: .medium, design: .monospaced))
                            .foregroundStyle(GC.fg)
                            .layoutPriority(1)
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
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    aktionen(b)
                }
                .padding(.horizontal, 14)
                .padding(.top, 4)
                .padding(.bottom, 12)

                Button {
                    zeigeInfo = true
                } label: {
                    Image(systemName: "info.circle")
                        .font(.system(size: 20))
                        .foregroundStyle(GC.desc)
                        .frame(width: 40, height: 40)
                        .background(.ultraThinMaterial, in: Circle())
                }
                .accessibilityLabel("Alle Angaben zum Beleg")
                .padding(.trailing, 18)
                .padding(.top, 10)
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
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .shadow(color: Color(hex: 0x1F1E1A).opacity(0.22), radius: 14, y: 7)
            } else {
                RoundedRectangle(cornerRadius: 14)
                    .fill(GC.accentSubtle)
                    .frame(height: 260)
            }
        }
        .overlay {
            // Der Haken feiert kurz groß in der Mitte und fliegt dann in die
            // Namenszeile — die Sicht gehört dem Beleg.
            if !hakenGeparkt {
                grosserHaken
                    .matchedGeometryEffect(id: "haken", in: hakenNS)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Beleg erfolgreich gelesen")
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
            hakenGeparkt = true
            return
        }
        withAnimation(.spring(response: 0.45, dampingFraction: 0.62).delay(0.05)) {
            hakenDa = true
        }
        Task {
            try? await Task.sleep(nanoseconds: 1_400_000_000)
            withAnimation(.spring(response: 0.55, dampingFraction: 0.8)) {
                hakenGeparkt = true
            }
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
                Text("Zu den Dokumenten").frame(maxWidth: .infinity)
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
            .warmerGrund()
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
