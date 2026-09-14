import Foundation

// Abgleich-Harness: die Regeln der Warteschlange, ohne Netz und Simulator.
//
// Ninas Fund vom 14.09.2026: Löschen und Ändern blieben auf dem Telefon.
// Hier steht, was die Schlange tun muss, damit das nicht wieder passiert —
// und was sie NICHT tun darf (nach einem Löschen noch Angaben schicken,
// ohne Servernamen einen Pfad bauen, ein Datum raten).

var fehler = 0
func pruefe(_ ok: Bool, _ name: String) {
    if ok { print("  ok  \(name)") } else { fehler += 1; print("  FEHLER  \(name)") }
}

let beleg = UUID()
let anderer = UUID()

// ————— Pfade: dieselben Routen wie das Portal —————
do {
    let a = AbgleichAuftrag(belegID: beleg, art: .loeschen, stamm: "20260914-1-x_beleg", felder: [:])
    pruefe(Abgleich.pfad(a) == "api/beleg/20260914-1-x_beleg/loeschen", "Löschen ruft die Portal-Route")
    let b = AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: "s", felder: ["brutto": "4,20"])
    pruefe(Abgleich.pfad(b) == "api/angaben/s", "Angaben rufen die Portal-Route")
    let c = AbgleichAuftrag(belegID: beleg, art: .bewirtung, stamm: "s", felder: [:])
    pruefe(Abgleich.pfad(c) == "api/bewirtung/s", "Bewirtung ruft die Portal-Route")
    let ohne = AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: nil, felder: [:])
    pruefe(Abgleich.pfad(ohne) == nil, "ohne Servernamen kein Pfad")
}

// ————— Einreihen: klein halten, Löschen gewinnt —————
do {
    var s: [AbgleichAuftrag] = []
    s = Abgleich.einreihen(AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: "s",
                                            felder: ["brutto": "4,20"]), in: s)
    s = Abgleich.einreihen(AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: "s",
                                            felder: ["konto": "6530"]), in: s)
    pruefe(s.count == 1, "zwei Angaben zum selben Beleg werden eine")
    pruefe(s[0].felder == ["brutto": "4,20", "konto": "6530"], "die Felder werden gemischt")
    s = Abgleich.einreihen(AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: "s",
                                            felder: ["brutto": "5,00"]), in: s)
    pruefe(s[0].felder["brutto"] == "5,00", "die spätere Angabe gewinnt")
    s = Abgleich.einreihen(AbgleichAuftrag(belegID: anderer, art: .angaben, stamm: "t",
                                            felder: ["lieferant": "dm"]), in: s)
    pruefe(s.count == 2, "ein anderer Beleg bekommt seinen eigenen Auftrag")
    s = Abgleich.einreihen(AbgleichAuftrag(belegID: beleg, art: .loeschen, stamm: "s", felder: [:]), in: s)
    pruefe(s.filter { $0.belegID == beleg }.count == 1
           && s.first { $0.belegID == beleg }?.art == .loeschen,
           "Löschen ersetzt alle Aufträge zum Beleg")
    s = Abgleich.einreihen(AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: "s",
                                            felder: ["brutto": "1,00"]), in: s)
    pruefe(s.filter { $0.belegID == beleg }.count == 1, "nach dem Löschen kommt nichts mehr dazu")
    pruefe(s.first { $0.belegID == anderer } != nil, "der andere Beleg bleibt unberührt")
}

// ————— Servername nachtragen, wenn der Upload später fertig wird —————
do {
    var s = [AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: nil, felder: ["brutto": "4,20"]),
             AbgleichAuftrag(belegID: anderer, art: .angaben, stamm: "t", felder: [:])]
    s = Abgleich.stammNachtragen(s, belegID: beleg, stamm: "20260914-x")
    pruefe(s[0].stamm == "20260914-x", "der Auftrag bekommt den Servernamen")
    pruefe(s[1].stamm == "t", "fremde Aufträge behalten ihren")
}

// ————— Bewirtung: eine Zeile wird zur Liste —————
do {
    let a = AbgleichAuftrag(belegID: beleg, art: .bewirtung, stamm: "s",
                            felder: ["anlass": "Teamessen", "personen": "Nina Baic, Bea; Chris\n"])
    let r = Abgleich.rumpf(a)
    pruefe(r["anlass"] as? String == "Teamessen", "Anlass geht mit")
    pruefe((r["teilnehmer"] as? [String]) == ["Nina Baic", "Bea", "Chris"], "Teilnehmer als Liste, ohne Leere")
    pruefe(Abgleich.rumpf(AbgleichAuftrag(belegID: beleg, art: .loeschen, stamm: "s", felder: [:])).isEmpty,
           "Löschen hat keinen Rumpf")
}

// ————— Datum und Betrag im Serverformat —————
do {
    pruefe(Abgleich.isoDatum("05.03.2026") == "2026-03-05", "deutsches Datum wird ISO")
    pruefe(Abgleich.isoDatum(" 5.3.2026 ") == "2026-03-05", "auch ohne führende Nullen")
    pruefe(Abgleich.isoDatum("2026-03-05") == nil, "ISO wird nicht doppelt gewandelt")
    pruefe(Abgleich.isoDatum("31.02.abc") == nil, "Unlesbares wird nicht geraten")
    pruefe(Abgleich.betragText(4.2) == "4,20", "Betrag mit Komma und zwei Stellen")
    pruefe(Abgleich.betragText(1234.5) == "1234,50", "kein Tausenderpunkt")
}

// ————— Pausen wie beim Upload —————
do {
    pruefe(Abgleich.pause(nachVersuchen: 0) == 0, "erster Versuch sofort")
    pruefe(Abgleich.pause(nachVersuchen: 1) == 30, "dann 30 s")
    pruefe(Abgleich.pause(nachVersuchen: 3) == 120, "verdoppelt sich")
    pruefe(Abgleich.pause(nachVersuchen: 20) == 1800, "höchstens 30 min")
}

// ————— Rundreise durch zustand.json —————
do {
    let a = AbgleichAuftrag(belegID: beleg, art: .angaben, stamm: "s", felder: ["brutto": "4,20"])
    let daten = try! JSONEncoder().encode([a])
    let zurueck = try! JSONDecoder().decode([AbgleichAuftrag].self, from: daten)
    pruefe(zurueck == [a], "Aufträge überleben das Speichern")
}

print(fehler == 0 ? "Abgleich-Harness: alles grün" : "Abgleich-Harness: \(fehler) Fehler")
exit(fehler == 0 ? 0 : 1)
