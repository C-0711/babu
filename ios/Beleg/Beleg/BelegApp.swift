import SwiftUI

@main
struct BelegApp: App {
    @StateObject private var store = AppStore()
    @UIApplicationDelegateAdaptor(PushDelegate.self) private var pushDelegate
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .tint(GC.accent)
                // Das Design ist bewusst hell (feste Farb-Tokens); ohne diese
                // Festlegung wären Listen und Editoren im Dunkelmodus unlesbar.
                .preferredColorScheme(.light)
                // Kaltstart: scenePhase meldet keinen Wechsel, wenn die App
                // frisch startet — dieser Aufruf ist der einzige, der dann greift.
                .task { store.beimSichtbarwerden() }
        }
        .onChange(of: scenePhase) { _, neu in
            switch neu {
            case .background: store.sichern()
            case .active: store.beimSichtbarwerden()
            default: break
            }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        Group {
            if store.onboarded {
                // Konzept „Ein Knopf" (Testphase): eine Seite statt Reiter.
                if store.einKnopf {
                    EinKnopfView()
                } else {
                    MainTabs()
                }
            } else {
                OnboardingView()
            }
        }
        // EIN Empfänger für alle Adressen, hier oben: der Anmelde-Link aus
        // der Mail kommt auch, wenn die Begrüßung noch offen ist — dort gab
        // es bis 08.10.2026 keinen, und der Link wäre verpufft.
        .onOpenURL { url in
            if let token = Anmeldelink.token(aus: url) {
                Task {
                    let antwort = await store.mitLinkAnmelden(
                        token: token, geraet: UIDevice.current.name)
                    // Über dem obersten Blatt zeigen: meist ist gerade das
                    // Konto-Blatt offen, in dem sie den Link bestellt hat.
                    Obenauf.hinweis(antwort.titel, antwort.text)
                }
                return
            }
            // Rechnung aus Mail, WhatsApp oder Dateien: „Teilen → In babu öffnen"
            store.tab = .erfassen
            store.geteilteDatei = url
        }
        .overlay {
            if store.anmeldungLaeuft {
                ZStack {
                    Color.black.opacity(0.15).ignoresSafeArea()
                    VStack(spacing: 12) {
                        ProgressView().controlSize(.large)
                        Text("Einen Moment — du wirst angemeldet …")
                            .font(.callout)
                            .foregroundStyle(GC.body)
                    }
                    .padding(28)
                    .background(GC.bg, in: RoundedRectangle(cornerRadius: 18))
                }
            }
        }
    }
}

struct MainTabs: View {
    @EnvironmentObject var store: AppStore

    /// Welche Reiter es gibt, steht in `Ausbaustufe` — an einer Stelle für
    /// beide Bauarten. Der schmale Bau hat drei: Erfassen, Dokumente, Fragen;
    /// eine Ambassadorin bekommt „Empfehlen" dazu.
    private var reiter: [Reiter] {
        Ausbaustufe.reiter(fuer: store.rechte, ambassadorin: store.ambassadorin)
    }

    var body: some View {
        ZStack {
            // Ein Reiter allein (Ambassadorin ohne eigene Ablage) bekommt
            // keine Leiste mit einem einzigen Knopf — er ist die Seite.
            if let seite = Ausbaustufe.ganzeSeite(fuer: store.rechte,
                                                  ambassadorin: store.ambassadorin) {
                inhalt(seite)
            } else {
                TabView(selection: $store.tab) {
                    ForEach(reiter, id: \.self) { reiter in
                        inhalt(reiter)
                            .tabItem { Label(reiter.titel, systemImage: reiter.symbol) }
                            .tag(reiter.tab)
                    }
                }
            }
        }
        // Einmal beim Start fragen, als wer dieses Gerät angemeldet ist —
        // damit das Zeichen oben rechts von Anfang an die Wahrheit sagt und
        // ein abgelaufener Zugang auffällt, bevor ein Beleg liegen bleibt.
        .task { await store.kontoNachfragen() }
        // Verschwindet der Reiter, in dem sie gerade ist (abgemeldet, keine
        // Ambassadorin mehr), nicht im Nichts stehen bleiben.
        .onChange(of: reiter) { _, neu in
            if !neu.contains(where: { $0.tab == store.tab }), let erster = neu.first {
                store.tab = erster.tab
            }
        }
    }

    /// Was hinter einem Reiter steckt.
    @ViewBuilder
    private func inhalt(_ reiter: Reiter) -> some View {
        switch reiter {
        case .erfassen:  CaptureTab()
        case .auslagen:  AuslagenTab()
        case .empfehlen: EmpfehlenTab()
        // Nicht mehr nur Belege: Kontoauszüge, Verträge und Post vom Amt
        // liegen hier ebenso, jedes in seiner Art.
        case .dokumente: ListeView()
        case .termine:   TermineTab()
        case .kasse:     KasseTab()
        case .fragen:    FragenTab()
        }
    }
}
