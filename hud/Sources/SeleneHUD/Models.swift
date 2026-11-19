import Foundation

public enum HUDDisplayMode: String, Codable, CaseIterable, Sendable {
    case notch
    case floating
}

public enum InteractionMode: String, Codable, Sendable {
    case ptt
    case handsFree = "hands_free"
}

public enum AgentState: String, Codable, Sendable {
    case idle
    case listening
    case thinking
    case speaking
    case disconnected

    public var title: String {
        switch self {
        case .idle: return "Selene"
        case .listening: return "Listening..."
        case .thinking: return "Thinking..."
        case .speaking: return "Speaking"
        case .disconnected: return "Connecting..."
        }
    }
}

public struct StudyCard: Identifiable, Codable, Sendable {
    public let id: Int
    public let topic: String
    public let question: String
    public let answer: String
    public let ease_factor: Double?
    public let interval_days: Double?
    public let repetitions: Int?
    public let due_at: String?

    public init(
        id: Int,
        topic: String,
        question: String,
        answer: String,
        ease_factor: Double? = nil,
        interval_days: Double? = nil,
        repetitions: Int? = nil,
        due_at: String? = nil
    ) {
        self.id = id
        self.topic = topic
        self.question = question
        self.answer = answer
        self.ease_factor = ease_factor
        self.interval_days = interval_days
        self.repetitions = repetitions
        self.due_at = due_at
    }
}

public struct HUDEvent: Codable, Sendable {
    public let type: String
    public let state: String?
    public let rms: Double?
    public let text: String?
    public let caption: String?
    public let app: String?
    public let window: String?
    public let selection_len: Int?
    public let cards_due: Int?
    public let muted: Bool?
    public let mode: String?
    public let cards: [StudyCard]?
}

public struct HUDCommand: Codable, Sendable {
    public let cmd: String
    public let text: String?
    public let command: String?
    public let mode: String?
    public let resume_mode: String?
    public let limit: Int?
    public let card_id: Int?
    public let quality: Int?

    public init(
        cmd: String,
        text: String? = nil,
        command: String? = nil,
        mode: String? = nil,
        resume_mode: String? = nil,
        limit: Int? = nil,
        card_id: Int? = nil,
        quality: Int? = nil
    ) {
        self.cmd = cmd
        self.text = text
        self.command = command
        self.mode = mode
        self.resume_mode = resume_mode
        self.limit = limit
        self.card_id = card_id
        self.quality = quality
    }
}
