import AppKit
import Foundation
import Observation

@Observable
@MainActor
public final class HUDViewModel {
    public var agentState: AgentState = .disconnected
    public var rmsEnergy: Double = 0.0
    public var captionText: String = ""
    public var streamingMarkdown: String = ""
    public var isWingExpanded: Bool = false {
        didSet {
            onWingExpandedChange?(isWingExpanded)
        }
    }
    public var interactionMode: InteractionMode = .ptt
    public var activeApp: String = ""
    public var activeWindow: String = ""
    public var selectionLen: Int = 0
    public var cardsDue: Int = 0
    public var isMuted: Bool = false
    public var isConnected: Bool = false
    public var languageMode: LanguageMode = .auto {
        didSet {
            UserDefaults.standard.set(languageMode.rawValue, forKey: "selene_hud_language_mode")
        }
    }
    public var replyPolicy: ReplyLanguagePolicy = .matchInput
    public var lastDetectedLanguage: String = "en"

    public var languageBadgeText: String {
        if languageMode == .auto {
            return "AUTO • \(lastDetectedLanguage.uppercased())"
        }
        return languageMode.badgeTitle
    }
    public var displayMode: HUDDisplayMode = .notch {
        didSet {
            UserDefaults.standard.set(displayMode.rawValue, forKey: "selene_hud_display_mode")
            onDisplayModeChange?(displayMode)
        }
    }
    public var onPillFrameChange: ((CGRect) -> Void)?
    public var onDisplayModeChange: ((HUDDisplayMode) -> Void)?
    public var onConnectionChange: ((Bool) -> Void)?
    public var onWingExpandedChange: ((Bool) -> Void)?
    public var onDueCardsReceived: (([StudyCard]) -> Void)?

    private var socketClient: SocketClient?

    public init(socketPath: String = "/tmp/selene.sock") {
        if let saved = UserDefaults.standard.string(forKey: "selene_hud_display_mode"),
           let mode = HUDDisplayMode(rawValue: saved) {
            self.displayMode = mode
        } else {
            self.displayMode = .notch
        }

        if let savedLang = UserDefaults.standard.string(forKey: "selene_hud_language_mode"),
           let mode = LanguageMode(rawValue: savedLang) {
            self.languageMode = mode
        } else {
            self.languageMode = .auto
        }

        self.socketClient = SocketClient(
            socketPath: socketPath,
            onEvent: { [weak self] event in
                self?.handleEvent(event)
            },
            onConnectionChange: { [weak self] connected in
                self?.handleConnectionChange(connected)
            }
        )
        self.socketClient?.start()
    }

    public func handleConnectionChange(_ connected: Bool) {
        self.isConnected = connected
        if !connected {
            self.agentState = .disconnected
        }
        onConnectionChange?(connected)
    }

    public func handleEvent(_ event: HUDEvent) {
        if event.type == "due_cards", let cards = event.cards {
            onDueCardsReceived?(cards)
            return
        }

        if let rawMode = event.mode, let parsedMode = InteractionMode(rawValue: rawMode) {
            self.interactionMode = parsedMode
        }

        if let rawState = event.state, let parsed = AgentState(rawValue: rawState) {
            let previousState = self.agentState
            self.agentState = parsed
            if parsed != previousState {
                if parsed == .listening {
                    performHaptic(.alignment)
                } else if parsed == .speaking {
                    performHaptic(.generic)
                }
            }

            if parsed == .idle {
                self.rmsEnergy = 0.0
            } else if parsed == .listening {
                self.captionText = ""
                self.streamingMarkdown = ""
            } else if parsed == .speaking && previousState != .speaking {
                // Clear previous thinking/query text so Selene's response streams cleanly
                self.captionText = ""
                self.streamingMarkdown = ""
            }
        }

        if let rms = event.rms {
            self.rmsEnergy = min(1.0, max(0.0, rms * 4.0))
        }

        if let caption = event.caption {
            self.captionText = caption
        }

        if let delta = event.text {
            self.captionText += delta
            self.streamingMarkdown += delta
        }

        if let app = event.app {
            self.activeApp = app
        }
        if let win = event.window {
            self.activeWindow = win
        }
        if let selLen = event.selection_len {
            self.selectionLen = selLen
        }
        if let cards = event.cards_due {
            self.cardsDue = cards
        }
        if let muted = event.muted {
            self.isMuted = muted
        }
        if let rawLang = event.language_mode, let parsed = LanguageMode(rawValue: rawLang) {
            self.languageMode = parsed
        }
        if let rawPolicy = event.reply_policy, let parsed = ReplyLanguagePolicy(rawValue: rawPolicy) {
            self.replyPolicy = parsed
        }
        if let detected = event.last_detected {
            self.lastDetectedLanguage = detected
        }
    }

    public func setLanguageMode(mode: LanguageMode, replyPolicy: ReplyLanguagePolicy? = nil) {
        performHaptic(.alignment)
        self.languageMode = mode
        let policy = replyPolicy ?? self.replyPolicy
        self.replyPolicy = policy
        socketClient?.sendCommand(HUDCommand(
            cmd: "set_language",
            mode: mode.rawValue,
            reply_policy: policy.rawValue
        ))
    }

    public func cycleLanguageMode() {
        setLanguageMode(mode: languageMode.nextMode)
    }

    public func interrupt() {
        performHaptic(.levelChange)
        socketClient?.sendCommand(HUDCommand(cmd: "interrupt"))
    }

    public func toggleMute() {
        performHaptic(.generic)
        socketClient?.sendCommand(HUDCommand(cmd: "toggle_mute"))
    }

    public func sendText(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        performHaptic(.generic)
        socketClient?.sendCommand(HUDCommand(cmd: "text", text: trimmed))
    }

    public func sendSlash(_ command: String) {
        let trimmed = command.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        performHaptic(.generic)
        socketClient?.sendCommand(HUDCommand(cmd: "slash", command: trimmed))
    }

    public func sendRawCommand(_ cmd: String, payload: [String: String] = [:]) {
        socketClient?.sendCommand(HUDCommand(
            cmd: cmd,
            mode: payload["mode"],
            resume_mode: payload["resume_mode"]
        ))
    }

    public func fetchDueCards(limit: Int = 20) {
        socketClient?.sendCommand(HUDCommand(cmd: "fetch_due_cards", limit: limit))
    }

    public func gradeCard(cardId: Int, quality: Int) {
        socketClient?.sendCommand(HUDCommand(cmd: "grade_card", card_id: cardId, quality: quality))
    }

    public func replayAudio(text: String) {
        socketClient?.sendCommand(HUDCommand(cmd: "speak_text", text: text))
    }

    public func requestScreenVision() {
        sendSlash("/screen")
    }

    public func requestQuitDaemon() {
        socketClient?.sendCommand(HUDCommand(cmd: "quit"))
    }

    public func requestStatus() {
        socketClient?.sendCommand(HUDCommand(cmd: "get_status"))
    }

    public func setDisplayMode(_ mode: HUDDisplayMode) {
        performHaptic(.alignment)
        self.displayMode = mode
    }

    public func toggleWing() {
        performHaptic(.alignment)
        isWingExpanded.toggle()
    }

    private func performHaptic(_ pattern: NSHapticFeedbackManager.FeedbackPattern = .generic) {
        NSHapticFeedbackManager.defaultPerformer.perform(pattern, performanceTime: .default)
    }
}
