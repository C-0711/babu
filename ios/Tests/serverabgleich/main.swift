import Foundation

// Harness: der Server ist die Wahrheit (ServerAbgleich.swift, 10.10.2026).
//
// Drei Meldungen, eine Ursache: die Belegliste lag nur auf dem Telefon.
// Hier wird die Zusammenführung geprüft — ohne Netz, ohne UIKit.

var fehler = 0
func pruefe(_ name: String, _ ok: Bool) {
    if ok { print("  ok  \(name)") } else { fehler += 1; print("  FEHLER  \(name)") }
}

func lokal(_ name: String?, status: AblageStatus?, datum: String = "03.08.2026",
           brutto: Double = 12.5, als: String? = nil) -> Beleg {
    var b = Beleg(lieferant: "Slavic Hair", belegNr: "ohne Nr.", datumText: datum,
                  netto: 10.5, ust: 2, brutto: brutto, ustSatz: 19, konto: "5400",
                  steuerschluessel: "9", kreditor: "70000", herkunft: .ki, confidence: 90,
                  status: .bestaetigt, begruendung: "", summenprobeOK: true)
    b.ablageDateiname = name
    b.ablageStatus = status
    b.abgelegtAls = als
    return b
}

func server(_ stamm: String, status: String = "geprüft", datum: String? = "2026-07-21",
            lieferant: String? = "Weingärtle", brutto: Double? = 44.9,
            hochgeladen: String? = "2026-07-21T10:00:00Z") -> ServerAbgleich.Zeile {
    ServerAbgleich.Zeile(stamm: stamm, datei: "docs/2026-07/\(stamm).jpg", monat: "2026-07",
                         status: status, lieferant: lieferant, datum: datum, brutto: brutto,
                         netto: 37.73, ust: 7.17, ustSatz: 19, konto: "6640", belegart: "Bewirtung",
                         dokumentklasse: "beleg", hochgeladen: hochgeladen)
}

print("— Zeile aus JSON —")
let json: [String: Any] = ["stamm": "20260721-1200-ab12cd-beleg_2026-07-21_weingaertle_988af90f",
                           "datei": "docs/2026-07/20260721-1200-ab12cd-beleg_2026-07-21_weingaertle_988af90f.jpg",
                           "monat": "2026-07", "status": "nachfrage", "lieferant": "Weingärtle",
                           "datum": "2026-07-21", "brutto": 44.9, "netto": 37.73, "ust": 7.17,
                           "ust_satz": 19, "konto_skr04": 6640, "hochgeladen": "2026-07-21T10:00:00Z"]
let z = ServerAbgleich.zeile(aus: json)
pruefe("Zeile gelesen", z != nil)
pruefe("Konto als Text, auch wenn der Server eine Zahl schickt", z?.konto == "6640")
pruefe("Steuersatz als Zahl", z?.ustSatz == 19)
pruefe("ohne Stamm keine Zeile", ServerAbgleich.zeile(aus: ["datei": "x"]) == nil)

print("— Datum und Stamm —")
pruefe("ISO → deutsch", ServerAbgleich.datumText(ausISO: "2026-07-21") == "21.07.2026")
pruefe("deutsch bleibt", ServerAbgleich.datumText(ausISO: "21.07.2026") == "21.07.2026")
pruefe("Unsinn wird leer (Ohne Datum)", ServerAbgleich.datumText(ausISO: "0000-00-00") == "")
pruefe("Stamm ohne Endung und Pfad",
       ServerAbgleich.stamm(ausDateiname: "docs/2026-07/abc-beleg_x.jpg") == "abc-beleg_x")
pruefe("Stamm mit Punkt im Namen bleibt",
       ServerAbgleich.stamm(ausDateiname: "beleg_2026-07-21_dm-drogerie.markt_1a2b3c4d.pdf")
           == "beleg_2026-07-21_dm-drogerie.markt_1a2b3c4d")
pruefe("Servername mit Präfix passt zum Telefon-Namen",
       ServerAbgleich.passt(lokalerStamm: "beleg_2026-07-21_weingaertle_988af90f",
                            serverStamm: "20260721-1200-ab12cd-beleg_2026-07-21_weingaertle_988af90f"))
pruefe("fremder Stamm passt nicht",
       !ServerAbgleich.passt(lokalerStamm: "beleg_2026-07-21_weingaertle_988af90f",
                             serverStamm: "20260721-1200-ab12cd-beleg_2026-07-21_weingaertle_11111111"))

print("— Beleg vom Server —")
let neu = ServerAbgleich.beleg(aus: server("s1", status: "nachfrage"))
pruefe("übertragen, ohne Foto", neu.ablageStatus == .uebertragen && neu.bildJpeg == nil)
pruefe("Name = Servername", neu.ablageDateiname == "s1.jpg")
pruefe("Datum deutsch", neu.datumText == "21.07.2026")
pruefe("nachfrage → offen mit Satz", neu.status == .offen && neu.begruendung.contains("Frage"))
pruefe("geprüft → bestätigt", ServerAbgleich.beleg(aus: server("s2")).status == .bestaetigt)
pruefe("exportiert → fixiert", ServerAbgleich.beleg(aus: server("s3", status: "exportiert")).status == .fixiert)
pruefe("Herkunft Historie", neu.herkunft == .historie)

