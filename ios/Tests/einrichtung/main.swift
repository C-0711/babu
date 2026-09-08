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

// ── Wann die Karte erscheint und wann nicht ────────────────────────────────
//
// BEWUSST GEÄNDERT am 08.09.2026. Bis dahin blieb „Dein Anfang" auf der
// Startseite stehen, bis alle fünf Zeilen abgehakt waren — also auch wegen
// einer fehlenden Steuernummer oder eines nicht begonnenen Kassenbuchs.
// Genau das war falsch herum: Betriebsangaben, Steuernummer und Kassenbuch
// wachsen aus den Unterlagen nach, sie sind keine Hausaufgabe. Die Karte
// hilft nur beim Allerersten — verbinden und einmal auslösen — und geht
// danach. Die Prüfungen oben auf `schritte` bleiben unverändert gültig: der
// volle Stand wird weiter berechnet, er steht nur nicht mehr auf der
// Startseite, sondern im Profil.

print("— Der Anfang: zwei Zeilen, mehr nicht —")
let anfang = Einrichtung.anfangsschritte(kontoVerbunden: false, ersterBeleg: false)
pruefe("genau zwei Zeilen", anfang.count == 2)
pruefe("Konto zuerst, dann der erste Beleg",
       anfang.map(\.ziel) == [.konto, .ersterBeleg])
pruefe("kein Kassenbuch", !anfang.contains { $0.ziel == .kassenbuch })
pruefe("keine Betriebsangaben", !anfang.contains { $0.ziel == .betrieb })
pruefe("keine Steuernummer", !anfang.contains { $0.ziel == .steuernummer })
pruefe("nichts steht auf „—“ — beide Zeilen weiß die App aus sich selbst",
       anfang.allSatisfy { $0.stand != .unbekannt })

print("— Wann die Karte geht —")
pruefe("nichts da: sie bleibt",
       !Einrichtung.anfangGeschafft(kontoVerbunden: false, ersterBeleg: false))
pruefe("nur verbunden: sie bleibt",
       !Einrichtung.anfangGeschafft(kontoVerbunden: true, ersterBeleg: false))
pruefe("nur ein Beleg, nicht verbunden: sie bleibt",
       !Einrichtung.anfangGeschafft(kontoVerbunden: false, ersterBeleg: true))
pruefe("verbunden und erster Beleg: sie geht",
       Einrichtung.anfangGeschafft(kontoVerbunden: true, ersterBeleg: true))
pruefe("und zwar OHNE Steuernummer, Betriebsangaben oder Kassenbuch",
       Einrichtung.anfangGeschafft(kontoVerbunden: true, ersterBeleg: true)
       && !Einrichtung.alleErledigt(
           Einrichtung.schritte(kontoVerbunden: true, angaben: [:],
                                ersterBeleg: true, kassenbuchBegonnen: false)))

print("— Das Profil zeigt, was da ist —")
let teilweise = ["betrieb_name": "Salon Nina", "finanzamt": "Stuttgart",
                 "ust_id": "DE123456789"]
let da = Einrichtung.bekannteFelder(teilweise)
pruefe("drei Angaben stehen fest", da.count == 3)
pruefe("in der Reihenfolge des Profils",
       da.map(\.feld.schluessel) == ["betrieb_name", "finanzamt", "steuernummer"])
pruefe("die USt-IdNr. steht unter „Steuernummer“",
       da.last?.wert == "DE123456789")
pruefe("leere Angaben stehen nicht da",
       Einrichtung.bekannteFelder(["telefon": "  "]).isEmpty)
pruefe("die sieben Formularfelder sind weiter sieben",
       Einrichtung.betriebsfelder.count == 7)
pruefe("Bankverbindung und Steuernummer stehen im Profil, nicht im Formular",
       Einrichtung.profilfelder.count == 9
       && Einrichtung.profilfelder.filter { !$0.imFormular }
              .map(\.schluessel) == ["steuernummer", "iban"])

print("— Was als Nächstes dazukäme —")
let offen = Einrichtung.naechstes(teilweise)
pruefe("jede Unterlage steht nur einmal da",
       Set(offen.map(\.quelle)).count == offen.count)
pruefe("ein Kontoauszug bringt die Bankverbindung",
       offen.first { $0.quelle == .kontoauszug }?.satz
       == "Fotografier einen Kontoauszug — dann kennt babu auch deine "
        + "Bankverbindung.")
// Hier steht die USt-IdNr. schon im Profil, also gilt die Steuernummer als
// bekannt und wird nicht noch einmal erbeten — der Brief bringt nur noch eins.
pruefe("der Brief vom Amt nennt nur, was wirklich noch fehlt",
       offen.first { $0.quelle == .amt }?.satz
       == "Fotografier einen Brief vom Finanzamt — dann kennt babu auch "
        + "deine Umsatzsteuer-Regelung.")
pruefe("fehlt beides, nennt derselbe Brief beides in einem Satz",
       Einrichtung.naechstes(["betrieb_name": "Salon Nina",
                              "finanzamt": "Stuttgart"])
           .first { $0.quelle == .amt }?.satz
       == "Fotografier einen Brief vom Finanzamt — dann kennt babu auch "
        + "deine Umsatzsteuer-Regelung und deine Steuernummer.")
pruefe("das Finanzamt steht schon fest und wird nicht noch einmal erbeten",
       !(offen.first { $0.quelle == .amt }?.satz.contains("dein Finanzamt")
         ?? true))
// Anschrift, Telefon und E-Mail stehen auf KEINER Unterlage über den Salon:
// auf einem Bescheid steht die Anschrift des Amts, im Mietvertrag die des
// Vermieters. `salonpruefung.ERLAUBT_JE_ART` erntet sie deshalb nirgends —
// die App darf kein Foto versprechen, aus dem nie etwas käme.
pruefe("für Anschrift, Telefon und E-Mail gibt es kein Foto",
       offen.first { $0.quelle == .nurSelbst }?.satz
       == "Deine Anschrift, deine Telefonnummer und deine E-Mail-Adresse "
        + "stehen auf keiner Unterlage über deinen Salon — das trägst du "
        + "selbst ein.")
pruefe("ist alles da, kommt nichts mehr",
       Einrichtung.naechstes(alles.merging(["iban": "DE02120300000000202051"]) {
           a, _ in a }).isEmpty)

print("— Aufzählungen lassen sich vorlesen —")
pruefe("eins", Lernquelle.und(["A"]) == "A")
pruefe("zwei", Lernquelle.und(["A", "B"]) == "A und B")
pruefe("drei", Lernquelle.und(["A", "B", "C"]) == "A, B und C")

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
