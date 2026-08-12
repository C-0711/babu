import SwiftUI
import UIKit

/// Erfassen: Scan → On-Device-OCR → Prüfschritte → Confidence-Routing.
struct CaptureTab: View {
    @EnvironmentObject var store: AppStore
    @State private var zeigeScanner = false
    @State private var phase: Phase = .bereit
    @State private var beleg: Beleg?
    @State private var schritte = 0
    @State private var startZeit = Date()

    enum Phase { case bereit, verarbeitet, ergebnis }

    var body: some View {
        NavigationStack {
            ZStack {
                GC.canvas.ignoresSafeArea()
                switch phase {
                case .bereit: bereitView
                case .verarbeitet: verarbeitungView
                case .ergebnis: ergebnisView
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
        }
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
            Text("Live-Kantenerkennung, automatischer Zuschnitt und Entzerrung — danach liest die On-Device-OCR die Felder in unter einer Sekunde.")
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
                Button {
                    Task { await verarbeite(DemoBeleg.bild()) }
                } label: {
                    Text(ScannerView.verfuegbar ? "Demo-Beleg einlesen" : "Demo-Beleg einlesen (Simulator)")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 12)
        }
    }

    // MARK: - Verarbeitung

    private var verarbeitungView: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Verarbeitung")
                    .font(.title3.weight(.semibold))
                    .fontDesign(.serif)
                schrittZeile(1, "Extraktion — On-Device-OCR (Vision)")
                schrittZeile(2, "Felder geparst · Summenprobe")
                schrittZeile(3, "Kontierung — Historie → Regeln")
                schrittZeile(4, "Merkle-Siegel & Archiv")
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
        if let b = beleg {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ErgebnisKarte(beleg: b, startZeit: startZeit) {
                        phase = .bereit
                    }
                }
                .padding(20)
            }
        }
    }

    // MARK: - Pipeline

    private func verarbeite(_ bild: UIImage) async {
        phase = .verarbeitet
        schritte = 0
        startZeit = Date()

        schritte = 1
        let ocr = await OCRService.erkenne(bild)

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 2
        let felder = FeldParser.parse(zeilen: ocr.zeilen)

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 3
        let jpeg = bild.jpegData(compressionQuality: 0.6)
        let neu = store.routen(felder: felder, bildJpeg: jpeg, ocrText: ocr.text)

        try? await Task.sleep(nanoseconds: 350_000_000)
        schritte = 4
        try? await Task.sleep(nanoseconds: 300_000_000)

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
                BadgeView(text: aktuell.herkunft.rawValue,
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
        if let siegel = beleg.siegel, let zeit = beleg.siegelZeit {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.seal")
                    .foregroundStyle(GC.accent)
                Text("\(siegel) · \(DateFormatter.siegel.string(from: zeit)) · gesiegelt")
                    .font(.caption2.monospaced())
                    .foregroundStyle(GC.accent)
            }
        }
    }
}
