import SwiftUI
import UIKit

/// Die Lage hinter der einen Seite: holt, was die Regie wissen darf, und
/// führt aus, was der Knopf verspricht. Verbunden kommt alles aus der
/// Belegbox; ohne Zugang (und im Simulator) läuft der Rundgang — ein
/// Skript mit Beispieldaten durch alle Seitentypen, damit sich das Konzept
/// ganz durchspielen lässt.
@MainActor
final class EinKnopfLage: ObservableObject {
    @Published private(set) var seite: Regie.Seite = .heim(abend: false)
    @Published private(set) var blatt = Regie.Blatt(zahl: "0,00 €", label: nil, satz: "",
                                                    knopf: "Reinwerfen", stimmung: .ruhig)
    @Published var moment: Moment?
    @Published private(set) var gruende: [Grund] = Rundgang.gruende
    /// Ersetzt den Satz für drei Sekunden — ein Hinweis, kein zweiter Knopf.
    @Published private(set) var hinweis: String?
    @Published private(set) var laedt = false
    private(set) var rundgang = false
    private(set) var lage = Regie.Lage(jetzt: Date())

    /// „Später" gilt für diese Sitzung. Beim nächsten Start ist die Seite
    /// wieder da — das ist das Ermahnen.
    private var zurueckgestellt: Set<String> = []
    private var schritt = 0
    private var zaehlerRundgang = 0.0
    private var heuteRundgang = 0
    private var heuteZurueckRundgang = 0.0

    enum Moment: Equatable, Identifiable {
        case katsching(KatschingAnlass)
        case unterwegs(id: UUID, satz: String)

        var id: UUID {
            switch self {
            case .katsching(let a): return a.id
            case .unterwegs(let id, _): return id
            }
        }
    }

    struct Grund: Identifiable, Equatable {
        let schluessel: String
        let name: String
        var id: String { schluessel }
    }

    // MARK: - Bewerten

    func starten(store: AppStore) async {
        #if targetEnvironment(simulator)
        rundgang = true
        #else
        rundgang = !(store.ablageAktiv && KeychainHelfer.ladePAT() != nil)
        #endif
        if !rundgang { await store.kontoNachfragen() }
        await neuBewerten(store: store)
    }

    func neuBewerten(store: AppStore) async {
        var l = rundgang
            ? Rundgang.lage(schritt: schritt, zaehler: zaehlerRundgang, heute: heuteRundgang,
                            heuteZurueck: heuteZurueckRundgang, jetzt: Date())
            : await liveLage(store: store)
        ausblenden(&l)
        lage = l
        let neu = Regie.entscheide(l)
        let b = Regie.blatt(neu, l)
        withAnimation(.easeInOut(duration: 0.35)) {
            seite = neu
            blatt = b
        }
    }

    /// Weggewischtes kommt in dieser Sitzung nicht wieder.
    private func ausblenden(_ l: inout Regie.Lage) {
        if zurueckgestellt.contains("frist") { l.frist = nil }
        if let f = l.frage, zurueckgestellt.contains("frage:\(f.kennung)") { l.frage = nil }
        if let f = l.fehlend, zurueckgestellt.contains("fehlt:\(f.schluessel)") { l.fehlend = nil }
        if let m = l.monat, zurueckgestellt.contains("monat:\(m.schluessel)") { l.monat = nil }
    }

    // MARK: - Aktionen (jede endet mit einer neuen Entscheidung)

    /// Wisch nach unten: nicht jetzt.
    func spaeter(store: AppStore) async {
        zurueckgestellt.insert(seite.kennung)
        if rundgang { schritt += 1 }
        await neuBewerten(store: store)
    }

    /// „Loslegen" auf der Frist-Seite: die Frist ist gesehen, jetzt kommen
    /// die offenen Punkte der Reihe nach.
    func loslegen(store: AppStore) async {
        zurueckgestellt.insert("frist")
        if rundgang { schritt += 1 }
        await neuBewerten(store: store)
    }

    /// Antwort aus dem Halbblatt (Rundgang): gebucht, Katsching.
    func antworten(_ option: String, store: AppStore) async {
        guard case .frage(let f) = seite else { return }
        zurueckgestellt.insert(seite.kennung)
        guard rundgang else { await neuBewerten(store: store); return }
        schritt += 1
        katsching(Rundgang.vorsteuer(fuer: f))
    }

