import Foundation

// Die Regie des Konzepts „Ein Knopf" — reine Logik, deshalb hier prüfbar.
// Jede Seite behauptet mit Zahl, Satz und Knopf etwas über die Lage. Steht
// dort „6 Tage", obwohl es drei sind, oder „Loslegen", obwohl nichts offen
// ist, führt die Seite in die Irre. Dazu die Tonsynthese: ein Puffer, der
// knackt oder übersteuert, ist kein Katsching.

setvbuf(stdout, nil, _IONBF, 0)
var fehler = 0
func pruefe(_ was: String, _ bedingung: Bool) {
    if bedingung {
        print("  ✓ \(was)")
    } else {
        print("  ✗ \(was)")
        fehler += 1
    }
}

var kal = Calendar(identifier: .gregorian)
kal.timeZone = TimeZone(identifier: "Europe/Berlin")!

func datum(_ j: Int, _ m: Int, _ t: Int, _ h: Int = 10) -> Date {
    kal.date(from: DateComponents(year: j, month: m, day: t, hour: h))!
}

let jetzt = datum(2026, 9, 4)
let frist = Regie.Frist(datum: datum(2026, 9, 10), tagText: "10.")
let slavic = Regie.Frage(kennung: "s1", belegID: nil, lieferant: "Slavic Hair Company",
                         betrag: 84.90,
                         text: "Slavic Hair Company, 84,90 € — Ware für den Salon oder privat?",
                         optionen: ["Ware für den Salon", "War privat"])
let stadtwerke = Regie.Fehlend(schluessel: "abc", datumKurz: "12.08.", betrag: 84.90,
                               an: "Slavic Hair Company")
let august = Regie.Monat(schluessel: "2026-08", name: "August", stand: "bereit",
                         zahllast: -312.40, ergebnis: 2318.00)

func lage(_ bauen: (inout Regie.Lage) -> Void = { _ in }) -> Regie.Lage {
    var l = Regie.Lage(jetzt: jetzt)
    bauen(&l)
    return l
}

func blatt(_ l: Regie.Lage) -> Regie.Blatt {
    Regie.blatt(Regie.entscheide(l, kalender: kal), l, kalender: kal)
}

print("— Priorität —")
let alles = lage { l in
    l.frist = frist; l.offeneAnzahl = 3; l.frage = slavic; l.fehlend = stadtwerke
    l.monat = august; l.zurueckgeholt = 70.37
}
pruefe("alles gesetzt → Frist zuerst",
       Regie.entscheide(alles, kalender: kal) == .fristNaht(tage: 6))
let fristBlatt = blatt(alles)
pruefe("Zahl „6 Tage\"", fristBlatt.zahl == "6 Tage")
pruefe("Satz nennt Tag und offene Belege",
       fristBlatt.satz == "Bis zum 10. muss die Umsatzsteuer raus. 3 Belege fehlen noch.")
pruefe("Knopf „Loslegen\"", fristBlatt.knopf == "Loslegen")
pruefe("6 Tage ist mahnend, nicht dringend", fristBlatt.stimmung == .mahnend)

var dringend = alles
dringend.frist = Regie.Frist(datum: datum(2026, 9, 7), tagText: "7.")
pruefe("3 Tage → dringend", blatt(dringend).stimmung == .dringend)

var weit = alles
weit.frist = Regie.Frist(datum: datum(2026, 9, 12), tagText: "12.")
pruefe("8 Tage → keine Frist-Seite, sondern die Frage",
       Regie.entscheide(weit, kalender: kal) == .frage(slavic))

var nichtsOffen = alles
nichtsOffen.offeneAnzahl = 0
pruefe("Frist ohne offene Punkte → keine Frist-Seite",
       Regie.entscheide(nichtsOffen, kalender: kal) == .frage(slavic))

