import Foundation

// Der Stand der Einrichtungskarte — reine Logik, deshalb hier prüfbar.
// Die Karte auf der Startseite behauptet mit jeder Zeile etwas über den
// echten Zustand. Steht dort „erledigt", obwohl nichts da ist, ist die
// Karte schlimmer als gar keine.

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

func stand(_ schritte: [Einrichtungsschritt],
           _ ziel: Einrichtungsziel) -> Einrichtungsschritt.Stand? {
    schritte.first { $0.ziel == ziel }?.stand
}

let alles: [String: String] = [
    "betrieb_name": "Salon Nina", "anschrift": "Musterweg 3, 70000 Stuttgart",
    "rechtsform": "Einzelunternehmen", "finanzamt": "Stuttgart",
    "telefon": "0711 1234", "email": "nina@0711.io",
    "kleinunternehmer": "Nein", "steuernummer": "12/345/67890",
]

print("— Nichts eingerichtet —")
let leer = Einrichtung.schritte(kontoVerbunden: false, angaben: nil,
                                ersterBeleg: false, kassenbuchBegonnen: false)
pruefe("fünf Zeilen", leer.count == 5)
pruefe("Konto ist offen", stand(leer, .konto) == .offen)
pruefe("Betriebsangaben sind unbekannt, nicht offen",
       stand(leer, .betrieb) == .unbekannt)
pruefe("Steuernummer ist unbekannt, nicht offen",
       stand(leer, .steuernummer) == .unbekannt)
pruefe("unbekannt zeigt einen Strich",
       leer.first { $0.ziel == .betrieb }?.standText == "—")
pruefe("nichts ist erledigt", !Einrichtung.alleErledigt(leer))

print("— Alles eingerichtet —")
let fertig = Einrichtung.schritte(kontoVerbunden: true, angaben: alles,
                                  ersterBeleg: true, kassenbuchBegonnen: true)
pruefe("alle fünf erledigt", Einrichtung.alleErledigt(fertig))
pruefe("erledigt zeigt einen Haken",
       fertig.allSatisfy { $0.standText == "✓" })

print("— Halb ausgefüllte Betriebsangaben —")
let halb = Einrichtung.schritte(
    kontoVerbunden: true,
    angaben: ["betrieb_name": "Salon Nina", "anschrift": "Musterweg 3",
              "finanzamt": "Stuttgart"],
    ersterBeleg: true, kassenbuchBegonnen: false)
pruefe("drei von sieben", stand(halb, .betrieb) == .teilweise(fertig: 3, gesamt: 7))
pruefe("und genau so steht es da",
       halb.first { $0.ziel == .betrieb }?.standText == "3 von 7")
pruefe("Kassenbuch ist offen", stand(halb, .kassenbuch) == .offen)
pruefe("noch nicht alles erledigt", !Einrichtung.alleErledigt(halb))
pruefe("vier Felder fehlen",
       Einrichtung.fehlendeBetriebsfelder(
           ["betrieb_name": "Salon Nina", "anschrift": "Musterweg 3",
            "finanzamt": "Stuttgart"]).count == 4)

print("— Randfälle —")
pruefe("Leerzeichen sind kein Inhalt",
       !Einrichtung.gefuellt(["betrieb_name": "   "], "betrieb_name"))
pruefe("ein leerer Name zählt nicht",
       !Einrichtung.gefuellt(["betrieb_name": ""], "betrieb_name"))
pruefe("USt-IdNr. reicht statt Steuernummer",
       Einrichtung.steuernummerDa(["ust_id": "DE123456789"]))
pruefe("ohne beides fehlt sie", !Einrichtung.steuernummerDa(["steuernummer": " "]))
pruefe("„Nein“ bei der Umsatzsteuer ist eine Antwort, kein leeres Feld",
       Einrichtung.gefuellt(["kleinunternehmer": "Nein"], "kleinunternehmer"))
pruefe("abgelaufener Zugang zählt nicht als verbunden",
       stand(Einrichtung.schritte(kontoVerbunden: false, angaben: alles,
                                  ersterBeleg: true, kassenbuchBegonnen: true),
             .konto) == .offen)
pruefe("und dann ist auch nicht alles erledigt",
       !Einrichtung.alleErledigt(
           Einrichtung.schritte(kontoVerbunden: false, angaben: alles,
                                ersterBeleg: true, kassenbuchBegonnen: true)))

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
