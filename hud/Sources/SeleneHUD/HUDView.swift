import SwiftUI

public struct PillFrameKey: PreferenceKey {
    public static var defaultValue: CGRect = .zero
    public static func reduce(value: inout CGRect, nextValue: () -> CGRect) {
        value = nextValue()
    }
}

public struct HUDView: View {
    @Bindable var model: HUDViewModel
    @State private var isInterruptPressed: Bool = false

    private var isNotchMode: Bool {
        return model.displayMode == .notch && (NSScreen.main?.hasPhysicalNotch ?? false)
    }

    private var notchHeight: CGFloat {
        return NSScreen.main?.notchHeight ?? 32.0
    }

    public var body: some View {
        HStack(spacing: 10) {
            // Animated Waveform Indicator
            WaveformView(state: model.agentState, rms: model.rmsEnergy)

            // State & Content Pill
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(statusTitle)
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(statusColor)
                        .fixedSize(horizontal: true, vertical: false)

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

                // Streaming Caption or Idle Subtitle
                if !model.captionText.isEmpty && (model.agentState == .speaking || model.agentState == .thinking) {
                    Text(model.agentState == .thinking ? "“\(model.captionText)”" : model.captionText)
                        .font(.system(size: 12, weight: .regular))
                        .foregroundStyle(model.agentState == .thinking ? Color.secondary : Color.primary)
                        .lineLimit(2)
                        .frame(maxWidth: 440, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .transition(
                            .asymmetric(
                                insertion: .opacity.combined(with: .offset(y: -4)),
                                removal: .opacity
                            )
                        )
                }
            }

            // Quick Interrupt Button when speaking with responsive press state
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
        .padding(.horizontal, 16)
        .padding(.top, isNotchMode ? notchHeight + 6 : 8)
        .padding(.bottom, 8)
        .background(
            GeometryReader { geo in
                Color.clear.preference(key: PillFrameKey.self, value: geo.frame(in: .global))
            }
        )
        .background(backgroundShape)
        .onPreferenceChange(PillFrameKey.self) { frame in
            model.onPillFrameChange?(frame)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .animation(.spring(response: 0.36, dampingFraction: 0.82), value: model.agentState)
        .animation(.spring(response: 0.36, dampingFraction: 0.82), value: model.displayMode)
        .animation(.easeOut(duration: 0.18), value: model.captionText)
    }

    @ViewBuilder
    private var backgroundShape: some View {
        if isNotchMode {
            UnevenRoundedRectangle(
                topLeadingRadius: 0,
                bottomLeadingRadius: 18,
                bottomTrailingRadius: 18,
                topTrailingRadius: 0,
                style: .continuous
            )
            .fill(Color.black.opacity(0.88))
            .background(
                UnevenRoundedRectangle(
                    topLeadingRadius: 0,
                    bottomLeadingRadius: 18,
                    bottomTrailingRadius: 18,
                    topTrailingRadius: 0,
                    style: .continuous
                )
                .fill(.ultraThinMaterial)
            )
            .overlay(
                UnevenRoundedRectangle(
                    topLeadingRadius: 0,
                    bottomLeadingRadius: 18,
                    bottomTrailingRadius: 18,
                    topTrailingRadius: 0,
                    style: .continuous
                )
                .strokeBorder(Color.white.opacity(0.12), lineWidth: 0.75)
            )
            .shadow(color: Color.black.opacity(0.35), radius: 14, x: 0, y: 5)
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
        case .idle: return "Selene"
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