var morgen = alles
morgen.frist = Regie.Frist(datum: datum(2026, 9, 5), tagText: "5."); morgen.offeneAnzahl = 1
let morgenBlatt = blatt(morgen)
pruefe("1 Tag, Einzahl", morgenBlatt.zahl == "1 Tag"
       && morgenBlatt.satz == "Bis zum 5. muss die Umsatzsteuer raus. 1 Beleg fehlt noch.")
var heuteFrist = alles
heuteFrist.frist = Regie.Frist(datum: datum(2026, 9, 4, 23), tagText: "4.")
pruefe("am Tag selbst → „Heute\"", blatt(heuteFrist).zahl == "Heute")

print("— Frage —")
let frageLage = lage { l in l.frage = slavic; l.fehlend = stadtwerke; l.monat = august }
let frageBlatt = blatt(frageLage)
pruefe("Frage vor fehlendem Beleg",
       Regie.entscheide(frageLage, kalender: kal) == .frage(slavic))
pruefe("Zahl ist der Belegbetrag", frageBlatt.zahl == "84,90 €")
pruefe("Label ist der Lieferant", frageBlatt.label == "Slavic Hair Company")
pruefe("Satz ist die Frage", frageBlatt.satz == slavic.text)
pruefe("Knopf „Antworten\"", frageBlatt.knopf == "Antworten")
var ohneBetrag = slavic; ohneBetrag.betrag = 0
let ohneBetragBlatt = Regie.blatt(.frage(ohneBetrag), frageLage, kalender: kal)
pruefe("ohne Betrag: Zahl „1\", Label „Beleg wartet\"",
       ohneBetragBlatt.zahl == "1" && ohneBetragBlatt.label == "Beleg wartet")

print("— Beleg fehlt —")
let fehltLage = lage { l in l.fehlend = stadtwerke; l.monat = august }
let fehltBlatt = blatt(fehltLage)
pruefe("fehlender Beleg vor fertigem Monat",
       Regie.entscheide(fehltLage, kalender: kal) == .belegFehlt(stadtwerke))
pruefe("Satz wortgenau",
       fehltBlatt.satz == "Am 12.08. gingen 84,90 € an Slavic Hair Company vom Konto. Dazu fehlt der Beleg.")
pruefe("Zahl und Label", fehltBlatt.zahl == "84,90 €" && fehltBlatt.label == "vom Konto abgegangen")
pruefe("Knopf „Beleg reinwerfen\"", fehltBlatt.knopf == "Beleg reinwerfen")
pruefe("datumKurz kürzt das Jahr weg", Regie.datumKurz("12.08.2026") == "12.08.")

print("— Monat fertig —")
let monatLage = lage { l in l.monat = august }
let monatBlatt = blatt(monatLage)
pruefe("bereit → Monat-Seite", Regie.entscheide(monatLage, kalender: kal) == .monatFertig(august))
pruefe("Erstattung: Betrag ohne Vorzeichen, Label „bekommst du zurück\"",
       monatBlatt.zahl == "312,40 €" && monatBlatt.label == "bekommst du zurück")
pruefe("Satz „Dein August ist gerechnet.\"", monatBlatt.satz == "Dein August ist gerechnet.")
pruefe("Knopf „Ans Finanzamt schicken\", Stimmung fertig",
       monatBlatt.knopf == "Ans Finanzamt schicken" && monatBlatt.stimmung == .fertig)
var zahlen = august; zahlen.zahllast = 312.40
pruefe("Zahllast positiv → „zahlst du\"",
       Regie.blatt(.monatFertig(zahlen), monatLage, kalender: kal).label == "zahlst du")
var klein = monatLage; klein.kleinunternehmerin = true
let kleinBlatt = blatt(klein)
pruefe("Kleinunternehmerin: „bleibt dir\" mit Ergebnis, Knopf „Monat abschließen\"",
       kleinBlatt.zahl == "2.318,00 €" && kleinBlatt.label == "bleibt dir"
       && kleinBlatt.knopf == "Monat abschließen")
