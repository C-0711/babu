// Kassenbuch: die Rechnung hinter dem Tagesblatt.
//
// Hier steckt das, was Nina nicht sehen soll: welcher Betrag Umsatz ist,
// welcher nur durchläuft, und was den Bargeldbestand bewegt. Die Ansicht
// stellt eine Frage — entscheiden tut dieses Modell. Also wird es hier
// geprüft und nicht am Bildschirm.
//
// Alles bleibt Tagessumme. Kein einzelner Zahlvorgang, keine Zahlung —
// sonst wäre babu ein Aufzeichnungssystem mit Kassenfunktion (§ 146a AO).
import Foundation

var fehler = 0

func pruefe(_ was: String, _ bedingung: Bool) {
    print(bedingung ? "✓ \(was)" : "✗ \(was)")
    if !bedingung { fehler += 1 }
}

func gleich(_ was: String, _ ist: Double, _ soll: Double) {
    pruefe("\(was) (\(ist) == \(soll))", abs(ist - soll) < 0.005)
}

// ————— BABU-34: der Gutschein zählt einmal, nicht zweimal —————
//
// Verkauf: Geld kommt in die Schublade, der Erlös ist realisiert
// (Einzweck-Gutschein — der Salon kennt den Steuersatz schon).
// Einlösung: kein Geldzufluss, der Erlös war schon.

do {
    var b = Kassenbericht(datum: "2026-08-20")
    b.bestandVortag = 200
    b.einnahmenBar = 300
    b.gutscheinVerkauf = 100
    b.gezaehltSchluss = 600

    gleich("verkaufter Gutschein liegt in der Schublade", b.rechnerischerBestand, 600)
    gleich("verkaufter Gutschein ist Umsatz", b.tagesumsatz, 400)
    pruefe("und dann stimmt die Kasse", b.kasseStimmt)
}

do {
    var b = Kassenbericht(datum: "2026-08-21")
    b.bestandVortag = 200
    b.einnahmenBar = 300
    b.gutscheineEingeloest = 100
    b.gezaehltSchluss = 500

    gleich("eingelöster Gutschein bringt kein Geld in die Kasse",
           b.rechnerischerBestand, 500)
    gleich("eingelöster Gutschein ist kein neuer Umsatz", b.tagesumsatz, 300)
    pruefe("die Kasse stimmt trotzdem", b.kasseStimmt)
}

do {
    // 100 € Behandlung, 60 € Gutschein, 40 € bar dazugelegt.
    // Zahlung ist nur die Differenz.
    var b = Kassenbericht(datum: "2026-08-21")
    b.einnahmenBar = 40
    b.gutscheineEingeloest = 60
    b.gezaehltSchluss = 40

    gleich("Zuzahlung: nur die Differenz ist Zahlung", b.tagesumsatz, 40)
    pruefe("Zuzahlung: die Kasse stimmt", b.kasseStimmt)
}

do {
    // Der doppelte Ansatz, den BABU-34 verhindern soll: derselbe Betrag
    // einmal beim Verkauf, einmal beim Einlösen.
    var b = Kassenbericht(datum: "2026-08-22")
    b.gutscheinVerkauf = 50
    b.gutscheineEingeloest = 50
    gleich("Verkauf und Einlösung am selben Tag zählen einmal", b.tagesumsatz, 50)
}

// ————— BABU-35: Trinkgeld per Karte —————
//
// Es kommt mit dem Kartenumsatz aufs Geschäftskonto, gehört dem Salon
// aber nicht. Was ans Team geht, läuft nur durch; was Nina selbst
// bekommt, ist Betriebseinnahme. Unterscheiden muss das die App.

do {
    var b = Kassenbericht(datum: "2026-08-20")
    b.bestandVortag = 100
    b.ecZahlungen = 500
    b.trinkgeldKarte = 30
    b.gezaehltSchluss = 100

    gleich("Trinkgeld per Karte ist kein Umsatz", b.tagesumsatz, 500)
    gleich("Trinkgeld per Karte liegt nicht in der Schublade",
           b.rechnerischerBestand, 100)
    gleich("was auf dem Kartenleser steht", b.kartenterminalSumme, 530)
    pruefe("Kasse stimmt, obwohl Trinkgeld kam", b.kasseStimmt)
}

