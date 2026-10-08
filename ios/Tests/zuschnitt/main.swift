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
    .auslagen,
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
    // BEWUSST GEÄNDERT am 08.10.2026: „Empfehlen" steht nur bei einer
    // Ambassadorin im Menü, und nur, wenn unten kein Platz für den Reiter
    // ist — im Grundmenü fehlt es mit Absicht.
    pruefe("kein Punkt der Aufzählung fehlt (außer Empfehlen, nur für Ambassadorinnen)",
           Set(Ausbaustufe.kontomenue)
           == Set(Kontomenuepunkt.allCases.filter { !$0.nurAmbassadorin }))
    print("— Einrichtung —")
    // BEWUSST GEÄNDERT am 08.09.2026. Hier stand: „fünf Schritte, das
    // Kassenbuch dabei" — geprüft an `sichtbareSchritte`, das die
    // Kassenbuch-Zeile im schmalen Bau wegfilterte, damit dort kein toter
    // Knopf stand. Die Karte zeigt jetzt in BEIDEN Bauten nur noch den
    // Anfang: verbinden und einmal auslösen. Damit ist der Filter gegen-
    // standslos — die Zeile gibt es nirgends mehr. Der volle Stand aller
    // fünf Schritte wird weiter berechnet (`schritte`, geprüft im
    // Einrichtungs-Harness), er steht nur nicht mehr auf der Startseite.
    pruefe("auch im großen Bau nur der Anfang",
           Einrichtung.anfangsschritte(kontoVerbunden: true,
                                       ersterBeleg: false).count == 2)
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
    // BEWUSST GEÄNDERT am 08.09.2026, siehe die Begründung im Pro-Zweig.
    // Die Sorge, die hier stand, bleibt geprüft — nur an der richtigen
    // Stelle: im schmalen Bau darf keine Zeile der Karte auf ein Ziel
    // zeigen, das es hier gar nicht gibt.
    let anfang = Einrichtung.anfangsschritte(kontoVerbunden: true,
                                             ersterBeleg: false)
    pruefe("zwei Schritte, in beiden Bauten dieselben", anfang.count == 2)
    pruefe("kein Kassenbuch — es führte hier ins Leere",
           !anfang.contains { $0.ziel == .kassenbuch })
    pruefe("jede Zeile der Karte führt an eine Stelle, die es hier gibt",
           anfang.allSatisfy { schritt in
               switch schritt.ziel {
               case .kassenbuch: return Ausbaustufe.erreichbar(Reiter.kasse)
               case .konto, .betrieb, .steuernummer, .ersterBeleg: return true
               }
           })
    pruefe("die Karte kann fertig werden, ohne dass eine Angabe ausgefüllt ist",
           Einrichtung.anfangGeschafft(kontoVerbunden: true, ersterBeleg: true))
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
    + [Ausbaustufe.name, Reiter.empfehlen.titel]
pruefe("kein Technik-Wort in dem, was sie liest",
       !sichtbar.contains { text in
           verboten.contains { text.range(of: $0, options: .caseInsensitive) != nil }
       })

// Mitarbeiterinnen (babu Expenses D1): nur, was sie dürfen.
let nurAuslagen = Ausbaustufe.Rechte(belege: false, kasse: false, auslagen: true)
pruefe("Mitarbeiterin mit Auslagen sieht nur den Reiter Auslagen",
       Ausbaustufe.reiter(fuer: nurAuslagen) == [.auslagen])
let mitBelegen = Ausbaustufe.Rechte(belege: true, kasse: false, auslagen: true)
pruefe("mit darf Belege kommt Erfassen dazu",
       Ausbaustufe.reiter(fuer: mitBelegen) == [.erfassen, .auslagen])
pruefe("das Menü der Mitarbeiterin ist kurz",
       Ausbaustufe.kontomenue(fuer: nurAuslagen) == [.meldungen, .einstellungen])
pruefe("die Inhaberin sieht keinen Reiter Auslagen",
       !Ausbaustufe.reiter(fuer: nil).contains(.auslagen))

// Empfehlen (Ambassadorinnen, 08.10.2026): in BEIDEN Bauten, aber nur, wenn
// der Server das Konto als Ambassadorin kennt — und nie fürs Team.
print("— Empfehlen —")
typealias Amb = Ausbaustufe.Ambassadorin
let alleAmb: [Amb] = [.nein, .mitAblage, .ohneAblage]
// Jede Kombination der drei Rechte einer Mitarbeiterin — und die Inhaberin (nil).
var alleRechte: [Ausbaustufe.Rechte?] = [nil]
for b in [false, true] { for k in [false, true] { for a in [false, true] {
    alleRechte.append(Ausbaustufe.Rechte(belege: b, kasse: k, auslagen: a))
} } }

