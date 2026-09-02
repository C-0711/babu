import Foundation

// Store-Harness: Gemmas Buchung wird auf den Beleg angewendet.
//
// Ninas Fund P0-2 (02.09.2026): ein Getränkemarkt-Bon druckt Netto 57,06 €
// und Steuer (19 %) 8,67 € bei Brutto 65,73 € — Pfand ist darin steuerfrei
// enthalten. `gemmaBuchungAnwenden` rechnete bisher IMMER erst blind
// 19 % auf den ganzen Betrag (55,24/10,49) und markierte das fälschlich
// als geprüft (`summenprobeOK = true`, ungeprüft geraten) — Gemmas eigene
// Steuertabelle (`steuersaetze`) kam erst DANACH und nur als Sonderfall.
// Jetzt gewinnt die Tabelle zuerst; die Rückrechnung ist der letzte
// Fallback und heißt dann ehrlich "geschätzt" (`summenprobeOK = false`).
//
// Läuft im Simulator (AppStore braucht Foundation-Persistenz und die
// restlichen Modell-Dateien) — Aufruf über run.sh. AppStore ist
// @MainActor; die Prüfungen laufen daher in einem Task auf dem MainActor.
// dispatchMain() statt einer wartenden Semaphore: die würde den einzigen
// Thread blockieren, auf dem der MainActor seine Arbeit überhaupt
// abarbeitet — der Task exited den Prozess selbst, wenn er fertig ist.

var fehler = 0
func pruefe(_ ok: Bool, _ name: String) {
    if ok { print("  ok  \(name)") } else { fehler += 1; print("  FEHLER  \(name)") }
}

func nahe(_ a: Double, _ b: Double, _ eps: Double = 0.005) -> Bool { abs(a - b) < eps }

Task { @MainActor in
    let store = AppStore()

    // ————— Fall 1: Gemmas Tabelle deckt den Betrag — sie gewinnt —————
    // (führender Satz 19 %, Pfand als eigene 0-%-Zeile, wie im Prompt jetzt
    // verlangt und wie gemma_buchung._steuertabelle es liefert.)
    do {
        let id = store.routen(bildJpeg: nil, ocrText: "Getränkemarkt\n65,73").id
        store.gemmaBuchungAnwenden(
            id: id, konto: "6815", ustSatz: 19, betragEur: 65.73, waehrung: "EUR",
            begruendung: "Getränke für den Salon",
            steuersaetze: [
                SteuerPosition(satz: 19, netto: 49.63, ust: 9.43, brutto: 59.06),
                SteuerPosition(satz: 0, netto: 6.67, ust: 0.0, brutto: 6.67),
            ])
        if let b = store.belege.first(where: { $0.id == id }) {
            pruefe(nahe(b.netto, 56.30), "Netto aus der Tabelle: 56,30 (ist \(b.netto))")
            pruefe(nahe(b.ust, 9.43), "USt aus der Tabelle: 9,43 (ist \(b.ust))")
            pruefe(b.summenprobeOK, "Tabelle deckt den Betrag → summenprobeOK true")
            // Nicht die blinde 19-%-Rückrechnung auf den ganzen Betrag.
            pruefe(!nahe(b.netto, 55.24) || !nahe(b.ust, 10.49),
                   "Nicht die blinde Rückrechnung (55,24/10,49)")
        } else {
            pruefe(false, "Beleg nach der Buchung auffindbar")
        }
    }

    // ————— Fall 2: keine Tabelle — Rückrechnung als Fallback, ehrlich markiert —————
    do {
        let id = store.routen(bildJpeg: nil, ocrText: "Getränkemarkt\n65,73").id
        store.gemmaBuchungAnwenden(
            id: id, konto: "6815", ustSatz: 19, betragEur: 65.73, waehrung: "EUR",
            begruendung: "Getränke für den Salon", steuersaetze: [])
        if let b = store.belege.first(where: { $0.id == id }) {
            pruefe(nahe(b.netto, 55.24), "Ohne Tabelle: Rückrechnung 55,24 (ist \(b.netto))")
            pruefe(nahe(b.ust, 10.49), "Ohne Tabelle: Rückrechnung 10,49 (ist \(b.ust))")
            pruefe(!b.summenprobeOK, "Ohne Tabelle ehrlich als geschätzt markiert (summenprobeOK false)")
        } else {
            pruefe(false, "Beleg nach der Buchung auffindbar")
        }
    }

    // ————— Fall 3: eine Tabelle, die den Betrag NICHT deckt — fällt zurück —————
    // (z. B. unvollständige Positionen) — darf nicht stillschweigend übernommen
    // werden, sonst zeigt die App eine Zahl, die zu keiner Probe gehört.
    do {
        let id = store.routen(bildJpeg: nil, ocrText: "Getränkemarkt\n65,73").id
        store.gemmaBuchungAnwenden(
            id: id, konto: "6815", ustSatz: 19, betragEur: 65.73, waehrung: "EUR",
            begruendung: "Getränke für den Salon",
            steuersaetze: [SteuerPosition(satz: 19, netto: 33.61, ust: 6.39, brutto: 40.00)])
        if let b = store.belege.first(where: { $0.id == id }) {
            pruefe(nahe(b.netto, 55.24), "Ungedeckte Tabelle: Rückrechnung greift (ist \(b.netto))")
            pruefe(!b.summenprobeOK, "Ungedeckte Tabelle: ehrlich geschätzt (summenprobeOK false)")
        } else {
            pruefe(false, "Beleg nach der Buchung auffindbar")
        }
    }

    print("")
    if fehler > 0 { print("\(fehler) Prüfung(en) fehlgeschlagen."); exit(1) }
    print("Alle Prüfungen bestanden.")
    exit(0)
}
dispatchMain()
