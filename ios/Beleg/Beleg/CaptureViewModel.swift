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
    private var onCancel: (() -> Void)?

    var statusText: String {
        switch phase {
        case .suchen: return "Beleg in den Rahmen halten"
        case .kandidat(let hinweis): return hinweis
        case .zuDunkel: return "Zu dunkel — Licht einschalten?"
        case .blendung: return "Blendung — Beleg leicht kippen"
        case .erkannt: return "Beleg erkannt — auslösen"
        case .ausgeloest: return ""
        }
    }

    // MARK: - Lebenszyklus

    func starte(onScan: @escaping (UIImage) -> Void, onCancel: @escaping () -> Void) async {
        self.onScan = onScan
        self.onCancel = onCancel

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

        // Zielbild (26.08.2026): ausgelöst wird per KLICK, nicht von der
        // Zustandsmaschine — „Beleg erkannt" bleibt als grüner Hinweis stehen.
        if case .ausgeloest = neuePhase {
            phase = .erkannt(fortschritt: 1.0)
        } else {
            phase = neuePhase
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

        _ = quad
        ausloeseTask = Task {
            do {
                // Zielbild: KEIN Zuschneiden, KEIN Entzerren — die Verzerrung
                // hat Belege kaputtgeschnitten, und Vision liest das rohe
                // Foto ohnehin. Klick → Foto → sofort weiter.
                let bild = try await kamera.fotoAufnehmen()
                eingefroren = bild
                try? await Task.sleep(nanoseconds: 120_000_000)
                guard !Task.isCancelled else { return }
                onScan?(bild)
            } catch {
                // Foto fehlgeschlagen (z. B. Unterbrechung): zurück in den Sucher.
                nimmtAuf = false
                gate.sperren(fuer: CaptureTuning.nachAbbruchSperre)
                phase = .suchen
            }
        }
    }
}