do {
    var b = Kassenbericht(datum: "2026-08-20")
    b.bestandVortag = 100
    b.ecZahlungen = 500
    b.trinkgeldKarte = 30
    b.trinkgeldTeamEC = 20          // bar aus der Schublade ans Team
    b.gezaehltSchluss = 80

    gleich("ausgezahltes Team-Trinkgeld mindert den Bestand",
           b.rechnerischerBestand, 80)
    gleich("was Nina selbst behält, ist Betriebseinnahme",
           b.trinkgeldInhaberin, 10)
    gleich("Team-Trinkgeld bleibt durchlaufender Posten",
           b.trinkgeldTeam, 20)
    gleich("Trinkgeld verändert den Umsatz nicht", b.tagesumsatz, 500)
}

do {
    // Alles ans Team: für Nina bleibt nichts, also keine Betriebseinnahme.
    var b = Kassenbericht(datum: "2026-08-20")
    b.trinkgeldKarte = 25
    b.trinkgeldTeamEC = 25
    gleich("alles weitergegeben → nichts zu versteuern", b.trinkgeldInhaberin, 0)
}

do {
    // Mehr ausgezahlt als heute reinkam (gestriges Trinkgeld nachgereicht):
    // Ninas Anteil wird davon nicht negativ.
    var b = Kassenbericht(datum: "2026-08-20")
    b.trinkgeldKarte = 10
    b.trinkgeldTeamEC = 40
    gleich("nachgereichtes Trinkgeld macht Ninas Anteil nicht negativ",
           b.trinkgeldInhaberin, 0)
}

do {
    // Die Spur: wer, wieviel. Ohne sie ist bei einer Kassenprüfung nicht
    // erklärbar, warum Geld die Schublade verlassen hat.
    var b = Kassenbericht(datum: "2026-08-20")
    b.trinkgeldTeamEC = 30
    b.trinkgeldVerteilt = [Trinkgeldanteil(name: "Jana", betrag: 18),
                           Trinkgeldanteil(name: "Merve", betrag: 12)]
    gleich("die Anteile summieren sich", b.summeTrinkgeldVerteilt, 30)
    pruefe("die Spur ist vollständig", b.trinkgeldSpurVollstaendig)

    b.trinkgeldVerteilt = [Trinkgeldanteil(name: "Jana", betrag: 18)]
    pruefe("fehlt ein Anteil, ist die Spur unvollständig",
           !b.trinkgeldSpurVollstaendig)

    b.trinkgeldTeamEC = 0
    b.trinkgeldVerteilt = []
    pruefe("ohne Auszahlung ist nichts zu belegen", b.trinkgeldSpurVollstaendig)
}

// ————— BABU-36: Entnahmen brauchen einen Grund —————
//
// Drei völlig verschiedene Dinge, die bisher alle „Entnahme" hießen.

do {
    pruefe("es gibt genau drei Gründe", Entnahmezweck.allCases.count == 3)

    var b = Kassenbericht(datum: "2026-08-20")
    b.bestandVortag = 500
    for zweck in Entnahmezweck.allCases {
        b[keyPath: zweck.pfad] = 50
    }
    gleich("jeder Grund hat sein eigenes Feld", b.summeEntnahmen, 150)
    gleich("und jeder mindert den Bestand", b.rechnerischerBestand, 350)
}

do {
    var b = Kassenbericht(datum: "2026-08-20")
    b.sonstigeAusgaben = 20         // Blumen
    b.privatentnahmen = 100         // ins Private
    b.vorschussTeam = 200           // Forderung, wird mit dem Lohn verrechnet
    b.auslagenErstattet = 30        // Nina hat privat gekauft, Salon erstattet

    gleich("Aufwand ist nur, was der Salon verbraucht hat", b.barAufwand, 50)
    pruefe("Privatentnahme ist kein Aufwand", !Entnahmezweck.privat.istAufwand)
    pruefe("Vorschuss ist kein Aufwand", !Entnahmezweck.vorschuss.istAufwand)
    pruefe("erstattete Auslage ist Aufwand", Entnahmezweck.auslage.istAufwand)
}

do {
    // Die Frage muss in Ninas Sprache stehen — kein „Darlehen an
    // Arbeitnehmer", kein „Privatentnahme gem. § 4 Abs. 1 EStG".
    let fachbegriffe = ["Darlehen", "Forderung", "Aufwand", "Entnahme",
                        "Verbindlichkeit", "Betriebseinnahme"]
    let saetze = Entnahmezweck.allCases.flatMap { [$0.knopf, $0.erklaerung] }
    pruefe("kein Fachwort in der Auswahl",
           !saetze.contains { satz in fachbegriffe.contains { satz.contains($0) } })
    pruefe("jeder Grund erklärt sich",
           Entnahmezweck.allCases.allSatisfy { !$0.knopf.isEmpty && !$0.erklaerung.isEmpty })
}

