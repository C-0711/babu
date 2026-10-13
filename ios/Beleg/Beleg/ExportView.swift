import SwiftUI
import MessageUI
import UniformTypeIdentifiers

struct ExportView: View {
    @EnvironmentObject var store: AppStore
    @State private var datei: URL?
    @State private var zeigeFixiertInfo = false
    @State private var zeigeAblage = false
    @State private var zeigeMail = false
    @State private var mailErgebnis: String?
    /// Was das Festschreiben gemeldet hat (409, kein Netz, abgelehnt).
    @State private var uebergabeMeldung: String?
    @State private var laeuft = false
    @State private var adresseBearbeiten = false
    @State private var adresseEntwurf = ""

    /// Die Adresse des Steuerbüros bleibt auf dem Gerät — sie ist eine
    /// Bequemlichkeit für den Versand, keine Einstellung des Betriebs.
    @AppStorage("steuerbueroAdresse") private var steuerbueroAdresse = ""

    /// Was in der Datei landet: entweder der Stapel, der gerade wartet, oder
    /// — nach dem Festschreiben — genau die Buchungen, die festgeschrieben
    /// wurden. Die Beschreibung darüber muss dieselbe Menge meinen.
    private var enthalten: [Beleg] {
        store.exportierbar.isEmpty && store.exportiert ? store.fixierte
                                                       : store.exportierbar
    }

    private var summe: Double { enthalten.reduce(0) { $0 + $1.brutto } }