    /// Nach dem Fragen-Cover (verbunden): hat die Buchhaltung gebucht?
    func nachFragen(id: UUID, store: AppStore) async {
        if let b = store.belege.first(where: { $0.id == id }), b.status != .offen {
            katsching(lage.kleinunternehmerin ? b.brutto : b.ust)
        } else {
            zurueckgestellt.insert("frage:\(id.uuidString)")
            await neuBewerten(store: store)
        }
    }

    /// Ein Foto ist da. Vision liest, der Beleg entsteht. Verbunden fragt
    /// die Buchhaltung (die View öffnet das Cover mit der ID); im Rundgang
    /// wird als Wareneinkauf 19 % gebucht und der Demo-Beleg bleibt Demo.
    func reingeworfen(_ bild: UIImage, store: AppStore) async -> UUID? {
        guard !laedt else { return nil }   // ein Foto nach dem anderen
        laedt = true
        defer { laedt = false }
        if case .belegFehlt(let f) = seite { zurueckgestellt.insert("fehlt:\(f.schluessel)") }
        let ocr = await OCRService.erkenne(bild)
        guard ocr.text.trimmingCharacters(in: .whitespacesAndNewlines).count >= 12 else {
            hinweisZeigen("Da war nichts zu lesen — bitte noch einmal fotografieren.")
            return nil
        }
        let jpeg = bild.jpegData(compressionQuality: 0.6)
        let neu = store.routen(bildJpeg: jpeg, ocrText: ocr.text, ocrGeoJson: ocr.geoJson)
        guard rundgang else { return neu.id }

        if let i = store.belege.firstIndex(where: { $0.id == neu.id }) {
            store.belege[i].istDemo = true
            store.belege[i].ablageStatus = nil   // Rundgang lädt nichts hoch
        }
        store.gemmaBuchungAnwenden(id: neu.id, konto: "5200", ustSatz: 19,
                                   betragEur: 119.00, waehrung: "EUR",
                                   begruendung: "Wareneinkauf, 19 %")
        schritt += 1
        let ust = store.belege.first { $0.id == neu.id }?.ust ?? 19.00
        katsching(ust)
        return nil
    }

    /// „Dazu gibt es keinen Beleg" — mit Grund.
    func klaeren(grund: String, store: AppStore) async {
        guard case .belegFehlt(let f) = seite else { return }
        zurueckgestellt.insert("fehlt:\(f.schluessel)")
        if rundgang {
            schritt += 1
        } else if let (url, pat) = zugang(store) {
            _ = await AblageService.belegFrageKlaeren(schluessel: f.schluessel, grund: grund,
                                                      basis: url, pat: pat)
        }
        await neuBewerten(store: store)
    }

    /// „Ans Finanzamt schicken": der Monat wird festgeschrieben und die
    /// Voranmeldung als Blatt abgelegt. Übermittelt wird damit nichts —
    /// der Moment sagt das ehrlich.
    func abschicken(store: AppStore) async {
        guard case .monatFertig(let m) = seite, !laedt else { return }
        laedt = true
        defer { laedt = false }
        if !rundgang, let (url, pat) = zugang(store) {
            if let fehler = await AblageService.monatFreigeben(monat: m.schluessel,
                                                               basis: url, pat: pat) {
                hinweisZeigen(fehler)
                return
            }
            if !lage.kleinunternehmerin,
               let fehler = await AblageService.ustvaErzeugen(monat: m.schluessel,
                                                              basis: url, pat: pat) {
                hinweisZeigen(fehler)
                return
            }
        }
        zurueckgestellt.insert("monat:\(m.schluessel)")
        if rundgang { schritt += 1 }
        let satz = lage.kleinunternehmerin
            ? "Dein \(m.name) ist festgeschrieben."
            : "Dein \(m.name) ist festgeschrieben. Die Voranmeldung liegt in deiner Ablage."
        moment = .unterwegs(id: UUID(), satz: satz)
    }

    /// Der Moment ist vorbei — die Regie entscheidet neu.
    func momentVorbei(store: AppStore) async {
        moment = nil
        await neuBewerten(store: store)
    }

