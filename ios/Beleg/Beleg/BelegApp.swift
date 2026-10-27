import SwiftUI

@main
struct BelegApp: App {
    @StateObject private var store = AppStore()
    /// Die Kasse (seit 10.10.2026): Stufen bei Apple kaufen. Sie liegt hier
    /// oben, weil Apple auch ohne offene Ansicht meldet — eine Verlängerung
    /// oder eine nachgereichte Freigabe kommt mitten in den Betrieb.
    @StateObject private var kasse = Kasse()
    @UIApplicationDelegateAdaptor(PushDelegate.self) private var pushDelegate
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .environmentObject(kasse)
                .tint(GC.accent)
                // Das Design ist bewusst hell (feste Farb-Tokens); ohne diese
                // Festlegung wären Listen und Editoren im Dunkelmodus unlesbar.
                .preferredColorScheme(.light)
                // Kaltstart: scenePhase meldet keinen Wechsel, wenn die App
                // frisch startet — dieser Aufruf ist der einzige, der dann greift.
                .task { store.beimSichtbarwerden() }
                // Die Kasse an den Server hängen und Apples Meldungen
                // mitlaufen lassen. `melden` gibt den signierten Beleg
                // weiter — geprüft wird er dort, nicht hier.
                .task {
                    kasse.melden = { jws in await store.apfelKaufMelden(jws) }
                    kasse.horchen()
                    // Was Apple an gültigen Belegen führt: fängt den Wechsel
                    // auf ein neues Telefon und den Fall, dass die Meldung
                    // nach dem Kauf nicht ankam.
                    if store.verbundenAls != nil {
                        _ = await kasse.laufendeMelden()
                    }
                }
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
                } else if store.breitErzwingen {
                    // Testphase: die breite Größenklasse erzwingen — derselbe
                    // Umgebungsschlüssel, den iPad und aufgeklapptes Duo setzen.
                    MainTabs().environment(\.horizontalSizeClass, .regular)
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
        // Die Stufenauswahl (seit 10.10.2026) hängt hier oben, nicht an
        // einem Reiter: „kein Platz" kann beim Fotografieren kommen, beim
        // Nachreichen eines wartenden Belegs oder im Konto.
        // Angefordert wird es nur über `store.platzZeigen()`: das erkennt einen
        // Schalter, der nach einem abgebrochenen Zeigen hängt. Ob das Blatt
        // wirklich da ist, meldet es selbst; erst dann zählt das Angebot nach
        // dem ersten Beleg als gezeigt.
        .sheet(isPresented: $store.zeigePlatz) {
            PlatzSheet()
                .formblatt()
                .onAppear {
                    store.platzBlattOffen = true
                    store.angebotGezeigt = true
                }
                .onDisappear { store.platzBlattOffen = false }
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
    /// Breit (iPad, aufgeklapptes Duo, Testphase-Schalter): Dokumente und
    /// Fragen werden zum Arbeitsplatz. Entschieden nach Größenklasse, nie
    /// nach Gerätemodell.
    @Environment(\.horizontalSizeClass) private var sizeClass
    private var breit: Bool { sizeClass == .regular }

    /// Welche Reiter es gibt, steht in `Ausbaustufe` — an einer Stelle für
    /// beide Bauarten. Der schmale Bau hat drei: Erfassen, Dokumente, Fragen;
    /// eine Ambassadorin bekommt „Empfehlen" dazu.
    private var reiter: [Reiter] {
        Ausbaustufe.reiter(fuer: store.rechte, ambassadorin: store.ambassadorin,
                           breit: breit)
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
        // Dasselbe beim Wechsel der Größenklasse (Fenster, Split View,
        // Testschalter): Arbeitsplatz ↔ Dokumente/Fragen statt zurück auf
        // „Erfassen" (`Ausbaustufe.reiterNachWechsel`, Harness zuschnitt).
        .onChange(of: reiter) { alt, neu in
            guard !neu.contains(where: { $0.tab == store.tab }) else { return }
            let aktuell = alt.first(where: { $0.tab == store.tab })
            let ziel = aktuell.flatMap { Ausbaustufe.reiterNachWechsel(aktuell: $0, neu: neu) }
                ?? neu.first
            if let ziel { store.tab = ziel.tab }
        }
        // „Zu den Dokumenten" und Co. sagen weiter `.belege` oder `.fragen`;
        // auf breit liegt beides im Arbeitsplatz.
        .onChange(of: store.tab) { _, neu in
            if breit, neu == .belege || neu == .fragen,
               reiter.contains(.arbeitsplatz) {
                store.tab = .arbeitsplatz
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
        case .arbeitsplatz: ArbeitsplatzView()
        }
    }
}
