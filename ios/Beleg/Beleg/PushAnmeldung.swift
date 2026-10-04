import SwiftUI
import UserNotifications

/// Push-Nachrichten (babu Expenses D1): nach dem Anmelden fragt die App
/// einmal um Erlaubnis; das Gerät meldet der AppStore beim Server an.
final class PushDelegate: NSObject, UIApplicationDelegate {
    /// Wer das Token beim Server anmeldet — setzt der AppStore.
    static var beiToken: ((String) -> Void)?

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        PushDelegate.beiToken?(token)
    }

    static func anfragen() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { erlaubt, _ in
            guard erlaubt else { return }
            DispatchQueue.main.async { UIApplication.shared.registerForRemoteNotifications() }
        }
    }

    static var umgebung: String {
        #if DEBUG
        return "sandbox"
        #else
        return "produktion"
        #endif
    }
}
