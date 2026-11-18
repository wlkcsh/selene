import AppKit
import SwiftUI

extension NSScreen {
    public var hasPhysicalNotch: Bool {
        return self.auxiliaryTopLeftArea != nil && self.auxiliaryTopRightArea != nil
    }

    public var notchHeight: CGFloat {
        return self.safeAreaInsets.top
    }

    public var notchWidth: CGFloat {
        guard let left = self.auxiliaryTopLeftArea, let right = self.auxiliaryTopRightArea else { return 0 }
        return right.minX - left.maxX
    }
}

public final class PassThroughHostingView<Content: View>: NSHostingView<Content> {
    public var pillFrame: NSRect = .zero

    public override func hitTest(_ point: NSPoint) -> NSView? {
        // If point is outside the active pill capsule (+4pt margin), return nil so clicks pass through to Cursor/Chrome/Kitty
        if !pillFrame.isEmpty && !pillFrame.insetBy(dx: -4, dy: -4).contains(point) {
            return nil
        }
        return super.hitTest(point)
    }
}

public final class FloatingPanel: NSPanel {
    private let viewModel: HUDViewModel
    private var screenObserver: NSObjectProtocol?

    public init(viewModel: HUDViewModel) {
        self.viewModel = viewModel
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 120),
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

        let hostingView = PassThroughHostingView(rootView: HUDView(model: viewModel))
        viewModel.onPillFrameChange = { [weak hostingView] frame in
            guard let hostingView = hostingView else { return }
            let boundsHeight = hostingView.bounds.height
            hostingView.pillFrame = NSRect(
                x: frame.minX,
                y: boundsHeight - frame.maxY,
                width: frame.width,
                height: frame.height
            )
        }
        self.contentView = hostingView

        viewModel.onDisplayModeChange = { [weak self] _ in
            self?.reposition()
        }

        self.screenObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.reposition()
        }

        self.reposition()
    }

    public func reposition() {
        guard let screen = NSScreen.main else { return }
        let panelSize = self.frame.size

        if viewModel.displayMode == .notch && screen.hasPhysicalNotch {
            self.level = .statusBar
            let x = screen.frame.midX - (panelSize.width / 2.0)
            let y = screen.frame.maxY - panelSize.height
            self.setFrameOrigin(NSPoint(x: x, y: y))
        } else {
            self.level = .floating
            let screenRect = screen.visibleFrame
            let x = screenRect.midX - (panelSize.width / 2.0)
            let y = screenRect.maxY - panelSize.height - 18.0
            self.setFrameOrigin(NSPoint(x: x, y: y))
        }
    }

    public func repositionTopCenter() {
        reposition()
    }

    deinit {
        if let observer = screenObserver {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    public override var canBecomeKey: Bool {
        return false // Strictly never steal keyboard focus from Cursor/VSCode/Kitty!
    }

    public override var canBecomeMain: Bool {
        return false
    }
}
