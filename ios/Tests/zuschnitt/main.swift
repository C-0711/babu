import Foundation

// Der Zuschnitt: was steht im schmalen Bau, was nur im großen?
//
// Dieselbe Quelle wird zweimal übersetzt — einmal ohne, einmal mit BABU_PRO.
// Beide Läufe prüfen dieselbe Datei; welcher gerade läuft, sagt
// `Ausbaustufe.voll`.
//
// Warum das hier steht: der Unterschied zwischen den beiden Apps ist eine
// Liste, und Listen wandern. Ohne diesen Harness rutschte beim nächsten Umbau
// still ein Kassenbuch zurück in die schmale App — und niemand merkte es,
// weil beide Bauten weiter übersetzen.

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

// Was die schmale App kann: fotografieren, lesen und erklären, das Bild des
// Betriebs bauen, den Stapel ans Steuerbüro geben. Sonst nichts.
let schmaleReiter: [Reiter] = [.erfassen, .dokumente, .fragen]
let schmalesMenue: [Kontomenuepunkt] = [
    .aufraeumen, .monatsabschluss, .export,   // das DATEV-Büchlein
    .betrieb, .vertraege, .kontoauszug,       // Profil, Papiere, Konto
    .wasBabuKann, .meldungen, .einstellungen, // das Konto selbst
]
// Der volle heutige Umfang — hier darf nie etwas verschwinden.
let volleReiter: [Reiter] = [.erfassen, .dokumente, .termine, .kasse, .fragen]
let vollesMenue: [Kontomenuepunkt] = [
    .aufraeumen, .rechnungen, .vorlagen, .briefkopf, .monatsabschluss, .export,
    .betrieb, .kundinnen, .preise, .kartenzahlung, .team, .vertraege,
    .kontoauszug, .marketing,
    .wasBabuKann, .meldungen, .einstellungen,
]

print(Ausbaustufe.voll ? "— Der große Bau (babu Pro) —" : "— Der schmale Bau (babu) —")
pruefe("die App nennt sich richtig",
       Ausbaustufe.name == (Ausbaustufe.voll ? "babu Pro" : "babu"))

if Ausbaustufe.voll {
    print("— Reiter —")
    pruefe("alle fünf Reiter, in dieser Reihenfolge",
           Ausbaustufe.reiter == volleReiter)
    print("— Konto-Menü —")
    pruefe("alle siebzehn Zeilen, in dieser Reihenfolge",
           Ausbaustufe.kontomenue == vollesMenue)
    pruefe("kein Punkt der Aufzählung fehlt",
           Set(Ausbaustufe.kontomenue) == Set(Kontomenuepunkt.allCases))
    print("— Einrichtung —")
    pruefe("fünf Schritte, das Kassenbuch dabei",
           Einrichtung.sichtbareSchritte(kontoVerbunden: true, angaben: [:],
                                         ersterBeleg: false,
                                         kassenbuchBegonnen: false).count == 5)
} else {
    print("— Reiter —")
    pruefe("genau drei: Erfassen, Dokumente, Fragen",
           Ausbaustufe.reiter == schmaleReiter)
    pruefe("kein Termine-Reiter", !Ausbaustufe.erreichbar(Reiter.termine))
    pruefe("kein Kassenbuch-Reiter", !Ausbaustufe.erreichbar(Reiter.kasse))

    print("— Konto-Menü —")
    pruefe("genau die neun Zeilen des schmalen Baus",
           Ausbaustufe.kontomenue == schmalesMenue)
    // Verträge fehlen hier bewusst: sie BLEIBEN im schmalen Bau
    // (Entscheidung 08.09.2026) und stehen deshalb in `schmalesMenue`.
    for weg in [Kontomenuepunkt.rechnungen, .vorlagen, .briefkopf, .kundinnen,
                .preise, .kartenzahlung, .team, .marketing] {
        pruefe("„\(weg.titel)“ steht nicht im Menü",
               !Ausbaustufe.erreichbar(weg))
    }
    for bleibt in schmalesMenue {
        pruefe("„\(bleibt.titel)“ bleibt", Ausbaustufe.erreichbar(bleibt))
    }

    print("— Einrichtung —")
    let schritte = Einrichtung.sichtbareSchritte(kontoVerbunden: true, angaben: [:],
                                                 ersterBeleg: false,
                                                 kassenbuchBegonnen: false)
    pruefe("vier Schritte — das Kassenbuch führte ins Leere",
           schritte.count == 4)
    pruefe("und es steht wirklich nicht mehr drin",
           !schritte.contains { $0.ziel == .kassenbuch })
    pruefe("ohne Kassenbuch kann die Karte trotzdem fertig werden",
           Einrichtung.alleErledigt(
               Einrichtung.sichtbareSchritte(
                   kontoVerbunden: true,
                   angaben: ["betrieb_name": "Salon Nina",
                             "anschrift": "Musterweg 3, 70000 Stuttgart",
                             "rechtsform": "Einzelunternehmen",
                             "finanzamt": "Stuttgart", "telefon": "0711 1234",
                             "email": "nina@0711.io", "kleinunternehmer": "Nein",
                             "steuernummer": "12/345/67890"],
                   ersterBeleg: true, kassenbuchBegonnen: false)))
}

print("— Beide Bauten —")
// Jede Zeile gehört in genau einen Abschnitt, und kein Abschnitt bleibt leer —
// eine Überschrift ohne Zeilen darunter sieht aus wie ein Ladefehler.
for abschnitt in [Kontomenuepunkt.Abschnitt.buchhaltung, .salon, .konto] {
    let drin = Ausbaustufe.kontomenue.filter { $0.abschnitt == abschnitt }
    pruefe("im Abschnitt „\(abschnitt.titel ?? "ohne Überschrift")“ steht etwas",
           !drin.isEmpty)
}
pruefe("die Reiter stehen in der Reihenfolge der Aufzählung",
       Ausbaustufe.reiter == Reiter.allCases.filter(Ausbaustufe.reiter.contains))
pruefe("jede Zeile hat einen Titel",
       Ausbaustufe.kontomenue.allSatisfy { !$0.titel.isEmpty && !$0.symbol.isEmpty })
pruefe("jeder Reiter hat einen Titel",
       Ausbaustufe.reiter.allSatisfy { !$0.titel.isEmpty && !$0.symbol.isEmpty })

// Sprachregel: kein Technik-Vokabular in sichtbarem Text.
let verboten = ["Server", "Token", "Hash", "Commit", "Queue", "Modell",
                "KI", "OCR", "Lesung", "Target", "Build", "Flag"]
let sichtbar = Ausbaustufe.reiter.map(\.titel)
    + Ausbaustufe.kontomenue.map(\.titel)
    + [Ausbaustufe.name]
pruefe("kein Technik-Wort in dem, was sie liest",
       !sichtbar.contains { text in
           verboten.contains { text.range(of: $0, options: .caseInsensitive) != nil }
       })

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