    var body: some View {
        ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 12) {
                        // „Buchungsstapel" heißt die Datei im DATEV-Format;
                        // hier steht, was drinsteht, in Ninas Worten.
                        Text("Buchungen für " + monatsName())
                            .font(.headline)
                            .fontDesign(.serif)

                        inhaltsangabe

                        ScrollView(.horizontal) {
                            Text(store.exportierbar.isEmpty ? "— nichts Neues zu übergeben —"
                                                            : store.extfText())
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(GC.desc)
                                .padding(11)
                        }
                        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 9))

                        // Festgeschrieben wird auf dem SERVER (14.10.2026):
                        // dort überlebt das Siegel eine Neuinstallation, und ein
                        // zweites Telefon sieht es. Vorher stand es nur hier.
                        Button {
                            laeuft = true
                            uebergabeMeldung = nil
                            Task {
                                let (url, meldung) = await store.monatUebergeben()
                                if let url { datei = url }
                                uebergabeMeldung = meldung
                                laeuft = false
                            }
                        } label: {
                            HStack(spacing: 8) {
                                if laeuft { ProgressView().controlSize(.small) }
                                Text(laeuft ? "Wird festgeschrieben …"
                                     : store.exportierbar.isEmpty && store.exportiert
                                     ? "Festgeschrieben ✓"
                                     : "Buchungen festschreiben und Datei erzeugen")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .disabled(store.exportierbar.isEmpty || laeuft)

                        if let uebergabeMeldung {
                            Text(uebergabeMeldung)
                                .font(.caption)
                                .foregroundStyle(GC.warn)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        if store.exportiert {
                            Button {
                                zeigeFixiertInfo = true
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "checkmark.seal")
                                    Text("Festgeschriebene Buchungen bleiben unverändert.")
                                        .font(.caption2.monospaced())
                                        .multilineTextAlignment(.leading)
                                    Image(systemName: "info.circle")
                                        .font(.caption)
                                }
                                .foregroundStyle(GC.accent)
                            }
                            .accessibilityLabel("Was heißt festgeschrieben?")
                        }

                        // Erst festschreiben, dann weitergeben — in dieser
                        // Reihenfolge stehen die Knöpfe auch da.
                        if datei != nil { versandwege }
                    }
                    .gcCard()

                    Text("Das ist dein Monat als Datei — festgeschrieben und fertig. Wohin sie geht, entscheidest du: weitergeben per Mail oder Nachricht, oder auf dem iPhone sichern. Deine Belege selbst bleiben, wo sie sind.")
                        .font(.caption)
                        .foregroundStyle(GC.muted)
                        .padding(.horizontal, 4)
                }
                .padding(20)
            }
            .background(GC.canvas)
            .warmerGrund()
            .navigationTitle("Export")
            .toolbarTitleDisplayMode(.inline)
            .alert("Was heißt „festgeschrieben“?", isPresented: $zeigeFixiertInfo) {
                Button("Verstanden") {}
            } message: {
                Text("Festgeschrieben heißt: Diese Buchungen ändern sich nicht mehr — so verlangt es das Finanzamt für die Buchhaltung. Neue Belege kommen einfach in die nächste Datei.")
            }
            .alert("An wen soll es gehen?", isPresented: $adresseBearbeiten) {
                TextField("E-Mail deines Steuerbüros", text: $adresseEntwurf)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                Button("Merken") {
                    steuerbueroAdresse = adresseEntwurf
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                }
                Button("Abbrechen", role: .cancel) {}
            } message: {
                Text("babu merkt sich die Adresse auf diesem Telefon und trägt sie beim Senden von allein ein. Verschickt wird trotzdem nur, was du selbst abschickst.")
            }
            .fileExporter(isPresented: $zeigeAblage,
                          document: datei.flatMap(StapelDokument.init(datei:)),
                          contentType: .commaSeparatedText,
                          defaultFilename: extfZeitraum(fuer: enthalten).dateiname) { _ in }
            .sheet(isPresented: $zeigeMail) {
                if let datei {
                    MailBlatt(an: steuerbueroAdresse,
                              betreff: "Buchungen " + monatsName() + " — " + salonName(),
                              text: mailText(),
                              anhang: datei,
                              dateiname: extfZeitraum(fuer: enthalten).dateiname) { ergebnis in
                        mailErgebnis = ergebnis
                    }
                }
            }
        .onAppear {
            if !store.exportierbar.isEmpty {
                datei = store.extfDatei()
            } else if store.exportiert, !store.fixierte.isEmpty {
                // Nach App-Neustart bleibt die fertige Datei verschickbar.
                datei = store.extfDatei(fuer: store.fixierte)
            }
        }
    }

    // MARK: - Was ist drin (BABU-47)

    /// Vor dem Verschicken muss dastehen, WAS verschickt wird. „Teilen" ohne
    /// diese vier Zeilen beantwortet keine der Fragen, die man sich in dem
    /// Moment stellt — Zeitraum, Umfang, Belege dabei, Kassenbuch dabei.
    private var inhaltsangabe: some View {
        let monat = extfZeitraum(fuer: enthalten)
        return VStack(alignment: .leading, spacing: 5) {
            angabe("Zeitraum", tagText(monat.von) + " – " + tagText(monat.bis))
            angabe("Buchungen", enthalten.isEmpty
                   ? "keine" : "\(enthalten.count) · \(fmtEur(summe))")
            angabe("Belegfotos", "nein — nur die Buchungszeilen")
            // Das Kassenbuch gibt es nur im großen Bau — im schmalen wäre
            // die Zeile eine Auskunft über etwas, das es nicht gibt.
            if Ausbaustufe.erreichbar(.kasse) {
                angabe("Kassenbuch", "nein — die Tagesblätter gehen einzeln")
            }
            if ausserhalb > 0 {
                Text(ausserhalb == 1
                     ? "Ein Beleg trägt ein Datum außerhalb dieses Monats."
                     : "\(ausserhalb) Belege tragen ein Datum außerhalb dieses Monats.")
                    .font(.caption2)
                    .foregroundStyle(GC.warn)
                    .padding(.top, 2)
            }
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(GC.canvas, in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(GC.linie))
    }

    private func angabe(_ was: String, _ wert: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(was)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(GC.muted)
                .frame(width: 86, alignment: .leading)
            Text(wert)
                .font(.caption)
                .foregroundStyle(GC.body)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Der Kopf der Datei nennt einen Zeitraum, die Belege müssen ihm aber
    /// nicht folgen. Wer das verschweigt, beschreibt die Datei falsch.
    ///
    /// Seit dem 11.10.2026 folgt der Zeitraum den Belegen (`extfZeitraum`),
    /// also ist diese Zahl im Normalfall 0. Sie bleibt als Wache stehen:
    /// schlägt sie an, stimmt der Kopf nicht mehr mit dem Inhalt überein.
    private var ausserhalb: Int {
        let spanne = extfZeitraum(fuer: enthalten)
        return enthalten.filter { beleg in
            let teile = beleg.datumText.split(separator: ".")
            guard teile.count == 3, let tag = Int(teile[0]), let monat = Int(teile[1]),
                  let jahr = Int(teile[2])
            else { return false }   // unlesbares Datum ist ein anderes Thema
            let tagText = String(format: "%04d%02d%02d", jahr, monat, tag)
            return tagText < spanne.von || tagText > spanne.bis
        }.count
    }

    /// „20260801" → „01.08.2026"
    private func tagText(_ roh: String) -> String {
        guard roh.count == 8 else { return roh }
        let z = Array(roh)
        return "\(z[6])\(z[7]).\(z[4])\(z[5]).\(z[0])\(z[1])\(z[2])\(z[3])"
    }

    // MARK: - Wohin die Datei geht (BABU-47)

    /// Einmal geschrieben, in beiden Zweigen benutzt — sonst laufen die
    /// Beschriftungen auseinander.
    private var teilenLabel: some View {
        Label("Weitergeben — Mail, Nachricht, WhatsApp",
              systemImage: "square.and.arrow.up")
            .frame(maxWidth: .infinity)
            .lineLimit(1)
            .minimumScaleFactor(0.7)
    }

    @ViewBuilder
    private var versandwege: some View {
        VStack(spacing: 8) {
            if !steuerbueroAdresse.isEmpty {
                Button {
                    mailErgebnis = nil
                    zeigeMail = true
                } label: {
                    Label("An \(steuerbueroAdresse) senden", systemImage: "paperplane")
                        .frame(maxWidth: .infinity)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!MFMailComposeViewController.canSendMail())

                Button("Andere Adresse") {
                    adresseEntwurf = steuerbueroAdresse
                    adresseBearbeiten = true
                }
                .font(.caption)
                .foregroundStyle(GC.accent)

                if !MFMailComposeViewController.canSendMail() {
                    Text("Auf diesem Gerät ist kein Mail-Konto eingerichtet — "
                         + "gib sie stattdessen über Teilen weiter.")
                        .font(.caption2)
                        .foregroundStyle(GC.warn)
                }
            } else {
                // Bis 13.10.2026 stand hier der Dateispeicher vorn: das nackte
                // Teilen-Blatt galt als Sackgasse, weil es „wohin?" fragt, ohne
                // etwas vorzuschlagen. Der Auftraggeber hat das umgedreht —
                // weitergegeben wird auf dem Telefon, per Mail, Nachricht oder
                // WhatsApp. Also steht Teilen vorn; sichern bleibt daneben.
                Button {
                    zeigeAblage = true
                } label: {
                    Label("Auf dem iPhone sichern", systemImage: "folder")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)

                Button("Adresse deines Steuerbüros hinterlegen") {
                    adresseEntwurf = ""
                    adresseBearbeiten = true
                }
                .font(.caption)
                .foregroundStyle(GC.accent)
            }

            if !steuerbueroAdresse.isEmpty {
                Button {
                    zeigeAblage = true
                } label: {
                    Label("Auf dem iPhone sichern", systemImage: "folder")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }

            // Ohne hinterlegtes Steuerbüro ist Teilen der Hauptweg und steht
            // hervorgehoben da; mit Adresse ist der Mail-Knopf oben der Hauptweg.
            // Zwei Zweige statt eines Ternaers: die Button-Stile sind
            // verschiedene Typen, ein `?:` dazwischen uebersetzt nicht.
            if let url = datei {
                if steuerbueroAdresse.isEmpty {
                    ShareLink(item: url) { teilenLabel }
                        .buttonStyle(.borderedProminent)
                } else {
                    ShareLink(item: url) { teilenLabel }
                        .buttonStyle(.bordered)
                }
            }

            if let mailErgebnis {
                Text(mailErgebnis).font(.caption2).foregroundStyle(GC.desc)
            }

            Text("Die Datei liegt auf deinem Telefon. Sie geht nur dorthin, "
                 + "wo du sie hinlegst oder hinschickst — von allein passiert nichts.")
                .font(.caption2)
                .foregroundStyle(GC.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// „August 2026" — ohne das DATEV-Wort davor. Folgt den Belegen, nicht
    /// dem Kalender: sonst hieße die Überschrift anders als der Inhalt.
    private func monatsName() -> String {
        extfZeitraum(fuer: enthalten).titel
            .replacingOccurrences(of: "Buchungsstapel ", with: "")
    }

    private func salonName() -> String {
        store.verbundenAls ?? "babu"
    }

    private func mailText() -> String {
        """
        Hallo,

        anbei die Buchungen für \(monatsName()).

        \(enthalten.count) Buchungen, zusammen \(fmtEur(summe)).
        \(Ausbaustufe.erreichbar(.kasse) ? "Belegfotos und Kassenbuch sind" : "Belegfotos sind") nicht in der Datei — \
        sag Bescheid, dann schicke ich sie nach.

        Viele Grüße
        """
    }
}

/// Die fertige Datei für „Auf dem iPhone sichern". Sie liegt schon auf der
/// Platte; hier wird sie nur durchgereicht, damit iOS den Dateien-Dialog zeigt.
struct StapelDokument: FileDocument {
    static var readableContentTypes: [UTType] { [.commaSeparatedText, .plainText] }

    let daten: Data

    init?(datei: URL) {
        guard let daten = try? Data(contentsOf: datei) else { return nil }
        self.daten = daten
    }

    init(configuration: ReadConfiguration) throws {
        daten = configuration.file.regularFileContents ?? Data()
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: daten)
    }
}

/// Das Mail-Fenster von iOS, mit Empfänger und Anhang schon eingetragen.
/// SwiftUI hat dafür nichts — ShareLink kann keinen Empfänger vorbelegen.
struct MailBlatt: UIViewControllerRepresentable {
    let an: String
    let betreff: String
    let text: String
    let anhang: URL
    let dateiname: String
    var fertig: (String?) -> Void

    func makeUIViewController(context: Context) -> MFMailComposeViewController {
        let fenster = MFMailComposeViewController()
        fenster.mailComposeDelegate = context.coordinator
        fenster.setToRecipients([an])
        fenster.setSubject(betreff)
        fenster.setMessageBody(text, isHTML: false)
        if let daten = try? Data(contentsOf: anhang) {
            fenster.addAttachmentData(daten, mimeType: "text/csv", fileName: dateiname)
        }
        return fenster
    }

    func updateUIViewController(_ fenster: MFMailComposeViewController,
                                context: Context) {}

    func makeCoordinator() -> Bote { Bote(fertig: fertig) }

    final class Bote: NSObject, MFMailComposeViewControllerDelegate {
        let fertig: (String?) -> Void
        init(fertig: @escaping (String?) -> Void) { self.fertig = fertig }

        func mailComposeController(_ fenster: MFMailComposeViewController,
                                   didFinishWith ergebnis: MFMailComposeResult,
                                   error: Error?) {
            fenster.dismiss(animated: true)
            switch ergebnis {
            case .sent: fertig("Abgeschickt.")
            case .saved: fertig("Als Entwurf gesichert.")
            case .failed: fertig("Das Verschicken hat nicht geklappt.")
            default: fertig(nil)
            }
        }
    }
}
