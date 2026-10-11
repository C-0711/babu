import Foundation

// Der Monatswechsler der Dokumentenliste — gegen die ECHTEN Funktionen aus
// Models.swift, nicht gegen einen Nachbau. Der alte Harness hatte
// `monatsBlaetter` abgeschrieben und nur gedruckt; eine Kopie kann keinen
// Rückschritt melden, und ein Druck entscheidet nichts.
//
// Die eine Regel, die hier hängt (gemessen am 11.10.2026, Befund „Beleg
// gezählt, aber in keinem Monat auffindbar"): JEDER Beleg muss auf einem
// Blatt liegen, und JEDES Blatt muss mit ‹ und › erreichbar sein. Fällt ein
// Beleg aus beiden Rastern, ist er in der App verschwunden, obwohl die Zahl
// am Reiter ihn zählt.

var fehler = 0
func pruefe(_ bedingung: Bool, _ was: String) {
    if bedingung { print("  ok   \(was)") }
    else { print("  FEHL \(was)"); fehler += 1 }
}

/// Das aufgeschlagene Blatt — wörtlich wie `ListeView.aktiverMonat`.
func aktiverMonat(_ monate: [String], gewaehlt: String?, heute: String) -> String {
    if let m = gewaehlt, monate.contains(m) { return m }
    return monate.contains(heute) ? heute : (monate.first ?? heute)
}

/// Ein Durchlauf: Blätter bilden, jeden Beleg zuordnen, alles abschreiten.
func fall(_ name: String, datumTexte: [String], heute: String) {
    print("— \(name)")
    let monate = monatsBlaetter(datumTexte: datumTexte, heute: heute)
    print("  Blätter: \(monate.map { $0.isEmpty ? "«ohne Datum»" : $0 })")

    // 1. Kein Beleg fällt aus allen Blättern.
    for t in datumTexte {
        let blatt = belegMonatSchluessel(t) ?? ""
        pruefe(monate.contains(blatt),
               "„\(t.isEmpty ? "«leer»" : t)" + "“ liegt auf Blatt "
               + "„\(blatt.isEmpty ? "«ohne Datum»" : blatt)“")
    }

    // 2. Das Startblatt ist eines der Blätter.
    let start = aktiverMonat(monate, gewaehlt: nil, heute: heute)
    pruefe(monate.contains(start), "Startblatt „\(start)“ ist in der Liste")

    // 3. Von vorn bis hinten durchblättern — ‹ (schritt +1) kommt überall an.
    var gesehen: Set<String> = []
    var m = monate.first ?? heute
    gesehen.insert(m)
    var runden = 0
    while let i = monate.firstIndex(of: m), i + 1 < monate.count, runden < 500 {
        m = monate[i + 1]
        gesehen.insert(m)
        runden += 1
    }
    pruefe(gesehen.count == monate.count,
           "‹ erreicht alle \(monate.count) Blätter (erreicht: \(gesehen.count))")

    // 4. Und › (schritt −1) wieder zurück.
    var zurueck = 0
    while let i = monate.firstIndex(of: m), i > 0, zurueck < 500 {
        m = monate[i - 1]
        zurueck += 1
    }
    pruefe(m == monate.first, "› führt zurück zum ersten Blatt")

    // 5. Die Knöpfe sperren nur an den Enden.
    let letzterIndex = monate.count - 1
    for (i, blatt) in monate.enumerated() {
        let linksGesperrt = i >= letzterIndex
        let rechtsGesperrt = i == 0
        pruefe(linksGesperrt == (i == letzterIndex),
               "‹ auf „\(blatt.isEmpty ? "«ohne Datum»" : blatt)“ gesperrt: \(linksGesperrt)")
        pruefe(rechtsGesperrt == (i == 0),
               "› auf „\(blatt.isEmpty ? "«ohne Datum»" : blatt)“ gesperrt: \(rechtsGesperrt)")
    }
    print("")
}

// Der gemessene Fall: ein Beleg vom 05.08., aufgenommen im Oktober.
fall("Beleg aus dem Vormonat (gemessen 11.10.2026)",
     datumTexte: ["05.08.2026"], heute: "2026-10")

// Noch ungelesen — bis die Buchung da ist, steht das Datum leer. Genau in
// diesem Fenster war der Beleg nicht zu finden.
fall("Datum noch nicht gelesen", datumTexte: [""], heute: "2026-10")

// Unlesbares Datum ist dasselbe wie keines: Blatt „Ohne Datum".
fall("Unlesbares Datum", datumTexte: ["0000-00-00", "32.13.2026", "irgendwas"],
     heute: "2026-10")

// Gemischt — mit und ohne Datum, über einen Jahreswechsel.
fall("Gemischt über den Jahreswechsel",
     datumTexte: ["15.01.26", "20.12.2025", "", "05.08.2026"], heute: "2026-02")

// Vordatiert: die Rechnung vom nächsten Monat liegt schon vor.
fall("Vordatierter Beleg", datumTexte: ["03.12.2026"], heute: "2026-10")

// Gar nichts — genau ein Blatt, der laufende Monat.
fall("Ohne Belege", datumTexte: [], heute: "2026-10")

// Ninas Fall #85/#88: nur Januar-Belege, heute September.
fall("Nur Januar, heute September",
     datumTexte: ["15.01.26", "20.01.26", "25.01.26"], heute: "2026-09")

if fehler > 0 {
    print("\(fehler) Fehler")
    exit(1)
}
print("Monatsnavigation: alles grün")
