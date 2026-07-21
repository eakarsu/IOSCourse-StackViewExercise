import UIKit

final class ViewController: UIViewController {
    private let statusLabel = UILabel()
    private let contentStack = UIStackView()
    private let retryButton = UIButton(type: .system)
    private let progress = UIActivityIndicatorView(style: .medium)
    private let scrollView = UIScrollView()
    private let rootStack = UIStackView()
    private lazy var store = JourneyStore(repository: makeRepository())

    override func viewDidLoad() {
        super.viewDidLoad()
        title = NSLocalizedString("journey.title", comment: "Screen title")
        view.backgroundColor = .systemBackground
        configureViews()
        store.onChange = { [weak self] state in self?.render(state) }
        Task { await store.restore(); await store.load() }
    }

    override func viewWillTransition(to size: CGSize, with coordinator: UIViewControllerTransitionCoordinator) {
        super.viewWillTransition(to: size, with: coordinator)
        coordinator.animate { [weak self] _ in self?.contentStack.axis = preferredAxis(width: size.width, height: size.height) == .horizontal ? .horizontal : .vertical }
    }

    override func encodeRestorableState(with coder: NSCoder) {
        super.encodeRestorableState(with: coder)
        coder.encode(true, forKey: "journeyWasVisible")
    }

    override func decodeRestorableState(with coder: NSCoder) {
        super.decodeRestorableState(with: coder)
        Task { await store.restore() }
    }

    private func configureViews() {
        restorationIdentifier = "StackJourney"
        statusLabel.numberOfLines = 0
        statusLabel.textAlignment = .center
        statusLabel.adjustsFontForContentSizeCategory = true
        statusLabel.font = .preferredFont(forTextStyle: .body)
        statusLabel.accessibilityIdentifier = "journey.status"
        statusLabel.accessibilityTraits = .header
        retryButton.setTitle(NSLocalizedString("journey.retry", comment: "Retry"), for: .normal)
        retryButton.accessibilityIdentifier = "journey.retry"
        retryButton.accessibilityHint = NSLocalizedString("journey.retry.hint", comment: "Retry hint")
        retryButton.addTarget(self, action: #selector(retry), for: .touchUpInside)
        contentStack.axis = .vertical
        contentStack.alignment = .fill
        contentStack.spacing = 12
        contentStack.translatesAutoresizingMaskIntoConstraints = false
        rootStack.addArrangedSubview(progress)
        rootStack.addArrangedSubview(statusLabel)
        rootStack.addArrangedSubview(retryButton)
        rootStack.addArrangedSubview(contentStack)
        rootStack.axis = .vertical
        rootStack.spacing = 16
        rootStack.translatesAutoresizingMaskIntoConstraints = false
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.alwaysBounceVertical = true
        scrollView.addSubview(rootStack)
        view.addSubview(scrollView)
        NSLayoutConstraint.activate([
            scrollView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            rootStack.leadingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.leadingAnchor, constant: 16),
            rootStack.trailingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.trailingAnchor, constant: -16),
            rootStack.topAnchor.constraint(equalTo: scrollView.contentLayoutGuide.topAnchor, constant: 16),
            rootStack.bottomAnchor.constraint(equalTo: scrollView.contentLayoutGuide.bottomAnchor, constant: -16),
            rootStack.widthAnchor.constraint(equalTo: scrollView.frameLayoutGuide.widthAnchor, constant: -32),
            retryButton.heightAnchor.constraint(greaterThanOrEqualToConstant: 44)
        ])
        contentStack.axis = preferredAxis(width: view.bounds.width, height: view.bounds.height) == .horizontal ? .horizontal : .vertical
    }

    @objc private func retry() { Task { await store.load() } }

    private func render(_ state: JourneyState) {
        contentStack.arrangedSubviews.forEach { $0.removeFromSuperview() }
        progress.stopAnimating()
        retryButton.isHidden = true
        switch state {
        case .idle: statusLabel.text = ""
        case .loading:
            statusLabel.text = NSLocalizedString("journey.loading", comment: "Loading")
            progress.startAnimating()
        case .empty:
            statusLabel.text = NSLocalizedString("journey.empty", comment: "Empty")
        case .failure(let code):
            statusLabel.text = NSLocalizedString("journey.error.\(code)", comment: "Failure")
            retryButton.isHidden = false
        case .offline(let items):
            statusLabel.text = NSLocalizedString("journey.offline", comment: "Offline")
            add(items)
            retryButton.isHidden = false
        case .loaded(let items):
            statusLabel.text = String(format: NSLocalizedString("journey.loaded", comment: "Loaded"), items.count)
            add(items)
        }
        UIAccessibility.post(notification: .announcement, argument: statusLabel.text)
    }

    private func add(_ items: [StackItem]) {
        for item in items {
            let label = UILabel()
            label.numberOfLines = 0
            label.adjustsFontForContentSizeCategory = true
            label.text = "\(item.title)\n\(item.details)"
            label.accessibilityLabel = "\(item.title). \(item.details)"
            label.isAccessibilityElement = true
            contentStack.addArrangedSubview(label)
        }
    }

    private func makeRepository() -> ItemRepositoryProtocol {
        if let index = ProcessInfo.processInfo.arguments.firstIndex(of: "-UITestFixture"), ProcessInfo.processInfo.arguments.indices.contains(index + 1), let fixture = FixtureItemRepository.Fixture(rawValue: ProcessInfo.processInfo.arguments[index + 1]) {
            return FixtureItemRepository(fixture: fixture)
        }
        let cache = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("stack-items.json")
        try? FileManager.default.createDirectory(at: cache.deletingLastPathComponent(), withIntermediateDirectories: true)
        let rawEndpoint = Bundle.main.object(forInfoDictionaryKey: "ITEMS_ENDPOINT") as? String
        return JSONItemRepository(endpoint: rawEndpoint.flatMap(URL.init(string:)), cacheURL: cache)
    }
}
