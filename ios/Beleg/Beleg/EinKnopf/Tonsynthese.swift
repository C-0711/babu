import Foundation

/// Der Ton entsteht auf dem Gerät. Keine Datei im Repo, kein Download —
/// ein paar Sinusschwingungen mit schnellem Abklingen, einmal gerechnet.
/// Reine Foundation-Mathematik, darum im Harness prüfbar.
enum Tonsynthese {
    static let abtastrate: Double = 44_100

    /// Münze: zwei kurze Töne, eine Quarte hoch (1975 → 2637 Hz), darunter
    /// zwei Glockenpartiale (2,5 und 4 kHz) und 30 ms Rauschen als „Ka".
    /// 0,35 s — am Ende ist die Hüllkurve unter 2 %, nichts wird abgeschnitten.
    static func muenze() -> [Float] {
        var s = [Float](repeating: 0, count: frames(0.35))
        muenze(in: &s, ab: 0, faktor: 1, halten: 1)
        normalisieren(&s, spitze: 0.8)
        return s
    }

    /// Fanfare: vier Münzen als aufsteigendes Arpeggio (Grundton, Terz,
    /// Quinte, Oktave), die letzte klingt länger aus. ~1,2 s.
    static func fanfare() -> [Float] {
        var s = [Float](repeating: 0, count: frames(1.2))
        let stufen: [(ab: Double, faktor: Double, halten: Double)] = [
            (0.00, 1.00, 1.0), (0.11, 1.25, 1.0), (0.22, 1.50, 1.0), (0.33, 2.00, 2.4)
        ]
        for st in stufen { muenze(in: &s, ab: st.ab, faktor: st.faktor, halten: st.halten) }
        ton(&s, f: 659.25, von: 0.33, bis: 1.15, amp: 0.18, tau: 0.35)   // E5 als Boden
        normalisieren(&s, spitze: 0.8)
        return s
    }

    // MARK: - Bausteine

    static func muenze(in s: inout [Float], ab: Double, faktor: Double, halten: Double) {
        rauschen(&s, von: ab, dauer: 0.03, amp: 0.20, tau: 0.010)
        ton(&s, f: 1975 * faktor, von: ab,        bis: ab + 0.08,          amp: 0.45, tau: 0.120)
        ton(&s, f: 2637 * faktor, von: ab + 0.08, bis: ab + 0.35 * halten, amp: 0.55, tau: 0.070 * halten)
        ton(&s, f: 2500 * faktor, von: ab + 0.08, bis: ab + 0.30,          amp: 0.10, tau: 0.090)
        ton(&s, f: 4000 * faktor, von: ab + 0.08, bis: ab + 0.25,          amp: 0.07, tau: 0.050)
    }

    /// Sinus mit 3 ms Einschwingrampe (kein Knacken) und e^(-t/τ)-Abklingen.
    static func ton(_ s: inout [Float], f: Double, von: Double, bis: Double,
                    amp: Double, tau: Double) {
        let i0 = max(0, Int(von * abtastrate))
        let i1 = min(Int(bis * abtastrate), s.count)
        guard i1 > i0 else { return }
        let rampe = Int(0.003 * abtastrate)
        let w = 2 * Double.pi * f / abtastrate
        for i in i0..<i1 {
            let n = i - i0
            let huelle = n < rampe
                ? Double(n) / Double(rampe)
                : exp(-(Double(n - rampe) / abtastrate) / tau)
            s[i] += Float(amp * huelle * sin(w * Double(n)))
        }
    }

    /// Weißes Rauschen, deterministisch (xorshift) — jedes Katsching klingt
    /// gleich. Auch hier eine kurze Rampe (1 ms), damit Sample 0 still ist.
    static func rauschen(_ s: inout [Float], von: Double, dauer: Double,
                         amp: Double, tau: Double) {
        var x: UInt32 = 0x9E37_79B9
        let i0 = max(0, Int(von * abtastrate))
        let i1 = min(Int((von + dauer) * abtastrate), s.count)
        guard i1 > i0 else { return }
        let rampe = Int(0.001 * abtastrate)
        for i in i0..<i1 {
            x ^= x << 13; x ^= x >> 17; x ^= x << 5
            let r = Double(x) / Double(UInt32.max) * 2 - 1
            let n = i - i0
            let t = Double(n) / abtastrate
            let einsatz = n < rampe ? Double(n) / Double(rampe) : 1
            s[i] += Float(amp * einsatz * exp(-t / tau) * r)
        }
    }

    /// Sekunden → Samples, gerundet statt abgeschnitten (0,35 s sind 15.435,
    /// nicht 15.434 — Fließkomma-Rest).
    static func frames(_ sekunden: Double) -> Int {
        Int((abtastrate * sekunden).rounded())
    }

    static func normalisieren(_ s: inout [Float], spitze: Float) {
        let maximum = s.reduce(0) { Swift.max($0, abs($1)) }
        guard maximum > 0 else { return }
        let k = spitze / maximum
        for i in s.indices { s[i] *= k }
    }
}
