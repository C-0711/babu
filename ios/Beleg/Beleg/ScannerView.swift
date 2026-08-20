import SwiftUI

/// Eigene Capture-Erfahrung statt des Stock-Scanners: AVFoundation-Sucher,
/// Vision-Dokument-Segmentierung, Auto-Auslösung mit Plausibilitäts-Gates
/// (kein Auto-Fire auf Bildschirme), Live-Felder im Sucher, Entzerrung —
/// alles im Unlimited-OCR-Design. API-kompatibel zum bisherigen Wrapper:
/// `CaptureTab` bleibt unverändert.
struct ScannerView: View {
    var onScan: (UIImage) -> Void
    var onCancel: () -> Void

    static var verfuegbar: Bool { CameraController.kameraVerfuegbar }

    @StateObject private var model = CaptureViewModel()

    var body: some View {
        ZStack {
            GC.scan.ignoresSafeArea()
            switch model.berechtigung {
            case .erteilt:
                CameraPreviewView(session: model.kamera.session)
                    .ignoresSafeArea()
                // Das Overlay bleibt INNERHALB der Safe Area: sonst liegt das
                // Abbrechen-X unter der Dynamic Island und lässt sich nicht tippen.
                CaptureOverlayView(model: model)
            case .verweigert:
                BerechtigungHinweis(onCancel: onCancel)
            case .unbestimmt:
                ProgressView().tint(.white)
            }
        }
        .task { await model.starte(onScan: onScan, onCancel: onCancel) }
        .onDisappear { model.stoppe() }
    }
}

/// Kamera-Zugriff verweigert: erklären und den Weg in die Einstellungen zeigen.
private struct BerechtigungHinweis: View {
    var onCancel: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "camera")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(GC.gold)
            Text("Kein Kamera-Zugriff")
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
                .foregroundStyle(.white)
            Text("Zum Erfassen von Belegen braucht die App die Kamera. Der Zugriff lässt sich in den Einstellungen erlauben.")
                .font(.footnote)
                .foregroundStyle(.white.opacity(0.65))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            VStack(spacing: 10) {
                Button {
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(url)
                    }
                } label: {
                    Text("Einstellungen öffnen").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                Button("Abbrechen") { onCancel() }
                    .foregroundStyle(.white.opacity(0.7))
            }
            .padding(.horizontal, 48)
        }
    }
}
