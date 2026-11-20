import AppKit
import ApplicationServices
import SwiftUI

struct MenuHeaderView: View {
    let isConnected: Bool
    let statusText: String
    let statusColor: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "moon.stars.fill")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(
                    LinearGradient(
                        colors: [.purple, .pink],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            Text("Selene")
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)

            Spacer(minLength: 16)

            HStack(spacing: 5) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 7, height: 7)
                Text(statusText)
                    .font(.system(size: 10, weight: .semibold, design: .rounded))
                    .foregroundStyle(isConnected ? .primary : .secondary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3.5)
            .background(Color.primary.opacity(0.06), in: Capsule())
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .frame(minWidth: 260)
    }
}

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
            button.image = NSImage(systemSymbolName: "moon.stars", accessibilityDescription: "Selene")?
                .withSymbolConfiguration(config)
        }
        buildMenu()
    }

    public func buildMenu() {
        let menu = NSMenu()

        // 1. Native Header Card
        let statusText: String
        let statusColor: Color
        if viewModel.isConnected {
            statusText = "Active"
            statusColor = .green
        } else if daemonManager.status == .starting {
            statusText = "Starting..."
            statusColor = .yellow
        } else {
            statusText = "Stopped"
            statusColor = .gray
        }

        let headerItem = NSMenuItem()
        let headerView = MenuHeaderView(
            isConnected: viewModel.isConnected,
            statusText: statusText,
            statusColor: statusColor
        )
        let hostingView = NSHostingView(rootView: headerView)
        hostingView.frame = NSRect(x: 0, y: 0, width: 260, height: 36)
        headerItem.view = hostingView
        menu.addItem(headerItem)

        if viewModel.cardsDue > 0 {
            let cardsItem = NSMenuItem(
                title: "Review Due Cards (\(viewModel.cardsDue) due)",
                action: #selector(reviewCards),
                keyEquivalent: ""
            )
            cardsItem.image = symbolImage(named: "book")
            cardsItem.target = self
            menu.addItem(cardsItem)
        }

        if !AXIsProcessTrusted() {
            let a11yItem = NSMenuItem(
                title: "Grant Accessibility to Selene...",
                action: #selector(requestAccessibility),
                keyEquivalent: ""
            )
            a11yItem.image = symbolImage(named: "exclamationmark.triangle", color: .systemOrange)
            a11yItem.target = self
            menu.addItem(a11yItem)
        }

        menu.addItem(NSMenuItem.separator())

        // Quick Input, Screen Vision, and Hands-Free
        let askItem = NSMenuItem(title: "Ask Selene...", action: #selector(showQuickInput), keyEquivalent: "k")
        askItem.keyEquivalentModifierMask = [.command, .shift]
        askItem.image = symbolImage(named: "bubble.left.and.bubble.right")
        askItem.target = self
        menu.addItem(askItem)

        let screenItem = NSMenuItem(title: "Capture Screen & Ask (/screen)", action: #selector(captureScreen), keyEquivalent: "s")
        screenItem.keyEquivalentModifierMask = [.command, .shift]
        screenItem.image = symbolImage(named: "camera.viewfinder")
        screenItem.target = self
        menu.addItem(screenItem)

        let handsFreeItem = NSMenuItem(
            title: "Hands-Free Study Mode",
            action: #selector(toggleHandsFreeMode),
            keyEquivalent: ""
        )
        handsFreeItem.image = symbolImage(named: "mic")
        handsFreeItem.target = self
        handsFreeItem.state = viewModel.interactionMode == .handsFree ? .on : .off
        menu.addItem(handsFreeItem)

        let langItem = NSMenuItem(title: "Speech Language", action: nil, keyEquivalent: "")
        langItem.image = symbolImage(named: "globe")
        let langSubmenu = NSMenu()

        for mode in LanguageMode.allCases {
            let item = NSMenuItem(
                title: mode.menuTitle,
                action: #selector(selectLanguageMode(_:)),
                keyEquivalent: ""
            )
            item.target = self
            item.representedObject = mode
            item.state = (viewModel.languageMode == mode) ? .on : .off
            langSubmenu.addItem(item)
        }

        langSubmenu.addItem(NSMenuItem.separator())

        let matchItem = NSMenuItem(
            title: "Match Spoken Language",
            action: #selector(setMatchLanguagePolicy),
            keyEquivalent: ""
        )
        matchItem.target = self
        matchItem.state = (viewModel.replyPolicy == .matchInput) ? .on : .off
        langSubmenu.addItem(matchItem)

        let forceEnItem = NSMenuItem(
            title: "Always Reply in English",
            action: #selector(setForceEnLanguagePolicy),
            keyEquivalent: ""
        )
        forceEnItem.target = self
        forceEnItem.state = (viewModel.replyPolicy == .alwaysEnglish) ? .on : .off
        langSubmenu.addItem(forceEnItem)

        langItem.submenu = langSubmenu
        menu.addItem(langItem)

        menu.addItem(NSMenuItem.separator())

        // Daemon Control Actions
        if viewModel.isConnected || daemonManager.status == .running {
            let restartItem = NSMenuItem(title: "Restart Voice Engine", action: #selector(restartDaemon), keyEquivalent: "")
            restartItem.image = symbolImage(named: "arrow.clockwise")
            restartItem.target = self
            menu.addItem(restartItem)

            let stopItem = NSMenuItem(title: "Stop Voice Engine", action: #selector(stopDaemon), keyEquivalent: "")
            stopItem.image = symbolImage(named: "stop.circle")
            stopItem.target = self
            menu.addItem(stopItem)
        } else {
            let startItem = NSMenuItem(title: "Start Voice Engine", action: #selector(startDaemon), keyEquivalent: "")
            startItem.image = symbolImage(named: "play.circle")
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
        hudToggle.keyEquivalentModifierMask = [.command, .shift]
        hudToggle.image = symbolImage(named: panel.isVisible ? "eye.slash" : "eye")
        hudToggle.target = self
        menu.addItem(hudToggle)

        let modeItem = NSMenuItem(title: "HUD Style", action: nil, keyEquivalent: "")
        modeItem.image = symbolImage(named: "slider.horizontal.3")
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
        muteToggle.keyEquivalentModifierMask = [.command, .shift]
        muteToggle.image = symbolImage(named: viewModel.isMuted ? "speaker.wave.2" : "speaker.slash")
        muteToggle.target = self
        menu.addItem(muteToggle)

        let resetPos = NSMenuItem(
            title: "Reset HUD Position to Top-Center",
            action: #selector(resetPosition),
            keyEquivalent: ""
        )
        resetPos.image = symbolImage(named: "arrow.counterclockwise")
        resetPos.target = self
        menu.addItem(resetPos)

        menu.addItem(NSMenuItem.separator())

        // Options
        let autoStartItem = NSMenuItem(
            title: "Auto-start Engine on Launch",
            action: #selector(toggleAutoStart),
            keyEquivalent: ""
        )
        autoStartItem.image = symbolImage(named: "bolt.badge.automatic")
        autoStartItem.target = self
        autoStartItem.state = daemonManager.autoStart ? .on : .off
        menu.addItem(autoStartItem)

        let logsItem = NSMenuItem(title: "Open Activity Log in Console...", action: #selector(openLogs), keyEquivalent: "l")
        logsItem.keyEquivalentModifierMask = [.command, .shift]
        logsItem.image = symbolImage(named: "terminal")
        logsItem.target = self
        menu.addItem(logsItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "Quit Selene", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.image = symbolImage(named: "power")
        quitItem.target = self
        menu.addItem(quitItem)

        self.statusItem.menu = menu
    }

    private func symbolImage(
        named name: String,
        color: NSColor? = nil,
        pointSize: CGFloat = 13,
        weight: NSFont.Weight = .regular
    ) -> NSImage? {
        var config = NSImage.SymbolConfiguration(pointSize: pointSize, weight: weight)
        if let color {
            config = config.applying(NSImage.SymbolConfiguration(paletteColors: [color]))
        }
        return NSImage(systemSymbolName: name, accessibilityDescription: nil)?.withSymbolConfiguration(config)
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

    @objc private func selectLanguageMode(_ sender: NSMenuItem) {
        if let mode = sender.representedObject as? LanguageMode {
            viewModel.setLanguageMode(mode: mode)
            buildMenu()
        }
    }

    @objc private func setMatchLanguagePolicy() {
        viewModel.setLanguageMode(mode: viewModel.languageMode, replyPolicy: .matchInput)
        buildMenu()
    }

    @objc private func setForceEnLanguagePolicy() {
        viewModel.setLanguageMode(mode: viewModel.languageMode, replyPolicy: .alwaysEnglish)
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
