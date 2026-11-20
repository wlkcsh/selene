import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var viewModel: HUDViewModel!
    private var daemonManager: DaemonManager!
    private var floatingPanel: FloatingPanel!
    private var quickInputPanel: QuickInputPanel!
    private var menuBarController: MenuBarController!
    private var hotkeyController: RightOptionHotkeyController!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.accessory)

        let socketPath = ProcessInfo.processInfo.environment["SELENE_SOCKET_PATH"] ?? "/tmp/selene.sock"
        viewModel = HUDViewModel(socketPath: socketPath)
        daemonManager = DaemonManager()
        floatingPanel = FloatingPanel(viewModel: viewModel)
        quickInputPanel = QuickInputPanel(viewModel: viewModel)
        menuBarController = MenuBarController(
            viewModel: viewModel,
            panel: floatingPanel,
            daemonManager: daemonManager,
            quickInputPanel: quickInputPanel
        )

        hotkeyController = RightOptionHotkeyController()
        hotkeyController.onSendCommand = { [weak self] cmd, payload in
            self?.viewModel.sendRawCommand(cmd, payload: payload)
        }
        hotkeyController.onQuickInputRequested = { [weak self] in
            self?.quickInputPanel.showPanel()
        }
        hotkeyController.start()

        viewModel.onConnectionChange = { [weak self] _ in
            self?.menuBarController.buildMenu()
        }

        floatingPanel.orderFront(nil)
        floatingPanel.reposition(animated: false)

        if daemonManager.autoStart {
            daemonManager.startDaemon()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        hotkeyController?.stop()
        viewModel.requestQuitDaemon()
        daemonManager.stopDaemon()
    }
}

MainActor.assumeIsolated {
    let myBundleID = Bundle.main.bundleIdentifier ?? "com.selene.assistant"
    let currentPID = ProcessInfo.processInfo.processIdentifier
    let existing = NSRunningApplication.runningApplications(withBundleIdentifier: myBundleID)
        .filter { $0.processIdentifier != currentPID }

    if !existing.isEmpty {
        // Another instance of Selene is already active; exit cleanly to prevent duplicates
        exit(0)
    }

    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
