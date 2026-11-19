import AppKit
import ApplicationServices

@MainActor
public final class MenuBarController: NSObject {
    private var statusItem: NSStatusItem!
    private let viewModel: HUDViewModel
    private let panel: FloatingPanel
    private let daemonManager: DaemonManager
    private let quickInputPanel: QuickInputPanel

    public init(
        viewModel: HUDViewModel,
        panel: FloatingPanel,
        daemonManager: DaemonManager,
        quickInputPanel: QuickInputPanel
    ) {
        self.viewModel = viewModel
        self.panel = panel
        self.daemonManager = daemonManager
        self.quickInputPanel = quickInputPanel
        super.init()

        self.setupStudyDeckBridge()
        self.setupStatusItem()
    }

    private func setupStudyDeckBridge() {
        viewModel.onDueCardsReceived = { cards in
            StudyDeckWindowController.shared.present(cards: cards)
        }
        StudyDeckWindowController.shared.viewModel.onGradeCard = { [weak viewModel] cardId, quality in
            viewModel?.gradeCard(cardId: cardId, quality: quality)
        }
        StudyDeckWindowController.shared.viewModel.onReplayAudio = { [weak viewModel] text in
            viewModel?.replayAudio(text: text)
        }
    }

    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .medium)
            button.image = NSImage(systemSymbolName: "sparkles", accessibilityDescription: "Selene")?
                .withSymbolConfiguration(config)
        }
        buildMenu()
    }

    public func buildMenu() {
        let menu = NSMenu()

        let titleItem = NSMenuItem(title: "💖 Selene Anime Mentor", action: nil, keyEquivalent: "")
        titleItem.isEnabled = false
        menu.addItem(titleItem)

        // Daemon Status
        let statusStr: String
        if viewModel.isConnected {
            statusStr = "🟢 Voice Engine: Active"
        } else if daemonManager.status == .starting {
            statusStr = "🟡 Voice Engine: Starting..."
        } else {
            statusStr = "⚪ Voice Engine: Stopped"
        }

        let statusMenuItem = NSMenuItem(title: statusStr, action: nil, keyEquivalent: "")
        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)

        if viewModel.cardsDue > 0 {
            let cardsItem = NSMenuItem(title: "📚 Review Due Cards (\(viewModel.cardsDue) due)", action: #selector(reviewCards), keyEquivalent: "")
            cardsItem.target = self
            menu.addItem(cardsItem)
        }

        if !AXIsProcessTrusted() {
            let a11yItem = NSMenuItem(
                title: "⚠️ Grant Accessibility to Selene...",
                action: #selector(requestAccessibility),
                keyEquivalent: ""
            )
            a11yItem.target = self
            menu.addItem(a11yItem)
        }

        menu.addItem(NSMenuItem.separator())

        // Quick Input, Screen Vision, and Hands-Free
        let askItem = NSMenuItem(title: "💬 Ask Selene...", action: #selector(showQuickInput), keyEquivalent: "k")
        askItem.target = self
        menu.addItem(askItem)

        let screenItem = NSMenuItem(title: "📸 Capture Screen & Ask (/screen)", action: #selector(captureScreen), keyEquivalent: "s")
        screenItem.target = self
        menu.addItem(screenItem)

        let handsFreeItem = NSMenuItem(
            title: "🎙️ Hands-Free Study Mode",
            action: #selector(toggleHandsFreeMode),
            keyEquivalent: ""
        )
        handsFreeItem.target = self
        handsFreeItem.state = viewModel.interactionMode == .handsFree ? .on : .off
        menu.addItem(handsFreeItem)

        menu.addItem(NSMenuItem.separator())

        // Daemon Control Actions
        if viewModel.isConnected || daemonManager.status == .running {
            let restartItem = NSMenuItem(title: "🔄 Restart Voice Engine", action: #selector(restartDaemon), keyEquivalent: "")
            restartItem.target = self
            menu.addItem(restartItem)

            let stopItem = NSMenuItem(title: "⏹ Stop Voice Engine", action: #selector(stopDaemon), keyEquivalent: "")
            stopItem.target = self
            menu.addItem(stopItem)
        } else {
            let startItem = NSMenuItem(title: "▶️ Start Voice Engine", action: #selector(startDaemon), keyEquivalent: "")
            startItem.target = self
            menu.addItem(startItem)
        }

        menu.addItem(NSMenuItem.separator())

        // HUD Controls
        let hudToggle = NSMenuItem(
            title: panel.isVisible ? "Hide Floating HUD" : "Show Floating HUD",
            action: #selector(toggleHUD),
            keyEquivalent: "h"
        )
        hudToggle.target = self
        menu.addItem(hudToggle)

        let modeItem = NSMenuItem(title: "HUD Style", action: nil, keyEquivalent: "")
        let modeSubmenu = NSMenu()

        let notchItem = NSMenuItem(
            title: "Notch Island",
            action: #selector(setNotchMode),
            keyEquivalent: "1"
        )
        notchItem.target = self
        notchItem.state = viewModel.displayMode == .notch ? .on : .off

        let floatItem = NSMenuItem(
            title: "Floating Pill",
            action: #selector(setFloatingMode),
            keyEquivalent: "2"
        )
        floatItem.target = self
        floatItem.state = viewModel.displayMode == .floating ? .on : .off

        modeSubmenu.addItem(notchItem)
        modeSubmenu.addItem(floatItem)
        modeItem.submenu = modeSubmenu
        menu.addItem(modeItem)

        let muteTitle = viewModel.isMuted ? "Unmute Voice" : "Mute Voice"
        let muteToggle = NSMenuItem(
            title: muteTitle,
            action: #selector(toggleMute),
            keyEquivalent: "m"
        )
        muteToggle.target = self
        menu.addItem(muteToggle)

        let resetPos = NSMenuItem(
            title: "Reset HUD Position to Top-Center",
            action: #selector(resetPosition),
            keyEquivalent: "r"
        )
        resetPos.target = self
        menu.addItem(resetPos)

        menu.addItem(NSMenuItem.separator())

        // Options
        let autoStartItem = NSMenuItem(
            title: "Auto-start Engine on Launch",
            action: #selector(toggleAutoStart),
            keyEquivalent: ""
        )
        autoStartItem.target = self
        autoStartItem.state = daemonManager.autoStart ? .on : .off
        menu.addItem(autoStartItem)

        let logsItem = NSMenuItem(title: "Open Activity Log in Console...", action: #selector(openLogs), keyEquivalent: "l")
        logsItem.target = self
        menu.addItem(logsItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "Quit Selene", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        self.statusItem.menu = menu
    }

    @objc private func showQuickInput() {
        quickInputPanel.showPanel()
    }

    @objc private func captureScreen() {
        viewModel.requestScreenVision()
    }

    @objc private func reviewCards() {
        viewModel.fetchDueCards()
    }

    @objc private func requestAccessibility() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
        _ = AXIsProcessTrustedWithOptions(options as CFDictionary)
        buildMenu()
    }

    @objc private func toggleHandsFreeMode() {
        let newMode = viewModel.interactionMode == .handsFree ? "ptt" : "hands_free"
        viewModel.sendRawCommand("set_mode", payload: ["mode": newMode])
        viewModel.interactionMode = newMode == "hands_free" ? .handsFree : .ptt
        buildMenu()
    }

    @objc private func startDaemon() {
        daemonManager.startDaemon()
        buildMenu()
    }

    @objc private func stopDaemon() {
        viewModel.requestQuitDaemon()
        daemonManager.stopDaemon()
        buildMenu()
    }

    @objc private func restartDaemon() {
        viewModel.requestQuitDaemon()
        daemonManager.restartDaemon()
        buildMenu()
    }

    @objc private func toggleAutoStart() {
        daemonManager.autoStart.toggle()
        buildMenu()
    }

    @objc private func openLogs() {
        daemonManager.openLogs()
    }

    @objc private func toggleHUD() {
        if panel.isVisible {
            panel.orderOut(nil)
        } else {
            panel.orderFront(nil)
        }
        buildMenu()
    }

    @objc private func setNotchMode() {
        viewModel.setDisplayMode(.notch)
        buildMenu()
    }

    @objc private func setFloatingMode() {
        viewModel.setDisplayMode(.floating)
        buildMenu()
    }

    @objc private func toggleMute() {
        viewModel.toggleMute()
        buildMenu()
    }

    @objc private func resetPosition() {
        panel.repositionTopCenter()
    }

    @objc private func quitApp() {
        viewModel.requestQuitDaemon()
        daemonManager.stopDaemon()
        NSApplication.shared.terminate(nil)
    }
}
