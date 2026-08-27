import SwiftUI
import AVFoundation
import UIKit

/// Klebstoff zwischen Kamera-Stack und SwiftUI: empfängt Beobachtungen und
/// OCR-Befunde, füttert die Gate-Zustandsmaschine und orchestriert die
/// Auslösung (Haptik → Foto → Entzerrung → Snap-Moment → onScan).
@MainActor
final class CaptureViewModel: ObservableObject {

    enum Berechtigung { case unbestimmt, erteilt, verweigert }

    @Published var berechtigung: Berechtigung = .unbestimmt
    @Published var phase: CapturePhase = .suchen
    @Published var anzeigeQuad: Quad?            // EMA-geglättet, nur fürs Overlay
    @Published var bufferGroesse: CGSize = .zero // Analyse-Frame (Portrait)
    @Published var liveFelder: LiveTextBefund?
    @Published var torchAn = false
    @Published var eingefroren: UIImage?         // entzerrtes Bild im Snap-Moment
    // Mehrseiten-Modus: mehrere Blätter werden EIN Beleg. Der Umschalter
    // steht im Sucher; ohne ihn läuft exakt der bisherige Ein-Seiten-Weg.
    @Published var mehrseiten = false
    @Published var seiten: [UIImage] = []

    let kamera = CameraController()

    private let detector = DocumentDetector()
    private let leser = LiveFieldsReader()
    private var gate = AutoCaptureGate()

    private var rohQuad: Quad?                   // ungeglättet, für die Entzerrung
    private var belichtungGesetzt = false
    private var nimmtAuf = false
    private var unterbrechungsTask: Task<Void, Never>?
    private var wiederaufnahmeTask: Task<Void, Never>?
    private var fehlerTask: Task<Void, Never>?
    private var ausloeseTask: Task<Void, Never>?

    private var onScan: ((UIImage) -> Void)?
    private var onFertig: (([UIImage]) -> Void)?
    private var onCancel: (() -> Void)?

    var statusText: String {
        if mehrseiten, case .suchen = phase {
            return "Seite \(seiten.count + 1) in den Rahmen halten"
        }
        switch phase {
        case .suchen: return "Beleg in den Rahmen halten"
        case .kandidat(let hinweis): return hinweis
        case .zuDunkel: return "Zu dunkel — Licht einschalten?"
        case .blendung: return "Blendung — Beleg leicht kippen"
        case .erkannt: return "Beleg erkannt — ruhig halten"
        case .ausgeloest: return ""
        }
    }

    // MARK: - Lebenszyklus

    func starte(onScan: @escaping (UIImage) -> Void, onCancel: @escaping () -> Void,
                onFertig: (([UIImage]) -> Void)? = nil) async {
        self.onScan = onScan
        self.onCancel = onCancel
        self.onFertig = onFertig

        guard CameraController.kameraVerfuegbar else {
            berechtigung = .verweigert
            return
        }
        let erlaubt = await CameraController.berechtigung()
        berechtigung = erlaubt ? .erteilt : .verweigert
        guard erlaubt else { return }

        detector.onBeobachtung = { [weak self] b in
            Task { @MainActor in self?.verarbeite(b) }
        }
        detector.onCrop = { [weak self] crop in
            self?.leser.verarbeite(crop)
        }
        leser.onBefund = { [weak self] befund in
            Task { @MainActor in self?.liveFelder = befund }
        }

        // Unterbrechung (Anruf, Backgrounding): Gate sauber zurücksetzen.
        unterbrechungsTask = Task { [weak self] in
            let mitte = NotificationCenter.default.notifications(
                named: AVCaptureSession.wasInterruptedNotification)
            for await _ in mitte {
                guard let self else { return }
                self.gate.sperren(fuer: CaptureTuning.nachAbbruchSperre)
                self.phase = .suchen
                self.anzeigeQuad = nil
                self.torchAn = false
            }
        }
        // Ende der Unterbrechung (Anruf vorbei): Sucher wieder anwerfen —
        // sonst bleibt ein schwarzes Standbild ohne Ausweg.
        wiederaufnahmeTask = Task { [weak self] in
            let ende = NotificationCenter.default.notifications(
                named: AVCaptureSession.interruptionEndedNotification)
            for await _ in ende {
                guard let self else { return }
                self.kamera.starte(delegate: self.detector)
                self.phase = .suchen
            }
        }
        // Laufzeitfehler der Session: einmal neu starten statt still stehen.
        fehlerTask = Task { [weak self] in
            let fehler = NotificationCenter.default.notifications(
                named: AVCaptureSession.runtimeErrorNotification)
            for await _ in fehler {
                guard let self else { return }
                self.kamera.stoppe()
                self.kamera.starte(delegate: self.detector)
                self.phase = .suchen
            }
        }

        kamera.starte(delegate: detector)
    }

