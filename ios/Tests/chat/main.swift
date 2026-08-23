import Foundation

// Die Texte des Fragen-Bereichs: der Verlauf, der mit der Frage zum Server
// reist (BABU-25 — der Server schreibt nichts mehr mit), und die Antwort auf
// einen fotografierten Brief vom Amt (BABU-40). Beides liest Nina direkt,
// beides ist reine Rechnung — also hier prüfbar.

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

print("— Verlauf für den Server —")
let gespraech = [
    ChatNachricht(vonMir: true, text: "Was habe ich beim Großhandel gekauft?"),
    ChatNachricht(vonMir: false, text: "Farbe und Folie für 141,00 €."),
    ChatNachricht(vonMir: true, text: "Und wie viel war das nochmal?"),
]
let verlauf = Chattexte.verlaufFuerServer(gespraech)
pruefe("alle drei Züge reisen mit", verlauf.count == 3)
pruefe("die Rolle stimmt", verlauf[0]["rolle"] == "user"
       && verlauf[1]["rolle"] == "assistant")
pruefe("der Text kommt unverändert an",
       verlauf[1]["text"] == "Farbe und Folie für 141,00 €.")

let mitLeerer = gespraech + [ChatNachricht(vonMir: false, text: "")]
pruefe("die noch leere Antwortblase bleibt draußen",
       Chattexte.verlaufFuerServer(mitLeerer).count == 3)
pruefe("Leerzeichen zählen nicht als Text",
       Chattexte.verlaufFuerServer([ChatNachricht(vonMir: false, text: "   ")]).isEmpty)

let lang = (0..<40).map { ChatNachricht(vonMir: $0 % 2 == 0, text: "Zug \($0)") }
let gekappt = Chattexte.verlaufFuerServer(lang)
pruefe("ein langer Verlauf wird gekappt", gekappt.count == Chattexte.zuege * 2)
pruefe("gekappt wird vorn, das Neueste bleibt",
       gekappt.last?["text"] == "Zug 39")

print("— Datum —")
pruefe("ISO wird deutsch", Chattexte.datumDeutsch("2026-09-15") == "15.09.2026")
pruefe("mit Uhrzeit geht auch",
       Chattexte.datumDeutsch("2026-09-15T10:00:00Z") == "15.09.2026")
pruefe("Unsinn bleibt Unsinn", Chattexte.datumDeutsch("bald") == nil)
pruefe("halbes Datum bleibt Unsinn", Chattexte.datumDeutsch("2026-09") == nil)

print("— Brief vom Amt —")
let voll = Chattexte.briefAntwort(
    einfach: "Das Finanzamt will deine Umsatzsteuer-Voranmeldung für August.",
    wasTun: "Schick sie über Elster ab.",
    bisWann: "2026-09-10",
    hinweis: nil)
pruefe("worum es geht steht oben", voll.hasPrefix("Das Finanzamt will"))
pruefe("was zu tun ist steht drin", voll.contains("Was du tun musst: Schick sie"))
pruefe("die Frist steht deutsch drin", voll.contains("bis: 10.09.2026"))
pruefe("kein ISO-Datum mehr", !voll.contains("2026-09-10"))
pruefe("die Belegbox wird erwähnt", voll.contains("Belegbox"))

let ohneFrist = Chattexte.briefAntwort(
    einfach: "Du hast eine neue Steuernummer.",
    wasTun: nil, bisWann: nil, hinweis: nil)
pruefe("ohne Frist wird das gesagt statt verschwiegen",
       ohneFrist.contains("Eine Frist steht in dem Brief nicht"))
pruefe("ohne Aufgabe steht keine leere Zeile da",
       !ohneFrist.contains("Was du tun musst"))

let mitGrenze = Chattexte.briefAntwort(
    einfach: "Das Finanzamt hat deinen Gewinn geschätzt.",
    wasTun: "Einspruch einlegen, wenn die Zahl nicht stimmt.",
    bisWann: "2026-09-15",
    hinweis: "Hier hört meine Auskunft auf und Beratung fängt an.")
pruefe("die Grenze zur Beratung steht am Ende",
       mitGrenze.hasSuffix("Hier hört meine Auskunft auf und Beratung fängt an."))

let unklareFrist = Chattexte.briefAntwort(
    einfach: "Kurz erklärt.", wasTun: nil, bisWann: "einen Monat nach Zugang",
    hinweis: nil)
pruefe("eine Frist ohne Datum bleibt im Wortlaut",
       unklareFrist.contains("bis: einen Monat nach Zugang"))

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
