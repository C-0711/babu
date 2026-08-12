import SwiftUI
import AVFoundation

/// Live-Vorschau der Kamera als SwiftUI-Wrapper um `AVCaptureVideoPreviewLayer`
/// (aspectFill — die Overlay-Umrechnung in `CaptureOverlayView` rechnet den
/// dadurch entstehenden Beschnitt heraus).
struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    final class PreviewUIView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }

    func makeUIView(context: Context) -> PreviewUIView {
        let view = PreviewUIView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {}
}
