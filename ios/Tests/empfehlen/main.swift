import Foundation

// Empfehlen: was aus `GET /api/ambassador/me` auf dem Bildschirm wird.
//
// Der Server wächst schneller als die App. Deshalb prüft dieser Harness vor
// allem, dass nichts kippt, wenn ein Feld fehlt, null ist oder als Text statt
// als Zahl kommt — und dass die drei Farben dasselbe sagen wie das Portal.

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

func stand(_ text: String) -> EmpfehlenStand? {
    EmpfehlenStand(daten: Data(text.utf8))
}

// Die echte Antwort vom lokalen Prüfstand (08.10.2026), so wie im Auftrag.
let echt = """
{"code":"JASMIN-37EA","name":"Jasmin","aktiv":true,"link":"https://mybabu.io/ambassador/JASMIN-37EA/salon",
 "verdient":0,"gezahlt":0,"offen":0,
 "salons":[{"email":"kim@example.org","salon":"Kims Haarstudio","eingelöst":"2026-10-08T20:51:36Z","meilenstein":"testet","verdienst":0,
   "testmonat":{"bis":"2026-11-06","tage_uebrig":30,"vorbei":false},"naechster_schritt":"Testet noch bis 06.11.2026 — in der letzten Woche nachfragen."}],
 "zahlen":{"eingeladen":1,"wartet":0,"testet":1,"abgelaufen":0,"gezeichnet":0,"gehalten":0},
 "einladungen":[],
 "geld":{"erwartet":null,"unterwegs":0,"verdient":0,"ausgezahlt":0,"offen":0,
   "naechster_lauf":{"datum":"2026-10-15","stichtag":"2026-09-30","betrag":0,"wird_ausgezahlt":false,"hinweis":"…","posten":[]}},
 "kontakte":[{"nr":1,"name":"Kim","salon":"Kims Haarstudio","telefon":"+49 171 2345678","stand":"probiert aus",
   "aktiv":"Noch kein Beleg","ton":"neutral","gesendet_am":null,"aufgabe":null}],
 "heute":[],"profil_vollstaendig":false,"profil_fehlt":["Kontodaten","Anschrift","Steuerangabe","Zustimmung"]}
"""

print("— Die echte Antwort —")
let j = stand(echt)
pruefe("lässt sich lesen", j != nil)
pruefe("Name und Link", j?.name == "Jasmin"
       && j?.link == "https://mybabu.io/ambassador/JASMIN-37EA/salon")
pruefe("0 € offen", j?.geld.offen == 0)
pruefe("bei 0 € der Satz für den Anfang",
       j?.geldSatz == "Sobald ein Salon mitmacht, steht dein Geld hier.")
pruefe("ohne Geld keine Mahnung wegen des Kontos", j?.kontoFehlt == false)
pruefe("Kim steht genau einmal da (Kontakt und Salon sind derselbe)",
       j?.salons.count == 1 && j?.salons.first?.name == "Kim")
pruefe("Kim probiert aus: gelb", j?.salons.first?.ampel == .gelb
       && j?.salons.first?.wort == "probiert aus")
pruefe("darunter, was sie tut", j?.salons.first?.aktiv == "Noch kein Beleg")
pruefe("ohne Aufgabe kein Knopf", j?.salons.first?.aufgabe == nil)

print("— Geld —")
pruefe("79 € ohne Komma", EmpfehlenStand.euro(79) == "79 €")
pruefe("Tausender mit Punkt", EmpfehlenStand.euro(1234) == "1.234 €")
pruefe("Cent nur, wenn es welche gibt", EmpfehlenStand.euro(79.5) == "79,50 €")
let jahr = Calendar(identifier: .gregorian).component(.year, from: Date())
pruefe("Datum lang, in diesem Jahr ohne Jahreszahl",
       EmpfehlenStand.datumLang("\(jahr)-10-15") == "15. Oktober")
pruefe("im nächsten Jahr mit", EmpfehlenStand.datumLang("\(jahr + 1)-01-15")
       == "15. Januar \(jahr + 1)")
pruefe("Murks gibt kein Datum", EmpfehlenStand.datumLang("bald") == nil)

func geld(_ g: String, profil: Bool = true) -> EmpfehlenStand? {
    stand("{\"geld\": \(g), \"profil_vollstaendig\": \(profil)}")
}
let kommt = geld("{\"offen\": 474, \"erwartet\": {\"datum\": \"\(jahr)-10-15\", \"betrag\": 474}}")
pruefe("mit erwartet: Datum der Überweisung",
       kommt?.geldSatz == "Kommt am 15. Oktober auf dein Konto.")
