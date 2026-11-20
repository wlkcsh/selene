import AppKit
import Carbon
import Foundation

public enum AutomationPermissionStatus: String, Sendable {
    case granted
    case needsPrompt = "needs_prompt"
    case denied
    case targetNotRunning = "target_not_running"
}

public actor AutomationPermissionGuard {
    public init() {}

    /// Launches target app silently in background if closed, then checks AppleEvents TCC off the main thread.
    public func ensureAuthorized(bundleID: String, promptIfNeeded: Bool = true) async -> AutomationPermissionStatus {
        if NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).isEmpty {
            guard await launchSilently(bundleID: bundleID) else {
                return .targetNotRunning
            }
            // Give target app a moment to register its AppleEvent port
            try? await Task.sleep(for: .milliseconds(450))
        }

        let initial = checkPermission(bundleID: bundleID, askUser: false)
        if initial == .needsPrompt && promptIfNeeded {
            // Safe to block inside Task.detached; never runs on @MainActor
            return await Task.detached(priority: .userInitiated) { [self] in
                self.checkPermission(bundleID: bundleID, askUser: true)
            }.value
        }
        return initial
    }

    nonisolated private func checkPermission(bundleID: String, askUser: Bool) -> AutomationPermissionStatus {
        let targetDesc = NSAppleEventDescriptor(bundleIdentifier: bundleID)
        let status = AEDeterminePermissionToAutomateTarget(
            targetDesc.aeDesc,
            typeWildCard,
            typeWildCard,
            askUser
        )

        switch status {
        case noErr:
            return .granted
        case OSStatus(errAEEventWouldRequireUserConsent): // -1744
            return .needsPrompt
        case OSStatus(errAEEventNotPermitted):           // -1743
            return .denied
        case OSStatus(procNotFound):                     // -600
            return .targetNotRunning
        default:
            return .denied
        }
    }

    @MainActor
    private func launchSilently(bundleID: String) async -> Bool {
        guard let appURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleID) else {
            return false
        }
        let config = NSWorkspace.OpenConfiguration()
        config.activates = false
        config.hides = true
        do {
            _ = try await NSWorkspace.shared.openApplication(at: appURL, configuration: config)
            return true
        } catch {
            return false
        }
    }

    @MainActor
    public func openAutomationSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation") {
            NSWorkspace.shared.open(url)
        }
    }
}
