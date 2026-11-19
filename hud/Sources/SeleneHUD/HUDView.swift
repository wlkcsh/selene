import SwiftUI

public struct PillFrameKey: PreferenceKey {
    public static var defaultValue: CGRect = .zero
    public static func reduce(value: inout CGRect, nextValue: () -> CGRect) {
        value = nextValue()
    }
}

public struct TranscriptHeightKey: PreferenceKey {
    public static var defaultValue: CGFloat = 0
    public static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

public struct HUDView: View {
    @Bindable var model: HUDViewModel
    @State private var isInterruptPressed: Bool = false
    @State private var isHovering: Bool = false
    @State private var hoverOffset: CGSize = .zero
    @State private var transcriptHeight: CGFloat = 0

    private var isNotchMode: Bool {
        return model.displayMode == .notch && (NSScreen.main?.hasPhysicalNotch ?? false)
    }

    private var isIdleNotch: Bool {
        return isNotchMode && model.agentState == .idle && !model.isWingExpanded
    }

    private var notchHeight: CGFloat {
        return NSScreen.main?.notchHeight ?? 32.0
    }

    private var idleNotchHeight: CGFloat {
        let base = NSScreen.main?.notchHeight ?? 32.0
        return max(base + 5.0, 37.0)
    }

    private var hardwareNotchWidth: CGFloat {
        return NSScreen.main?.notchWidth ?? 185.0
    }

    private var minNotchWidth: CGFloat {
        let base = isIdleNotch ? (hardwareNotchWidth + 80.0) : max(hardwareNotchWidth + 24.0, 210.0)
        return base + (isHovering ? 8.0 : 0.0)
    }

    public var body: some View {
        VStack(spacing: 0) {
            if isIdleNotch {
                // Flush Menu-Bar Notch Ear Bar (Zero overlay into windows during idle)
                HStack(spacing: 0) {
                    // Left Ear: Ambient Waveform Heartbeat
                    HStack(spacing: 6) {
                        WaveformView(state: model.agentState, rms: model.rmsEnergy)
                        if model.isMuted {
                            Image(systemName: "speaker.slash.fill")
                                .font(.system(size: 9))
                                .foregroundStyle(.red.opacity(0.85))
                        }
                        if model.interactionMode == .handsFree {
                            Text("🎙️")
                                .font(.system(size: 9))
                        }
                    }
                    .padding(.leading, 12)
                    .padding(.trailing, 6)

                    // Center: Physical Camera Notch Spacer
                    Spacer(minLength: 0)
                        .frame(width: hardwareNotchWidth)

                    // Right Ear: Spreading / Transcript Button or Due Cards
                    HStack(spacing: 6) {
                        if !model.streamingMarkdown.isEmpty {
                            Button(action: { model.toggleWing() }) {
                                Image(systemName: "chevron.down.circle.fill")
                                    .font(.system(size: 13))
                                    .foregroundStyle(.secondary)
                            }
                            .buttonStyle(.plain)
                            .help("Expand Transcript")
                        } else if model.cardsDue > 0 {
                            Text("📚 \(model.cardsDue)")
                                .font(.system(size: 10, weight: .semibold, design: .rounded))
                                .foregroundStyle(.purple)
                        } else {
                            // Symmetrical balance spacer matching left ear icon width
                            Color.clear.frame(width: 22, height: 18)
                        }
                    }
                    .padding(.leading, 6)
                    .padding(.trailing, 12)
                }
                .frame(height: idleNotchHeight)
                .transition(.opacity)
            } else {
                // Active / Speaking / Wing Expanded Island
                HStack(spacing: 10) {
                    // Animated Waveform Indicator
                    WaveformView(state: model.agentState, rms: model.rmsEnergy)

                    // State & Content Pill
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            if !statusTitle.isEmpty {
                                Text(statusTitle)
                                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                                    .foregroundStyle(statusColor)
                                    .fixedSize(horizontal: true, vertical: false)
                            }

                            if model.interactionMode == .handsFree {
                                Text("🎙️ Hands-Free")
                                    .font(.system(size: 9, weight: .semibold, design: .rounded))
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.green.opacity(0.2), in: Capsule())
                                    .foregroundStyle(.green)
                                    .fixedSize(horizontal: true, vertical: false)
                            }

                            if !model.activeApp.isEmpty && model.agentState != .idle {
                                Text("•  \(model.activeApp)")
                                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .fixedSize(horizontal: true, vertical: false)
                            }

                            if model.cardsDue > 0 && model.agentState == .idle {
                                Text("📚 \(model.cardsDue)")
                                    .font(.system(size: 10, weight: .medium, design: .rounded))
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.purple.opacity(0.2), in: Capsule())
                                    .foregroundStyle(.purple)
                                    .fixedSize(horizontal: true, vertical: false)
                            }

                            if model.isMuted {
                                Image(systemName: "speaker.slash.fill")
                                    .font(.system(size: 9))
                                    .foregroundStyle(.red.opacity(0.85))
                            }
                        }

                        // Compact Streaming Caption or Idle Subtitle
                        if !model.captionText.isEmpty && !model.isWingExpanded && (model.agentState == .speaking || model.agentState == .thinking) {
                            Text(model.agentState == .thinking ? "“\(model.captionText)”" : model.captionText)
                                .font(.system(size: 12, weight: .regular))
                                .foregroundStyle(model.agentState == .thinking ? Color.secondary : Color.primary)
                                .lineLimit(2)
                                .frame(maxWidth: 380, alignment: .leading)
                                .fixedSize(horizontal: false, vertical: true)
                                .transition(.opacity.combined(with: .offset(y: -4)))
                        }
                    }

