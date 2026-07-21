import XCTest

final class StackViewJourneyUITests: XCTestCase {
    func testLoadingAndOfflineRecoveryAreAccessible() {
        let app = XCUIApplication()
        app.launchArguments = ["-UITestFixture", "offline-cache"]
        app.launch()
        let status = app.staticTexts["journey.status"]
        XCTAssertTrue(status.waitForExistence(timeout: 5))
        XCTAssertTrue(status.label.contains("Offline"))
        XCTAssertTrue(app.buttons["journey.retry"].isHittable)
    }

    func testLocalizedLandscapeLayoutRemainsNavigable() {
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(es)", "-AppleLocale", "es_ES", "-UITestFixture", "success"]
        XCUIDevice.shared.orientation = .landscapeLeft
        app.launch()
        let status = app.staticTexts["journey.status"]
        XCTAssertTrue(status.waitForExistence(timeout: 5))
        XCTAssertTrue(status.label.contains("elementos cargados"))
    }

    func testMalformedPayloadOffersRetry() {
        let app = XCUIApplication()
        app.launchArguments = ["-UITestFixture", "malformed"]
        app.launch()
        XCTAssertTrue(app.staticTexts["journey.status"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["journey.retry"].isHittable)
    }
}