for stand in ["laeuft", "wartet", "freigegeben"] {
    var m = august; m.stand = stand
    let l = lage { $0.monat = m }
    pruefe("Stand „\(stand)\" → heim", Regie.entscheide(l, kalender: kal) == .heim(abend: false))
}

print("— Heim —")
let tag = lage { l in l.jetzt = datum(2026, 9, 4, 17); l.zurueckgeholt = 70.37 }
let tagBlatt = blatt(tag)
pruefe("17 Uhr ist Tag", Regie.entscheide(tag, kalender: kal) == .heim(abend: false))
pruefe("Zähler mit Monatslabel",
       tagBlatt.zahl == "70,37 €" && tagBlatt.label == "zurückgeholt im September")
pruefe("Satz lädt zum Reinwerfen", tagBlatt.satz.hasPrefix("Wirf alles rein")
       && tagBlatt.knopf == "Reinwerfen")
var kleinTag = tag; kleinTag.kleinunternehmerin = true
pruefe("Kleinunternehmerin: „erfasst im September\"",
       blatt(kleinTag).label == "erfasst im September")

let abend = lage { l in
    l.jetzt = datum(2026, 9, 4, 18); l.zurueckgeholt = 70.37
    l.heuteBelege = 3; l.heuteZurueck = 48.00; l.ergebnisMonat = 2318.00
}
let abendBlatt = blatt(abend)
pruefe("18 Uhr ist Abend", Regie.entscheide(abend, kalender: kal) == .heim(abend: true))
pruefe("Abend: Ergebnis als Zahl, „Bleibt dir\"",
       abendBlatt.zahl == "2.318,00 €" && abendBlatt.label == "Bleibt dir")
pruefe("Abend-Satz wortgenau",
       abendBlatt.satz == "Heute 3 Belege reingeworfen, 48,00 € zurückgeholt. Im September bleiben dir bisher 2.318,00 €.")
var leerAbend = abend; leerAbend.heuteBelege = 0; leerAbend.heuteZurueck = 0
pruefe("nichts reingeworfen — auch gut",
       blatt(leerAbend).satz == "Heute nichts reingeworfen — auch gut. Im September bleiben dir bisher 2.318,00 €.")
var ohneErgebnis = abend; ohneErgebnis.ergebnisMonat = nil
let ohneErgebnisBlatt = blatt(ohneErgebnis)
pruefe("ohne Ergebnis: kein zweiter Satz, Zähler bleibt die Zahl",
       ohneErgebnisBlatt.satz == "Heute 3 Belege reingeworfen, 48,00 € zurückgeholt."
       && ohneErgebnisBlatt.zahl == "70,37 €")
var einer = abend; einer.heuteBelege = 1
pruefe("Einzahl „1 Beleg\"", blatt(einer).satz.hasPrefix("Heute 1 Beleg reingeworfen"))
var kleinAbend = abend; kleinAbend.kleinunternehmerin = true
pruefe("Kleinunternehmerin abends ohne „zurückgeholt\"",
       blatt(kleinAbend).satz.hasPrefix("Heute 3 Belege reingeworfen. Im September"))

print("— Zähler —")
func beleg(_ lieferant: String, _ datumText: String, ust: Double, brutto: Double,
           status: BelegStatus = .bestaetigt, demo: Bool = false,
           gesiegelt: Date? = nil) -> Beleg {
    var b = Beleg(lieferant: lieferant, belegNr: "", datumText: datumText,
                  netto: brutto - ust, ust: ust, brutto: brutto, ustSatz: 19,
                  konto: "5200", steuerschluessel: "9", kreditor: "",
                  herkunft: .ki, confidence: 99, status: status,
                  begruendung: "", summenprobeOK: true)
    b.istDemo = demo ? true : nil
    b.siegelZeit = gesiegelt
    return b
}
let belege = [
    beleg("Slavic Hair", "02.09.2026", ust: 13.56, brutto: 84.90, gesiegelt: datum(2026, 9, 4, 9)),
    beleg("delilà", "03.09.2026", ust: 37.81, brutto: 236.81, status: .fixiert),
    beleg("offen", "03.09.2026", ust: 5.00, brutto: 31.30, status: .offen),
    beleg("August", "28.08.2026", ust: 9.00, brutto: 56.40),
    beleg("Demo", "01.09.2026", ust: 19.00, brutto: 119.00, demo: true),
    beleg("gestern", "03.09.2026", ust: 2.00, brutto: 12.52, gesiegelt: datum(2026, 9, 3, 20)),
]
let z = Regie.zaehler(belege: belege, monat: "2026-09", jetzt: jetzt,
                      kleinunternehmerin: false, kalender: kal)
