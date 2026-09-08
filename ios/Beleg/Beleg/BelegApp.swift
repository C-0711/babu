import SwiftUI

@main
struct BelegApp: App {
    @StateObject private var store = AppStore()
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
        if store.onboarded {
            MainTabs()
        } else {
            OnboardingView()
        }
    }
}

struct MainTabs: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        // Welche Reiter es gibt, steht in `Ausbaustufe` — an einer Stelle für
        // beide Bauarten. Der schmale Bau hat drei: Erfassen, Dokumente, Fragen.
        TabView(selection: $store.tab) {
            ForEach(Ausbaustufe.reiter, id: \.self) { reiter in
                inhalt(reiter)
                    .tabItem { Label(reiter.titel, systemImage: reiter.symbol) }
                    .tag(reiter.tab)
            }
        }
        // Einmal beim Start fragen, als wer dieses Gerät angemeldet ist —
        // damit das Zeichen oben rechts von Anfang an die Wahrheit sagt und
        // ein abgelaufener Zugang auffällt, bevor ein Beleg liegen bleibt.
        .task { await store.kontoNachfragen() }
        // Rechnung aus Mail, WhatsApp oder Dateien: „Teilen → In babu öffnen"
        .onOpenURL { url in
            store.tab = .erfassen
            store.geteilteDatei = url
        }
    }

    /// Was hinter einem Reiter steckt.
    @ViewBuilder
    private func inhalt(_ reiter: Reiter) -> some View {
        switch reiter {
        case .erfassen:  CaptureTab()
        // Nicht mehr nur Belege: Kontoauszüge, Verträge und Post vom Amt
        // liegen hier ebenso, jedes in seiner Art.
        case .dokumente: ListeView()
        case .termine:   TermineTab()
        case .kasse:     KasseTab()
        case .fragen:    FragenTab()
        }
    }
}

extension Reiter {
    /// Die Marke, die der Reiter im Zustand trägt. `AppStore.Tab` kennt mehr
    /// Fälle als es Reiter gibt (alte gespeicherte Stände) — deshalb zwei
    /// Aufzählungen und diese eine Übersetzung.
    var tab: AppStore.Tab {
        switch self {
        case .erfassen:  return .erfassen
        case .dokumente: return .belege
        case .termine:   return .termine
        case .kasse:     return .kasse
        case .fragen:    return .fragen
        }
    }
}
