import Foundation

public enum HUDDisplayMode: String, Codable, CaseIterable, Sendable {
    case notch
    case floating
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
}

public struct HUDCommand: Codable, Sendable {
    public let cmd: String

    public init(cmd: String) {
        self.cmd = cmd
    }
}
