import Foundation

// Kassenbuch-Harness: Unveränderbarkeit und Korrekturspur.
//
// Nina, 22.08.2026: „Im Kassenbuch darf nichts einfach verschwinden."
// Geprüft wird genau das — und die Grenze davor: solange der Tag ein Entwurf
// ist, darf sie frei tippen, ohne für jede Zahl einen Aufsatz zu schreiben.

var fehler = 0
func pruefe(_ name: String, _ bedingung: Bool) {
    if bedingung {
        print("  ok   \(name)")
    } else {
        print("  FEHL \(name)")
        fehler += 1
    }
}

func tag(_ datum: String = "2026-08-20") -> Kassenbericht {
    var b = Kassenbericht(datum: datum)
    b.bestandVortag = 150.00
    b.einnahmenBar = 420.00
    b.ecZahlungen = 380.00
    b.gezaehltSchluss = 570.00
    return b
}

print("— Entwurf: frei änderbar —")
do {
    let alt = tag()                        // uebermittelt == nil
    var neu = alt
    neu.einnahmenBar = 430.00
    let erg = try kassenberichtKorrigieren(alt: alt, neu: neu, grund: "")
    pruefe("Entwurf braucht keinen Grund", erg.einnahmenBar == 430.00)
    pruefe("Entwurf legt keine Korrekturspur an", (erg.korrekturen ?? []).isEmpty)
    pruefe("Entwurf ist nicht festgeschrieben", !alt.festgeschrieben)
} catch {
    pruefe("Entwurf ohne Grund wirft nicht", false)
}

print("— Festgeschrieben: nur mit Grund —")
do {
    var alt = tag()
    alt.uebermittelt = Date()
    pruefe("übermittelt heißt festgeschrieben", alt.festgeschrieben)

    var neu = alt
    neu.einnahmenBar = 430.00
    do {
        _ = try kassenberichtKorrigieren(alt: alt, neu: neu, grund: "")
        pruefe("ohne Grund wird abgelehnt", false)
    } catch Kassenfehler.grundFehlt {
        pruefe("ohne Grund wird abgelehnt", true)
    } catch {
        pruefe("ohne Grund wird abgelehnt (falscher Fehler)", false)
    }

    do {
        _ = try kassenberichtKorrigieren(alt: alt, neu: neu, grund: "  x ")
        pruefe("ein Zeichen ist kein Grund", false)
    } catch Kassenfehler.grundFehlt {
        pruefe("ein Zeichen ist kein Grund", true)
    } catch {
        pruefe("ein Zeichen ist kein Grund (falscher Fehler)", false)
    }
}

print("— Die alte Fassung bleibt lesbar —")
do {
    var alt = tag()
    alt.uebermittelt = Date()
    var neu = alt
    neu.einnahmenBar = 430.00
    neu.gezaehltSchluss = 580.00

    let erg = try kassenberichtKorrigieren(
        alt: alt, neu: neu, grund: "Zwei Bons waren nicht eingetippt")
    let spur = erg.korrekturen ?? []
    pruefe("eine Korrektur ist verzeichnet", spur.count == 1)
    pruefe("der Grund steht dran", spur.first?.grund == "Zwei Bons waren nicht eingetippt")
    pruefe("beide geänderten Felder stehen drin", spur.first?.aenderungen.count == 2)

    let bar = spur.first?.aenderungen.first { $0.feld == "Bareinnahmen" }
    pruefe("der alte Wert ist noch feststellbar", bar?.vorher == "420.00")
    pruefe("der neue Wert steht daneben", bar?.nachher == "430.00")
    pruefe("das Blatt geht neu raus", erg.uebermittelt == nil)
    pruefe("der Tag bleibt derselbe Vorgang", erg.id == alt.id)
}

print("— Mehrere Korrekturen sammeln sich, sie ersetzen sich nicht —")
do {
    var alt = tag()
    alt.uebermittelt = Date()
    var eins = alt
    eins.einnahmenBar = 430.00
    var zwei = try kassenberichtKorrigieren(alt: alt, neu: eins, grund: "erste Korrektur")
    zwei.uebermittelt = Date()          // wieder übermittelt
    var drei = zwei
    drei.sonstigeAusgaben = 12.50
    let erg = try kassenberichtKorrigieren(alt: zwei, neu: drei, grund: "Trinkgeld nachgetragen")
    pruefe("zwei Korrekturen stehen nebeneinander", (erg.korrekturen ?? []).count == 2)
    pruefe("die erste ist noch da",
           erg.korrekturen?.first?.grund == "erste Korrektur")
}

print("— Ohne Änderung gibt es nichts zu begründen —")
do {
    var alt = tag()
    alt.uebermittelt = Date()
    do {
        _ = try kassenberichtKorrigieren(alt: alt, neu: alt, grund: "irgendwas")
        pruefe("unveränderte Korrektur wird abgelehnt", false)
    } catch Kassenfehler.keineAenderung {
        pruefe("unveränderte Korrektur wird abgelehnt", true)
    } catch {
        pruefe("unveränderte Korrektur wird abgelehnt (falscher Fehler)", false)
    }
}

print("— Was die Kasse rechnet, bleibt richtig —")
do {
    var b = tag()
    b.einzahlungBank = 300.00       // Geld zur Bank: kein Umsatz, nur Bestand
    b.gutscheineEingeloest = 50.00  // kein Zufluss, kein neuer Umsatz
    pruefe("Einzahlung mindert den Bestand",
           abs(b.rechnerischerBestand - 270.00) < 0.001)
    pruefe("Gutschein zählt nicht zum Tagesumsatz",
           abs(b.tagesumsatz - 800.00) < 0.001)
    pruefe("Gutschein ändert den Bestand nicht",
           abs(b.rechnerischerBestand - 270.00) < 0.001)
}

print(fehler == 0 ? "\nKasse: alles grün.\n" : "\nKasse: \(fehler) Fehler.\n")
exit(fehler == 0 ? 0 : 1)