pruefe("Vorsteuer nur gebuchter, echter September-Belege",
       abs(z.betrag - (13.56 + 37.81 + 2.00)) < 0.001)
pruefe("Label „zurückgeholt im September\"", z.label == "zurückgeholt im September")
pruefe("heute zählt nur, was heute gesiegelt wurde",
       z.heuteBelege == 1 && abs(z.heuteZurueck - 13.56) < 0.001)
let zk = Regie.zaehler(belege: belege, monat: "2026-09", jetzt: jetzt,
                       kleinunternehmerin: true, kalender: kal)
pruefe("Kleinunternehmerin: Brutto als „erfasst\"",
       abs(zk.betrag - (84.90 + 236.81 + 12.52)) < 0.001 && zk.label == "erfasst im September")

print("— Kennungen —")
var zweite = slavic; zweite.kennung = "s2"
pruefe("zwei Fragen, zwei Kennungen",
       Regie.Seite.frage(slavic).kennung != Regie.Seite.frage(zweite).kennung)
pruefe("gleiche Frage, gleiche Kennung",
       Regie.Seite.frage(slavic).kennung == Regie.Seite.frage(slavic).kennung)
pruefe("Tag und Abend sind zwei Seiten",
       Regie.Seite.heim(abend: true).kennung != Regie.Seite.heim(abend: false).kennung)

print("— Sprachregel —")
let verboten = ["Server", "Token", "Hash", "Commit", "Queue", "Modell", "KI", "OCR", "Lesung"]
func sauber(_ text: String) -> Bool {
    let woerter = text.split { !$0.isLetter }.map(String.init)
    return !woerter.contains { verboten.contains($0) }
}
pruefe("Wortgrenze: „Skizze\" ist kein Treffer", sauber("Skizze"))
for l in [alles, dringend, frageLage, fehltLage, monatLage, klein, tag, abend, leerAbend, kleinAbend] {
    let b = blatt(l)
    pruefe("Blatt „\(b.knopf)\" ohne Systemwörter",
           sauber(b.zahl) && sauber(b.label ?? "") && sauber(b.satz) && sauber(b.knopf))
}

print("— Tonsynthese —")
let muenze = Tonsynthese.muenze()
pruefe("Münze ist 0,35 s lang (15.435 Samples)", muenze.count == 15_435)
pruefe("Spitze höchstens 0,8", muenze.map(abs).max()! <= 0.8001)
pruefe("kein NaN", !muenze.contains { $0.isNaN })
pruefe("beginnt bei null (kein Knacken)", muenze[0] == 0)
pruefe("klingt aus (letzte 50 Samples < 0,02)",
       muenze.suffix(50).allSatisfy { abs($0) < 0.02 })
pruefe("es ist überhaupt Ton drin", muenze.map(abs).max()! > 0.5)
let fanfare = Tonsynthese.fanfare()
pruefe("Fanfare 1,2 s, kein NaN, Spitze ≤ 0,8",
       fanfare.count == 52_920 && !fanfare.contains { $0.isNaN }
       && fanfare.map(abs).max()! <= 0.8001)
pruefe("Fanfare klingt aus", fanfare.suffix(50).allSatisfy { abs($0) < 0.05 })

print(fehler == 0 ? "Alles in Ordnung." : "\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
