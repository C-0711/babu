import Foundation

// Was eine Antwort des Servers für die Übertragung bedeutet.
// 403/409 heißt „keine Ablage“ und schaltet die Übertragung ab — außer der
// Server nennt einen Grund, der nur diesen einen Beleg betrifft. Fund aus dem
// Simulator-Test 04.10.2026: Leas Verbindungstest bekam 403 (keine Freigabe für
// /ablage), die App hielt das für „keine Ablage“ und lud nie wieder etwas hoch.

var fehler = 0
func pruefe(_ ok: Bool, _ was: String) {
    print(ok ? "  ok  \(was)" : "  FEHLER  \(was)")
    if !ok { fehler += 1 }
}
func json(_ o: [String: Any]) -> Data { try! JSONSerialization.data(withJSONObject: o) }

pruefe(AblageErgebnis.aus(status: 200, daten: nil) == .uebertragen, "2xx ist übertragen")
pruefe(AblageErgebnis.aus(status: 401, daten: nil) == .tokenFehler, "401 ist Zugang abgelaufen")
pruefe(AblageErgebnis.aus(status: 500, daten: nil) == .abgelehnt(500), "500 ist ein Fehlschlag")
pruefe(AblageErgebnis.aus(status: 403, daten: json(["fehler": "Noch keine Ablage."])) == .keineAblage,
       "403 ohne Grund heißt keine Ablage")
pruefe(AblageErgebnis.aus(status: 409, daten: json(["fehler": "Box wird eingerichtet."])) == .keineAblage,
       "409 ohne Grund heißt Ablage noch nicht eingerichtet")
pruefe(AblageErgebnis.aus(status: 403, daten: nil) == .keineAblage, "403 ohne Körper bleibt keine Ablage")

let doppelt = json(["fehler": "Dieses Foto liegt schon im Betrieb.", "grund": "dublette"])
pruefe(AblageErgebnis.aus(status: 409, daten: doppelt) == .abgelehnt(409),
       "doppeltes Foto schaltet die Ablage nicht ab")
pruefe(AblageErgebnis.hinweis(doppelt) == "Dieses Foto liegt schon im Betrieb.",
       "der Hinweis des Servers kommt mit")

let ohneRecht = json(["fehler": "Dafür fehlt dir die Freigabe.", "grund": "freigabe"])
pruefe(AblageErgebnis.aus(status: 403, daten: ohneRecht) == .abgelehnt(403),
       "fehlende Freigabe schaltet die Ablage nicht ab")
pruefe(AblageErgebnis.hinweis(json(["fehler": "Noch keine Ablage."])) == nil,
       "ohne Grund kein Hinweis am Beleg")
pruefe(AblageErgebnis.hinweis(nil) == nil, "ohne Körper kein Hinweis")

// Kein Platz mehr (seit 10.10.2026, paket.py). Eigener Fall, weil daran
// nichts falsch ist: der Beleg bleibt wartend liegen und geht los, sobald
// eine Stufe gebucht ist. Als `abgelehnt` hätte die App ihn abgestempelt wie
// ein kaputtes Foto; als `keineAblage` hätte sie die Übertragung abgeschaltet
// und nie wieder angeklopft.
let freiWeg = json(["fehler": "Deine zehn freien Belege sind abgelegt.",
                    "grund": "frei_aufgebraucht", "nur_lesen": true])
pruefe(AblageErgebnis.aus(status: 403, daten: freiWeg) == .platzVoll,
       "aufgebrauchtes Freikontingent ist Platz voll")
let platzWeg = json(["fehler": "Dein Platz ist voll.",
                     "grund": "speicher_voll", "nur_lesen": true])
pruefe(AblageErgebnis.aus(status: 403, daten: platzWeg) == .platzVoll,
       "voller Speicher ist Platz voll")
pruefe(AblageErgebnis.hinweis(platzWeg) == "Dein Platz ist voll.",
       "der Satz des Servers kommt an den Beleg")
// Negativkontrolle: ein anderer Grund darf NICHT als Platzproblem gelten,
// sonst öffnete die App die Stufenauswahl bei jeder Ablehnung.
pruefe(AblageErgebnis.aus(status: 403, daten: ohneRecht) != .platzVoll,
       "fehlende Freigabe ist kein Platzproblem")
pruefe(AblageErgebnis.aus(status: 409, daten: doppelt) != .platzVoll,
       "doppeltes Foto ist kein Platzproblem")
// Und die Gründe müssen genau die sein, die abo.TEXTE_PLATZ kennt.
pruefe(AblageErgebnis.PLATZ_GRUENDE == ["speicher_voll", "frei_aufgebraucht"],
       "die beiden Gründe stehen fest")

if fehler > 0 { print("\(fehler) Fehler"); exit(1) }
print("Ablage-Harness: alles grün")
