import SwiftUI

/// Der Kassenbuch-Ablauf: die Zahlen des Papier-Kassenberichts werden
/// EINZELN abgefragt — eine Frage, eine Zahl, ein großer Weiter-Knopf.
/// Oben steht immer, wie viele Zahlen noch fehlen. Am Ende rechnet die
/// App selbst und sagt in einem Satz, ob die Kasse stimmt.
struct KassenberichtWorkflow: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let tag: String

    private struct Schritt {
        let frage: String
        let hilfe: String
        let optional: Bool           // „Nichts — weiter" als Abkürzung
        let pfad: WritableKeyPath<Kassenbericht, Double>
    }

    private static let schritte: [Schritt] = [
        Schritt(frage: "Wie viel Geld war am Abend vorher in der Kasse?",
                hilfe: "Wenn wir es kennen, steht die Zahl schon drin — einfach Weiter.",
                optional: false, pfad: \.bestandVortag),
        Schritt(frage: "Wie viel Bargeld hast du heute eingenommen?",
                hilfe: "Alle Barzahlungen deiner Kundinnen zusammen.",
                optional: false, pfad: \.einnahmenBar),
        Schritt(frage: "Hast du eigenes Geld in die Kasse gelegt?",
                hilfe: "Meistens nicht — dann einfach unten auf Nichts tippen.",
                optional: true, pfad: \.privateinlagen),
        Schritt(frage: "Hast du Bargeld von der Bank geholt und in die Kasse gelegt?",
                hilfe: "",
                optional: true, pfad: \.barabhebungBank),
        Schritt(frage: "Wie viel wurde heute mit Karte bezahlt?",
                hilfe: "Steht auf dem Tagesabschluss deines Kartenlesers.",
                optional: false, pfad: \.ecZahlungen),
        Schritt(frage: "Hat heute jemand mit einem Gutschein bezahlt?",
                hilfe: "Nur der Wert der eingelösten Gutscheine. Das ist keine neue Einnahme — das Geld kam schon damals rein, als du den Gutschein verkauft hast.",
                optional: true, pfad: \.gutscheineEingeloest),
        Schritt(frage: "Trinkgeld fürs Team bar aus der Kasse gegeben, das mit Karte bezahlt war?",
                hilfe: "Nur das Team-Trinkgeld, das Kundinnen mit Karte gegeben haben und du bar auszahlst. Es wird sauber notiert — wie es steuerlich läuft, klärt deine Ansprechperson.",
                optional: true, pfad: \.trinkgeldTeamEC),
        Schritt(frage: "Hast du sonst etwas aus der Kasse bezahlt?",
                hilfe: "Zum Beispiel Blumen, Getränke, Kleinkram — oder ein Vorschuss fürs Team. Am Ende kannst du dazuschreiben, wofür es war.",
                optional: true, pfad: \.sonstigeAusgaben),
        Schritt(frage: "Hast du Geld für dich privat herausgenommen?",
                hilfe: "",
                optional: true, pfad: \.privatentnahmen),
        Schritt(frage: "Hast du Bargeld zur Bank gebracht?",
                hilfe: "",
                optional: true, pfad: \.einzahlungBank),
        Schritt(frage: "Jetzt zählen: Wie viel Geld ist in der Kasse?",
                hilfe: "Scheine und Münzen zusammenzählen — lass dir Zeit.",
                optional: false, pfad: \.gezaehltSchluss),
    ]

    @State private var bericht = Kassenbericht(datum: "")
    @State private var index = 0
    @State private var eingabe = ""
    @State private var fertig = false
    @State private var differenzGrund = ""
    @State private var sonstigeNotiz = ""
    @FocusState private var feldAktiv: Bool

    private var schritt: Schritt { Self.schritte[index] }
    private var verbleibend: Int { Self.schritte.count - index }
    private var wert: Double? {
        let t = eingabe.trimmingCharacters(in: .whitespaces)
        if t.isEmpty { return nil }
        return FeldParser.parseBetrag(t) ?? Double(t.replacingOccurrences(of: ",", with: "."))
    }

    var body: some View {
        VStack(spacing: 0) {
            kopf
            if fertig {
                ergebnis
            } else {
                frageAnsicht
            }
        }
        .background(GC.canvas.ignoresSafeArea())
        .onAppear(perform: vorbereiten)
    }

    // MARK: - Kopf mit Fortschritt

    private var kopf: some View {
        VStack(spacing: 10) {
            HStack {
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(GC.desc)
                        .frame(width: 44, height: 44)
                        .background(GC.chrome, in: Circle())
                }
                .accessibilityLabel("Schließen")
                Spacer()
                if !fertig {
                    Text(verbleibend == 1 ? "Letzte Zahl"
                         : "Noch \(verbleibend) Zahlen")
                        .font(.body.weight(.medium))
                        .foregroundStyle(GC.desc)
                }
            }
            if !fertig {
                ProgressView(value: Double(index), total: Double(Self.schritte.count))
                    .tint(GC.ok)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
    }

    // MARK: - Eine Frage, eine Zahl

    private var frageAnsicht: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 16)
            Text(schritt.frage)
                .font(.system(size: 28, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 28)
            if !schritt.hilfe.isEmpty {
                Text(schritt.hilfe)
                    .font(.body)
                    .foregroundStyle(GC.desc)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            HStack(alignment: .firstTextBaseline, spacing: 8) {
                TextField("0", text: $eingabe)
                    .keyboardType(.decimalPad)
                    .focused($feldAktiv)
                    .font(.system(size: 54, weight: .medium, design: .monospaced))
                    .multilineTextAlignment(.center)
                    .fixedSize()
                    .padding(.horizontal, 18)
                    .padding(.vertical, 8)
                    .background(GC.bg, in: RoundedRectangle(cornerRadius: 16))
                Text("€")
                    .font(.system(size: 44, weight: .medium))
                    .foregroundStyle(GC.muted)
            }
            .padding(.top, 6)

            if schritt.optional {
                Button {
                    eingabe = "0"
                    weiter()
                } label: {
                    Text("Nichts — weiter")
                        .font(.title3)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }

            Spacer()

            VStack(spacing: 10) {
                Button(action: weiter) {
                    Text("Weiter")
                        .font(.title3.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(wert == nil)

                if index > 0 {
                    Button {
                        zurueck()
                    } label: {
                        Text("Zurück").font(.body)
                    }
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 16)
        }
    }

    // MARK: - Ergebnis: die App rechnet, die Nutzerin liest einen Satz

    private var ergebnis: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 24)
            Image(systemName: bericht.kasseStimmt ? "checkmark.circle.fill" : "equal.circle")
                .font(.system(size: 84))
                .foregroundStyle(bericht.kasseStimmt ? GC.ok : GC.warn)
            Text(bericht.kasseStimmt ? "Deine Kasse stimmt"
                 : "Unterschied: \(fmtEur(bericht.differenz))")
                .font(.system(size: 30, weight: .semibold, design: .serif))
                .foregroundStyle(GC.fg)
                .multilineTextAlignment(.center)
            if !bericht.kasseStimmt {
                Text("Das kann passieren — es wird so notiert und am Monatsende geklärt.")
                    .font(.body)
                    .foregroundStyle(GC.desc)
                TextField("Magst du kurz notieren, warum? (z. B. verzählt, Geld fehlt)",
                          text: $differenzGrund)
                    .font(.subheadline)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(GC.bg, in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal, 24)
            }
            if bericht.sonstigeAusgaben > 0 {
                TextField("Wofür war die sonstige Ausgabe? (z. B. Blumen, Vorschuss)",
                          text: $sonstigeNotiz)
                    .font(.subheadline)
                    .padding(.horizontal, 13)
                    .padding(.vertical, 10)
                    .background(GC.bg, in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal, 24)
            }

            VStack(spacing: 10) {
                ergebnisZeile("Bargeld eingenommen", fmtEur(bericht.einnahmenBar))
                ergebnisZeile("Mit Karte bezahlt", fmtEur(bericht.ecZahlungen))
                if bericht.gutscheineEingeloest > 0 {
                    ergebnisZeile("Mit Gutschein bezahlt", fmtEur(bericht.gutscheineEingeloest))
                    Text("Gutscheine zählen hier nicht mit — das Geld kam schon beim Verkauf rein.")
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                }
                ergebnisZeile("Tagesumsatz gesamt", fmtEur(bericht.tagesumsatz))
                Divider()
                ergebnisZeile("So viel müsste drin sein", fmtEur(bericht.rechnerischerBestand))
                ergebnisZeile("Gezählt hast du", fmtEur(bericht.gezaehltSchluss))
            }
            .padding(16)
            .background(GC.bg, in: RoundedRectangle(cornerRadius: 14))
            .padding(.horizontal, 24)

            Spacer()

            Button {
                // Notizen mitnehmen und den Tag (erneut) sichern + übermitteln.
                let grund = differenzGrund.trimmingCharacters(in: .whitespaces)
                let notiz = sonstigeNotiz.trimmingCharacters(in: .whitespaces)
                bericht.differenzGrund = grund.isEmpty ? nil : grund
                bericht.sonstigeNotiz = notiz.isEmpty ? nil : notiz
                store.kassenberichtSpeichern(bericht)
                dismiss()
            } label: {
                Text("Fertig")
                    .font(.title3.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal, 24)
            .padding(.bottom, 16)
        }
    }

    private func ergebnisZeile(_ label: String, _ wert: String) -> some View {
        HStack {
            Text(label)
                .font(.body)
                .foregroundStyle(GC.desc)
            Spacer()
            Text(wert)
                .font(.body.monospaced().weight(.medium))
                .foregroundStyle(GC.fg)
        }
    }

    // MARK: - Ablauf

    private func vorbereiten() {
        if let vorhanden = store.kassenbericht(fuer: tag) {
            bericht = vorhanden            // Ändern: alte Zahlen stehen schon drin
            differenzGrund = vorhanden.differenzGrund ?? ""
            sonstigeNotiz = vorhanden.sonstigeNotiz ?? ""
        } else {
            bericht = Kassenbericht(datum: tag)
            if let vortag = store.kassenVortagsbestand(vor: tag) {
                bericht.bestandVortag = vortag
            }
        }
        eingabeLaden()
    }

    private func eingabeLaden() {
        let aktuell = bericht[keyPath: schritt.pfad]
        eingabe = aktuell == 0 ? "" : fmtBetrag(aktuell)
        feldAktiv = true
    }

    private func weiter() {
        guard let wert else { return }
        bericht[keyPath: schritt.pfad] = wert
        if index + 1 < Self.schritte.count {
            index += 1
            eingabeLaden()
        } else {
            bericht.erstellt = Date()
            store.kassenberichtSpeichern(bericht)
            feldAktiv = false
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            withAnimation(.spring(duration: 0.35)) { fertig = true }
        }
    }

    private func zurueck() {
        guard index > 0 else { return }
        if let wert { bericht[keyPath: schritt.pfad] = wert }
        index -= 1
        eingabeLaden()
    }
}
