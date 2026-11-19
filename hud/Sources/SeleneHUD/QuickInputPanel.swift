import AppKit
import SwiftUI

public struct QuickInputView: View {
    @Bindable var viewModel: HUDViewModel
    var onDismiss: () -> Void

    @State private var inputText: String = ""
    @FocusState private var isFocused: Bool

    public var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: "sparkles")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.purple)

                TextField("Ask Selene anything, or type /cards, /screen, /memory...", text: $inputText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14, weight: .regular, design: .rounded))
                    .focused($isFocused)
                    .onSubmit {
                        submit()
                    }

                if !inputText.isEmpty {
                    Button(action: { inputText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }

                Button(action: submit) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(inputText.isEmpty ? Color.secondary : Color.purple)
                }
                .buttonStyle(.plain)
                .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color(nsColor: .windowBackgroundColor).opacity(0.85))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(Color.purple.opacity(0.3), lineWidth: 1)
            )

            HStack {
                Text("Press Return to send • Esc to close")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if viewModel.cardsDue > 0 {
                    Button(action: {
                        viewModel.sendSlash("/cards")
                        onDismiss()
                    }) {
                        Text("📚 \(viewModel.cardsDue) Cards Due")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.purple)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 4)
        }
        .padding(14)
        .frame(width: 520)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color.white.opacity(0.15), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.25), radius: 20, x: 0, y: 10)
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
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 90),
            styleMask: [.nonactivatingPanel, .titled, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )

        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.isOpaque = false
        self.backgroundColor = .clear
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        self.isMovableByWindowBackground = true

        let rootView = QuickInputView(viewModel: viewModel) { [weak self] in
            self?.closePanel()
        }
        self.contentView = NSHostingView(rootView: rootView)
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
        self.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    public func closePanel() {
        self.orderOut(nil)
    }
}
