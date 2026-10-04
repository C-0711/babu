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

if fehler > 0 { print("\(fehler) Fehler"); exit(1) }
print("Ablage-Harness: alles grün")
