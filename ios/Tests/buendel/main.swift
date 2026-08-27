import UIKit
import PDFKit

// Bündel-Harness: mehrseitige Belege (GitLab #69).
// Läuft im Simulator (UIKit/PDFKit) — Aufruf über run.sh.

var fehler = 0
func pruefe(_ ok: Bool, _ name: String) {
    if ok { print("  ok  \(name)") } else { fehler += 1; print("  FEHLER  \(name)") }
}

func testbild(_ farbe: UIColor, breite: CGFloat, hoehe: CGFloat) -> Data {
    let r = UIGraphicsImageRenderer(size: CGSize(width: breite, height: hoehe))
    let bild = r.image { ctx in
        farbe.setFill()
        ctx.fill(CGRect(x: 0, y: 0, width: breite, height: hoehe))
    }
    return bild.jpegData(compressionQuality: 0.6)!
}

// ————— Dateiname: Bündel = .pdf, ohne „auszug" im Slug —————
var einzeln = Beleg(lieferant: "Henkel", belegNr: "1", datumText: "24.02.2026",
                    netto: 0, ust: 0, brutto: 0, ustSatz: 0, konto: nil,
                    steuerschluessel: "0", kreditor: "70000", herkunft: .ki,
                    confidence: 0, status: .offen, begruendung: "",
                    summenprobeOK: false)
pruefe(ablageDateiname(fuer: einzeln).hasSuffix(".jpg"),
       "Einzelseite bleibt .jpg")

var buendel = einzeln
buendel.seitenJpeg = [Data([1]), Data([2])]
let name = ablageDateiname(fuer: buendel)
pruefe(name.hasSuffix(".pdf"), "Bündel wird .pdf")

var falle = buendel
falle.lieferant = "Kontoauszug Service GmbH"
let fallenName = ablageDateiname(fuer: falle)
pruefe(!fallenName.lowercased().contains("auszug"),
       "Bündel-Slug trägt nie „auszug“ (Server-Fallen-Schutz): \(fallenName)")

// ————— Siegel: ohne Seiten der alte Weg, mit Seiten alle Seiten —————
let zeit = Date(timeIntervalSince1970: 1_756_252_800)
var alt = einzeln
alt.bildJpeg = Data([9, 9, 9])
let siegelVorher = siegelHash(alt, zeit: zeit)
alt.seitenJpeg = nil
pruefe(siegelHash(alt, zeit: zeit) == siegelVorher,
       "Siegel ohne Seiten unverändert (Bestandssiegel bleiben gültig)")

var mitSeiten = alt
mitSeiten.seitenJpeg = [Data([1]), Data([2])]
let siegelA = siegelHash(mitSeiten, zeit: zeit)
mitSeiten.seitenJpeg = [Data([1]), Data([3])]
pruefe(siegelHash(mitSeiten, zeit: zeit) != siegelA,
       "Siegel ändert sich, wenn sich EINE Seite ändert")

// ————— PDF-Bau: zwei Seiten, eigene Formate, %PDF —————
let s1 = testbild(.white, breite: 800, hoehe: 1100)
let s2 = testbild(.lightGray, breite: 900, hoehe: 1200)
if let pdf = BelegBuendelPDF.bauen(seitenJpeg: [s1, s2]) {
    pruefe(pdf.prefix(4) == Data("%PDF".utf8), "PDF beginnt mit %PDF")
    if let doc = PDFDocument(data: pdf) {
        pruefe(doc.pageCount == 2, "PDF hat 2 Seiten (ist: \(doc.pageCount))")
        let b0 = doc.page(at: 0)!.bounds(for: .mediaBox)
        let b1 = doc.page(at: 1)!.bounds(for: .mediaBox)
        pruefe(abs(b0.width - 800) < 2 && abs(b0.height - 1100) < 2,
               "Seite 1 behält ihr Format")
        pruefe(abs(b1.width - 900) < 2 && abs(b1.height - 1200) < 2,
               "Seite 2 behält ihr Format")
    } else {
        pruefe(false, "PDFDocument kann das Bündel öffnen")
    }
} else {
    pruefe(false, "BelegBuendelPDF.bauen liefert Daten")
}
// Übergroße Seite wird auf die 2200er-Kante begrenzt.
let gross = testbild(.white, breite: 4400, hoehe: 3000)
if let pdf = BelegBuendelPDF.bauen(seitenJpeg: [gross]),
   let doc = PDFDocument(data: pdf), let seite = doc.page(at: 0) {
    let b = seite.bounds(for: .mediaBox)
    pruefe(max(b.width, b.height) <= 2201, "Lange Kante ≤ 2200 (ist: \(max(b.width, b.height)))")
} else {
    pruefe(false, "Groß-Seite ließ sich bündeln")
}

if fehler > 0 { print("Bündel-Harness: \(fehler) Fehler"); exit(1) }
print("Bündel-Harness ok")
exit(0)