                    if model.isWingExpanded {
                        Spacer(minLength: 0)
                    }

                    // Action controls sitting neatly beside content
                    HStack(spacing: 8) {
                        // Expandable Transcript Wing Toggle
                        if !model.streamingMarkdown.isEmpty {
                            Button(action: { model.toggleWing() }) {
                                Image(systemName: model.isWingExpanded ? "chevron.up.circle.fill" : "chevron.down.circle.fill")
                                    .font(.system(size: 14))
                                    .foregroundStyle(.secondary)
                            }
                            .buttonStyle(.plain)
                            .help(model.isWingExpanded ? "Collapse Transcript" : "Expand Markdown Transcript")
                        }

                        // Quick Interrupt Button when speaking
                        if model.agentState == .speaking {
                            Button(action: { model.interrupt() }) {
                                Image(systemName: "stop.circle.fill")
                                    .font(.system(size: 15))
                                    .foregroundStyle(.red.opacity(0.9))
                                    .scaleEffect(isInterruptPressed ? 0.92 : 1.0)
                                    .animation(.spring(response: 0.18, dampingFraction: 0.7), value: isInterruptPressed)
                            }
                            .buttonStyle(.plain)
                            .simultaneousGesture(
                                DragGesture(minimumDistance: 0)
                                    .onChanged { _ in isInterruptPressed = true }
                                    .onEnded { _ in isInterruptPressed = false }
                            )
                            .help("Interrupt Selene")
                            .transition(.opacity.combined(with: .scale(scale: 0.95)))
                        }
                    }
                }

