import SwiftUI
import UIKit
import PhotosUI
import PDFKit

/// Erfassen: Scan → On-Device-OCR → Prüfschritte → Confidence-Routing.
struct CaptureTab: View {
    @EnvironmentObject var store: AppStore
    @State private var zeigeScanner = false
    /// Nur beim ersten Öffnen von selbst aufmachen — wer die Kamera schließt,
    /// will sie nicht sofort wieder im Gesicht haben.
    @State private var kameraGezeigt = false
    @State private var phase: Phase = .bereit
    @State private var beleg: Beleg?
    @State private var schritte = 0
    @State private var startZeit = Date()
    @State private var ergebnisBild: UIImage?
    @State private var markierungen: [CGRect] = []
    // Abbruch-Marke: ein X während der Verarbeitung entwertet den laufenden
    // Durchlauf, damit er die Ansicht nicht später doch noch umschaltet.
    @State private var verarbeitungsLauf = UUID()
    // Beleg aus der Mediathek oder aus Dateien — nicht jede Rechnung
    // liegt als Papier auf dem Tresen.
    @State private var fotoAuswahl: PhotosPickerItem?
    @State private var zeigeDateien = false
    @State private var ladeFehler: String?

    // MARK: Einrichtung (BABU-51)
    /// Die Angaben aus dem babu-Konto. `nil` heißt „noch nicht nachgesehen" —
    /// das ist etwas anderes als „nicht ausgefüllt" und wird auch so gezeigt.
    @State private var kontoAngaben: [String: String]?
    @State private var angabenGeholt = false
    /// Welches Blatt die Karte gerade aufgeschlagen hat. Ein einziges
    /// `.sheet(item:)` statt zweier Schalter — zwei sheet-Modifier an
    /// derselben Ansicht (neben Scanner und Konto-Menü) liefern in SwiftUI
    /// zuverlässig ein leeres weißes Blatt.
    @State private var blatt: Einrichtungsblatt?
    /// Einmal fertig, für immer weg — auch wenn später jemand alle Belege
    /// löscht, ist das kein Grund, wieder von vorn anzuleiten.
    @AppStorage("einrichtungFertig") private var einrichtungFertig = false

    enum Phase { case bereit, verarbeitet, ergebnis, nichtsErkannt }

    enum Einrichtungsblatt: String, Identifiable {
        case konto, betrieb
        var id: String { rawValue }
    }

    private var einrichtungsschritte: [Einrichtungsschritt] {
        Einrichtung.schritte(
            kontoVerbunden: store.verbundenAls != nil && !store.zugangAbgelaufen,
            angaben: kontoAngaben,
            ersterBeleg: store.belege.contains { $0.istDemo != true },
            kassenbuchBegonnen: !store.kassenberichte.isEmpty)
    }

