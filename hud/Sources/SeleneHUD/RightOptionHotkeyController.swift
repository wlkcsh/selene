import AppKit
import ApplicationServices

@MainActor
public final class RightOptionHotkeyController {
    private static let rightOptionKeyCode: UInt16 = 61 // kVK_RightOption (0x3D)
    private let holdThreshold: TimeInterval = 0.22
    private let doubleTapWindow: TimeInterval = 0.30

    private var globalMonitor: Any?
    private var localMonitor: Any?
    private var isRightOptionDown = false
    private var wasChording = false
    private var pressStartTime: Date?
    private var lastQuickTapTime: Date?

    public var mode: InteractionMode = .ptt
    public var agentState: AgentState = .idle
    public var onSendCommand: ((_ cmd: String, _ payload: [String: String]) -> Void)?

    public init() {}

    @discardableResult
    public func checkAccessibilityPermissions(prompt: Bool = false) -> Bool {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: prompt]
        return AXIsProcessTrustedWithOptions(options as CFDictionary)
    }

    public func start() {
        _ = checkAccessibilityPermissions(prompt: true)

        // Global monitor catches events when Xcode/Cursor/browsers are active
        globalMonitor = NSEvent.addGlobalMonitorForEvents(
            matching: [.flagsChanged, .keyDown]
        ) { [weak self] event in
            MainActor.assumeIsolated { self?.handle(event) }
        }

        // Local monitor catches events when Selene's windows/panels are key
        localMonitor = NSEvent.addLocalMonitorForEvents(
            matching: [.flagsChanged, .keyDown]
        ) { [weak self] event in
            MainActor.assumeIsolated { self?.handle(event) }
            return event
        }
    }

    public func stop() {
        if let globalMonitor { NSEvent.removeMonitor(globalMonitor) }
        if let localMonitor { NSEvent.removeMonitor(localMonitor) }
        globalMonitor = nil
        localMonitor = nil
    }

    private func handle(_ event: NSEvent) {
        if event.type == .keyDown {
            if isRightOptionDown {
                wasChording = true
                onSendCommand?("ptt_cancel", [:])
            }
            return
        }

        guard event.type == .flagsChanged, event.keyCode == Self.rightOptionKeyCode else {
            return
        }

        let pressed = event.modifierFlags.contains(.option)
        if pressed && !isRightOptionDown {
            isRightOptionDown = true
            wasChording = false
            handleKeyDown()
        } else if !pressed && isRightOptionDown {
            isRightOptionDown = false
            handleKeyUp()
        }
    }

    private func handleKeyDown() {
        pressStartTime = Date()

        switch mode {
        case .ptt:
            // Optimistic start: 0ms latency; if released <220ms, ptt_cancel discards buffer.
            onSendCommand?("ptt_start", [:])

        case .handsFree:
            if agentState == .speaking || agentState == .thinking {
                // Single tap during speech triggers immediate barge-in and keeps hands-free active
                onSendCommand?("barge_in", ["resume_mode": "hands_free"])
            } else {
                // Single tap while idle/listening exits hands-free mode
                mode = .ptt
                lastQuickTapTime = nil
                onSendCommand?("set_mode", ["mode": "ptt"])
            }
        }
    }

    private func handleKeyUp() {
        defer {
            pressStartTime = nil
            wasChording = false
        }

        guard mode == .ptt, let start = pressStartTime else { return }
        if wasChording { return }

        let now = Date()
        let duration = now.timeIntervalSince(start)

        if duration >= holdThreshold {
            lastQuickTapTime = nil
            onSendCommand?("ptt_commit", [:])
            return
        }

        // Quick tap (<220ms): cancel optimistic recording and evaluate double-tap
        onSendCommand?("ptt_cancel", [:])

        if let prevTap = lastQuickTapTime, now.timeIntervalSince(prevTap) <= doubleTapWindow {
            lastQuickTapTime = nil
            mode = .handsFree
            onSendCommand?("set_mode", ["mode": "hands_free"])
        } else {
            lastQuickTapTime = now
        }
    }
}
