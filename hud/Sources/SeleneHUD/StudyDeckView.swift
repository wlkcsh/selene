import AppKit
import SwiftUI

@MainActor
@Observable
public final class StudyDeckViewModel {
    public var cards: [StudyCard] = []
    public var currentIndex: Int = 0
    public var isAnswerRevealed: Bool = false

    public var currentCard: StudyCard? {
        guard cards.indices.contains(currentIndex) else { return nil }
        return cards[currentIndex]
    }

    public var onGradeCard: ((_ cardId: Int, _ quality: Int) -> Void)?
    public var onReplayAudio: ((_ text: String) -> Void)?

    public init() {}

    public func revealAnswer() {
        withAnimation(.spring(response: 0.24, dampingFraction: 0.86)) {
            isAnswerRevealed = true
        }
    }

    public func submitGrade(_ quality: Int) {
        guard let card = currentCard else { return }
        onGradeCard?(card.id, quality)

        withAnimation(.spring(response: 0.26, dampingFraction: 0.86)) {
            isAnswerRevealed = false
            currentIndex += 1
        }
    }

    public func replayCurrentCardAudio() {
        guard let card = currentCard else { return }
        let spokenText = isAnswerRevealed ? card.answer : card.question
        onReplayAudio?(spokenText)
    }
}

public struct StudyDeckView: View {
    public let viewModel: StudyDeckViewModel
    @FocusState private var isDeckFocused: Bool

    public var body: some View {
        Group {
            if let card = viewModel.currentCard {
                VStack(alignment: .leading, spacing: 18) {
                    // Header Progress + Topic + Replay Trigger
                    HStack {
                        Text("Card \(viewModel.currentIndex + 1) of \(viewModel.cards.count)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)

                        Text("•  \(card.topic)")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(.purple)

                        Spacer()

                        Button {
                            viewModel.replayCurrentCardAudio()
                        } label: {
                            Label("Replay Voice (R)", systemImage: "speaker.wave.2.fill")
                                .font(.caption)
                        }
                        .buttonStyle(.bordered)
                    }

                    // Question / Prompt
                    Text(LocalizedStringKey(card.question))
                        .font(.title3.weight(.semibold))
                        .textSelection(.enabled)

                    if viewModel.isAnswerRevealed {
                        Divider()

                        ScrollView {
                            Text(LocalizedStringKey(card.answer))
                                .font(.body)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                    }

                    Spacer()

                    // Action Footer
                    if !viewModel.isAnswerRevealed {
                        Button("Reveal Answer (Space)") {
                            viewModel.revealAnswer()
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.purple)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                    } else {
                        HStack(spacing: 10) {
                            gradeButton(title: "1 • Again", quality: 1, tint: .red)
                            gradeButton(title: "2 • Hard", quality: 3, tint: .orange)
                            gradeButton(title: "3 • Good", quality: 4, tint: .blue)
                            gradeButton(title: "4 • Easy", quality: 5, tint: .green)
                        }
                    }
                }
                .padding(24)
            } else {
                ContentUnavailableView(
                    "Session Complete",
                    systemImage: "checkmark.seal.fill",
                    description: Text("All due cards reviewed. Press Esc to close.")
                )
            }
        }
        .frame(minWidth: 560, minHeight: 400)
        .focusable()
        .focusEffectDisabled()
        .focused($isDeckFocused)
        .onAppear { isDeckFocused = true }
        .onKeyPress { press in
            handleKeyPress(press)
        }
    }

    private func gradeButton(title: String, quality: Int, tint: Color) -> some View {
        Button(title) {
            viewModel.submitGrade(quality)
        }
        .buttonStyle(.borderedProminent)
        .tint(tint)
        .frame(maxWidth: .infinity)
    }

    private func handleKeyPress(_ press: KeyPress) -> KeyPress.Result {
        if press.key == .escape {
            StudyDeckWindowController.shared.close()
            return .handled
        }
        if press.characters.lowercased() == "r" {
            viewModel.replayCurrentCardAudio()
            return .handled
        }
        if press.key == .space, !viewModel.isAnswerRevealed {
            viewModel.revealAnswer()
            return .handled
        }
        if viewModel.isAnswerRevealed {
            switch press.characters {
            case "1": viewModel.submitGrade(1); return .handled
            case "2": viewModel.submitGrade(3); return .handled
            case "3": viewModel.submitGrade(4); return .handled
            case "4": viewModel.submitGrade(5); return .handled
            default: break
            }
        }
        return .ignored
    }
}

@MainActor
public final class StudyDeckWindowController: NSWindowController, NSWindowDelegate {
    public static let shared = StudyDeckWindowController()
    public let viewModel = StudyDeckViewModel()

    private init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 640, height: 460),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Selene • Study Deck"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.center()

        super.init(window: window)
        window.delegate = self

        let hostingController = NSHostingController(rootView: StudyDeckView(viewModel: viewModel))
        window.contentViewController = hostingController
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError() }

    public func present(cards: [StudyCard]) {
        viewModel.cards = cards
        viewModel.currentIndex = 0
        viewModel.isAnswerRevealed = false

        // Temporarily elevate to .regular so Cmd+Tab and WindowServer key focus work cleanly
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
    }

    public func windowWillClose(_ notification: Notification) {
        // Restore pure menu-bar accessory state when Study Deck closes
        NSApp.setActivationPolicy(.accessory)
    }
}
