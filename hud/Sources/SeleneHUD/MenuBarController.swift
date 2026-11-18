import AppKit

@MainActor
public final class MenuBarController: NSObject {
    private var statusItem: NSStatusItem!
    private let viewModel: HUDViewModel
    private let panel: FloatingPanel

    public init(viewModel: HUDViewModel, panel: FloatingPanel) {
        self.viewModel = viewModel
        self.panel = panel
        super.init()
        self.setupStatusItem()
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

        let statusStr = viewModel.isConnected ? "🟢 Daemon: Connected" : "🟠 Daemon: Offline (/tmp/selene.sock)"
        let statusItem = NSMenuItem(title: statusStr, action: nil, keyEquivalent: "")
        statusItem.isEnabled = false
        menu.addItem(statusItem)

        if viewModel.cardsDue > 0 {
            let cardsItem = NSMenuItem(title: "📚 \(viewModel.cardsDue) Study Cards Due", action: nil, keyEquivalent: "")
            cardsItem.isEnabled = false
            menu.addItem(cardsItem)
        }

        menu.addItem(NSMenuItem.separator())

        let hudToggle = NSMenuItem(
            title: panel.isVisible ? "Hide HUD" : "Show HUD",
            action: #selector(toggleHUD),
            keyEquivalent: "h"
        )
        hudToggle.target = self
        menu.addItem(hudToggle)

        let modeItem = NSMenuItem(title: "Display Mode", action: nil, keyEquivalent: "")
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

        let quitItem = NSMenuItem(title: "Quit Selene HUD", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        self.statusItem.menu = menu
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
        NSApplication.shared.terminate(nil)
    }
}