// ————— BABU-50: wie wird das Tagesblatt übermittelt? —————

do {
    var b = Kassenbericht(datum: "2026-08-20")
    pruefe("frisch eingetragen heißt: liegt noch hier",
           Uebermittlung.fuer(b) == .offen)
    pruefe("und das steht auch so da",
           Uebermittlung.fuer(b).satz.contains("Telefon"))

    let wann = Date(timeIntervalSince1970: 1_787_227_200)   // 20.08.2026, 12 Uhr UTC
    b.uebermittelt = wann
    pruefe("abgelegt heißt: mit Zeitpunkt",
           Uebermittlung.fuer(b) == .inBelegbox(wann))
    pruefe("der Satz nennt die Belegbox",
           Uebermittlung.fuer(b).satz.contains("Belegbox"))
    pruefe("der Satz nennt einen Zeitpunkt",
           Uebermittlung.fuer(b).satz.contains("2026"))
    pruefe("und was am Monatsende passiert, steht auch da",
           Uebermittlung.monatsende.contains("Monatsende"))
}

do {
    // Ein Name für die Sache: die App führt das KASSENBUCH. „Kasse" ist
    // die Schublade und bleibt dafür reserviert.
    pruefe("das Buch heißt Kassenbuch", Kassenwort.buch == "Kassenbuch")
    pruefe("die Schublade heißt Kasse", Kassenwort.schublade == "Kasse")
    pruefe("eingetragen wird ins Buch",
           Kassenwort.eintragen.contains(Kassenwort.buch))
    pruefe("gestimmt hat die Schublade",
           Kassenwort.stimmt.contains(Kassenwort.schublade)
           && !Kassenwort.stimmt.contains(Kassenwort.buch))
}

// ————— Ältere Stände dürfen nicht verschwinden —————
//
// `zustand.json` wird mit `try?` gelesen: scheitert das Dekodieren an
// EINEM fehlenden Schlüssel, ist der ganze Zustand weg — Belege
// inbegriffen. Neue Felder müssen deshalb fehlen dürfen.

do {
    let alt = """
    {"id":"3F2504E0-4F89-11D3-9A0C-0305E82C3301","datum":"2026-08-01",
     "bestandVortag":100,"einnahmenBar":250,"privateinlagen":0,
     "barabhebungBank":0,"ecZahlungen":400,"sonstigeAusgaben":0,
     "privatentnahmen":0,"einzahlungBank":0,"gezaehltSchluss":350,
     "erstellt":770000000}
    """.data(using: .utf8)!
    let b = try? JSONDecoder().decode(Kassenbericht.self, from: alt)
    pruefe("ein Tagesblatt von vor der Änderung lädt noch", b != nil)
    gleich("mit seinen alten Zahlen", b?.gezaehltSchluss ?? -1, 350)
    gleich("und Null in den neuen Feldern", b?.gutscheinVerkauf ?? -1, 0)
    pruefe("auch die Trinkgeld-Spur ist dann leer",
           (b?.trinkgeldVerteilt ?? [Trinkgeldanteil(name: "x", betrag: 1)]).isEmpty)
}

do {
    // Und was geschrieben wird, muss auch wieder hereinkommen.
    var b = Kassenbericht(datum: "2026-08-20")
    b.gutscheinVerkauf = 75
    b.trinkgeldKarte = 12.5
    b.vorschussTeam = 200
    b.auslagenErstattet = 8.9
    b.trinkgeldVerteilt = [Trinkgeldanteil(name: "Jana", betrag: 12.5)]
    let roh = try! JSONEncoder().encode(b)
    let zurueck = try! JSONDecoder().decode(Kassenbericht.self, from: roh)
    pruefe("Hin und Zurück ändert nichts", zurueck == b)
}


// ————— GoBD: im Kassenbuch verschwindet nichts —————
//
// Nina, 22.08.2026: „Im Kassenbuch darf nichts einfach verschwinden."
// Ein festgeschriebener Tag wird nur mit Begründung geändert, und die
// alte Fassung bleibt feststellbar (§ 146 Abs. 4 AO).

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

print(fehler == 0 ? "\nAlle Prüfungen bestanden."
                  : "\n\(fehler) Prüfung(en) fehlgeschlagen.")
exit(fehler == 0 ? 0 : 1)