let teil = geld("{\"offen\": 474, \"erwartet\": {\"datum\": \"\(jahr)-10-15\", \"betrag\": 237}}")
pruefe("nur ein Teil kommt: Betrag und Datum",
       teil?.geldSatz == "Davon kommen 237 € am 15. Oktober, der Rest später.")
let klein = geld("{\"offen\": 40, \"erwartet\": null}")
pruefe("unter der Mindestsumme: wann überwiesen wird",
       klein?.geldSatz == "Überwiesen wird, sobald 100 € zusammen sind.")
let weg = geld("{\"offen\": 237, \"unterwegs\": 237}")
pruefe("schon überwiesen", weg?.geldSatz == "Ist schon auf dem Weg zu dir.")
let ohneKonto = geld("{\"offen\": 237}", profil: false)
pruefe("Geld da, Konto fehlt: Hinweis aufs Konto", ohneKonto?.kontoFehlt == true)
pruefe("… und kein Datum, das nicht stimmt",
       ohneKonto?.geldSatz.contains("sobald dein Konto da ist") == true)
pruefe("Zahl als Text wird gelesen", geld("{\"offen\": \"79\"}")?.geld.offen == 79)
pruefe("ohne geld-Feld zählt das alte offen", stand("{\"offen\": 79}")?.geld.offen == 79)
pruefe("ein leeres Objekt ist kein Fehler", stand("{}") != nil)
pruefe("leeres Objekt: aktiv, kein Alarm", stand("{}")?.aktiv == true
       && stand("{}")?.kontoFehlt == false)
pruefe("Unsinn ist kein Stand", stand("[1,2]") == nil && stand("kaputt") == nil)

print("— Farben —")
typealias A = EmpfehlenStand
pruefe("noch nicht gestartet: grau, eingeladen",
       A.ampel(stand: "noch nicht gestartet", meilenstein: nil) == (.grau, "eingeladen"))
pruefe("macht mit: grün, zahlt", A.ampel(stand: "macht mit", meilenstein: nil) == (.gruen, "zahlt"))
pruefe("hat abgeschlossen: grün", A.ampel(stand: "hat abgeschlossen", meilenstein: nil).0 == .gruen)
pruefe("Zahlung offen: gelb, das Wort bleibt",
       A.ampel(stand: "Zahlung offen", meilenstein: nil) == (.gelb, "Zahlung offen"))
pruefe("Test vorbei: grau, das Wort bleibt",
       A.ampel(stand: "Test vorbei", meilenstein: nil) == (.grau, "Test vorbei"))
pruefe("ohne Stand zählt der Meilenstein: gezeichnet = grün",
       A.ampel(stand: nil, meilenstein: "gezeichnet").0 == .gruen)
pruefe("gehalten = grün", A.ampel(stand: nil, meilenstein: "gehalten").0 == .gruen)
pruefe("testet = gelb", A.ampel(stand: nil, meilenstein: "testet") == (.gelb, "probiert aus"))
pruefe("gar nichts = grau, eingeladen", A.ampel(stand: nil, meilenstein: nil) == (.grau, "eingeladen"))

print("— Salons ohne Kontaktzeile —")
let gemischt = stand("""
{"kontakte":[{"nr":3,"name":"Sabine","salon":null,"stand":"noch nicht gestartet","aktiv":"Hat den Link noch nicht geöffnet",
   "aufgabe":{"nr":3,"art":"nicht_gestartet","grund":"Seit 4 Tagen nicht gestartet","knopf":"Beim Start helfen",
              "nachricht":"Hallo Sabine …","whatsapp":"https://wa.me/491712345678?text=Hallo"}}],
 "salons":[{"salon":"Haarwerk Ost","meilenstein":"gezeichnet","naechster_schritt":"Zahlt seit September."}]}
""")
pruefe("beide stehen da", gemischt?.salons.map(\.name) == ["Sabine", "Haarwerk Ost"])
pruefe("der Salon ohne Kontakt ist grün", gemischt?.salons.last?.ampel == .gruen)
pruefe("… mit seinem nächsten Schritt darunter", gemischt?.salons.last?.aktiv == "Zahlt seit September.")
let auf = gemischt?.salons.first?.aufgabe
pruefe("die Aufgabe trägt Nummer, Art, Knopf und WhatsApp",
       auf?.nr == 3 && auf?.art == "nicht_gestartet" && auf?.knopf == "Beim Start helfen"
       && auf?.whatsapp?.hasPrefix("https://wa.me/") == true)
