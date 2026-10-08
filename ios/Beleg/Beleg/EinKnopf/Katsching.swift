import AVFoundation
import SwiftUI
import UIKit

/// Das Geräusch, wenn Geld zurückkommt.
///
/// Ein Ton, eine Bewegung, an echtes Geld gebunden, abschaltbar — so
/// verträgt es sich mit „kein Verspieltes" aus dem Design-Brief. Der Ton
/// wird auf dem Gerät gerechnet (`Tonsynthese`), es liegt keine Datei im
/// Repo. Der Stummschalter am iPhone gilt immer (`.ambient`), Musik aus
/// anderen Apps läuft weiter.
@MainActor
enum Katsching {
    /// Schalter im Konzept-Dialog. `UserDefaults` reicht — das muss keinen
    /// Gerätewechsel überleben.
    static let stummSchluessel = "katschingStumm"
    static var stumm: Bool {
        get { UserDefaults.standard.bool(forKey: stummSchluessel) }
        set { UserDefaults.standard.set(newValue, forKey: stummSchluessel) }
    }

    /// Münze — ein Beleg ist gebucht, die Vorsteuer kommt zurück.
    /// `haptik: false`, wenn der Aufrufer die Haptik schon selbst auslöst —
    /// sonst brummt es zweimal.
    static func spielen(haptik: Bool = true) {
        if haptik { UINotificationFeedbackGenerator().notificationOccurred(.success) }
        guard !stumm else { return }
        Tonmotor.geteilt.spielen(.muenze)
    }

    /// Fanfare — der Monat ist erledigt.
    static func fanfare(haptik: Bool = true) {
        if haptik { UINotificationFeedbackGenerator().notificationOccurred(.success) }
        guard !stumm else { return }
        Tonmotor.geteilt.spielen(.fanfare)
    }
}

/// Motor hinter dem Katsching: Puffer einmal gebaut, Engine faul gestartet,
/// nach drei Sekunden Ruhe wieder pausiert. Wird erst beim ersten Ton
/// erzeugt — wer das Konzept nie einschaltet, zahlt nichts.
@MainActor
private final class Tonmotor {
    static let geteilt = Tonmotor()
    enum Klang { case muenze, fanfare }

    private let engine = AVAudioEngine()
    private let spieler = AVAudioPlayerNode()
    private let format = AVAudioFormat(standardFormatWithSampleRate: Tonsynthese.abtastrate,
                                       channels: 1)
    private var puffer: [Klang: AVAudioPCMBuffer] = [:]
    private var verdrahtet = false
    private var letzteWiedergabe = Date.distantPast

    private init() {
        // Vorab bauen — beim ersten Katsching darf nichts rechnen.
        if let m = puffer(aus: Tonsynthese.muenze()) { puffer[.muenze] = m }
        if let f = puffer(aus: Tonsynthese.fanfare()) { puffer[.fanfare] = f }
    }

    func spielen(_ klang: Klang) {
        guard let buf = puffer[klang], sicherstellen() else { return }
        letzteWiedergabe = Date()
        // `.interrupts`: die zweite Münze schneidet die erste ab, statt sich
        // dahinter einzureihen — fünf schnelle Buchungen bleiben fünf Münzen,
        // nicht ein Nachhall von zwei Sekunden.
        spieler.scheduleBuffer(buf, at: nil, options: .interrupts,
                               completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor in self?.nachWiedergabe() }
        }
        if !spieler.isPlaying { spieler.play() }
    }

    /// Session und Motor hochfahren — idempotent, nie `try!`. Geht im
    /// Simulator ohne Ausgabegerät etwas schief, bleibt es still statt
    /// abzustürzen. Nach Anruf oder Kopfhörerwechsel ist der Motor aus und
    /// startet hier beim nächsten Ton wieder.
    private func sicherstellen() -> Bool {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
            try session.setActive(true)
            if !verdrahtet, let format {
                engine.attach(spieler)
                engine.connect(spieler, to: engine.mainMixerNode, format: format)
                verdrahtet = true
            }
            if !engine.isRunning {
                engine.prepare()
                try engine.start()
            }
            return true
        } catch {
            return false
        }
    }

    /// Drei Sekunden nach dem letzten Ton schlafen legen — ein laufender
    /// Motor kostet Strom, den kein Ton braucht.
    private func nachWiedergabe() {
        let stand = letzteWiedergabe
        Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard let self, self.letzteWiedergabe == stand else { return }
            self.spieler.stop()
            self.engine.pause()
        }
    }

    private func puffer(aus samples: [Float]) -> AVAudioPCMBuffer? {
        guard let format,
              let buf = AVAudioPCMBuffer(pcmFormat: format,
                                         frameCapacity: AVAudioFrameCount(samples.count)),
              let kanal = buf.floatChannelData?[0] else { return nil }
        buf.frameLength = buf.frameCapacity
        samples.withUnsafeBufferPointer { quelle in
            guard let basis = quelle.baseAddress else { return }
            kanal.update(from: basis, count: samples.count)
        }
        return buf
    }
}
