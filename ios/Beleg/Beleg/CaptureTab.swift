import SwiftUI
import UIKit
import PhotosUI
import PDFKit

/// Erfassen: Scan → On-Device-OCR → Prüfschritte → Confidence-Routing.
struct CaptureTab: View {
    @EnvironmentObject var store: AppStore
    @State private var zeigeScanner = false
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

    enum Phase { case bereit, verarbeitet, ergebnis, nichtsErkannt }

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
            .navigationTitle("Erfassen")
            .toolbarTitleDisplayMode(.inline)
            .fullScreenCover(isPresented: $zeigeScanner) {
                ScannerView(
                    onScan: { bild in
                        zeigeScanner = false
                        Task { await verarbeite(bild) }
                    },
                    onCancel: { zeigeScanner = false }
                )
                .ignoresSafeArea()
            }
            .fileImporter(isPresented: $zeigeDateien,
                          allowedContentTypes: [.pdf, .image]) { ergebnis in
                switch ergebnis {
                case .success(let url): ladeFehler = nil; ladeDatei(url)
                case .failure: ladeFehler = "Die Datei ließ sich nicht öffnen — bitte noch einmal versuchen."
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
            Spacer()
            ZStack {
                RoundedRectangle(cornerRadius: 24)
                    .fill(GC.scan)
                    .frame(width: 240, height: 300)
                VStack(spacing: 12) {
                    Image(systemName: "viewfinder")
                        .font(.system(size: 52, weight: .light))
                        .foregroundStyle(GC.gold)
                    Text("Beleg in den Rahmen halten —\nAuslösung erfolgt automatisch")
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.white.opacity(0.55))
                }
            }
            Text("Der Beleg wird automatisch erkannt, begradigt und gelesen.")
                .font(.footnote)
                .foregroundStyle(GC.desc)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 36)
            Spacer()

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
            VStack(alignment: .leading, spacing: 12) {
                Text("Verarbeitung")
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                schrittZeile(1, "Beleg lesen")
                schrittZeile(2, "Beträge und Summen prüfen")
                schrittZeile(3, "Kategorie zuordnen")
                schrittZeile(4, "Versiegeln und ablegen")
            }
            .gcCard()
            .padding(20)
            Spacer()
        }
    }

    private func schrittZeile(_ n: Int, _ text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: schritte >= n ? "checkmark.circle" : "circle.dotted")
                .foregroundStyle(schritte >= n ? GC.ok : GC.muted)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(schritte >= n ? GC.body : GC.muted)
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
                Text("Wahrscheinlich wurde er gerade in der Belegliste gelöscht — alles gut.")
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
        let felder = FeldParser.parse(zeilen: ocr.parserZeilen)

        // Komplett unlesbares Foto: keinen 0,00-€-Beleg anlegen.
        if felder.brutto == nil && felder.lieferant == nil {
            if lauf == verarbeitungsLauf { phase = .nichtsErkannt }
            return
        }

        // Für die Ergebnis-Ansicht: Foto + Positionen der erkannten Felder.
        ergebnisBild = bild
        markierungen = FeldMarker.markierungen(zeilen: ocr.zeilen, felder: felder)

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 3
        let jpeg = bild.jpegData(compressionQuality: 0.6)
        let neu = store.routen(felder: felder, bildJpeg: jpeg, ocrText: ocr.text)

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
                          color: aktuell.herkunft == .historie ? GC.accent : aktuell.herkunft == .regel ? GC.ok : GC.warn)
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
                Label("Sieht aus wie ein Beleg, den du schon hast — gleicher Betrag, gleicher Tag. Doppelt erfasst? Einen davon in der Belegliste nach links wischen und löschen.",
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
                Button("Später — zur Belegliste") {
                    fertig()
                    store.tab = .belege
                }
                .font(.footnote)
                .frame(maxWidth: .infinity)
            default:
                SiegelZeile(beleg: aktuell)
                abschlussButtons
            }
        }
        .gcCard()
        .sheet(isPresented: $zeigeReview) {
            ReviewSheet(belegID: beleg.id, startZeit: startZeit)
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
                Text("Zur Belegliste").frame(maxWidth: .infinity)
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
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(Color(hex: 0xEFEFEF)))
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
