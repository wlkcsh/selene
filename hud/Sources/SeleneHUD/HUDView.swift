import SwiftUI

public struct HUDView: View {
    @Bindable var model: HUDViewModel
    @State private var isHovered = false

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
                            .foregroundStyle(.red.opacity(0.8))
                    }
                }

                // Streaming Caption or Idle Subtitle
                if !model.captionText.isEmpty && (model.agentState == .speaking || model.agentState == .thinking) {
                    Text(model.captionText)
                        .font(.system(size: 12, weight: .regular))
                        .foregroundStyle(.primary)
                        .lineLimit(2)
                        .frame(maxWidth: 420, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }

            // Quick Interrupt Button when speaking
            if model.agentState == .speaking {
                Button(action: { model.interrupt() }) {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(.red.opacity(0.9))
                }
                .buttonStyle(.plain)
                .help("Interrupt Selene")
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(
            Capsule()
                .fill(.ultraThinMaterial)
                .overlay(
                    Capsule()
                        .strokeBorder(Color.white.opacity(0.18), lineWidth: 0.75)
                )
                .shadow(color: Color.black.opacity(0.28), radius: 12, x: 0, y: 4)
        )
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .onHover { isHovered = $0 }
        .animation(.spring(response: 0.35, dampingFraction: 0.78), value: model.agentState)
        .animation(.easeOut(duration: 0.2), value: model.captionText)
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
