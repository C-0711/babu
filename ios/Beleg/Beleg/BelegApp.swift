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
        TabView(selection: $store.tab) {
            CaptureTab()
                .tabItem { Label("Erfassen", systemImage: "viewfinder") }
                .tag(AppStore.Tab.erfassen)
            ListeView()
                .tabItem { Label("Belege", systemImage: "doc.text") }
                .tag(AppStore.Tab.belege)
            KasseTab()
                .tabItem { Label("Kassenbuch", systemImage: "banknote") }
                .tag(AppStore.Tab.kasse)
            RechnungenTab()
                .tabItem { Label("Rechnungen", systemImage: "eurosign.circle") }
                .tag(AppStore.Tab.rechnungen)
            FragenTab()
                .tabItem { Label("Fragen", systemImage: "questionmark.bubble") }
                .tag(AppStore.Tab.fragen)
        }
        // Rechnung aus Mail, WhatsApp oder Dateien: „Teilen → In babu öffnen"
        .onOpenURL { url in
            store.tab = .erfassen
            store.geteilteDatei = url
        }
    }
}
