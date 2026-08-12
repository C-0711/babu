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
        }
        .onChange(of: scenePhase) { _, neu in
            if neu == .background { store.sichern() }
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
            ExportView()
                .tabItem { Label("Export", systemImage: "square.and.arrow.up") }
                .tag(AppStore.Tab.export)
        }
    }
}