pruefe("ohne Ambassadorin kein Empfehlen — weder unten noch im Menü",
       !Ausbaustufe.reiter.contains(.empfehlen)
       && !Ausbaustufe.reiter(fuer: nil).contains(.empfehlen)
       && !Ausbaustufe.kontomenue(fuer: nil).contains(.empfehlen))

// Höchstens fünf Reiter, in jedem Bau und für jede Kombination — ein sechster
// landet unter dem „Mehr" von iOS (doppelter Kopf, fremde Liste).
var nieMehrAlsFuenf = true
for r in alleRechte {
    for a in alleAmb where Ausbaustufe.reiter(fuer: r, ambassadorin: a).count > 5 {
        nieMehrAlsFuenf = false
        print("    zu viele: \(String(describing: r)) \(a) → \(Ausbaustufe.reiter(fuer: r, ambassadorin: a))")
    }
}
pruefe("höchstens fünf Reiter je Bau und Rechte-Kombination", nieMehrAlsFuenf)

// Wer Ambassadorin ist, findet Empfehlen genau einmal: unten ODER im Menü.
for a in [Amb.mitAblage, .ohneAblage] {
    let unten = Ausbaustufe.reiter(fuer: nil, ambassadorin: a).contains(.empfehlen)
    let oben = Ausbaustufe.kontomenue(fuer: nil, ambassadorin: a).contains(.empfehlen)
    pruefe("Ambassadorin (\(a)): Empfehlen genau an einer Stelle", unten != oben)
}

let mitSalon = Ausbaustufe.reiter(fuer: nil, ambassadorin: .mitAblage)
if Ausbaustufe.voll {
    pruefe("babu Pro mit Salon: die fünf Reiter bleiben genau, wie sie sind",
           mitSalon == Ausbaustufe.reiter)
    pruefe("… und Empfehlen steht im Menü, im Abschnitt des Kontos",
           Ausbaustufe.kontomenue(fuer: nil, ambassadorin: .mitAblage)
               .filter { $0.abschnitt == .konto }.first == .empfehlen)
} else {
    pruefe("babu mit Salon: alles wie immer, Empfehlen kommt hinten dazu",
           mitSalon == Ausbaustufe.reiter + [.empfehlen])
    pruefe("… und steht dann nicht noch einmal im Menü",
           !Ausbaustufe.kontomenue(fuer: nil, ambassadorin: .mitAblage).contains(.empfehlen))
}
// Ohne eigene Ablage führt jeder andere Reiter ins Leere (08.10.2026):
// nur „Empfehlen", als ganze Seite ohne Leiste; im Menü nur das Konto.
pruefe("ohne Ablage: nur Empfehlen",
       Ausbaustufe.reiter(fuer: nil, ambassadorin: .ohneAblage) == [.empfehlen])
pruefe("… als ganze Seite, ohne Leiste",
       Ausbaustufe.ganzeSeite(fuer: nil, ambassadorin: .ohneAblage) == .empfehlen)
pruefe("… im Menü nur Meldungen und Einstellungen (Konto, Abmelden)",
       Ausbaustufe.kontomenue(fuer: nil, ambassadorin: .ohneAblage) == [.meldungen, .einstellungen])
pruefe("mit Salon: die Leiste wie immer",
       Ausbaustufe.ganzeSeite(fuer: nil, ambassadorin: .mitAblage) == nil)
pruefe("wer keine Ambassadorin ist: die Leiste wie immer",
       Ausbaustufe.ganzeSeite(fuer: nil, ambassadorin: .nein) == nil)
var teamNie = true
for r in alleRechte.compactMap({ $0 }) {
    for a in alleAmb {
        if Ausbaustufe.reiter(fuer: r, ambassadorin: a).contains(.empfehlen)
            || Ausbaustufe.kontomenue(fuer: r, ambassadorin: a).contains(.empfehlen)
            || Ausbaustufe.ganzeSeite(fuer: r, ambassadorin: a) != nil {
            teamNie = false
        }
    }
}
pruefe("eine Mitarbeiterin sieht Empfehlen nie, weder unten noch im Menü", teamNie)
pruefe("Empfehlen gibt es in beiden Bauten", !Reiter.empfehlen.nurVoll
       && !Kontomenuepunkt.empfehlen.nurVoll)
pruefe("Reiter und Menüzeile heißen gleich und sehen gleich aus",
       Reiter.empfehlen.titel == Kontomenuepunkt.empfehlen.titel
       && Reiter.empfehlen.symbol == Kontomenuepunkt.empfehlen.symbol)

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