    /// Erst zeigen, wenn wir wirklich nachgesehen haben. Sonst blitzt die
    /// Karte bei jeder eingerichteten Nutzerin kurz auf und behauptet „—".
    private var zeigeEinrichtung: Bool {
        guard !einrichtungFertig, angabenGeholt else { return false }
        return !Einrichtung.alleErledigt(einrichtungsschritte)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                GC.canvas.ignoresSafeArea()
                switch phase {
                case .bereit: bereitView
                case .verarbeitet: verarbeitungView
                case .ergebnis: ergebnisView
                case .nichtsErkannt: nichtsErkanntView
                }
            }
            .warmerGrund()
            .navigationTitle("Erfassen")
            .mitMeldenKnopf("Erfassen")
            .toolbarTitleDisplayMode(.inline)
            .mitKontoMenu()
            // Kamera an, sobald der Reiter offen ist. Ein Platzhalter, den
            // man erst wegtippen muss, kostet bei jedem Beleg eine Sekunde —
            // und der Sinn dieses Reiters ist genau eine Sache.
            .onAppear { einrichtungNachsehen(); kameraVielleichtOeffnen() }
            // Solange etwas fehlt, ist die Einrichtungskarte das Erste, was
            // sie sieht — die Kamera würde sie zudecken.
            .task {
                await angabenHolen()
                kameraVielleichtOeffnen()
            }
            .sheet(item: $blatt) { welches in
                NavigationStack {
                    Group {
                        switch welches {
                        case .konto: EinstellungenView()
                        case .betrieb: BetriebsangabenView()
                        }
                    }
                    // Beide Ansichten werden sonst geschoben und haben von
                    // sich aus keinen Weg zurück. Ein Blatt ohne sichtbaren
                    // Ausgang ist eine Sackgasse.
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Fertig") { blatt = nil }
                        }
                    }
                }
                .environmentObject(store)
            }
            .onChange(of: blatt) { _, offen in
                // Nach dem Ausfüllen den Stand neu holen, sonst zählt die
                // Karte weiter „3 von 7".
                if offen == nil { Task { await angabenHolen() } }
            }
            .fullScreenCover(isPresented: $zeigeScanner) {
                ScannerView(
                    onScan: { bild in
                        zeigeScanner = false
                        Task { await verarbeite(bild) }
                    },
                    onCancel: { zeigeScanner = false }
                )
            }
            .fileImporter(isPresented: $zeigeDateien,
                          allowedContentTypes: [.pdf, .image]) { ergebnis in
                switch ergebnis {
                case .success(let url): ladeFehler = nil; ladeDatei(url)
                case .failure: ladeFehler = "Die Datei ließ sich nicht öffnen — bitte noch einmal versuchen."
                }
            }
            .onChange(of: store.geteilteDatei) { _, neu in
                guard let neu else { return }
                store.geteilteDatei = nil
                ladeFehler = nil
                ladeDatei(neu)
            }
            .onAppear {
                // Beim Start geteilt? Dann jetzt einlesen.
                if let offen = store.geteilteDatei {
                    store.geteilteDatei = nil
                    ladeDatei(offen)
                }
            }
            .onChange(of: fotoAuswahl) { _, neu in
                guard let neu else { return }
                ladeFehler = nil
                Task {
                    if let daten = try? await neu.loadTransferable(type: Data.self),
                       let bild = UIImage(data: daten) {
                        fotoAuswahl = nil
                        await verarbeite(bild)
                    } else {
                        fotoAuswahl = nil
                        ladeFehler = "Dieses Foto konnten wir nicht laden — bitte ein anderes wählen."
                    }
                }
            }
        }
    }

    /// Datei aus dem Dateien-Bereich: Bild direkt, PDF wird zur Seite 1
    /// gerendert (mehrseitige Bündel bitte einzeln — wie beim Scannen).
    private func ladeDatei(_ url: URL) {
        let zugriff = url.startAccessingSecurityScopedResource()
        defer { if zugriff { url.stopAccessingSecurityScopedResource() } }
        guard let daten = try? Data(contentsOf: url) else {
            ladeFehler = "Die Datei ließ sich nicht lesen — bitte noch einmal versuchen."
            return
        }
        if let bild = UIImage(data: daten) {
            Task { await verarbeite(bild) }
            return
        }
        guard let doc = PDFDocument(data: daten), let seite = doc.page(at: 0) else {
            ladeFehler = "Damit können wir nichts anfangen — bitte ein Foto oder ein PDF wählen."
            return
        }
        let feld = seite.bounds(for: .mediaBox)
        let skala = min(2200 / max(feld.width, feld.height), 3.0)
        let groesse = CGSize(width: feld.width * skala, height: feld.height * skala)
        let bild = UIGraphicsImageRenderer(size: groesse).image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: groesse))
            ctx.cgContext.translateBy(x: 0, y: groesse.height)
            ctx.cgContext.scaleBy(x: skala, y: -skala)
            seite.draw(with: .mediaBox, to: ctx.cgContext)
        }
        Task { await verarbeite(bild) }
    }

    // MARK: - Bereit

    private var bereitView: some View {
        VStack(spacing: 22) {
            if zeigeEinrichtung {
                ScrollView {
                    EinrichtungsKarte(
                        schritte: einrichtungsschritte,
                        kontoVerbunden: store.verbundenAls != nil
                                        && !store.zugangAbgelaufen,
                        wahl: weiterZu)
                        .padding(.horizontal, 20)
                        .padding(.top, 10)
                }
            } else {
                Spacer()
                // Kein schwarzer Kasten mehr: die Kamera geht beim Öffnen von
                // selbst auf. Was hier steht, sieht nur, wer sie geschlossen hat.
                Image(systemName: "viewfinder")
                    .font(.system(size: 44, weight: .light))
                    .foregroundStyle(GC.gold)
                Text("Halt drauf — egal ob Kassenbon, Vertrag oder Brief vom Amt.\nbabu legt es an die richtige Stelle.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 36)
                Spacer()
            }

            VStack(spacing: 10) {
                if ScannerView.verfuegbar {
                    Button {
                        zeigeScanner = true
                    } label: {
                        Label("Beleg scannen", systemImage: "doc.viewfinder")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
                Menu {
                    PhotosPicker(selection: $fotoAuswahl, matching: .images,
                                 photoLibrary: .shared()) {
                        Label("Aus deinen Fotos", systemImage: "photo.on.rectangle")
                    }
                    Button {
                        zeigeDateien = true
                    } label: {
                        Label("Aus Dateien (auch PDF)", systemImage: "folder")
                    }
                } label: {
                    Label("Beleg aus Datei oder Foto hochladen",
                          systemImage: "square.and.arrow.up")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)

                if let ladeFehler {
                    Text(ladeFehler)
                        .font(.footnote)
                        .foregroundStyle(GC.warn)
                        .multilineTextAlignment(.center)
                }
                #if targetEnvironment(simulator)
                // Nur im Simulator — auf dem Gerät hat der Beispiel-Beleg
                // im echten Bestand nichts verloren.
                Button {
                    Task { await verarbeite(DemoBeleg.bild()) }
                } label: {
                    Text("Demo-Beleg einlesen (Simulator)")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                #endif
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 12)
        }
    }

    // MARK: - Einrichtung (BABU-51)

    /// Den Stand der Angaben im babu-Konto holen. Auch ohne Verbindung gilt
    /// die Frage danach als gestellt — sonst wartet die Karte ewig.
    private func angabenHolen() async {
        defer { angabenGeholt = true; einrichtungNachsehen() }
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        if let geladen = await AblageService.stammdatenLaden(basis: url, pat: pat) {
            kontoAngaben = geladen
        }
    }

    /// Sobald einmal alles steht, ist die Karte für immer weg.
    private func einrichtungNachsehen() {
        if angabenGeholt, Einrichtung.alleErledigt(einrichtungsschritte) {
            einrichtungFertig = true
        }
    }

    /// Jede Zeile der Karte führt an die Stelle, an der es weitergeht.
    private func weiterZu(_ ziel: Einrichtungsziel) {
        switch ziel {
        case .konto: blatt = .konto
        case .betrieb, .steuernummer: blatt = .betrieb
        case .ersterBeleg: zeigeScanner = true
        case .kassenbuch: store.tab = .kasse
        }
    }

    /// Die Kamera geht von selbst auf — aber nicht über die Einrichtungskarte
    /// hinweg, und erst, wenn feststeht, ob es die Karte überhaupt braucht.
    private func kameraVielleichtOeffnen() {
        guard phase == .bereit, !zeigeScanner, ScannerView.verfuegbar,
              !kameraGezeigt, einrichtungFertig || angabenGeholt,
              !zeigeEinrichtung else { return }
        kameraGezeigt = true
        zeigeScanner = true
    }

    // MARK: - Verarbeitung

    private var verarbeitungView: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button {
                    verarbeitungsLauf = UUID()
                    phase = .bereit
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(GC.desc)
                        .frame(width: 44, height: 44)
                        .background(GC.chrome, in: Circle())
                }
                .accessibilityLabel("Schließen")
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.top, 8)
            // Kein Schritt-für-Schritt-Theater: das Lesen dauert Sekunden,
            // und eine Liste, die vier Haken setzt, macht es nicht schneller.
            VStack(spacing: 14) {
                ProgressView()
                Text("Einen Moment …")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 60)
            Spacer()
        }
    }


    // MARK: - Ergebnis

    @ViewBuilder
    private var ergebnisView: some View {
        // Der Beleg kann inzwischen gelöscht sein (Belegliste) — dann darf
        // hier keine leere Sackgasse stehen, sondern ein Weg zurück.
        if let b = beleg, store.belege.contains(where: { $0.id == b.id }) {
            ErgebnisUebersicht(belegID: b.id, bild: ergebnisBild,
                               markierungen: markierungen, startZeit: startZeit) {
                phase = .bereit
            }
        } else {
            VStack(spacing: 18) {
                Spacer()
                Image(systemName: "tray")
                    .font(.system(size: 44, weight: .light))
                    .foregroundStyle(GC.muted)
                Text("Der Beleg ist nicht mehr da")
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                Text("Wahrscheinlich wurde er gerade unter „Dokumente“ gelöscht — alles gut.")
                    .font(.footnote)
                    .foregroundStyle(GC.desc)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 36)
                Spacer()
                Button {
                    beleg = nil
                    phase = .bereit
                } label: {
                    Text("Weiter erfassen").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding(.horizontal, 24)
                .padding(.bottom, 12)
            }
        }
    }

    // MARK: - Nichts erkannt

    /// Kein Betrag und kein Name lesbar → nichts anlegen, ehrlich nachfragen.
    private var nichtsErkanntView: some View {
        VStack(spacing: 18) {
            Spacer()
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(GC.muted)
            Text("Da war nichts zu lesen")
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
            Text("Auf dem Foto war weder ein Betrag noch ein Name zu erkennen. Am besten noch einmal mit mehr Licht und ruhiger Hand.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 36)
            Spacer()
            VStack(spacing: 10) {
                if ScannerView.verfuegbar {
                    Button {
                        phase = .bereit
                        zeigeScanner = true
                    } label: {
                        Label("Noch mal versuchen", systemImage: "doc.viewfinder")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                }
                Button {
                    phase = .bereit
                } label: {
                    Text("Abbrechen").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 12)
        }
    }

    // MARK: - Pipeline

    private func verarbeite(_ bild: UIImage) async {
        let lauf = verarbeitungsLauf
        phase = .verarbeitet
        schritte = 0
        startZeit = Date()

        schritte = 1
        let ocr = await OCRService.erkenne(bild)

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 2
        // Kein Parser mehr: Vision liefert die Zeilen, Gemma liest sie.
        // Unlesbar ist ein Foto nur, wenn Vision praktisch nichts erkennt.
        if ocr.text.trimmingCharacters(in: .whitespacesAndNewlines).count < 12 {
            if lauf == verarbeitungsLauf { phase = .nichtsErkannt }
            return
        }

        ergebnisBild = bild
        markierungen = []

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 3
        let jpeg = bild.jpegData(compressionQuality: 0.6)
        let neu = store.routen(bildJpeg: jpeg, ocrText: ocr.text,
                               ocrGeoJson: ocr.geoJson)

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 4
        try? await Task.sleep(nanoseconds: 300_000_000)

        // Abgebrochen (X während der Verarbeitung)? Der Beleg ist trotzdem
        // aufgenommen und liegt in der Belegliste — nur nicht mehr aufdrängen.
        guard lauf == verarbeitungsLauf else { return }
        beleg = store.belege.first { $0.id == neu.id } ?? neu
        phase = .ergebnis
    }
}

/// Ergebnis-Karte mit Buchungssatz, Confidence und Routing-Aktion.
struct ErgebnisKarte: View {
    @EnvironmentObject var store: AppStore
    let beleg: Beleg
    let startZeit: Date
    var fertig: () -> Void

    @State private var zeigeReview = false
    @State private var zeigeBuchungsfragen = false
    @State private var zeigeBewirtung = false

    private var aktuell: Beleg { store.belege.first { $0.id == beleg.id } ?? beleg }

    /// Gleicher Betrag, gleicher Tag, gleicher Lieferant oder gleiche Nummer —
    /// vermutlich derselbe Beleg noch einmal fotografiert.
    private var moeglichesDuplikat: Beleg? {
        store.belege.first {
            $0.id != beleg.id &&
            abs($0.brutto - aktuell.brutto) < 0.005 &&
            $0.datumText == aktuell.datumText &&
            ($0.lieferant == aktuell.lieferant || $0.belegNr == aktuell.belegNr)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(aktuell.lieferant)
                    .font(.headline)
                    .fontDesign(.serif)
                Spacer()
                Text(fmtEur(aktuell.brutto))
                    .font(.subheadline.monospaced())
            }
            Text("\(aktuell.belegNr) · \(aktuell.datumText)")
                .font(.caption.monospaced())
                .foregroundStyle(GC.muted)

            BuchsatzView(beleg: aktuell)

            HStack(spacing: 10) {
                BadgeView(text: aktuell.herkunft.kurz,
                          color: herkunftsFarbe(aktuell.herkunft))
                ProgressView(value: Double(aktuell.confidence), total: 100)
                    .tint(confColor(aktuell.confidence))
                Text("\(aktuell.confidence) %")
                    .font(.caption.monospaced())
                    .foregroundStyle(GC.desc)
            }

            Text(aktuell.begruendung)
                .font(.footnote)
                .foregroundStyle(GC.desc)

            if !aktuell.summenprobeOK {
                Label("Summenprobe nicht bestanden — Beträge bitte prüfen.", systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
            }

            if aktuell.gutschriftSignal == true {
                Label("Sieht nach Gutschrift oder Erstattung aus — bitte vor dem Buchen prüfen.",
                      systemImage: "arrow.uturn.left.circle")
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
            }

            if moeglichesDuplikat != nil {
                Label("Sieht aus wie ein Beleg, den du schon hast — gleicher Betrag, gleicher Tag. Doppelt erfasst? Einen davon unter „Dokumente“ nach links wischen und löschen.",
                      systemImage: "doc.on.doc")
                    .font(.footnote)
                    .foregroundStyle(GC.warn)
            }

            switch aktuell.status {
            case .automatisch:
                SiegelZeile(beleg: aktuell)
                abschlussButtons
            case .offen:
                if aktuell.brauchtBewirtungsangaben {
                    Label("Bewirtungsangaben fehlen — beim Bestätigen wird nachgefragt.",
                          systemImage: "person.2")
                        .font(.footnote)
                        .foregroundStyle(GC.warn)
                }
                if store.ablageAktiv {
                    // Das Telefon hat gelesen und beurteilt — die Buchung
                    // holt sich Nina direkt: Profil + Lesung gehen als Text
                    // an die Buchhaltung, die fragt oder bucht.
                    Button {
                        zeigeBuchungsfragen = true
                    } label: {
                        Label("Einschätzen & buchen", systemImage: "questionmark.bubble")
                            .font(.title3.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    abschlussButtons
                } else {
                    if aktuell.confidence >= 80 {
                        Button {
                            if aktuell.brauchtBewirtungsangaben {
                                zeigeBewirtung = true
                            } else {
                                store.buchen(id: aktuell.id, konto: nil, steuerschluessel: nil,
                                             dauer: Date().timeIntervalSince(startZeit))
                            }
                        } label: {
                            Text("Buchung bestätigen").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                    } else {
                        Button {
                            zeigeReview = true
                        } label: {
                            Text("Kontierung prüfen").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    Button("Später — zu den Dokumenten") {
                        fertig()
                        store.tab = .belege
                    }
                    .font(.footnote)
                    .frame(maxWidth: .infinity)
                }
            default:
                SiegelZeile(beleg: aktuell)
                abschlussButtons
            }
        }
        .gcCard()
        .sheet(isPresented: $zeigeReview) {
            ReviewSheet(belegID: beleg.id, startZeit: startZeit)
        }
        .sheet(isPresented: $zeigeBuchungsfragen) {
            BuchungsfragenView(belegID: beleg.id)
                .environmentObject(store)
        }
        // Keine Erstauswertung mehr (24.08.2026): nach der Aufnahme gehen
        // die Daten direkt nach hinten, und hier erscheint sofort das
        // Ergebnis — die Buchung oder die Fragen. Wer das Blatt weglegt,
        // behält den Knopf auf der Karte als Wiedereinstieg.
        .onAppear {
            if store.ablageAktiv, aktuell.status == .offen {
                zeigeBuchungsfragen = true
            }
        }
        .sheet(isPresented: $zeigeBewirtung) {
            BewirtungsangabenSheet(belegID: beleg.id) {
                store.buchen(id: beleg.id, konto: nil, steuerschluessel: nil,
                             dauer: Date().timeIntervalSince(startZeit))
            }
        }
    }

    /// Nach dem Abschluss immer beide Wege anbieten: weiter erfassen
    /// oder zurück zur Übersicht.
    private var abschlussButtons: some View {
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
}

struct BuchsatzView: View {
    let beleg: Beleg

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if let konto = beleg.konto {
                Text("\(konto) \(Kontenplan.bezeichnung(konto))  \(fmtBetrag(beleg.netto)) S")
                if beleg.steuerschluessel != "0" {
                    Text("1406 \(beleg.ksLabel)  \(fmtBetrag(beleg.ust)) S")
                }
                Text("  an \(beleg.kreditor) Kred. \(beleg.lieferant)  \(fmtBetrag(beleg.brutto)) H")
            } else {
                Text("Noch nicht kontiert.")
            }
        }
        .font(.caption.monospaced())
        .foregroundStyle(GC.desc)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(11)
        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(GC.linie))
    }
}

struct SiegelZeile: View {
    let beleg: Beleg

    var body: some View {
        // Kein Hex-Fingerabdruck in der Oberfläche — Vertrauen ist der Haken.
        if beleg.siegel != nil, let zeit = beleg.siegelZeit {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.seal")
                    .foregroundStyle(GC.accent)
                Text("Festgehalten am \(DateFormatter.siegel.string(from: zeit)) — bleibt unverändert")
                    .font(.caption2)
                    .foregroundStyle(GC.accent)
            }
        }
    }
}
