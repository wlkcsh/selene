import AppKit
import SwiftUI

public final class FloatingPanel: NSPanel {
    public init(viewModel: HUDViewModel) {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 240, height: 44),
            styleMask: [
                .nonactivatingPanel,
                .titled,
                .fullSizeContentView
            ],
            backing: .buffered,
            defer: false
        )

        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.isMovableByWindowBackground = true
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false // SwiftUI handles shadow on Capsule
        self.level = .floating
        self.collectionBehavior = [
            .canJoinAllSpaces,
            .fullScreenAuxiliary,
            .transient
        ]
        self.becomesKeyOnlyIfNeeded = true

        let hostingView = NSHostingView(rootView: HUDView(model: viewModel))
        self.contentView = hostingView

        self.repositionTopCenter()
    }

    public func repositionTopCenter() {
        guard let screen = NSScreen.main else { return }
        let screenRect = screen.visibleFrame
        let panelSize = self.frame.size
        let x = screenRect.midX - (panelSize.width / 2.0)
        let y = screenRect.maxY - panelSize.height - 18.0

        self.setFrameOrigin(NSPoint(x: x, y: y))
    }

    public override var canBecomeKey: Bool {
        return false // Strictly never steal keyboard focus from Cursor/VSCode/Kitty!
    }

    public override var canBecomeMain: Bool {
        return false
    }
}
