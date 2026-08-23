import SwiftUI

/// Der Kassenbuch-Ablauf: die Zahlen des Papier-Kassenberichts werden
/// EINZELN abgefragt — eine Frage, eine Zahl, ein großer Weiter-Knopf.
/// Oben steht immer, wie viele Zahlen noch fehlen. Am Ende rechnet die
/// App selbst und sagt in einem Satz, ob die Kasse stimmt.
///
/// Was steuerlich woraus folgt, entscheidet das Modell (Kassenbuch.swift).
/// Hier wird nur gefragt — und zwar in Ninas Sprache.
struct KassenberichtWorkflow: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss

    let tag: String

    private struct Schritt {
        let frage: String
        let hilfe: String
        let optional: Bool           // „Nichts — weiter" als Abkürzung
        /// Wohin die Zahl gehört. Bei der Entnahme steht das erst fest,
        /// wenn Nina gesagt hat, wofür das Geld war — dann `nil`.
        let pfad: WritableKeyPath<Kassenbericht, Double>?

        var zweckwahl: Bool { pfad == nil }
    }

    private static let schritte: [Schritt] = [
        Schritt(frage: "Wie viel Geld war am Abend vorher in der Kasse?",
                hilfe: "Wenn wir es kennen, steht die Zahl schon drin — einfach Weiter.",
                optional: false, pfad: \.bestandVortag),
        Schritt(frage: "Wie viel Bargeld hast du heute eingenommen?",
                hilfe: "Alle Barzahlungen deiner Kundinnen zusammen — ohne Gutscheine, die kommen gleich.",
                optional: false, pfad: \.einnahmenBar),
        Schritt(frage: "Für wie viel hast du heute Gutscheine verkauft?",
                hilfe: "Nur verkaufte Gutscheine. Dieses Geld zählt jetzt — deshalb steht es hier für sich und nicht noch mal beim Bargeld.",
                optional: true, pfad: \.gutscheinVerkauf),
        Schritt(frage: "Hast du eigenes Geld in die Kasse gelegt?",
                hilfe: "Meistens nicht — dann einfach unten auf Nichts tippen.",
                optional: true, pfad: \.privateinlagen),
        Schritt(frage: "Hast du Bargeld von der Bank geholt und in die Kasse gelegt?",
                hilfe: "",
                optional: true, pfad: \.barabhebungBank),
        Schritt(frage: "Wie viel wurde heute mit Karte bezahlt?",
                hilfe: "Was deine Kundinnen für die Behandlungen bezahlt haben — Trinkgeld kommt gleich extra.",
                optional: false, pfad: \.ecZahlungen),
        Schritt(frage: "War Trinkgeld auf der Karte dabei?",
                hilfe: "Das Trinkgeld, das mit auf dem Kartenbeleg steht. Es landet auf deinem Konto, gehört dem Salon aber nicht — babu hält es getrennt.",
                optional: true, pfad: \.trinkgeldKarte),
        Schritt(frage: "Hat heute jemand mit einem Gutschein bezahlt?",
                hilfe: "Nur der Wert der eingelösten Gutscheine. Das ist keine neue Einnahme — das Geld kam schon damals rein, als du den Gutschein verkauft hast. Was die Kundin draufgezahlt hat, steht oben beim Bargeld oder bei der Karte.",
                optional: true, pfad: \.gutscheineEingeloest),
        Schritt(frage: "Hast du Trinkgeld bar ans Team ausgezahlt?",
                hilfe: "Das Geld, das du aus der Kasse ans Team weitergegeben hast. Gleich fragt babu noch kurz, wer was bekommen hat.",
                optional: true, pfad: \.trinkgeldTeamEC),
        Schritt(frage: "Hast du sonst etwas aus der Kasse bezahlt?",
                hilfe: "Zum Beispiel Blumen, Getränke, Kleinkram. Am Ende kannst du dazuschreiben, wofür es war.",
                optional: true, pfad: \.sonstigeAusgaben),
        Schritt(frage: "Hast du Geld aus der Kasse genommen?",
                hilfe: "Sag kurz, wofür — das ist für die Buchhaltung jedes Mal etwas anderes.",
                optional: true, pfad: nil),
        Schritt(frage: "Hast du Bargeld zur Bank gebracht?",
                hilfe: "",
                optional: true, pfad: \.einzahlungBank),
        Schritt(frage: "Jetzt zählen: Wie viel Geld ist in der Kasse?",
                hilfe: "Scheine und Münzen zusammenzählen — lass dir Zeit.",
                optional: false, pfad: \.gezaehltSchluss),
    ]

    /// Eine Zeile der Trinkgeld-Spur, solange sie noch getippt wird.
    private struct AnteilEingabe: Identifiable {
        let id = UUID()
        var name = ""
        var betrag = ""
    }

    @State private var bericht = Kassenbericht(datum: "")
    @State private var index = 0
    @State private var eingabe = ""
    @State private var zweck: Entnahmezweck = .privat
    @State private var fertig = false
    @State private var differenzGrund = ""
    @State private var sonstigeNotiz = ""
    // Ein festgeschriebener Tag wird nur mit Begründung geändert (GoBD).
    // Die Frage kommt erst, wenn sie nötig ist — nicht bei jedem Speichern.
    @State private var korrekturGrund = ""
    @State private var fragtNachGrund = false
    @State private var anteile: [AnteilEingabe] = []
    @FocusState private var feldAktiv: Bool

    private var schritt: Schritt { Self.schritte[index] }
    private var verbleibend: Int { Self.schritte.count - index }
    /// Wohin die aktuelle Zahl gehört — bei der Entnahme hängt das am Zweck.
    private var zielPfad: WritableKeyPath<Kassenbericht, Double> {
        schritt.pfad ?? zweck.pfad
    }
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
        // Ein Tag, dessen Blatt schon in der Belegbox liegt, wird nicht
        // stillschweigend überschrieben. Die Frage kommt nur dann.
        .alert("Diesen Tag korrigieren?", isPresented: $fragtNachGrund) {
            TextField("Warum? z. B. „Zwei Bons waren nicht eingetippt“",
                      text: $korrekturGrund)
            Button("Korrigieren") { sichern() }
                .disabled(korrekturGrund.trimmingCharacters(
                    in: .whitespacesAndNewlines).count < 3)
            Button("Abbrechen", role: .cancel) { korrekturGrund = "" }
        } message: {
            Text("Der Tag ist schon abgeschlossen. Die alte Fassung bleibt "
                 + "erhalten — schreib kurz dazu, was nicht stimmte.")
        }
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
            // Die Frage samt Zweckauswahl kann höher werden als der Platz
            // über der Tastatur — deshalb rollt sie, statt die Knöpfe
            // unten hinauszudrücken. Passt sie hin, sieht man davon nichts.
            ScrollView {
                VStack(spacing: 18) {
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

                    if schritt.zweckwahl { zweckAuswahl }

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
                }
                .padding(.top, 16)
            }
            .scrollBounceBehavior(.basedOnSize)

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

    /// Wofür das Geld die Kasse verlassen hat. Drei feste Möglichkeiten
    /// statt eines Freitextes — Nina tippt eine an, den Rest macht die App.
    /// Jeder Zweck hat sein eigenes Feld, deshalb darf am selben Tag auch
    /// mehr als einer vorkommen: Umschalten legt die Zahl beim vorigen ab.
    private var zweckAuswahl: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                ForEach(Entnahmezweck.allCases) { z in
                    Button {
                        zweckWechseln(zu: z)
                    } label: {
                        Text(z.knopf)
                            .font(.footnote.weight(z == zweck ? .semibold : .regular))
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(z == zweck ? GC.accentSubtle : GC.bg,
                                        in: RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12)
                                .stroke(z == zweck ? GC.accent : GC.linie,
                                        lineWidth: z == zweck ? 1.5 : 1))
                            .foregroundStyle(z == zweck ? GC.fg : GC.desc)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 24)
            Text(zweck.erklaerung)
                .font(.caption)
                .foregroundStyle(GC.muted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
        }
    }

    // MARK: - Ergebnis: die App rechnet, die Nutzerin liest einen Satz

    private var ergebnis: some View {
        ScrollView {
            VStack(spacing: 18) {
                Image(systemName: bericht.kasseStimmt ? "checkmark.circle.fill" : "equal.circle")
                    .font(.system(size: 84))
                    .foregroundStyle(bericht.kasseStimmt ? GC.ok : GC.warn)
                    .padding(.top, 16)
                Text(bericht.kasseStimmt ? "Deine Kasse stimmt"
                     : "Unterschied: \(fmtEur(bericht.differenz))")
                    .font(.system(size: 30, weight: .semibold, design: .serif))
                    .foregroundStyle(GC.fg)
                    .multilineTextAlignment(.center)
                if !bericht.kasseStimmt {
                    Text("Das kann passieren — es wird so notiert und am Monatsende geklärt.")
                        .font(.body)
                        .foregroundStyle(GC.desc)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                    TextField("Magst du kurz notieren, warum? (z. B. verzählt, Geld fehlt)",
                              text: $differenzGrund)
                        .font(.subheadline)
                        .padding(.horizontal, 13)
                        .padding(.vertical, 10)
                        .background(GC.bg, in: RoundedRectangle(cornerRadius: 12))
                        .padding(.horizontal, 24)
                }
                if bericht.sonstigeAusgaben > 0 {
                    TextField("Wofür war die sonstige Ausgabe? (z. B. Blumen)",
                              text: $sonstigeNotiz)
                        .font(.subheadline)
                        .padding(.horizontal, 13)
                        .padding(.vertical, 10)
                        .background(GC.bg, in: RoundedRectangle(cornerRadius: 12))
                        .padding(.horizontal, 24)
                }

                if bericht.trinkgeldTeamEC > 0 { trinkgeldSpur }

                zusammenfassung

                Button {
                    sichern()
                } label: {
                    Text("Fertig")
                        .font(.title3.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding(.horizontal, 24)
                .padding(.bottom, 24)
            }
        }
    }

    /// Wer hat das ausgezahlte Trinkgeld bekommen? Für die Empfängerin ist
    /// es steuerfrei — gefragt wird, damit bei einer Kassenprüfung
    /// erklärbar bleibt, warum Geld die Schublade verlassen hat.
    private var trinkgeldSpur: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Wer hat das Trinkgeld bekommen?")
                .font(.body.weight(.medium))
                .foregroundStyle(GC.fg)
            Text("Kurz eintragen — dann muss später niemand fragen, warum "
                 + "Geld aus der Kasse ist.")
                .font(.caption)
                .foregroundStyle(GC.desc)

            ForEach($anteile) { $a in
                HStack(spacing: 8) {
                    TextField("Name", text: $a.name)
                        .font(.subheadline)
                        .padding(.horizontal, 11).padding(.vertical, 9)
                        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 10))
                    TextField("0,00", text: $a.betrag)
                        .font(.subheadline.monospaced())
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .frame(width: 78)
                        .padding(.horizontal, 11).padding(.vertical, 9)
                        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 10))
                    Text("€").font(.subheadline).foregroundStyle(GC.muted)
                }
            }

            HStack {
                Button {
                    anteile.append(AnteilEingabe())
                } label: {
                    Label("Noch jemand", systemImage: "plus.circle")
                        .font(.footnote)
                }
                .buttonStyle(.plain)
                .foregroundStyle(GC.accent)
                Spacer()
                Text(restText)
                    .font(.caption)
                    .foregroundStyle(offenerRest > 0.005 ? GC.warn : GC.ok)
            }
        }
        .padding(16)
        .background(GC.bg, in: RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal, 24)
    }

    private var zusammenfassung: some View {
        VStack(spacing: 10) {
            ergebnisZeile("Bargeld eingenommen", fmtEur(bericht.einnahmenBar))
            ergebnisZeile("Mit Karte bezahlt", fmtEur(bericht.ecZahlungen))
            if bericht.gutscheinVerkauf > 0 {
                ergebnisZeile("Gutscheine verkauft", fmtEur(bericht.gutscheinVerkauf))
            }
            if bericht.gutscheineEingeloest > 0 {
                ergebnisZeile("Mit Gutschein bezahlt", fmtEur(bericht.gutscheineEingeloest))
                Text("Eingelöste Gutscheine zählen hier nicht mit — das Geld "
                     + "kam schon beim Verkauf rein.")
                    .font(.caption)
                    .foregroundStyle(GC.muted)
            }
            ergebnisZeile("Tagesumsatz gesamt", fmtEur(bericht.tagesumsatz))

            if bericht.trinkgeldKarte > 0 {
                Divider()
                ergebnisZeile("Trinkgeld auf der Karte", fmtEur(bericht.trinkgeldKarte))
                ergebnisZeile("Auf dem Kartenleser steht",
                              fmtEur(bericht.kartenterminalSumme))
                if bericht.trinkgeldTeam > 0 {
                    ergebnisZeile("davon ans Team", fmtEur(bericht.trinkgeldTeam))
                }
                if bericht.trinkgeldInhaberin > 0 {
                    ergebnisZeile("davon für dich", fmtEur(bericht.trinkgeldInhaberin))
                    Text("Was ans Team geht, läuft nur durch. Was bei dir "
                         + "bleibt, zählt babu als Einnahme — du musst nichts "
                         + "weiter tun.")
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                }
            }

            if bericht.summeEntnahmen > 0 {
                Divider()
                ForEach(Entnahmezweck.allCases) { z in
                    let betrag = bericht[keyPath: z.pfad]
                    if betrag > 0 {
                        ergebnisZeile(z.knopf, fmtEur(betrag))
                    }
                }
            }

            Divider()
            ergebnisZeile("So viel müsste drin sein", fmtEur(bericht.rechnerischerBestand))
            ergebnisZeile("Gezählt hast du", fmtEur(bericht.gezaehltSchluss))
        }
        .padding(16)
        .background(GC.bg, in: RoundedRectangle(cornerRadius: 14))
        .padding(.horizontal, 24)
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

    // MARK: - Trinkgeld-Spur rechnen

    private var verteilteAnteile: [Trinkgeldanteil] {
        anteile.compactMap { a in
            let name = a.name.trimmingCharacters(in: .whitespaces)
            let betrag = FeldParser.parseBetrag(a.betrag)
                ?? Double(a.betrag.replacingOccurrences(of: ",", with: "."))
            guard !name.isEmpty, let betrag, betrag > 0 else { return nil }
            return Trinkgeldanteil(name: name, betrag: betrag)
        }
    }

    private var offenerRest: Double {
        bericht.trinkgeldTeamEC - verteilteAnteile.reduce(0) { $0 + $1.betrag }
    }

    private var restText: String {
        if abs(offenerRest) < 0.005 { return "passt" }
        if offenerRest > 0 { return "noch \(fmtEur(offenerRest)) offen" }
        return "\(fmtEur(-offenerRest)) zu viel"
    }

    // MARK: - Ablauf

    private func vorbereiten() {
        if let vorhanden = store.kassenbericht(fuer: tag) {
            bericht = vorhanden            // Ändern: alte Zahlen stehen schon drin
            differenzGrund = vorhanden.differenzGrund ?? ""
            sonstigeNotiz = vorhanden.sonstigeNotiz ?? ""
            anteile = vorhanden.trinkgeldVerteilt.map {
                AnteilEingabe(name: $0.name, betrag: fmtBetrag($0.betrag))
            }
            // Beim Nacharbeiten den Zweck vorwählen, der schon eine Zahl hat.
            zweck = Entnahmezweck.allCases.first { vorhanden[keyPath: $0.pfad] > 0 }
                 ?? .privat
        } else {
            bericht = Kassenbericht(datum: tag)
            if let vortag = store.kassenVortagsbestand(vor: tag) {
                bericht.bestandVortag = vortag
            }
        }
        eingabeLaden()
    }

    private func eingabeLaden() {
        let aktuell = bericht[keyPath: zielPfad]
        eingabe = aktuell == 0 ? "" : fmtBetrag(aktuell)
        feldAktiv = true
    }

    /// Umschalten legt die getippte Zahl beim bisherigen Zweck ab und holt
    /// die des neuen. So kann ein Tag Vorschuss UND Privatentnahme haben,
    /// ohne dass die Frage doppelt gestellt wird.
    private func zweckWechseln(zu neu: Entnahmezweck) {
        guard neu != zweck else { return }
        bericht[keyPath: zweck.pfad] = wert ?? 0
        zweck = neu
        eingabeLaden()
    }

    private func weiter() {
        guard let wert else { return }
        bericht[keyPath: zielPfad] = wert
        if index + 1 < Self.schritte.count {
            index += 1
            eingabeLaden()
        } else {
            bericht.erstellt = Date()
            if store.kassenberichtSpeichern(bericht) == .grundFehlt {
                fragtNachGrund = true
                return
            }
            // Wurde Trinkgeld ausgezahlt, steht gleich die Frage nach dem
            // Wer — mit einer leeren Zeile, damit sie nicht erst gesucht
            // werden muss.
            if bericht.trinkgeldTeamEC > 0 && anteile.isEmpty {
                anteile = [AnteilEingabe()]
            }
            feldAktiv = false
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            withAnimation(.spring(duration: 0.35)) { fertig = true }
        }
    }

    private func zurueck() {
        guard index > 0 else { return }
        if let wert { bericht[keyPath: zielPfad] = wert }
        index -= 1
        eingabeLaden()
    }

    /// Notizen und Trinkgeld-Spur mitnehmen und den Tag (erneut) sichern.
    ///
    /// Ist der Tag schon festgeschrieben, kommt vorher die Frage nach dem
    /// Grund — nur dann, nicht bei jedem Speichern.
    private func sichern() {
        let grund = differenzGrund.trimmingCharacters(in: .whitespaces)
        let notiz = sonstigeNotiz.trimmingCharacters(in: .whitespaces)
        bericht.differenzGrund = grund.isEmpty ? nil : grund
        bericht.sonstigeNotiz = notiz.isEmpty ? nil : notiz
        bericht.trinkgeldVerteilt = verteilteAnteile
        if store.kassenberichtSpeichern(bericht, grund: korrekturGrund) == .grundFehlt {
            fragtNachGrund = true
            return
        }
        korrekturGrund = ""
        dismiss()
    }
}
