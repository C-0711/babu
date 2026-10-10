import Foundation

// Der Platz, wie die App ihn anzeigt (Platz.swift, seit 10.10.2026).
// Gerechnet wird auf dem Server (paket.py, test_paket.py); hier geht es um
// das, was nur die App tut: den Balken und die Zahl im Satz. Beides hat
// seine eigene Falle — im Freikontingent zählen BELEGE, mit Stufe BYTES.

var fehler = 0
func pruefe(_ ok: Bool, _ was: String) {
    print(ok ? "  ok  \(was)" : "  FEHLER  \(was)")
    if !ok { fehler += 1 }
}
func nah(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 0.001 }

let GB = 1024 * 1024 * 1024

func frei(_ offen: Int, belege: Int) -> PlatzStand {
    PlatzStand(stufe: nil, grenze: nil, verbraucht: 0, voll: offen == 0,
               knapp: offen > 0 && offen <= 3, belege: belege, freiOffen: offen)
}
func mitStufe(_ stufe: String, grenze: Int, verbraucht: Int) -> PlatzStand {
    PlatzStand(stufe: stufe, grenze: grenze, verbraucht: verbraucht,
               voll: verbraucht >= grenze, knapp: false, belege: 0, freiOffen: nil)
}

// --- Der Balken im Freikontingent: er zählt Belege, nicht Bytes ---------
pruefe(nah(frei(10, belege: 0).anteil, 0), "frisches Konto: Balken leer")
pruefe(nah(frei(5, belege: 5).anteil, 0.5), "halb verbraucht: Balken halb")
pruefe(nah(frei(0, belege: 10).anteil, 1), "aufgebraucht: Balken voll")
// Der Server zählt nur aufwärts, aber ein alter Stand auf dem Telefon darf
// den Balken nicht über das Ende hinausschieben.
pruefe(nah(frei(0, belege: 14).anteil, 1), "mehr als zehn bleibt bei voll")

// --- Mit Stufe: er zählt Bytes -----------------------------------------
pruefe(nah(mitStufe("klein", grenze: GB, verbraucht: 0).anteil, 0),
       "neue Stufe: Balken leer")
pruefe(nah(mitStufe("klein", grenze: GB, verbraucht: GB / 4).anteil, 0.25),
       "ein Viertel belegt")
pruefe(nah(mitStufe("klein", grenze: GB, verbraucht: GB * 2).anteil, 1),
       "übervoll bleibt bei voll")
// Eine Grenze von 0 darf nicht durch Null teilen.
pruefe(nah(mitStufe("klein", grenze: 0, verbraucht: 500).anteil, 0),
       "Grenze 0 ergibt keinen Absturz")

// --- Die Stufen, wie der Server sie schickt -----------------------------
let stufen = [PlatzStufe(stufe: "klein", gb: 1, cent: 999, apple: "babu.speicher.1gb"),
              PlatzStufe(stufe: "mittel", gb: 5, cent: 1999, apple: "babu.speicher.5gb"),
              PlatzStufe(stufe: "gross", gb: 100, cent: 9900, apple: "babu.speicher.100gb")]
pruefe(stufen.map(\.preisNotfalls) == ["9,99 €", "19,99 €", "99,00 €"],
       "die drei Preise stehen richtig da")
pruefe(stufen.map(\.id) == ["klein", "mittel", "gross"],
       "jede Stufe ist für sich erkennbar")

// --- „rund so viele Belege" -------------------------------------------
// Gerechnet mit 550 KB je Beleg (am 10.10.2026 am Bestand gemessen).
// Die Zahl ist gerundet, weil eine genaue eine Genauigkeit vorgäbe, die es
// nicht gibt — aber sie muss in der richtigen Größenordnung liegen.
pruefe(stufen[0].belegeText == "rund 2000 Belege", "1 GB ≈ 2000 Belege")
pruefe(stufen[1].belegeText == "rund 9500 Belege", "5 GB ≈ 9500 Belege")
pruefe(stufen[2].belegeText == "rund 190 Tausend Belege",
       "100 GB ≈ 190 Tausend Belege")

if fehler > 0 { print("\(fehler) Fehler"); exit(1) }
print("Platz-Harness: alles grün")
