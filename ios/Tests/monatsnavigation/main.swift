import Foundation

// Nachbau der Logik aus ListeView.swift zum Testen

func belegMonatSchluessel(_ datumText: String) -> String? {
    let t = datumText.split(separator: ".")
    guard t.count == 3, let tag = Int(t[0]), let monat = Int(t[1]),
          var jahr = Int(t[2]), (1...31).contains(tag),
          (1...12).contains(monat) else { return nil }
    if jahr < 100 { jahr += 2000 }
    guard jahr >= 2000 else { return nil }
    return String(format: "%04d-%02d", jahr, monat)
}

func monatsBlaetter(datumTexte: [String], heute: String) -> [String] {
    var monate = Set<String>()
    var ohneDatum = false
    for t in datumTexte {
        if let m = belegMonatSchluessel(t) { monate.insert(m) }
        else { ohneDatum = true }
    }
    let aeltester = min(monate.min() ?? heute, heute)
    let neuester = max(monate.max() ?? heute, heute)
    var blaetter: [String] = []
    var m = neuester
    while m >= aeltester {
        blaetter.append(m)
        guard let jahr = Int(m.prefix(4)), let monat = Int(m.suffix(2)) else { break }
        m = monat == 1 ? String(format: "%04d-12", jahr - 1)
                       : String(format: "%04d-%02d", jahr, monat - 1)
    }
    return blaetter + (ohneDatum ? [""] : [])
}

func aktuellerMonatSchluessel() -> String {
    return "2026-09"  // September 2026 simulieren
}

// Simuliere Ninas Szenario: nur Belege im Januar, heute ist September
let datumTexte = ["15.01.26", "20.01.26", "25.01.26"]
let heute = aktuellerMonatSchluessel()
let monate = monatsBlaetter(datumTexte: datumTexte, heute: heute)

print("Monate:", monate)
print("Anzahl Monate:", monate.count)

// Aktivem Monat berechnen (wie in ListeView)
var gewaehlterMonat: String? = nil
func aktiverMonat() -> String {
    if let m = gewaehlterMonat, monate.contains(m) { return m }
    return monate.contains(heute) ? heute : (monate.first ?? heute)
}

print("Aktiver Monat (initial):", aktiverMonat())

// Index berechnen
let index0 = monate.firstIndex(of: aktiverMonat()) ?? 0
print("Index:", index0)

// Disabled-Zustände
let linkerDisabled = index0 >= monate.count - 1
let rechterDisabled = index0 == 0
print("Linker Button disabled:", linkerDisabled)
print("Rechter Button disabled:", rechterDisabled)

// Versuche zu blättern (linker Button, +1)
print("\nVersuche nach links zu blättern (zu älterem Monat)...")
if !linkerDisabled {
    if let i = monate.firstIndex(of: aktiverMonat()),
       monate.indices.contains(i + 1) {
        gewaehlterMonat = monate[i + 1]
        print("Erfolgreich! Neuer Monat:", gewaehlterMonat!)
    } else {
        print("Guard fehlgeschlagen!")
    }
} else {
    print("Button ist disabled!")
}

// Versuche zu blättern (rechter Button, -1)
print("\nVersuche nach rechts zu blättern (zu neuerem Monat)...")
if !rechterDisabled {
    if let i = monate.firstIndex(of: aktiverMonat()),
       monate.indices.contains(i - 1) {
        gewaehlterMonat = monate[i - 1]
        print("Erfolgreich! Neuer Monat:", gewaehlterMonat!)
    } else {
        print("Guard fehlgeschlagen!")
    }
} else {
    print("Button ist disabled!")
}

// Jetzt mehrfach nach links blättern, um zum Januar zu kommen
print("\n=== Blättern zum Januar ===")
for schritt in 1...10 {
    let aktuell = aktiverMonat()
    print("\nSchritt \(schritt): Aktueller Monat: \(aktuell)")

    if let i = monate.firstIndex(of: aktuell) {
        let linkerDisabled = i >= monate.count - 1
        let rechterDisabled = i == 0
        print("Index: \(i), Linker disabled: \(linkerDisabled), Rechter disabled: \(rechterDisabled)")

        if !linkerDisabled {
            if monate.indices.contains(i + 1) {
                gewaehlterMonat = monate[i + 1]
                print("→ Geblättert zu: \(gewaehlterMonat!)")
                if gewaehlterMonat == "2026-01" {
                    print("✓ Januar erreicht!")
                    break
                }
            } else {
                print("✗ Kann nicht blättern (Index außerhalb)")
                break
            }
        } else {
            print("✗ Button disabled (am Ende)")
            break
        }
    } else {
        print("✗ FEHLER: Aktiver Monat nicht in Liste gefunden!")
        break
    }
}
