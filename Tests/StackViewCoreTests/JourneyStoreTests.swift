import Foundation
import XCTest
@testable import StackViewCore

private actor StubRepository: ItemRepositoryProtocol {
    let result: Result<[StackItem], Error>
    let cache: [StackItem]
    init(result: Result<[StackItem], Error>, cache: [StackItem] = []) { self.result = result; self.cache = cache }
    func refresh() async throws -> [StackItem] { try result.get() }
    func cached() async -> [StackItem] { cache }
}

final class JourneyStoreTests: XCTestCase {
    func testModelTrimsAndValidatesInput() throws {
        let item = try StackItem(title: "  Valid  ", details: " Details ")
        XCTAssertEqual(item.title, "Valid")
        XCTAssertThrowsError(try StackItem(title: "", details: "x"))
        XCTAssertThrowsError(try StackItem(title: "x", details: String(repeating: "a", count: 241)))
    }

    func testDecodedModelCannotBypassValidation() throws {
        let invalid = #"{"id":"00000000-0000-0000-0000-000000000001","title":"","details":"x","updatedAt":"2026-01-01T00:00:00Z"}"#.data(using: .utf8)!
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        XCTAssertThrowsError(try decoder.decode(StackItem.self, from: invalid))
    }

    @MainActor func testLifecycleMovesLoadingToLoaded() async throws {
        let item = try StackItem(title: "One", details: "First")
        let store = JourneyStore(repository: StubRepository(result: .success([item])))
        await store.load()
        XCTAssertEqual(store.state, .loaded([item]))
    }

    @MainActor func testEmptyResponseHasExplicitState() async {
        let store = JourneyStore(repository: StubRepository(result: .success([])))
        await store.load()
        XCTAssertEqual(store.state, .empty)
    }

    @MainActor func testOfflineUsesPersistedCacheAndRecovers() async throws {
        let item = try StackItem(title: "Saved", details: "Offline")
        let store = JourneyStore(repository: StubRepository(result: .failure(RepositoryError.offline), cache: [item]))
        await store.load()
        XCTAssertEqual(store.state, .offline([item]))
    }

    @MainActor func testOfflineWithoutCacheIsActionableFailure() async {
        let store = JourneyStore(repository: StubRepository(result: .failure(RepositoryError.offline)))
        await store.load()
        XCTAssertEqual(store.state, .failure("offline_no_cache"))
    }

    @MainActor func testMalformedInputHasDedicatedFailure() async {
        let store = JourneyStore(repository: StubRepository(result: .failure(RepositoryError.malformedResponse)))
        await store.load()
        XCTAssertEqual(store.state, .failure("malformed_response"))
    }

    @MainActor func testInvalidHTTPStatusHasDedicatedFailure() async {
        let store = JourneyStore(repository: StubRepository(result: .failure(RepositoryError.invalidStatus(503))))
        await store.load()
        XCTAssertEqual(store.state, .failure("service_unavailable"))
    }

    @MainActor func testRestoreUsesPersistedState() async throws {
        let item = try StackItem(title: "Restored", details: "Lifecycle")
        let store = JourneyStore(repository: StubRepository(result: .success([]), cache: [item]))
        await store.restore()
        XCTAssertEqual(store.state, .offline([item]))
    }

    func testLegacyCacheMigratesToVersionedEnvelope() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let cache = directory.appendingPathComponent("items.json")
        let item = try StackItem(title: "Legacy", details: "Cache", updatedAt: Date(timeIntervalSince1970: 0))
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        try encoder.encode([item]).write(to: cache)
        let repository = JSONItemRepository(endpoint: nil, cacheURL: cache)
        let restored = await repository.cached()
        XCTAssertEqual(restored, [item])
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        let migrated = try decoder.decode(CacheEnvelope.self, from: Data(contentsOf: cache))
        XCTAssertEqual(migrated.schemaVersion, CacheEnvelope.currentSchemaVersion)
        XCTAssertEqual(migrated.items, [item])
    }

    func testEnglishAndSpanishLocalizationsHaveTheRequiredStateKeys() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        for language in ["en", "es"] {
            let text = try String(contentsOf: root.appendingPathComponent("stackviewtest/\(language).lproj/Localizable.strings"), encoding: .utf8)
            for key in ["journey.loading", "journey.empty", "journey.offline", "journey.retry", "journey.error.malformed_response", "journey.error.service_unavailable"] { XCTAssertTrue(text.contains("\"\(key)\""), "Missing \(key) in \(language)") }
        }
    }

    func testRotationUsesStableAxisRule() {
        XCTAssertEqual(preferredAxis(width: 800, height: 400), .horizontal)
        XCTAssertEqual(preferredAxis(width: 400, height: 800), .vertical)
    }
}
