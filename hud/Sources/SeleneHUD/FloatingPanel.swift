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

    public override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }

    public override func hitTest(_ point: NSPoint) -> NSView? {
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
                .borderless,
                .nonactivatingPanel
            ],
            backing: .buffered,
            defer: false
        )

        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.isMovableByWindowBackground = true
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false
        self.level = .floating
        self.collectionBehavior = [
            .canJoinAllSpaces,
            .fullScreenAuxiliary,
            .transient
        ]
        self.becomesKeyOnlyIfNeeded = true

        let hostingView = PassThroughHostingView(rootView: HUDView(model: viewModel))
        hostingView.sizingOptions = [] // Prevent SwiftUI intrinsic constraints from fighting panel spring resize
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
            self?.reposition(animated: false)
        }

        viewModel.onWingExpandedChange = { [weak self] _ in
            self?.reposition(animated: true)
        }

        self.screenObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.reposition(animated: false)
        }

        self.reposition(animated: false)
    }

    public func reposition(animated: Bool = false) {
        guard let screen = NSScreen.main else { return }
        let targetSize = viewModel.isWingExpanded
            ? NSSize(width: 500, height: 300)
            : NSSize(width: 620, height: 100)

        let targetOrigin: NSPoint
        if viewModel.displayMode == .notch && screen.hasPhysicalNotch {
            self.level = .statusBar
            self.isMovableByWindowBackground = false
            let x = screen.frame.midX - (targetSize.width / 2.0)
            let y = screen.frame.maxY - targetSize.height + 2.0
            targetOrigin = NSPoint(x: x, y: y)
        } else {
            self.level = .floating
            self.isMovableByWindowBackground = true
            let screenRect = screen.visibleFrame
            let x = screenRect.midX - (targetSize.width / 2.0)
            let y = screenRect.maxY - targetSize.height - 18.0
            targetOrigin = NSPoint(x: x, y: y)
        }

        let targetFrame = NSRect(origin: targetOrigin, size: targetSize)
        if animated {
            if #available(macOS 15.0, *) {
                let spring = Animation.spring(response: 0.28, dampingFraction: 0.86)
                NSAnimationContext.animate(spring) {
                    self.animator().setFrame(targetFrame, display: true)
                }
            } else {
                NSAnimationContext.runAnimationGroup { context in
                    context.duration = 0.28
                    context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                    self.animator().setFrame(targetFrame, display: true)
                }
            }
        } else {
            self.setFrame(targetFrame, display: true)
        }
    }

    public override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect {
        return frameRect
    }

    public func repositionTopCenter() {
        reposition(animated: false)
    }
}