pruefe("Nummer 1 ist eine Zahl, kein Ja", stand("""
{"kontakte":[{"name":"Kim","aufgabe":{"nr":1,"art":"kein_beleg","knopf":"Nachfragen"}}]}
""")?.salons.first?.aufgabe?.nr == 1)
pruefe("eine Aufgabe ohne Knopf ist keine", stand("""
{"kontakte":[{"name":"Kim","aufgabe":{"nr":1,"art":"kein_beleg"}}]}
""")?.salons.first?.aufgabe == nil)
let alt = stand("""
{"salons":[{"salon":"Kims Haarstudio","meilenstein":"testet"},{"salon":"Studio 7","meilenstein":"gehalten"}]}
""")
pruefe("älterer Stand ohne kontakte: alle Salons", alt?.salons.count == 2)

print("— Einladen —")
let mitNummer = A.einladung(Data("""
{"link":"https://mybabu.io/ambassador/JASMIN-37EA/kim-1a2b","id":7,"text":"Hallo Kim …","whatsapp":"https://wa.me/49171?text=x"}
""".utf8))
pruefe("Antwort mit Nummer: Link, Text, WhatsApp",
       mitNummer?.text == "Hallo Kim …" && mitNummer?.whatsapp != nil)
let ohneNummer = A.einladung(Data("{\"link\":\"https://mybabu.io/x\",\"id\":8}".utf8))
pruefe("Antwort ohne Nummer: nur der Link", ohneNummer?.link == "https://mybabu.io/x"
       && ohneNummer?.text == nil && ohneNummer?.whatsapp == nil)
pruefe("ohne Link keine Einladung", A.einladung(Data("{\"fehler\":\"x\"}".utf8)) == nil)
pruefe("der Text, wenn babu keinen schreibt",
       A.einladungstext(vorname: "Kim", link: "https://mybabu.io/x")
       == "Hallo Kim, ich mache meine Belege jetzt mit babu: Foto machen, fertig. "
        + "Probier es 30 Tage kostenlos aus: https://mybabu.io/x")
pruefe("ohne Vornamen nur Hallo",
       A.einladungstext(vorname: "", link: "L").hasPrefix("Hallo, ich mache"))

print("— Handynummer aus dem Kontakt —")
pruefe("als Mobil gespeichert gewinnt",
       A.handynummer([(false, "0711 123456"), (true, "0171 2345678")]) == "0171 2345678")
pruefe("ohne Bezeichnung: was wie ein Handy aussieht",
       A.handynummer([(false, "0711 123456"), (false, "+49 160 1234567")]) == "+49 160 1234567")
pruefe("nur Festnetz: keine", A.handynummer([(false, "0711 123456")]) == nil)
pruefe("gar keine Nummer: keine", A.handynummer([]) == nil)
pruefe("0049 zählt wie +49", A.siehtNachHandyAus("0049 151 23456789"))
pruefe("Österreich", A.siehtNachHandyAus("+43 664 1234567"))
pruefe("Schweiz", A.siehtNachHandyAus("+41 79 123 45 67"))
pruefe("deutsches Festnetz nicht", !A.siehtNachHandyAus("+49 711 1234567"))

print("— Anmelden per Link —")
pruefe("babu://anmelden/<token>",
       Anmeldelink.token(aus: URL(string: "babu://anmelden/abc_DEF-123")!) == "abc_DEF-123")
pruefe("babupro://anmelden/<token>",
       Anmeldelink.token(aus: URL(string: "babupro://anmelden/xyz")!) == "xyz")
pruefe("Großschreibung im Schema stört nicht",
       Anmeldelink.token(aus: URL(string: "BABU://Anmelden/xyz")!) == "xyz")
pruefe("ohne Token nichts", Anmeldelink.token(aus: URL(string: "babu://anmelden/")!) == nil)
pruefe("eine geteilte Datei ist kein Anmelde-Link",
       Anmeldelink.token(aus: URL(fileURLWithPath: "/tmp/rechnung.pdf")) == nil)
pruefe("die Webseite selbst auch nicht",
       Anmeldelink.token(aus: URL(string: "https://mybabu.io/anmelden/abc")!) == nil)
pruefe("anderes Ziel im selben Schema auch nicht",
       Anmeldelink.token(aus: URL(string: "babu://beleg/abc")!) == nil)

