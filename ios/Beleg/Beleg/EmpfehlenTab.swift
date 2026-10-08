import SwiftUI
import UIKit
import CoreImage.CIFilterBuiltins

/// Der Reiter „Empfehlen" — nur für Ambassadorinnen (`GET /api/ambassador/me`
/// sagt 200). Derselbe Kopf wie auf jedem Reiter: Titel, Rückmeldung, Menü.
/// Wo unten kein Platz für den Reiter ist (babu Pro), schiebt das Menü
/// dieselbe `EmpfehlenAnsicht` auf — dort mit dem Kopf der Menüansichten.
struct EmpfehlenTab: View {
    var body: some View {
        NavigationStack {
            EmpfehlenAnsicht()
                .mitMeldenKnopf("Empfehlen")
                .mitKontoMenu()
        }
    }
}

/// Eine Zahl, ein Knopf: oben ihr Geld, darunter „Salon einladen". Wer
/// eingeladen wird, sucht sie aus ihren Kontakten aus — sie tippt keine
/// Nummer ab, die das iPhone schon kennt. Geld- und Steuerangaben bleiben
/// vorerst im Portal.
struct EmpfehlenAnsicht: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.scenePhase) private var phase
    @Environment(\.openURL) private var oeffnen

    @State private var zeigeQR = false
    /// Nach dem Einladen: „Wie willst du Kim schreiben?"
    @State private var offen: OffeneEinladung?
    @State private var einladenLaeuft = false
    @State private var fehler: String?
    /// Eine Zeile Rückmeldung nach einer Aktion („Gesendet an Kim.").
    @State private var meldung: String?
    /// Der letzte Versuch kam ohne Antwort zurück — und es gibt nichts
    /// Gespeichertes zu zeigen. Dann ein Satz und „Nochmal", kein Dauerkreisel.
    @State private var ladeFehler = false
    @State private var laedt = false
    /// Ka-ching: ein Salon ist zahlende Kundin geworden, seit sie zuletzt
    /// hier war. Nur, solange die Ansicht wirklich zu sehen ist — ein Reiter
    /// im Hintergrund klingelt nicht.
    @State private var ereignis: KachingEreignis?
    @State private var sichtbar = false

    var body: some View {
        ScrollView {
            EmpfehlenInhalt(
                stand: store.empfehlen,
                ladeFehler: ladeFehler && !laedt,
                ereignis: ereignis,
                meldung: meldung,
                einladenLaeuft: einladenLaeuft,
                portal: URL(string: store.ablageURL + "/portal#empfehlen"),
                nochmal: { Task { await laden() } },
                einladen: einladen,
                qrZeigen: { zeigeQR = true },
                erinnern: erinnern)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
        }
        .warmerGrund()
        .navigationTitle("Empfehlen")
        .navigationBarTitleDisplayMode(.inline)
        // Bei jedem Öffnen frisch — ihr Geld und ihre Salons ändern sich,
        // während sie woanders ist.
        .onAppear { sichtbar = true }
        .onDisappear {
            sichtbar = false
            ereignis = nil
        }
        .task { await laden() }
        .refreshable { await laden() }
        // Zurück aus WhatsApp: dann soll der neue Stand dastehen.
        .onChange(of: phase) { _, neu in
            if neu == .active, sichtbar { Task { await laden() } }
        }
        .sheet(item: $offen, onDismiss: {
            Task { await laden() }
        }) { e in
            SchreibenBlatt(einladung: e) { satz in
                if let satz { meldung = satz }
                offen = nil
            }
            .presentationDetents([.medium, .large])
        }
        .fullScreenCover(isPresented: $zeigeQR) {
            QRBlatt(link: store.empfehlen?.link ?? "", name: store.empfehlen?.name)
        }
        .alert("Das ging gerade nicht", isPresented: Binding(
            get: { fehler != nil }, set: { if !$0 { fehler = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(fehler ?? "")
        }
    }

    /// Laden mit Zeitgrenze (die Anfrage gibt nach 15 s auf). Ohne Antwort
    /// bleibt stehen, was schon da ist; war nichts da, sagt es ein Satz.
    private func laden() async {
        laedt = true
        defer { laedt = false }
        switch await store.empfehlenLaden() {
        case .da(let neu)?:
            ladeFehler = false
            if sichtbar { feiern(neu) }
        case .keine?:
            // 404: Reiter und Menüzeile verschwinden von selbst.
            ladeFehler = false
        case .unbekannt?, nil:
            ladeFehler = store.empfehlen == nil
        }
    }

    /// Hat sich seit dem letzten Mal ein Salon in eine zahlende Kundin
    /// verwandelt? Dann Ka-ching — einmal, danach ist der Stand gemerkt.
    private func feiern(_ neu: EmpfehlenStand) {
        let schluessel = "empfehlen.gesehen." + (neu.code ?? "-")
        let gemerkt = UserDefaults.standard.data(forKey: schluessel)
            .flatMap { try? JSONDecoder().decode(Merkstand.self, from: $0) }
        if let e = neu.kaching(seit: gemerkt) {
            ereignis = e
            Kaching.klingeln()
        }
        if let daten = try? JSONEncoder().encode(neu.merkstand) {
            UserDefaults.standard.set(daten, forKey: schluessel)
        }
    }

    // MARK: - Einladen

    private func zugang() -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    private func einladen() {
        meldung = nil
        Kontaktwahl.shared.oeffnen { person in
            guard let person else { return }
            Task { await einladen(person) }
        }
    }

    private func einladen(_ p: Kontaktwahl.Person) async {
        #if DEBUG
        // Beispielmodus (Bildschirmfotos im Simulator): kein Netz, die
        // Antwort so, wie der Server sie mit Handynummer gäbe.
        if store.empfehlenBeispiel != nil {
            let link = "https://mybabu.io/ambassador/JASMIN-37EA/kate-1a2b"
            let text = EmpfehlenStand.einladungstext(vorname: p.vorname, link: link)
            try? await Task.sleep(nanoseconds: 600_000_000)
            offen = OffeneEinladung(
                vorname: p.vorname, telefon: p.handy,
                einladung: .init(link: link, text: p.handy == nil ? nil : text,
                                 whatsapp: p.handy == nil ? nil : "https://wa.me/4915550000?text=Hallo"),
                hinweis: p.handy == nil ? "Bei \(p.vorname) ist keine Handynummer gespeichert. "
                    + "Schick die Einladung einfach anders." : nil)
            return
        }
        #endif
        guard let (url, pat) = zugang() else {
            fehler = "Bitte zuerst anmelden — oben rechts im Menü."
            return
        }
        einladenLaeuft = true
        defer { einladenLaeuft = false }
        let start = Date()
        var telefon = p.handy
        var hinweis: String? = telefon == nil
            ? "\(p.vorname.isEmpty ? "Hier" : "Bei \(p.vorname)") ist keine Handynummer "
              + "gespeichert. Schick die Einladung einfach anders."
            : nil
        var antwort = await AblageService.salonEinladen(person: p.vorname, telefon: telefon,
                                                        basis: url, pat: pat)
        if antwort.nummerFalsch {
            // Die Nummer taugt nicht — die Einladung gibt es trotzdem, nur
            // ohne WhatsApp. Sie soll nicht noch einmal von vorn anfangen.
            hinweis = (antwort.fehler.map { $0 + " " } ?? "")
                + "Schick die Einladung einfach anders."
            telefon = nil
            antwort = await AblageService.salonEinladen(person: p.vorname, telefon: nil,
                                                        basis: url, pat: pat)
        }
        guard let einladung = antwort.einladung else {
            fehler = antwort.fehler
            return
        }
        // Die Kontaktliste schließt sich gerade noch — ein Blatt, das zu früh
        // kommt, zeigt iOS nicht.
        let vergangen = Date().timeIntervalSince(start)
        if vergangen < 0.6 {
            try? await Task.sleep(nanoseconds: UInt64((0.6 - vergangen) * 1_000_000_000))
        }
        offen = OffeneEinladung(vorname: p.vorname, telefon: telefon,
                                einladung: einladung, hinweis: hinweis)
        await laden()
    }

    /// Der Knopf an einem Salon: WhatsApp mit dem Text, den babu geschrieben
    /// hat, öffnen — und merken, dass sie nachgefragt hat.
    private func erinnern(_ a: EmpfehlenStand.Aufgabe, _ name: String) {
        guard let wa = a.whatsapp, let ziel = URL(string: wa) else { return }
        oeffnen(ziel)
        Task {
            if let (url, pat) = zugang() {
                await AblageService.ambassadorErinnert(nr: a.nr, art: a.art,
                                                       basis: url, pat: pat)
            }
            meldung = "Gesendet an \(name)."
            await laden()
        }
    }
}

/// Eine frisch angelegte Einladung, die noch verschickt werden will.
struct OffeneEinladung: Identifiable {
    let id = UUID()
    let vorname: String
    let telefon: String?
    let einladung: EmpfehlenStand.Einladung
    let hinweis: String?

    /// Der Text der Einladung — von babu geschrieben oder, ohne Nummer, hier.
    var text: String {
        einladung.text ?? EmpfehlenStand.einladungstext(vorname: vorname,
                                                        link: einladung.link)
    }
}

// MARK: - Der Inhalt

/// Was in der Ansicht steht — ohne Netz und ohne Store, damit es sich auch
/// mit Beispieldaten zeigen lässt (Vorschau unten). Gebaut aus dem, was die
/// App schon hat: Karten wie im Monatsabschluss (`gcCard`), Hinweise wie
/// „Deine Ablage wird noch eingerichtet", Knöpfe wie auf „Erfassen".
struct EmpfehlenInhalt: View {
    let stand: EmpfehlenStand?
    var ladeFehler = false
    var ereignis: KachingEreignis?
    var meldung: String?
    var einladenLaeuft = false
    var portal: URL?
    var nochmal: () -> Void = {}
    var einladen: () -> Void = {}
    var qrZeigen: () -> Void = {}
    var erinnern: (EmpfehlenStand.Aufgabe, String) -> Void = { _, _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            GeldKarte(stand: stand, ladeFehler: ladeFehler, ereignis: ereignis,
                      portal: portal, nochmal: nochmal)

            if stand?.aktiv == false {
                hinweisKarte("Gerade kannst du niemanden neu einladen. Deine Salons und "
                             + "dein Geld bleiben hier.")
            } else {
                knoepfe
            }

            if let meldung {
                Label(meldung, systemImage: "checkmark.circle")
                    .font(.footnote)
                    .foregroundStyle(GC.ok)
            }

            // Ohne Stand keine Überschrift ohne Inhalt darunter.
            if let stand {
                abschnitt("Deine Salons")
                if stand.salons.isEmpty {
                    hinweisKarte("Noch niemand eingeladen — tipp oben auf „Salon einladen“.")
                } else {
                    ForEach(stand.salons) { s in salonZeile(s) }
                }
            }
        }
    }

    // MARK: Teile

    /// Wie auf „Erfassen": ein Hauptknopf, darunter ein Nebenknopf.
    private var knoepfe: some View {
        VStack(spacing: 10) {
            Button(action: einladen) {
                HStack(spacing: 8) {
                    if einladenLaeuft {
                        ProgressView().tint(.white)
                    }
                    Label("Salon einladen", systemImage: "person.badge.plus")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(einladenLaeuft)

            // Erst, wenn es etwas zu zeigen gibt — kein grauer Knopf.
            if stand?.link != nil {
                Button(action: qrZeigen) {
                    Label("QR-Code zeigen", systemImage: "qrcode")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
        }
    }

    /// Wie die Zeilen unter „Meine Auslagen": Name, Stand, ein Satz.
    private func salonZeile(_ s: EmpfehlenStand.Salonzeile) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Circle()
                    .fill(farbe(s.ampel))
                    .frame(width: 10, height: 10)
                    .accessibilityHidden(true)
                Text(s.name)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(GC.fg)
                    .lineLimit(1)
                Spacer(minLength: 8)
                Text(s.wort)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(farbe(s.ampel))
                    .lineLimit(1)
            }
            if let aktiv = s.aktiv {
                Text(aktiv)
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let a = s.aufgabe, a.whatsapp != nil {
                Button(a.knopf) { erinnern(a, s.name) }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
    }

    private func abschnitt(_ titel: String) -> some View {
        Text(titel)
            .font(.headline)
            .fontDesign(.serif)
            .foregroundStyle(GC.fg)
            .padding(.top, 6)
    }

    /// Wie der Hinweis „Noch keine Auslage".
    private func hinweisKarte(_ text: String) -> some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(GC.desc)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(GC.accentSubtle, in: RoundedRectangle(cornerRadius: 14))
    }

    /// Grau = eingeladen, gelb = probiert aus, grün = zahlt.
    private func farbe(_ a: EmpfehlenStand.Ampel) -> Color {
        switch a {
        case .grau:  return GC.muted
        case .gelb:  return GC.warn
        case .gruen: return GC.ok
        }
    }
}

// MARK: - Dein Geld

/// Die Karte oben: „Dein Geld", die Zahl, der Topf bis zur Überweisung.
///
/// Wird ein Salon zahlende Kundin (`KachingEreignis`), zählt die Zahl vom
/// alten zum neuen Betrag hoch, der Topf füllt sich, ein paar Münzen fallen
/// hinein — einmal, keine Schleife. Wer „Bewegung reduzieren" eingestellt
/// hat, sieht nur den neuen Stand (Klang und Klopfen bleiben).
struct GeldKarte: View {
    let stand: EmpfehlenStand?
    var ladeFehler = false
    var ereignis: KachingEreignis?
    var portal: URL?
    var nochmal: () -> Void = {}

    @Environment(\.accessibilityReduceMotion) private var wenigBewegung
    @State private var zahl: Double?
    @State private var fuellung: Double?
    @State private var muenzen = false
    @State private var glanz = false
    @State private var gestartet: UUID?

    /// Vor dem ersten Bild schon den alten Betrag zeigen — sonst blitzt der
    /// neue kurz auf, bevor er hochzählt.
    private var wartet: Bool {
        guard let e = ereignis, e.geldGeaendert, !wenigBewegung else { return false }
        return gestartet != e.id
    }

    private var betrag: Double {
        if let zahl { return zahl }
        if wartet, let e = ereignis { return e.offenVorher }
        return stand?.geld.offen ?? 0
    }

    private var topf: Double {
        if let fuellung { return fuellung }
        return EmpfehlenStand.fuellung(betrag)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Dein Geld")
                .font(.headline)
                .fontDesign(.serif)
                .foregroundStyle(GC.fg)
            if let stand {
                // Zählt beim Ka-ching durch jeden Betrag dazwischen
                // (`.numericText` allein rollte nur einmal die Ziffern um).
                EmptyView().modifier(Zaehler(wert: betrag))
                Topf(fuellung: topf, muenzen: muenzen, glanz: glanz)
                    .padding(.vertical, 4)
                    .accessibilityLabel("Bis zur Überweisung: \(Int((topf * 100).rounded())) Prozent")
                if let e = ereignis, !e.satz.isEmpty {
                    Label(e.satz, systemImage: "sparkles")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(GC.ok)
                        .fixedSize(horizontal: false, vertical: true)
                        .transition(.opacity)
                }
                Text(stand.geldSatz)
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .fixedSize(horizontal: false, vertical: true)
                if stand.kontoFehlt, let portal {
                    Link(destination: portal) {
                        Label("Damit dein Geld kommt: einmal im Portal dein Konto angeben ›",
                              systemImage: "exclamationmark.circle")
                            .font(.footnote)
                            .foregroundStyle(GC.warn)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                }
            } else if ladeFehler {
                Text("Gerade keine Verbindung.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                Button("Nochmal", action: nochmal)
                    .buttonStyle(.bordered)
                    .padding(.top, 4)
            } else {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .gcCard()
        .accessibilityElement(children: .combine)
        .task(id: ereignis?.id) {
            guard let e = ereignis, gestartet != e.id else { return }
            await abspielen(e)
        }
    }

    /// Einmal hochzählen und auffüllen (~1,4 s), Münzen fallen dabei hinein;
    /// über der Grenze zum Schluss ein kurzer Glanz.
    private func abspielen(_ e: KachingEreignis) async {
        guard e.geldGeaendert, !wenigBewegung else {
            gestartet = e.id
            return
        }
        zahl = e.offenVorher
        fuellung = EmpfehlenStand.fuellung(e.offenVorher)
        gestartet = e.id
        try? await Task.sleep(nanoseconds: 60_000_000)
        withAnimation(.easeOut(duration: 1.4)) {
            zahl = e.offenJetzt
            fuellung = EmpfehlenStand.fuellung(e.offenJetzt)
        }
        muenzen = true
        try? await Task.sleep(nanoseconds: 1_300_000_000)
        if e.offenJetzt >= EmpfehlenStand.mindestsumme {
            withAnimation(.easeInOut(duration: 0.7)) { glanz = true }
        }
        try? await Task.sleep(nanoseconds: 300_000_000)
        muenzen = false
        try? await Task.sleep(nanoseconds: 600_000_000)
        glanz = false
        zahl = nil
        fuellung = nil
    }
}

/// Die große Zahl. Animierbar, damit sie beim Ka-ching durch alle Beträge
/// zwischen alt und neu läuft — in Euro-Schritten, ohne zu springen.
struct Zaehler: ViewModifier, Animatable {
    var wert: Double
    var animatableData: Double {
        get { wert }
        set { wert = newValue }
    }

    func body(content: Content) -> some View {
        Text(EmpfehlenStand.euro(wert.rounded()))
            .font(.system(size: 30, weight: .semibold, design: .serif))
            .monospacedDigit()
            .foregroundStyle(GC.fg)
    }
}

/// Der Topf bis zur Überweisung: ein schmaler Balken in Gold, voll ab der
/// Summe, ab der überwiesen wird.
struct Topf: View {
    let fuellung: Double
    var muenzen = false
    var glanz = false

    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(GC.linie)
                gefuellt(breite: g.size.width * fuellung)
            }
            .overlay(alignment: .bottomLeading) {
                if muenzen { muenzRegen(gesamt: g.size.width) }
            }
        }
        .frame(height: 10)
    }

    private func gefuellt(breite: CGFloat) -> some View {
        Capsule()
            .fill(GC.gold)
            .frame(width: fuellung > 0 ? max(breite, 10) : 0)
            .overlay { lichtstreif(breite: breite) }
            .clipShape(Capsule())
    }

    /// Ein Lichtstreif, einmal von links nach rechts — wenn der Topf voll ist.
    private func lichtstreif(breite: CGFloat) -> some View {
        LinearGradient(colors: [.clear, .white.opacity(0.75), .clear],
                       startPoint: .leading, endPoint: .trailing)
            .frame(width: 70)
            .offset(x: glanz ? breite : -breite - 70)
            .opacity(glanz ? 1 : 0)
    }

    private func muenzRegen(gesamt: CGFloat) -> some View {
        ZStack(alignment: .bottomLeading) {
            ForEach(0..<6, id: \.self) { i in
                Muenze(verzoegerung: Double(i) * 0.13)
                    .offset(x: muenzX(i, gesamt: gesamt))
            }
        }
    }

    /// Wohin Münze `i` fällt: kurz vor das Ende der Füllung, leicht verstreut.
    private func muenzX(_ i: Int, gesamt: CGFloat) -> CGFloat {
        let ziel: CGFloat = gesamt * fuellung - 34
        let streuung: CGFloat = CGFloat(i % 3) * 12 + CGFloat(i / 3) * 6
        return min(max(ziel + streuung, 0), max(gesamt - 10, 0))
    }
}

/// Eine Münze, die einmal von oben in den Topf fällt und verschwindet.
struct Muenze: View {
    let verzoegerung: Double
    @State private var gefallen = false
    @State private var weg = false

    var body: some View {
        Circle()
            .fill(GC.gold)
            .overlay(Circle().stroke(GC.accentHover.opacity(0.7), lineWidth: 1))
            .frame(width: 10, height: 10)
            .offset(y: gefallen ? 0 : -46)
            .opacity(weg ? 0 : 1)
            .accessibilityHidden(true)
            .onAppear {
                withAnimation(.easeIn(duration: 0.45).delay(verzoegerung)) { gefallen = true }
                withAnimation(.easeOut(duration: 0.25).delay(verzoegerung + 0.4)) { weg = true }
            }
    }
}

// MARK: - Wie willst du schreiben?

/// Nach dem Einladen: drei Wege, die Einladung zu verschicken. Ohne
/// Handynummer bleibt nur „Anders teilen" — mit dem Link.
struct SchreibenBlatt: View {
    let einladung: OffeneEinladung
    /// Schließt das Blatt; mit einem Satz für die Ansicht, wenn verschickt.
    var fertig: (String?) -> Void
    @Environment(\.openURL) private var oeffnen

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text(einladung.vorname.isEmpty ? "Wie willst du schreiben?"
                     : "Wie willst du \(einladung.vorname) schreiben?")
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                    .foregroundStyle(GC.fg)
                    .fixedSize(horizontal: false, vertical: true)
                if let hinweis = einladung.hinweis {
                    Label(hinweis, systemImage: "exclamationmark.circle")
                        .font(.footnote)
                        .foregroundStyle(GC.warn)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(spacing: 10) {
                    if let wa = einladung.einladung.whatsapp, let ziel = URL(string: wa) {
                        Button {
                            oeffnen(ziel)
                            fertig("Eingeladen. \(einladung.vorname.isEmpty ? "Der Salon" : einladung.vorname) steht jetzt in deiner Liste.")
                        } label: {
                            Label("WhatsApp", systemImage: "bubble.left.and.bubble.right")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                    }
                    if let telefon = einladung.telefon {
                        Button {
                            Nachricht.shared.schreiben(an: telefon, text: einladung.text)
                        } label: {
                            Label("Nachricht", systemImage: "message")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                    }
                    ShareLink(item: einladung.text) {
                        Label("Anders teilen", systemImage: "square.and.arrow.up")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                }
                .padding(.top, 6)

                Spacer(minLength: 0)
            }
            .padding(.horizontal, 24)
            .padding(.top, 8)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .warmerGrund()
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fertig") { fertig(nil) }
                }
            }
        }
    }
}

// MARK: - QR-Code

/// Vollbild mit dem QR-Code ihres allgemeinen Links — zum Hinhalten im Salon.
/// Der Bildschirm wird dafür ganz hell und danach wieder wie vorher.
struct QRBlatt: View {
    let link: String
    let name: String?
    @Environment(\.dismiss) private var schliessen
    @State private var helligkeitVorher: CGFloat?

    var body: some View {
        VStack(spacing: 22) {
            Spacer(minLength: 12)
            Text("30 Tage babu gratis — einfach scannen")
                .font(.system(size: 30, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            if let bild = QRBild.erzeugen(link) {
                Image(uiImage: bild)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: 320)
                    .accessibilityLabel("QR-Code zum Scannen")
            }
            if let name {
                Text(name)
                    .font(.headline)
                    .fontDesign(.serif)
                    .foregroundStyle(GC.body)
            }
            Spacer(minLength: 12)
            Button {
                schliessen()
            } label: {
                Text("Fertig").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // Ein QR-Code liest sich auf reinem Weiß am besten — nicht auf Papier-Ton.
        .background(GC.bg.ignoresSafeArea())
        .onAppear {
            guard let bildschirm = Obenauf.bildschirm else { return }
            helligkeitVorher = bildschirm.brightness
            bildschirm.brightness = 1
        }
        .onDisappear {
            if let vorher = helligkeitVorher { Obenauf.bildschirm?.brightness = vorher }
        }
    }
}

enum QRBild {
    /// Ein scharfer QR-Code: in ganzen Vielfachen hochgerechnet, ohne Glätten.
    static func erzeugen(_ text: String, kante: CGFloat = 1024) -> UIImage? {
        guard !text.isEmpty else { return nil }
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let roh = filter.outputImage, roh.extent.width > 0 else { return nil }
        let faktor = max(1, (kante / roh.extent.width).rounded(.down))
        let gross = roh.transformed(by: CGAffineTransform(scaleX: faktor, y: faktor))
        guard let cg = CIContext().createCGImage(gross, from: gross.extent) else { return nil }
        return UIImage(cgImage: cg)
    }
}

#if DEBUG
// MARK: - Beispieldaten (nur Entwicklungs-Builds)

extension EmpfehlenStand {
    /// Beispiele für Vorschau und Bildschirmfotos im Simulator — ohne Konto,
    /// ohne Netz. `leer`: 0 € und noch niemand eingeladen; `voll`: 237 €,
    /// zwei Salons (gelb mit Aufgabe, grün); `voll-konto`: dasselbe, aber das
    /// Konto für die Überweisung fehlt noch.
    static func beispiel(_ art: String) -> EmpfehlenStand? {
        let kopf = """
        "code":"JASMIN-37EA","name":"Jasmin","aktiv":true,
        "link":"https://mybabu.io/ambassador/JASMIN-37EA/salon",
        """
        let json: String
        switch art {
        case "leer":
            json = """
            {\(kopf)
             "verdient":0,"geld":{"offen":0,"unterwegs":0,"erwartet":null},
             "kontakte":[],"salons":[],"profil_vollstaendig":false}
            """
        case "voll", "voll-konto":
            json = """
            {\(kopf)
             "verdient":237,
             "geld":{"offen":237,"unterwegs":0,"verdient":237,
                     "erwartet":{"datum":"2027-01-15","betrag":237},
                     "bewegungen":[{"datum":"2026-10-08","art":"provision","betrag":237,
                                    "text":"Provision Haarwerk Ost, gezeichnet"}]},
             "kontakte":[
               {"nr":1,"name":"Kim","salon":"Kims Haarstudio","stand":"probiert aus",
                "aktiv":"Noch kein Beleg",
                "aufgabe":{"nr":1,"art":"kein_beleg","grund":"Seit 4 Tagen kein Beleg",
                           "knopf":"Beim Start helfen","whatsapp":"https://wa.me/491712345678?text=Hallo"}},
               {"nr":2,"name":"Sabine","salon":"Haarwerk Ost","stand":"macht mit",
                "aktiv":"12 Belege diese Woche"}],
             "salons":[{"salon":"Kims Haarstudio","meilenstein":"testet"},
                       {"salon":"Haarwerk Ost","meilenstein":"gezeichnet"}],
             "profil_vollstaendig":\(art == "voll" ? "true" : "false")}
            """
        default:
            return nil
        }
        return EmpfehlenStand(daten: Data(json.utf8))
    }
}

#Preview("Empfehlen") {
    ScrollView {
        EmpfehlenInhalt(stand: .beispiel("voll-konto"),
                        portal: URL(string: "https://mybabu.io/portal#empfehlen"))
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
    }
    .warmerGrund()
}

#Preview("Leer") {
    ScrollView {
        EmpfehlenInhalt(stand: .beispiel("leer"))
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
    }
    .warmerGrund()
}

#Preview("QR-Code") {
    QRBlatt(link: "https://mybabu.io/ambassador/JASMIN-37EA/salon", name: "Jasmin")
}
#endif
