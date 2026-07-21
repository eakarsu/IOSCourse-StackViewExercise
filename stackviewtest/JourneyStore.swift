import Foundation

enum JourneyState: Equatable, Sendable {
    case idle
    case loading
    case loaded([StackItem])
    case empty
    case offline([StackItem])
    case failure(String)
}

@MainActor
final class JourneyStore {
    private let repository: ItemRepositoryProtocol
    private(set) var state: JourneyState = .idle { didSet { onChange?(state) } }
    var onChange: ((JourneyState) -> Void)?

    init(repository: ItemRepositoryProtocol) { self.repository = repository }

    func load() async {
        state = .loading
        do {
            let items = try await repository.refresh()
            state = items.isEmpty ? .empty : .loaded(items)
        } catch RepositoryError.offline {
            let cache = await repository.cached()
            state = cache.isEmpty ? .failure("offline_no_cache") : .offline(cache)
        } catch RepositoryError.malformedResponse {
            state = .failure("malformed_response")
        } catch RepositoryError.invalidStatus {
            state = .failure("service_unavailable")
        } catch {
            state = .failure("unexpected_error")
        }
    }

    func restore() async {
        let cache = await repository.cached()
        state = cache.isEmpty ? .empty : .offline(cache)
    }
}
