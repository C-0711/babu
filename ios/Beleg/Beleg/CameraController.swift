import AVFoundation
import UIKit

enum CameraFehler: Error {
    case keinBild
}

/// Kapselt die AVCaptureSession: Konfiguration, Start/Stopp, Torch, Belichtung
/// und Foto-Aufnahme — alles auf einer eigenen seriellen Queue, nie auf Main.
final class CameraController: NSObject {

    static var kameraVerfuegbar: Bool {
        AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) != nil
    }

    /// Berechtigung anfragen bzw. lesen (fragt nur beim ersten Mal).
    static func berechtigung() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return true
        case .notDetermined: return await AVCaptureDevice.requestAccess(for: .video)
        default: return false
        }
    }

    let session = AVCaptureSession()

    private let sessionQueue = DispatchQueue(label: "io.0711.beleg.session")
    private let videoDataQueue = DispatchQueue(label: "io.0711.beleg.frames")
    private let fotoOutput = AVCapturePhotoOutput()
    private let videoOutput = AVCaptureVideoDataOutput()
    private var device: AVCaptureDevice?
    private var fotoDelegate: FotoDelegate?   // stark referenziert bis zum Callback

    /// Session konfigurieren (einmalig) und starten. `delegate` bekommt die
    /// Analyse-Frames auf der videoDataQueue.
    func starte(delegate: AVCaptureVideoDataOutputSampleBufferDelegate) {
        sessionQueue.async { [self] in
            if session.inputs.isEmpty {
                konfiguriere(delegate: delegate)
            }
            if !session.isRunning { session.startRunning() }
        }
    }

    func stoppe() {
        sessionQueue.async { [self] in
            setzeTorchIntern(an: false)
            if session.isRunning { session.stopRunning() }
        }
    }

    private func konfiguriere(delegate: AVCaptureVideoDataOutputSampleBufferDelegate) {
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.sessionPreset = .photo

        guard let dev = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: dev),
              session.canAddInput(input) else { return }
        session.addInput(input)
        device = dev

        videoOutput.alwaysDiscardsLateVideoFrames = true
        videoOutput.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
        ]
        videoOutput.setSampleBufferDelegate(delegate, queue: videoDataQueue)
        if session.canAddOutput(videoOutput) { session.addOutput(videoOutput) }
        if session.canAddOutput(fotoOutput) { session.addOutput(fotoOutput) }

        // Analyse-Frames aufrecht (Portrait) liefern — App ist Portrait-only.
        if let conn = videoOutput.connection(with: .video),
           conn.isVideoRotationAngleSupported(90) {
            conn.videoRotationAngle = 90
        }
    }

    // MARK: - Torch

    func setzeTorch(an: Bool) {
        sessionQueue.async { self.setzeTorchIntern(an: an) }
    }

    private func setzeTorchIntern(an: Bool) {
        guard let dev = device, dev.hasTorch,
              (try? dev.lockForConfiguration()) != nil else { return }
        if an {
            // Level 0.7: volle Leistung wirft auf Thermopapier zu harte Highlights.
            try? dev.setTorchModeOn(level: 0.7)
        } else if dev.torchMode != .off {
            dev.torchMode = .off
        }
        dev.unlockForConfiguration()
    }

    // MARK: - Belichtung

    /// Belichtung/Fokus einmalig aufs Beleg-Zentrum setzen (Punkt oben-links-normiert
    /// im Portrait-Frame). Wird bewusst nicht nachgeführt — sonst „pumpt" die
    /// Belichtung und verletzt das Stabilitäts-Gate.
    func belichteAuf(punkt: CGPoint) {
        sessionQueue.async { [self] in
            guard let dev = device,
                  (try? dev.lockForConfiguration()) != nil else { return }
            // Portrait → Sensorkoordinaten (Sensor liegt quer): x' = y, y' = 1 − x
            let geraetePunkt = CGPoint(x: punkt.y, y: 1 - punkt.x)
            if dev.isExposurePointOfInterestSupported {
                dev.exposurePointOfInterest = geraetePunkt
                dev.exposureMode = .continuousAutoExposure
            }
            if dev.isFocusPointOfInterestSupported {
                dev.focusPointOfInterest = geraetePunkt
                dev.focusMode = .continuousAutoFocus
            }
            dev.unlockForConfiguration()
        }
    }

    // MARK: - Foto

    /// Nimmt ein Foto auf und liefert es aufrecht (EXIF-Orientierung im UIImage).
    func fotoAufnehmen() async throws -> UIImage {
        try await withCheckedThrowingContinuation { continuation in
            sessionQueue.async { [self] in
                guard session.isRunning else {
                    continuation.resume(throwing: CameraFehler.keinBild)
                    return
                }
                if let conn = fotoOutput.connection(with: .video),
                   conn.isVideoRotationAngleSupported(90) {
                    conn.videoRotationAngle = 90
                }
                let einstellungen = AVCapturePhotoSettings()
                einstellungen.flashMode = .off   // Dauerlicht ggf. über Torch
                let delegate = FotoDelegate { [weak self] ergebnis in
                    self?.sessionQueue.async { self?.fotoDelegate = nil }
                    continuation.resume(with: ergebnis)
                }
                fotoDelegate = delegate
                fotoOutput.capturePhoto(with: einstellungen, delegate: delegate)
            }
        }
    }

    private final class FotoDelegate: NSObject, AVCapturePhotoCaptureDelegate {
        private let fertig: (Result<UIImage, Error>) -> Void
        init(fertig: @escaping (Result<UIImage, Error>) -> Void) { self.fertig = fertig }

        func photoOutput(_ output: AVCapturePhotoOutput,
                         didFinishProcessingPhoto photo: AVCapturePhoto,
                         error: Error?) {
            if let error { fertig(.failure(error)); return }
            guard let daten = photo.fileDataRepresentation(),
                  let bild = UIImage(data: daten) else {
                fertig(.failure(CameraFehler.keinBild))
                return
            }
            fertig(.success(bild))
        }
    }
}
