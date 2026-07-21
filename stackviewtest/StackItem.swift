import Foundation

enum StackItemValidationError: Error, Equatable {
    case invalidTitle
    case detailsTooLong
}

struct StackItem: Codable, Equatable, Identifiable, Sendable {
    let id: UUID
    let title: String
    let details: String
    let updatedAt: Date

    init(id: UUID = UUID(), title: String, details: String, updatedAt: Date = Date()) throws {
        let cleanTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanDetails = details.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (1...80).contains(cleanTitle.count) else { throw StackItemValidationError.invalidTitle }
        guard cleanDetails.count <= 240 else { throw StackItemValidationError.detailsTooLong }
        self.id = id
        self.title = cleanTitle
        self.details = cleanDetails
        self.updatedAt = updatedAt
    }

    private enum CodingKeys: String, CodingKey { case id, title, details, updatedAt }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            id: values.decode(UUID.self, forKey: .id),
            title: values.decode(String.self, forKey: .title),
            details: values.decode(String.self, forKey: .details),
            updatedAt: values.decode(Date.self, forKey: .updatedAt)
        )
    }
}

enum StackAxis: Equatable, Sendable { case vertical, horizontal }

func preferredAxis(width: Double, height: Double) -> StackAxis {
    width > height ? .horizontal : .vertical
}