                // Collapsible Downward Transcript Wing with Markdown & Auto-scroll ONLY when genuinely tall
                if model.isWingExpanded && !model.streamingMarkdown.isEmpty {
                    Divider()
                        .opacity(0.2)
                        .padding(.vertical, 4)

                    Group {
                        if transcriptHeight > 240.0 {
                            ScrollViewReader { proxy in
                                ScrollView(.vertical, showsIndicators: true) {
                                    transcriptTextContent
                                    Color.clear
                                        .frame(height: 1)
                                        .id("wing_bottom")
                                }
                                .frame(height: 240)
                                .onChange(of: model.streamingMarkdown) { _, _ in
                                    proxy.scrollTo("wing_bottom", anchor: .bottom)
                                }
                            }
                        } else {
                            transcriptTextContent
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
        }
        .frame(minWidth: isNotchMode ? minNotchWidth : 0)
        .padding(.horizontal, isNotchMode ? (isIdleNotch ? 0 : 20) : 16)
        .padding(.top, isNotchMode ? (isIdleNotch ? 0 : (model.isWingExpanded ? notchHeight + 2 : notchHeight + 1)) : 6)
        .padding(.bottom, isNotchMode ? (isIdleNotch ? 0 : (isHovering ? 8 : 6)) : 8)
        .rotation3DEffect(
            .degrees(isNotchMode ? hoverOffset.height * 0.8 : 0),
            axis: (x: 1, y: 0, z: 0)
        )
        .rotation3DEffect(
            .degrees(isNotchMode ? hoverOffset.width * -0.8 : 0),
            axis: (x: 0, y: 1, z: 0)
        )
        .offset(
            x: isNotchMode ? hoverOffset.width * 0.5 : 0,
            y: isNotchMode ? hoverOffset.height * 0.3 : 0
        )
        .scaleEffect(1.0)
        .background(
            GeometryReader { geo in
                Color.clear.preference(key: PillFrameKey.self, value: geo.frame(in: .global))
            }
        )
        .background(backgroundShape)
        .clipShape(isNotchMode ? AnyShape(NotchShape(topCornerRadius: 6, bottomCornerRadius: isIdleNotch ? 12 : 18)) : AnyShape(RoundedRectangle(cornerRadius: 18, style: .continuous)))
        .onPreferenceChange(PillFrameKey.self) { frame in
            model.onPillFrameChange?(frame)
        }
        .onContinuousHover { phase in
            switch phase {
            case .active(let location):
                if !isHovering {
                    NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .default)
                }
                guard NSEvent.pressedMouseButtons == 0 else { return }
                let normX = (location.x / max(minNotchWidth, 1.0)) * 2 - 1
                let normY = (location.y / max(notchHeight + 24.0, 1.0)) * 2 - 1
                withAnimation(.interactiveSpring(response: 0.22, dampingFraction: 0.86)) {
                    isHovering = true
                    hoverOffset = CGSize(width: normX, height: normY)
                }
            case .ended:
                withAnimation(.spring(response: 0.32, dampingFraction: 0.88)) {
                    isHovering = false
                    hoverOffset = .zero
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .ignoresSafeArea()
        .animation(.spring(response: 0.36, dampingFraction: 0.82), value: model.agentState)
        .animation(.spring(response: 0.36, dampingFraction: 0.82), value: model.displayMode)
        .animation(.spring(response: 0.36, dampingFraction: 0.82), value: model.isWingExpanded)
        .animation(.spring(response: 0.32, dampingFraction: 0.72), value: isHovering)
        .animation(.easeOut(duration: 0.18), value: model.captionText)
    }

    private var transcriptTextContent: some View {
        Text(LocalizedStringKey(model.streamingMarkdown))
            .font(.system(size: 12, design: .rounded))
            .lineSpacing(3)
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                GeometryReader { geo in
                    Color.clear.preference(key: TranscriptHeightKey.self, value: geo.size.height)
                }
            )
            .onPreferenceChange(TranscriptHeightKey.self) { height in
                transcriptHeight = height
            }
    }

    @ViewBuilder
    private var backgroundShape: some View {
        if isNotchMode {
            NotchShape(topCornerRadius: 6, bottomCornerRadius: isIdleNotch ? 12 : 18)
                .fill(Color.black)
                .overlay(alignment: .top) {
                    Rectangle()
                        .fill(Color.black)
                        .frame(height: 6)
                }
                .shadow(color: Color.black.opacity(isIdleNotch ? 0.25 : 0.4), radius: isIdleNotch ? 4 : 10, x: 0, y: isIdleNotch ? 2 : 4)
        } else {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .strokeBorder(Color.white.opacity(0.18), lineWidth: 0.75)
                )
                .shadow(color: Color.black.opacity(0.28), radius: 12, x: 0, y: 4)
        }
    }

    private var statusTitle: String {
        switch model.agentState {
        case .idle: return ""
        case .listening: return "Listening..."
        case .thinking: return "Thinking..."
        case .speaking: return "Speaking..."
        case .disconnected: return "Connecting to daemon..."
        }
    }

    private var statusColor: Color {
        switch model.agentState {
        case .idle: return Color(red: 0.90, green: 0.40, blue: 0.95)
        case .listening: return Color(red: 0.22, green: 0.82, blue: 0.98)
        case .thinking: return Color(red: 0.96, green: 0.65, blue: 0.14)
        case .speaking: return Color(red: 0.98, green: 0.35, blue: 0.65)
        case .disconnected: return Color.secondary
        }
    }
}
