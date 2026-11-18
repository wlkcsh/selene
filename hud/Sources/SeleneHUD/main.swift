import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var viewModel: HUDViewModel!
    private var floatingPanel: FloatingPanel!
    private var menuBarController: MenuBarController!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.accessory)

        viewModel = HUDViewModel()
        floatingPanel = FloatingPanel(viewModel: viewModel)
        menuBarController = MenuBarController(viewModel: viewModel, panel: floatingPanel)

        floatingPanel.orderFront(nil)
    }
}

MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
