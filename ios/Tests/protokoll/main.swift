import Foundation

// Der Setzer für das Leseprotokoll — reine Logik, deshalb hier prüfbar.
// Er muss genau das können, was der Server schreibt: Überschriften,
// Tabellen mit maskierten Strichen, die eingerückte Steuerrechnung,
// Aufzählungen und Zitate. Ein Fehler hier heißt: Nina sieht das
// Protokoll zerfallen statt gesetzt.

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

let beispiel = """
# bon.jpg

**Ein Brötchen beim Bäcker um die Ecke.**

Dieses Protokoll zeigt vollständig, was babu gelesen hat.

## Das Ergebnis

| Feld | Wert | Woher |
|---|---|---|
| Lieferant | Bäckerei Probe GmbH | Zeile 1 · größte Schrift im Kopf |
| Rechnungsbetrag | 1,30 € | Zeile 6 · Zeile nennt „SUMME“ |

## Die Steuerrechnung

    Netto             1,21 €
  + Steuer            0,09 €
    ─────────────────────────
  = Brutto            1,30 €   ✓ geht auf

## Wie babu den Beleg gelesen hat

- Die Beträge stehen in einer Spalte.
- Ab Zeile 9 steht Kleingedrucktes.

> Netto und Steuer gehen nicht auf.

## Jede erkannte Zeile

| # | | Text | Erkennung |
|---:|---|---|---|
| 1 | › | Bäckerei Probe GmbH | sicher (97%) |
| 2 | | Königstr. 1 \\| Stuttgart | gut (91%) |
"""

let bloecke = Protokollsatz.bloecke(aus: beispiel)

print("— Blöcke —")
var titel = 0, abschnitte = 0, tabellen = 0, punkte = 0, zitate = 0
var rechnungen = 0, hervorgehoben = 0
var tabellenZeilen: [[[String]]] = []
for b in bloecke {
    switch b {
    case .titel: titel += 1
    case .abschnitt: abschnitte += 1
    case .punkt: punkte += 1
    case .zitat: zitate += 1
    case .rechnung: rechnungen += 1
    case .hervorgehoben: hervorgehoben += 1
    case .tabelle(_, let zeilen): tabellen += 1; tabellenZeilen.append(zeilen)
    case .absatz: break
    }
}
pruefe("ein Titel", titel == 1)
pruefe("vier Abschnitte", abschnitte == 4)
pruefe("die Zusammenfassung ist hervorgehoben", hervorgehoben == 1)
pruefe("zwei Tabellen", tabellen == 2)
pruefe("zwei Aufzählungspunkte", punkte == 2)
pruefe("ein Zitat", zitate == 1)
pruefe("eine Steuerrechnung", rechnungen == 1)

print("— Tabellen —")
pruefe("Trennzeile fällt weg", tabellenZeilen.first?.count == 2)
pruefe("Wert steht in der Zelle",
       tabellenZeilen.first?.first?.contains("Bäckerei Probe GmbH") == true)
pruefe("Herkunft bleibt erhalten",
       tabellenZeilen.first?.last?.last?.contains("SUMME") == true)

print("— Maskierter Strich —")
let zeilenTabelle = tabellenZeilen.count > 1 ? tabellenZeilen[1] : []
pruefe("maskiertes | zerlegt die Zeile nicht", zeilenTabelle.count == 2)
pruefe("der Strich steht wieder im Text",
       zeilenTabelle.last?.contains(where: { $0.contains("Königstr. 1 | Stuttgart") }) == true)

print("— Steuerrechnung —")
if case .rechnung(let zeilen)? = bloecke.first(where: {
    if case .rechnung = $0 { return true } else { return false } }) {
    pruefe("vier Zeilen", zeilen.count == 4)
    pruefe("Einrückung bleibt", zeilen.count > 1 && zeilen[1].hasPrefix("+ Steuer"))
    pruefe("die Probe steht drin", zeilen.last?.contains("✓ geht auf") == true)
} else {
    pruefe("Steuerrechnung gefunden", false)
}

print("— Auszeichnung —")
pruefe("Sternchen weg", Protokollsatz.ohneAuszeichnung("**fett**") == "fett")
pruefe("Backticks weg", Protokollsatz.ohneAuszeichnung("`code`") == "code")
pruefe("nbsp weg", Protokollsatz.ohneAuszeichnung("&nbsp;") == "")

print("— Randfälle —")
pruefe("leerer Text ergibt nichts", Protokollsatz.bloecke(aus: "").isEmpty)
pruefe("nur Leerzeilen ergeben nichts", Protokollsatz.bloecke(aus: "\n\n\n").isEmpty)
pruefe("eine Tabelle ohne Inhalt wird verworfen",
       Protokollsatz.bloecke(aus: "| a | b |\n|---|---|\n").isEmpty)
pruefe("eine Zelle mit Doppelpunkt bleibt heil",
       Protokollsatz.zellen("| Datum | 14.08.2026 |") == ["Datum", "14.08.2026"])

print(fehler == 0 ? "\nAlles in Ordnung." : "\n\(fehler) Fehler.")
exit(fehler == 0 ? 0 : 1)
