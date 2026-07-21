import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

enum RepositoryError: Error, Equatable { case offline, malformedResponse, invalidStatus(Int) }

protocol ItemRepositoryProtocol: Sendable {
    func refresh() async throws -> [StackItem]
    func cached() async -> [StackItem]
}

struct CacheEnvelope: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1
    let schemaVersion: Int
    let items: [StackItem]

    init(schemaVersion: Int = Self.currentSchemaVersion, items: [StackItem]) {
        self.schemaVersion = schemaVersion
        self.items = items
    }
}

actor JSONItemRepository: ItemRepositoryProtocol {
    private let endpoint: URL?
    private let cacheURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(endpoint: URL?, cacheURL: URL, session: URLSession = .shared) {
        self.endpoint = endpoint
        self.cacheURL = cacheURL
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
        decoder.dateDecodingStrategy = .iso8601
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
    }

    func refresh() async throws -> [StackItem] {
        guard let endpoint else { throw RepositoryError.offline }
        var request = URLRequest(url: endpoint)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadRevalidatingCacheData
        let (data, response): (Data, URLResponse)
        do { (data, response) = try await session.data(for: request) }
        catch { throw RepositoryError.offline }
        guard let http = response as? HTTPURLResponse else { throw RepositoryError.malformedResponse }
        guard http.statusCode == 200 else { throw RepositoryError.invalidStatus(http.statusCode) }
        let items: [StackItem]
        do { items = try decoder.decode([StackItem].self, from: data) }
        catch { throw RepositoryError.malformedResponse }
        try encoder.encode(CacheEnvelope(items: items)).write(to: cacheURL, options: [.atomic, .completeFileProtection])
        return items
    }

    func cached() async -> [StackItem] {
        guard let data = try? Data(contentsOf: cacheURL) else { return [] }
        if let envelope = try? decoder.decode(CacheEnvelope.self, from: data), envelope.schemaVersion == CacheEnvelope.currentSchemaVersion { return envelope.items }
        guard let legacyItems = try? decoder.decode([StackItem].self, from: data) else { return [] }
        try? encoder.encode(CacheEnvelope(items: legacyItems)).write(to: cacheURL, options: [.atomic, .completeFileProtection])
        return legacyItems
    }
}

actor FixtureItemRepository: ItemRepositoryProtocol {
    enum Fixture: String { case success, empty, offlineCache = "offline-cache", malformed }
    private let fixture: Fixture

    init(fixture: Fixture) { self.fixture = fixture }

    func refresh() async throws -> [StackItem] {
        switch fixture {
        case .success: return [try StackItem(title: "Fixture item", details: "Loaded for UI verification")]
        case .empty: return []
        case .offlineCache: throw RepositoryError.offline
        case .malformed: throw RepositoryError.malformedResponse
        }
    }

    func cached() async -> [StackItem] {
        guard fixture == .offlineCache else { return [] }
        return (try? [StackItem(title: "Saved fixture", details: "Available without a network")]) ?? []
    }
}