    func stoppe() {
        unterbrechungsTask?.cancel()
        wiederaufnahmeTask?.cancel()
        fehlerTask?.cancel()
        ausloeseTask?.cancel()
        kamera.stoppe()
    }

    func abbrechen() {
        // Abbruch gilt auch mitten im Snap-Moment: der laufende Auslöse-Task
        // darf danach keinen Beleg mehr erzeugen.
        ausloeseTask?.cancel()
        onCancel?()
    }

    // MARK: - Frame-Verarbeitung

    private func verarbeite(_ b: BelegBeobachtung) {
        guard !nimmtAuf, eingefroren == nil else { return }

        bufferGroesse = CGSize(width: b.bufferBreite, height: b.bufferHoehe)
        rohQuad = b.quad
        if let neu = b.quad {
            anzeigeQuad = anzeigeQuad?.gemischt(mit: neu, anteil: 0.35) ?? neu
        } else if case .suchen = phase {
            anzeigeQuad = nil
        }

        let neuePhase = gate.verarbeite(b, liveText: liveFelder, torchAn: torchAn)

        if case .erkannt = neuePhase {
            if !belichtungGesetzt, let q = b.quad {
                belichtungGesetzt = true
                kamera.belichteAuf(punkt: q.zentrumObenLinks)
            }
        } else if neuePhase != .ausgeloest {
            belichtungGesetzt = false
        }

        phase = neuePhase
        if neuePhase == .ausgeloest {
            loeseAus()
        }
    }

    // MARK: - Auslösung

    func torchUmschalten() {
        torchAn.toggle()
        kamera.setzeTorch(an: torchAn)
    }

    /// Fallback-Auslöser: umgeht alle Gates; entzerrt wird mit dem besten
    /// aktuellen Quad, sonst per Neu-Detektion auf dem Foto bzw. Vollbild.
    func manuellAusloesen() {
        guard berechtigung == .erteilt, !nimmtAuf, eingefroren == nil else { return }
        phase = .ausgeloest
        loeseAus()
    }

    private func loeseAus() {
        guard !nimmtAuf else { return }
        nimmtAuf = true
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        let quad = rohQuad

        ausloeseTask = Task {
            do {
                let foto = try await kamera.fotoAufnehmen()
                let bild = await Task.detached(priority: .userInitiated) {
                    Dewarper.entzerre(foto, liveQuad: quad)
                }.value

                let reduziert = UIAccessibility.isReduceMotionEnabled
                if reduziert {
                    eingefroren = bild
                } else {
                    withAnimation(.spring(duration: 0.45)) { eingefroren = bild }
                }
                // Snap-Moment kurz stehen lassen, dann übernimmt die Pipeline.
                try? await Task.sleep(nanoseconds: reduziert ? 120_000_000 : 550_000_000)
                guard !Task.isCancelled else { return }
                if mehrseiten {
                    // Mehrseiten-Modus: Seite in den Stapel, zurück in den
                    // Sucher — die Aufnahme endet erst mit „Fertig".
                    seiten.append(bild)
                    weiterImSucher()
                } else {
                    onScan?(bild)
                }
            } catch {
                // Foto fehlgeschlagen (z. B. Unterbrechung): zurück in den Sucher.
                nimmtAuf = false
                gate.sperren(fuer: CaptureTuning.nachAbbruchSperre)
                phase = .suchen
            }
        }
    }

    // MARK: - Mehrseiten-Modus

    /// Umschalten geht nur, solange noch keine Seite im Stapel liegt —
    /// mittendrin die Bedeutung der schon gemachten Fotos zu ändern wäre
    /// eine Falle.
    func mehrseitenUmschalten() {
        guard seiten.isEmpty, eingefroren == nil, !nimmtAuf else { return }
        mehrseiten.toggle()
    }

    /// Nach einem Seiten-Snap wieder aufnahmebereit werden. Dasselbe Rezept
    /// wie der Fehlerpfad in `loeseAus` — die Gate-Sperre verhindert, dass
    /// das noch aufgelegte Blatt sofort erneut auslöst.
    private func weiterImSucher() {
        eingefroren = nil
        nimmtAuf = false
        gate.sperren(fuer: CaptureTuning.nachAbbruchSperre)
        phase = .suchen
    }

    /// „Fertig (n Seiten)": der Stapel wird EIN Beleg.
    func mehrseitenFertig() {
        guard mehrseiten, !seiten.isEmpty, eingefroren == nil, !nimmtAuf else { return }
        let stapel = seiten
        seiten = []
        mehrseiten = false
        onFertig?(stapel)
    }

    /// Abbrechen im Mehrseiten-Modus: gesammelte Seiten verwerfen.
    func mehrseitenVerwerfen() {
        seiten = []
        mehrseiten = false
    }
}
