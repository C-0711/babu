import UIKit
import AVFoundation
import Contacts
import ContactsUI
import MessageUI

// Die Blätter, die iOS selbst mitbringt: Kontakte wählen, eine Nachricht
// schreiben, ein Hinweis über allem. SwiftUI hat für die ersten beiden
// nichts Eigenes, und aus einem `.sheet` heraus zeigen sie sich nur
// unzuverlässig (leeres weißes Blatt) — deshalb legen sie sich hier direkt
// auf das oberste Blatt, das gerade zu sehen ist.

@MainActor
enum Obenauf {
    /// Das Blatt, das gerade ganz oben liegt.
    static func controller() -> UIViewController? {
        let szenen = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let szene = szenen.first { $0.activationState == .foregroundActive } ?? szenen.first
        let fenster = szene?.windows.first { $0.isKeyWindow } ?? szene?.windows.first
        var oben = fenster?.rootViewController
        while let darueber = oben?.presentedViewController, !darueber.isBeingDismissed {
            oben = darueber
        }
        return oben
    }

    /// Ein Hinweis mit einem OK — über jedem Blatt, auch über dem Konto-Menü.
    static func hinweis(_ titel: String, _ text: String) {
        let alert = UIAlertController(title: titel, message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        controller()?.present(alert, animated: true)
    }

    /// Die Helligkeit des Bildschirms, an dem die App gerade hängt.
    static var bildschirm: UIScreen? {
        (UIApplication.shared.connectedScenes.first { $0 is UIWindowScene } as? UIWindowScene)?
            .screen
    }
}

/// Einen Kontakt aus dem Adressbuch wählen. Braucht KEINE Erlaubnis für die
/// Kontakte: iOS zeigt die Liste selbst und gibt nur den einen gewählten
/// Kontakt heraus.
@MainActor
final class Kontaktwahl: NSObject, CNContactPickerDelegate {
    static let shared = Kontaktwahl()

    /// Vorname (oder Firmenname) und die Handynummer, falls es eine gibt.
    struct Person {
        let vorname: String
        let handy: String?
    }

    private var fertig: ((Person?) -> Void)?

    func oeffnen(_ fertig: @escaping (Person?) -> Void) {
        guard let oben = Obenauf.controller() else { fertig(nil); return }
        self.fertig = fertig
        let liste = CNContactPickerViewController()
        liste.delegate = self
        liste.displayedPropertyKeys = [CNContactPhoneNumbersKey]
        oben.present(liste, animated: true)
    }

    nonisolated func contactPicker(_ picker: CNContactPickerViewController,
                                   didSelect contact: CNContact) {
        let person = Self.person(aus: contact)
        MainActor.assumeIsolated {
            fertig?(person)
            fertig = nil
        }
    }

    nonisolated func contactPickerDidCancel(_ picker: CNContactPickerViewController) {
        MainActor.assumeIsolated {
            fertig?(nil)
            fertig = nil
        }
    }

    /// Vorname, sonst der Salonname, sonst der Nachname — und die Nummer,
    /// die nach Handy aussieht (Regel in `EmpfehlenStand.handynummer`).
    nonisolated static func person(aus k: CNContact) -> Person {
        func wert(_ schluessel: String, _ lesen: () -> String) -> String {
            k.isKeyAvailable(schluessel)
                ? lesen().trimmingCharacters(in: .whitespacesAndNewlines) : ""
        }
        let vorname = [wert(CNContactGivenNameKey) { k.givenName },
                       wert(CNContactOrganizationNameKey) { k.organizationName },
                       wert(CNContactFamilyNameKey) { k.familyName }]
            .first { !$0.isEmpty } ?? ""
        var nummern: [(mobil: Bool, nummer: String)] = []
        if k.isKeyAvailable(CNContactPhoneNumbersKey) {
            nummern = k.phoneNumbers.map { eintrag in
                (mobil: eintrag.label == CNLabelPhoneNumberMobile
                     || eintrag.label == CNLabelPhoneNumberiPhone,
                 nummer: eintrag.value.stringValue)
            }
        }
        return Person(vorname: vorname, handy: EmpfehlenStand.handynummer(nummern))
    }
}

/// Eine SMS bzw. iMessage mit Empfängerin und Text schon eingetragen —
/// abschicken tut sie selbst. Ohne Nachrichten-Dienst (Simulator, iPad) geht
/// es über `sms:` an die Nachrichten-App.
@MainActor
final class Nachricht: NSObject, MFMessageComposeViewControllerDelegate {
    static let shared = Nachricht()

    func schreiben(an nummer: String, text: String) {
        if MFMessageComposeViewController.canSendText(), let oben = Obenauf.controller() {
            let fenster = MFMessageComposeViewController()
            fenster.messageComposeDelegate = self
            fenster.recipients = [nummer]
            fenster.body = text
            oben.present(fenster, animated: true)
            return
        }
        let ziffern = nummer.filter { $0.isNumber || $0 == "+" }
        let inhalt = text.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed
            .subtracting(CharacterSet(charactersIn: "&=?+"))) ?? ""
        if let url = URL(string: "sms:\(ziffern)&body=\(inhalt)") {
            UIApplication.shared.open(url)
        }
    }

    nonisolated func messageComposeViewController(_ fenster: MFMessageComposeViewController,
                                                  didFinishWith result: MessageComposeResult) {
        MainActor.assumeIsolated {
            fenster.dismiss(animated: true)
        }
    }
}

/// Der Kassenklang, wenn ein Salon zahlende Kundin wird. Eigener Klang
/// (`werkzeuge/klang/kaching.py`); dieselbe Datei dient später als Push-Ton
/// (`"sound": "kaching.caf"`).
@MainActor
enum Kaching {
    /// Festgehalten, solange er klingt — sonst verstummt er sofort.
    private static var spieler: AVAudioPlayer?

    /// Klang und ein kurzes Klopfen. `.ambient` heißt: der Stummschalter
    /// gilt, und laufende Musik wird nicht unterbrochen.
    static func klingeln() {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        guard let url = Bundle.main.url(forResource: "kaching", withExtension: "caf")
        else { return }
        try? AVAudioSession.sharedInstance().setCategory(.ambient)
        spieler = try? AVAudioPlayer(contentsOf: url)
        spieler?.play()
    }
}
