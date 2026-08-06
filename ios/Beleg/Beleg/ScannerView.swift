import SwiftUI
import VisionKit

/// Echtes Dokument-Scannen mit VisionKit: Live-Kantenerkennung,
/// Auto-Auslösung, Entzerrung — die Capture-Sequenz des Produkts.
struct ScannerView: UIViewControllerRepresentable {
    var onScan: (UIImage) -> Void
    var onCancel: () -> Void

    /// Im Simulator meldet sich VisionKit als verfügbar, die Aufnahme scheitert
    /// dann aber mangels Kamera (FigCaptureSessionSimulator -12782) — deshalb
    /// dort hart abschalten und den Demo-Beleg-Pfad anbieten.
    static var verfuegbar: Bool {
        #if targetEnvironment(simulator)
        return false
        #else
        return VNDocumentCameraViewController.isSupported
        #endif
    }

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let vc = VNDocumentCameraViewController()
        vc.delegate = context.coordinator
        return vc
    }

    func updateUIViewController(_ uiViewController: VNDocumentCameraViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        let parent: ScannerView
        init(_ parent: ScannerView) { self.parent = parent }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController,
                                          didFinishWith scan: VNDocumentCameraScan) {
            guard scan.pageCount > 0 else { parent.onCancel(); return }
            parent.onScan(scan.imageOfPage(at: 0))
        }

        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
            parent.onCancel()
        }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController,
                                          didFailWithError error: Error) {
            parent.onCancel()
        }
    }
}