    func vonVorn(store: AppStore) async {
        schritt = 0
        zaehlerRundgang = 0
        heuteRundgang = 0
        heuteZurueckRundgang = 0
        zurueckgestellt = []
        await neuBewerten(store: store)
    }

    private func katsching(_ betrag: Double) {
        let vorher = rundgang ? zaehlerRundgang : lage.zurueckgeholt
        if rundgang {
            zaehlerRundgang += betrag
            heuteRundgang += 1
            heuteZurueckRundgang += betrag
        }
        moment = .katsching(KatschingAnlass(
            betrag: betrag, vorher: vorher,
            label: lage.kleinunternehmerin ? "erfasst" : "zurückgeholt"))
    }

    private func hinweisZeigen(_ text: String) {
        hinweis = text
        Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            if self?.hinweis == text { self?.hinweis = nil }
        }
    }

    private func zugang(_ store: AppStore) -> (URL, String)? {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return nil }
        return (url, pat)
    }

    // MARK: - Verbunden: die Lage aus der Belegbox

    private func liveLage(store: AppStore) async -> Regie.Lage {
        var l = Regie.Lage(jetzt: Date())
        guard let (url, pat) = zugang(store) else { return l }

        if store.profil.isEmpty,
           let p = await AblageService.stammdatenLaden(basis: url, pat: pat) {
            store.profil = p
        }
        l.kleinunternehmerin = store.profil["kleinunternehmer"] == "Ja"

        let kal = Calendar.current
        let jahr = kal.component(.year, from: l.jetzt)
        let monatJetzt = aktuellerMonatSchluessel(l.jetzt)

        async let laufAufruf = AblageService.monatslauf(basis: url, pat: pat)
        async let fehltAufruf = AblageService.fehlendeBelege(basis: url, pat: pat)
        async let termineAufruf = AblageService.fristen(jahr: jahr, basis: url, pat: pat)
        async let abschlussAufruf = AblageService.monatsabschluss(monat: monatJetzt,
                                                                   basis: url, pat: pat)
        let (lauf, fehlt, termine, abschluss) = await (laufAufruf, fehltAufruf,
                                                       termineAufruf, abschlussAufruf)

        if let j = lauf, let schluessel = j["monat"] as? String {
            let zahlen = j["zahlen"] as? [String: Any]
            l.monat = Regie.Monat(schluessel: schluessel,
                                  name: Regie.monatsname(schluessel: schluessel),
                                  stand: j["stand"] as? String ?? "laeuft",
                                  zahllast: zahlen?["zahllast"] as? Double,
                                  ergebnis: zahlen?["ergebnis"] as? Double)
            for o in j["offen"] as? [[String: Any]] ?? [] {
                l.offeneAnzahl += o["anzahl"] as? Int ?? 0
            }
        }

        let serverGruende = fehlt.gruende.compactMap { g -> Grund? in
            guard let s = g["schluessel"] as? String, let n = g["name"] as? String else { return nil }
            return Grund(schluessel: s, name: n)
        }
        if !serverGruende.isEmpty { gruende = serverGruende }
        l.offeneAnzahl += fehlt.fragen.count
        if let f = fehlt.fragen.first(where: { eintrag in
            guard let k = eintrag["schluessel"] as? String else { return false }
            return !zurueckgestellt.contains("fehlt:\(k)")
        }), let k = f["schluessel"] as? String {
            l.fehlend = Regie.Fehlend(schluessel: k,
                                      datumKurz: Regie.datumKurz(f["datum"] as? String ?? ""),
                                      betrag: f["betrag"] as? Double ?? 0,
                                      an: f["text"] as? String ?? "")
        }

        if let t = termine.first(where: { $0["art"] as? String == "ustva" }),
           let iso = t["datum"] as? String, let d = Self.isoDatum(iso, kal) {
            l.frist = Regie.Frist(datum: d, tagText: "\(kal.component(.day, from: d)).")
        }

        let offene = store.belege.filter { $0.status == .offen && $0.istDemo != true
                                           && !$0.ocrText.isEmpty }
        l.offeneAnzahl += offene.count
        if let b = offene.first(where: { !zurueckgestellt.contains("frage:\($0.id.uuidString)") }) {
            l.frage = Regie.Frage(kennung: b.id.uuidString, belegID: b.id,
                                  lieferant: b.lieferant, betrag: b.brutto,
                                  text: b.offeneFrage
                                        ?? "babu hat eine Frage zu deinem Beleg von \(b.lieferant).",
                                  optionen: [])
        }

        let z = Regie.zaehler(belege: store.belege, monat: monatJetzt, jetzt: l.jetzt,
                              kleinunternehmerin: l.kleinunternehmerin)
        l.zurueckgeholt = (l.kleinunternehmerin ? nil : abschluss?.vorsteuer) ?? z.betrag
        l.heuteBelege = z.heuteBelege
        l.heuteZurueck = z.heuteZurueck
        l.ergebnisMonat = abschluss?.ergebnis
        return l
    }

    private static func isoDatum(_ iso: String, _ kal: Calendar) -> Date? {
        let t = iso.prefix(10).split(separator: "-")
        guard t.count == 3, let j = Int(t[0]), let m = Int(t[1]), let d = Int(t[2]) else { return nil }
        return kal.date(from: DateComponents(year: j, month: m, day: d, hour: 12))
    }

    // MARK: - Rundgang: Beispieldaten durch alle Seiten

    enum Rundgang {
        static let gruende = [
            Grund(schluessel: "kommt_noch", name: "Der Beleg kommt noch"),
            Grund(schluessel: "vertrag", name: "Das läuft über einen Vertrag"),
            Grund(schluessel: "privat", name: "War privat"),
            Grund(schluessel: "kein_beleg", name: "Dazu gibt es keinen Beleg"),
        ]

        static let slavic = Regie.Frage(
            kennung: "rundgang-slavic", belegID: nil, lieferant: "Slavic Hair Company",
            betrag: 84.90,
            text: "Slavic Hair Company, 84,90 € — Ware für den Salon oder privat?",
            optionen: ["Ware für den Salon", "War privat", "Weiß ich nicht mehr"])

        static let delila = Regie.Frage(
            kennung: "rundgang-delila", belegID: nil, lieferant: "delilà Hair Extensions",
            betrag: 236.81,
            text: "Rechnung von delilà Hair Extensions — Extensions zum Weiterverkauf "
                  + "oder Verbrauch im Salon?",
            optionen: ["Zum Weiterverkauf", "Verbrauch im Salon", "Beides"])

        static let stadtwerke = Regie.Fehlend(
            schluessel: "rundgang-stadtwerke", datumKurz: "03.08.", betrag: 412.00,
            an: "Stadtwerke Stuttgart")

        static let weingaertle = Regie.Fehlend(
            schluessel: "rundgang-weingaertle", datumKurz: "21.08.", betrag: 68.40,
            an: "Rotenberger Weingärtle")

        static let august = Regie.Monat(
            schluessel: "2026-08", name: "August", stand: "bereit",
            zahllast: -312.40, ergebnis: 2318.00)

        static func lage(schritt: Int, zaehler: Double, heute: Int, heuteZurueck: Double,
                         jetzt: Date) -> Regie.Lage {
            var l = Regie.Lage(jetzt: jetzt)
            l.zurueckgeholt = zaehler
            l.heuteBelege = heute
            l.heuteZurueck = heuteZurueck
            let kal = Calendar.current
            switch schritt {
            case 0:
                let d = kal.date(byAdding: .day, value: 6, to: jetzt) ?? jetzt
                l.frist = Regie.Frist(datum: d, tagText: "\(kal.component(.day, from: d)).")
                l.offeneAnzahl = 3
            case 1: l.frage = slavic
            case 2: l.frage = delila
            case 3: l.fehlend = stadtwerke
            case 4: l.fehlend = weingaertle
            case 5: l.monat = august
            default: l.ergebnisMonat = august.ergebnis
            }
            return l
        }

        /// 19 % aus dem Brutto — im Rundgang gibt es keine Steuertabelle.
        static func vorsteuer(fuer f: Regie.Frage) -> Double {
            ((f.betrag - f.betrag / 1.19) * 100).rounded() / 100
        }
    }
}
