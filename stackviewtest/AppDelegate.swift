import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        application.isIdleTimerDisabled = false
        return true
    }

    func application(_ application: UIApplication, shouldSaveApplicationState coder: NSCoder) -> Bool { true }
    func application(_ application: UIApplication, shouldRestoreApplicationState coder: NSCoder) -> Bool { true }
}
