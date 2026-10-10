import SwiftUI

/// Ein Anlass für ein Katsching: die Vorsteuer des gebuchten Belegs, dazu
/// der Zählerstand davor, damit der Zähler sichtbar hochtickt. `id` sorgt
/// dafür, dass zwei gleiche Beträge nacheinander zwei Momente sind.
struct KatschingAnlass: Identifiable, Equatable {
    let id = UUID()
    var betrag: Double
    var vorher: Double
    /// „zurückgeholt" — Kleinunternehmerin: „erfasst"
    var label: String
}

/// Eine Zahl, die zählt statt springt. `Animatable` interpoliert `wert`
/// zwischen altem und neuem Stand — SwiftUI ruft den Body je Bild auf.
struct AnimierteZahl: View, Animatable {
    var wert: Double
    var groesse: CGFloat = 44
    var farbe: Color = GC.fg

    var animatableData: Double {
        get { wert }
        set { wert = newValue }
    }

    var body: some View {
        Text(fmtEur(wert))
            .font(.system(size: groesse, weight: .semibold, design: .serif))
            .monospacedDigit()
            .foregroundStyle(farbe)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
    }
}

/// Der Moment nach einer Buchung, 1,8 s: Münzton + Haptik, „+13,56 €" groß
/// in Grün, darunter der Zähler, der von alt auf neu hochtickt. Mit
/// „Bewegung reduzieren": kein Aufspringen, der Zähler springt auf den
/// neuen Stand. Kein Konfetti — belohnt wird nur Geld, das da ist.
struct KatschingMoment: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let anlass: KatschingAnlass

    @State private var zaehler: Double
    @State private var aufgesprungen = false

    init(anlass: KatschingAnlass) {
        self.anlass = anlass
        _zaehler = State(initialValue: anlass.vorher)
    }

    var body: some View {
        VStack(spacing: 6) {
            Spacer()
            Text("+" + fmtEur(anlass.betrag))
                .font(.system(size: 64, weight: .semibold, design: .serif))
                .monospacedDigit()
                .foregroundStyle(GC.ok)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
                .scaleEffect(aufgesprungen || reduceMotion ? 1 : 0.6)
                .opacity(aufgesprungen || reduceMotion ? 1 : 0)
            Text(anlass.label.uppercased())
                .font(.system(size: 11, design: .monospaced))
                .kerning(1.2)
                .foregroundStyle(GC.desc)
                .padding(.bottom, 26)
            AnimierteZahl(wert: zaehler, groesse: 30, farbe: GC.fg)
            Text("bisher diesen Monat")
                .font(.footnote)
                .foregroundStyle(GC.desc)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 28)
        .background(GC.canvas.ignoresSafeArea())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(fmtEur(anlass.betrag)) \(anlass.label)")
        .accessibilityValue("Jetzt \(fmtEur(anlass.vorher + anlass.betrag)) diesen Monat")
        .task { await ablauf() }
    }

    private func ablauf() async {
        Katsching.spielen()
        if reduceMotion {
            zaehler = anlass.vorher + anlass.betrag
            return
        }
        withAnimation(.spring(response: 0.45, dampingFraction: 0.7)) { aufgesprungen = true }
        try? await Task.sleep(nanoseconds: 300_000_000)
        withAnimation(.easeOut(duration: 0.9)) { zaehler = anlass.vorher + anlass.betrag }
    }
}

/// Der Moment nach „Monat abschließen": der eine grüne Haken, ein
/// Wort, ein ehrlicher Satz — und die Fanfare.
struct UnterwegsMoment: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let satz: String
    @State private var erschienen = false

    var body: some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(GC.ok)
                .scaleEffect(erschienen || reduceMotion ? 1 : 0.4)
                .opacity(erschienen || reduceMotion ? 1 : 0)
            Text("Unterwegs")
                .font(.system(size: 34, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)
            Text(satz)
                .font(.title3)
                .fontDesign(.serif)
                .foregroundStyle(GC.body)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 28)
        .background(GC.canvas.ignoresSafeArea())
        .task {
            Katsching.fanfare()
            withAnimation(.spring(response: 0.45, dampingFraction: 0.7)) { erschienen = true }
        }
    }
}