print("— Ka-ching —")
// Ein Salon wird zahlende Kundin: Geld kommt dazu, ein Salon wird grün.
func kStand(verdient: Int, offen: Int, gruen: [String], gelb: [String] = [],
            bewegung: String? = nil) -> EmpfehlenStand {
    let k = (gruen.map { "{\"name\":\"\($0)\",\"stand\":\"macht mit\"}" }
             + gelb.map { "{\"name\":\"\($0)\",\"stand\":\"probiert aus\"}" })
        .joined(separator: ",")
    let b = bewegung.map { ",\"bewegungen\":[{\"art\":\"provision\",\"text\":\"\($0)\",\"betrag\":237}]" } ?? ""
    return stand("""
    {"code":"JASMIN-37EA","verdient":\(verdient),"geld":{"offen":\(offen),"verdient":\(verdient)\(b)},
     "kontakte":[\(k)]}
    """)!
}
let vorher = kStand(verdient: 0, offen: 0, gruen: [], gelb: ["Kim", "Mara"])
pruefe("erster Start: nur merken, kein Ka-ching", vorher.kaching(seit: nil) == nil)
pruefe("nichts Neues: kein Ka-ching", vorher.kaching(seit: vorher.merkstand) == nil)
let kimZahlt = kStand(verdient: 237, offen: 237, gruen: ["Kim"], gelb: ["Mara"],
                      bewegung: "Provision Kims Haarstudio, gezeichnet")
let e1 = kimZahlt.kaching(seit: vorher.merkstand)
pruefe("Geld und neu grün: ein Ereignis", e1 != nil)
pruefe("… mit Betrag und Namen", e1?.satz == "+237 € — Kim macht mit!")
pruefe("… die Zahl zählt von 0 auf 237", e1?.offenVorher == 0 && e1?.offenJetzt == 237)
pruefe("… und das Geld hat sich geändert", e1?.geldGeaendert == true)
pruefe("danach gemerkt: kein zweites Ka-ching", kimZahlt.kaching(seit: kimZahlt.merkstand) == nil)
let nurGruen = kStand(verdient: 0, offen: 0, gruen: ["Kim"], gelb: ["Mara"])
let e2 = nurGruen.kaching(seit: vorher.merkstand)
pruefe("nur grün, Geld noch nicht da: Ka-ching ohne Betrag",
       e2?.satz == "Kim macht mit!" && e2?.geldGeaendert == false)
let beide = kStand(verdient: 474, offen: 474, gruen: ["Kim", "Mara"])
pruefe("zwei zugleich: ein Ereignis, beide genannt",
       beide.kaching(seit: vorher.merkstand)?.satz == "+474 € — Kim und Mara machen mit!")
let drei = kStand(verdient: 0, offen: 0, gruen: ["Kim", "Mara", "Sabine"])
pruefe("drei: mit Komma und „und“",
       drei.kaching(seit: vorher.merkstand)?.satz == "Kim, Mara und Sabine machen mit!")
let zweiteProvision = kStand(verdient: 474, offen: 474, gruen: ["Kim"], gelb: ["Mara"],
                             bewegung: "Provision Kims Haarstudio, 3 Monate dabei")
pruefe("Geld ohne neuen grünen Salon: Salon aus der jüngsten Provision",
       zweiteProvision.kaching(seit: kimZahlt.merkstand)?.satz
       == "+237 € — Kims Haarstudio macht mit!")
let ohneSalon = kStand(verdient: 474, offen: 474, gruen: ["Kim"], gelb: ["Mara"],
                       bewegung: "Provision Salon, gezeichnet")
pruefe("Provision ohne eindeutigen Salon: nur der Betrag",
       ohneSalon.kaching(seit: kimZahlt.merkstand)?.satz == "+237 €")
let storno = kStand(verdient: 0, offen: 0, gruen: [], gelb: ["Kim", "Mara"])
pruefe("Storno (verdient fällt): still, kein Ka-ching", storno.kaching(seit: kimZahlt.merkstand) == nil)
let ausgezahlt = kStand(verdient: 474, offen: 237, gruen: ["Kim", "Mara"])
pruefe("nach einer Auszahlung zählt die Zahl vom richtigen Stand",
       ausgezahlt.kaching(seit: kimZahlt.merkstand).map { ($0.offenVorher, $0.offenJetzt) }
       .map { $0 == (0, 237) } == true)
pruefe("Topf: Bezug sind die 100 €", A.fuellung(0) == 0 && A.fuellung(50) == 0.5
       && A.fuellung(237) == 1)
pruefe("Provision lesen: nur „provision“", A.provisionSalon(["art": "auszahlung",
       "text": "Provision X, gezeichnet"]) == nil)
pruefe("Merkstand übersteht Speichern und Laden",
       (try? JSONDecoder().decode(Merkstand.self,
            from: JSONEncoder().encode(kimZahlt.merkstand))) == kimZahlt.merkstand)

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
