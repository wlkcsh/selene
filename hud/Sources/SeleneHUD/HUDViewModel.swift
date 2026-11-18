import Foundation
import Observation

@Observable
@MainActor
public final class HUDViewModel {
    public var agentState: AgentState = .disconnected
    public var rmsEnergy: Double = 0.0
    public var captionText: String = ""
    public var activeApp: String = ""
    public var activeWindow: String = ""
    public var selectionLen: Int = 0
    public var cardsDue: Int = 0
    public var isMuted: Bool = false
    public var isConnected: Bool = false

    private var socketClient: SocketClient?

    public init() {
        self.socketClient = SocketClient(
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
    }

    public func handleEvent(_ event: HUDEvent) {
        if let rawState = event.state, let parsed = AgentState(rawValue: rawState) {
            self.agentState = parsed
            if parsed == .idle {
                // Keep the final caption visible briefly or reset
                self.rmsEnergy = 0.0
            } else if parsed == .listening {
                self.captionText = ""
            }
        }

        if let rms = event.rms {
            // Smooth RMS amplitude for waveform
            self.rmsEnergy = min(1.0, max(0.0, rms * 4.0))
        }

        if let delta = event.text {
            self.captionText += delta
        }

        if let caption = event.caption, !caption.isEmpty {
            self.captionText = caption
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
    }

    public func interrupt() {
        socketClient?.sendCommand(HUDCommand(cmd: "interrupt"))
    }

    public func toggleMute() {
        socketClient?.sendCommand(HUDCommand(cmd: "toggle_mute"))
    }
}
