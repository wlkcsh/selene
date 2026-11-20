import SwiftUI

public struct WaveformView: View {
    let state: AgentState
    let rms: Double

    public var body: some View {
        if state == .thinking {
            // Active 60 FPS kinetic wave only while Selene is deep in thought
            TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { context in
                let time = context.date.timeIntervalSinceReferenceDate
                HStack(spacing: 3) {
                    ForEach(0..<4) { index in
                        let wave = (sin(time * 6.0 + Double(index) * 1.05) + 1.0) / 2.0
                        let heightWave = sin(time * 5.8 + Double(index) * 1.05)
                        RoundedRectangle(cornerRadius: 1.5)
                            .fill(
                                Color(
                                    red: 0.98,
                                    green: 0.62 + wave * 0.22,
                                    blue: 0.12 + wave * 0.25
                                ).opacity(0.70 + wave * 0.30)
                            )
                            .frame(width: 3, height: CGFloat(max(3.5, min(14.5, 8.0 + heightWave * 5.5))))
                    }
                }
                .frame(width: 22, height: 18)
            }
        } else {
            // Calm, non-animated static presentation when idle or not thinking
            HStack(spacing: 3) {
                ForEach(0..<4) { index in
                    RoundedRectangle(cornerRadius: 1.5)
                        .fill(staticBarColor)
                        .frame(width: 3, height: staticBarHeight(for: index))
                        .animation(.easeOut(duration: 0.08), value: rms)
                }
            }
            .frame(width: 22, height: 18)
        }
    }

    private var staticBarColor: Color {
        switch state {
        case .idle:
            return Color(red: 0.85, green: 0.27, blue: 0.94) // Clean static violet
        case .listening:
            return Color(red: 0.22, green: 0.82, blue: 0.98) // Static cyan
        case .thinking:
            return Color(red: 0.98, green: 0.65, blue: 0.14) // Amber / Gold
        case .speaking:
            return Color(red: 0.98, green: 0.35, blue: 0.65) // Magenta / Pink
        case .disconnected:
            return Color.gray.opacity(0.6)
        }
    }

    private func staticBarHeight(for index: Int) -> CGFloat {
        switch state {
        case .listening, .speaking:
            let base = 4.0
            let multiplier = CGFloat(index + 1) * 0.25
            let dynamic = CGFloat(rms) * 16.0 * multiplier
            return min(16, max(3, base + dynamic))
        case .idle:
            return (index == 1 || index == 2) ? 6 : 4
        case .thinking:
            return 8
        case .disconnected:
            return 3
        }
    }
}
