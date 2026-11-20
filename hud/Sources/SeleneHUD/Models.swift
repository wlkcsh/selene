import Foundation

public enum HUDDisplayMode: String, Codable, CaseIterable, Sendable {
    case notch
    case floating
}

public enum InteractionMode: String, Codable, Sendable {
    case ptt
    case handsFree = "hands_free"
}

public enum LanguageMode: String, CaseIterable, Codable, Sendable {
    case auto = "auto"
    case english = "en"
    case russian = "ru"

    public var badgeTitle: String {
        switch self {
        case .auto: return "AUTO"
        case .english: return "EN"
        case .russian: return "RU"
        }
    }

    public var menuTitle: String {
        switch self {
        case .auto: return "Auto-detect (EN / RU)"
        case .english: return "English (en)"
        case .russian: return "Русский (ru)"
        }
    }

    public var nextMode: LanguageMode {
        switch self {
        case .auto: return .english
        case .english: return .russian
        case .russian: return .auto
        }
    }
}

public enum ReplyLanguagePolicy: String, Codable, Sendable {
    case matchInput = "match"
    case alwaysEnglish = "force_en"
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
    public let language_mode: String?
    public let reply_policy: String?
    public let last_detected: String?
}

public struct AutomationRequest: Codable, Sendable {
    public let reqId: String
    public let app: String
    public let action: String
    public let args: [String]

    enum CodingKeys: String, CodingKey {
        case reqId
        case req_id
        case app
        case action
        case args
    }

    public init(reqId: String, app: String, action: String, args: [String]) {
        self.reqId = reqId
        self.app = app
        self.action = action
        self.args = args
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let id = try? container.decode(String.self, forKey: .reqId) {
            self.reqId = id
        } else if let id = try? container.decode(String.self, forKey: .req_id) {
            self.reqId = id
        } else {
            self.reqId = ""
        }
        self.app = (try? container.decode(String.self, forKey: .app)) ?? ""
        self.action = (try? container.decode(String.self, forKey: .action)) ?? ""
        self.args = (try? container.decode([String].self, forKey: .args)) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(reqId, forKey: .reqId)
        try container.encode(app, forKey: .app)
        try container.encode(action, forKey: .action)
        try container.encode(args, forKey: .args)
    }
}

public struct AutomationResponse: Codable, Sendable {
    public let reqId: String
    public let ok: Bool
    public let output: String?
    public let errorCode: String?
    public let errorMessage: String?

    public init(
        reqId: String,
        ok: Bool,
        output: String? = nil,
        errorCode: String? = nil,
        errorMessage: String? = nil
    ) {
        self.reqId = reqId
        self.ok = ok
        self.output = output
        self.errorCode = errorCode
        self.errorMessage = errorMessage
    }
}

public struct HUDCommand: Codable, Sendable {
    public let cmd: String
    public let text: String?
    public let command: String?
    public let mode: String?
    public let reply_policy: String?
    public let resume_mode: String?
    public let limit: Int?
    public let card_id: Int?
    public let quality: Int?
    public let req_id: String?
    public let reqId: String?
    public let ok: Bool?
    public let output: String?
    public let error_code: String?
    public let error_message: String?

    public init(
        cmd: String,
        text: String? = nil,
        command: String? = nil,
        mode: String? = nil,
        reply_policy: String? = nil,
        resume_mode: String? = nil,
        limit: Int? = nil,
        card_id: Int? = nil,
        quality: Int? = nil,
        req_id: String? = nil,
        reqId: String? = nil,
        ok: Bool? = nil,
        output: String? = nil,
        error_code: String? = nil,
        error_message: String? = nil
    ) {
        self.cmd = cmd
        self.text = text
        self.command = command
        self.mode = mode
        self.reply_policy = reply_policy
        self.resume_mode = resume_mode
        self.limit = limit
        self.card_id = card_id
        self.quality = quality
        self.req_id = req_id
        self.reqId = reqId ?? req_id
        self.ok = ok
        self.output = output
        self.error_code = error_code
        self.error_message = error_message
    }
}
