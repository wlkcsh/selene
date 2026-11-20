import AppKit
import SwiftUI

public struct QuickInputView: View {
    @Bindable var viewModel: HUDViewModel
    var onDismiss: () -> Void

    @State private var inputText: String = ""
    @FocusState private var isFocused: Bool

    public var body: some View {
        VStack(spacing: 0) {
            // Main Input Row
            HStack(spacing: 12) {
                Image(systemName: "moon.stars.fill")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.purple, .pink],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )

                TextField("Ask Selene anything, or type /cards, /screen, /memory...", text: $inputText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14, weight: .medium, design: .rounded))
                    .focused($isFocused)
                    .onSubmit {
                        submit()
                    }

                if !inputText.isEmpty {
                    Button(action: { inputText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }

                Button(action: submit) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(
                            inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? Color.secondary.opacity(0.35)
                                : Color.purple
                        )
                }
                .buttonStyle(.plain)
                .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)

            // Subtle Hairline Divider
            Rectangle()
                .fill(Color.white.opacity(0.08))
                .frame(height: 0.5)

            // Footer Telemetry & Shortcuts
            HStack(spacing: 12) {
                Text("Press Return ↵ to send • Esc to close")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)

                Spacer()

                if viewModel.cardsDue > 0 {
                    Button(action: {
                        viewModel.sendSlash("/cards")
                        onDismiss()
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: "book.fill")
                                .font(.system(size: 9))
                            Text("\(viewModel.cardsDue) Cards Due")
                                .font(.system(size: 10, weight: .semibold, design: .rounded))
                        }
                        .foregroundStyle(.purple)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 2.5)
                        .background(Color.purple.opacity(0.15), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.black.opacity(0.12))
        }
        .frame(width: 540)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.14), lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .onAppear {
            isFocused = true
        }
    }

    private func submit() {
        let trimmed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if trimmed.hasPrefix("/") {
            viewModel.sendSlash(trimmed)
        } else {
            viewModel.sendText(trimmed)
        }
        inputText = ""
        onDismiss()
    }
}

public final class QuickInputPanel: NSPanel {
    private let viewModel: HUDViewModel

    public init(viewModel: HUDViewModel) {
        self.viewModel = viewModel
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 540, height: 86),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = true
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        self.isMovableByWindowBackground = true

        let rootView = QuickInputView(viewModel: viewModel) { [weak self] in
            self?.closePanel()
        }
        self.contentView = NSHostingView(rootView: rootView)
    }

    public override var canBecomeKey: Bool {
        return true
    }

    public override var canBecomeMain: Bool {
        return true
    }

    public override func cancelOperation(_ sender: Any?) {
        closePanel()
    }

    public func showPanel() {
        if let screen = NSScreen.main {
            let screenFrame = screen.visibleFrame
            let x = screenFrame.midX - (self.frame.width / 2)
            let y = screenFrame.midY + (screenFrame.height * 0.15)
            self.setFrameOrigin(NSPoint(x: x, y: y))
        }
        self.invalidateShadow()
        self.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    public func closePanel() {
        self.orderOut(nil)
    }
}