print("— Zusammenführen —")
let eigener = lokal("20260803-0900-ffeeaa-beleg_2026-08-03_slavic-hair_0a0a0a0a.jpg", status: .uebertragen)
let wartend = lokal("beleg_2026-08-04_slavic-hair_0b0b0b0b.jpg", status: .ausstehend)
let geloescht = lokal("20260801-0800-dddddd-beleg_2026-08-01_dm_0c0c0c0c.jpg", status: .uebertragen)
let vertrag = lokal("20260801-0800-eeeeee-vertrag_x.pdf", status: .uebertragen, als: "vertrag")
let nieHochgeladen = lokal(nil, status: nil)
let liste = [eigener, wartend, geloescht, vertrag, nieHochgeladen]
let serverListe = [server("20260803-0900-ffeeaa-beleg_2026-08-03_slavic-hair_0a0a0a0a"),
                   server("20260721-1200-ab12cd-beleg_2026-07-21_weingaertle_988af90f")]

let voll = ServerAbgleich.zusammenfuehren(lokal: liste, server: serverListe, vollstaendig: true)
pruefe("eigener bleibt (genau einmal)",
       voll.filter { $0.ablageDateiname == eigener.ablageDateiname }.count == 1)
pruefe("wartender Upload bleibt", voll.contains { $0.ablageDateiname == wartend.ablageDateiname })
pruefe("im Portal gelöschter geht", !voll.contains { $0.ablageDateiname == geloescht.ablageDateiname })
pruefe("Vertrag aus anderem Fach bleibt", voll.contains { $0.ablageDateiname == vertrag.ablageDateiname })
pruefe("nie hochgeladener bleibt", voll.contains { $0.ablageDateiname == nil })
pruefe("Server-Beleg kommt dazu",
       voll.contains { $0.ablageDateiname == "20260721-1200-ab12cd-beleg_2026-07-21_weingaertle_988af90f.jpg" })
pruefe("Monat Juli ist jetzt da", voll.contains { $0.datumText == "21.07.2026" })
pruefe("Summe stimmt", voll.count == 5)

let halb = ServerAbgleich.zusammenfuehren(lokal: liste, server: serverListe, vollstaendig: false)
pruefe("unvollständige Liste löscht nichts",
       halb.contains { $0.ablageDateiname == geloescht.ablageDateiname } && halb.count == 6)

print("— Lücken füllen, nie überschreiben —")
var ohneDatum = lokal("beleg_0000-00-00_beleg_0d0d0d0d.jpg", status: .uebertragen, datum: "", brutto: 0)
ohneDatum.lieferant = "Beleg"
let gefuellt = ServerAbgleich.zusammenfuehren(
    lokal: [ohneDatum], server: [server("20260901-0001-abcabc-beleg_0000-00-00_beleg_0d0d0d0d")],
    vollstaendig: true)
pruefe("Datum und Lieferant nachgetragen",
       gefuellt[0].datumText == "21.07.2026" && gefuellt[0].lieferant == "Weingärtle")
pruefe("Betrag nachgetragen", gefuellt[0].brutto == 44.9)
pruefe("Servername übernommen", gefuellt[0].ablageDateiname == "20260901-0001-abcabc-beleg_0000-00-00_beleg_0d0d0d0d.jpg")
let eigeneBuchung = ServerAbgleich.zusammenfuehren(
    lokal: [eigener], server: [server("20260803-0900-ffeeaa-beleg_2026-08-03_slavic-hair_0a0a0a0a")],
    vollstaendig: true)
pruefe("eigene Buchung bleibt unberührt",
       eigeneBuchung[0].lieferant == "Slavic Hair" && eigeneBuchung[0].brutto == 12.5
           && eigeneBuchung[0].datumText == "03.08.2026")

print("— Zustandsdatei je Zugang —")
pruefe("ohne Zugang die alte Datei", ServerAbgleich.zustandsDateiName(zugang: nil) == "zustand.json")
let a = ServerAbgleich.zustandsDateiName(zugang: "gcpat-aaaa")
let b = ServerAbgleich.zustandsDateiName(zugang: "gcpat-bbbb")
pruefe("stabil", a == ServerAbgleich.zustandsDateiName(zugang: "gcpat-aaaa"))
pruefe("zwei Zugänge, zwei Dateien", a != b && a.hasPrefix("zustand-") && a.hasSuffix(".json"))
pruefe("kein Schlüssel im Namen", !a.contains("gcpat"))

print(fehler == 0 ? "ALLE OK" : "\(fehler) FEHLER")
exit(fehler == 0 ? 0 : 1)
