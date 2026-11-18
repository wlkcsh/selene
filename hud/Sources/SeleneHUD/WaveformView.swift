import SwiftUI

public struct WaveformView: View {
    let state: AgentState
    let rms: Double

    @State private var phase: Double = 0.0

    private var accentColor: Color {
        switch state {
        case .idle:
            return Color(red: 0.85, green: 0.27, blue: 0.94) // Neon Rose / Violet
        case .listening:
            return Color(red: 0.22, green: 0.82, blue: 0.98) // Cyan / Electric Blue
        case .thinking:
            return Color(red: 0.96, green: 0.65, blue: 0.14) // Amber / Gold
        case .speaking:
            return Color(red: 0.98, green: 0.35, blue: 0.65) // Magenta / Pink
        case .disconnected:
            return Color.gray.opacity(0.6)
        }
    }

    public var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<4) { index in
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(accentColor)
                    .frame(width: 3, height: barHeight(for: index))
                    .animation(.easeOut(duration: 0.08), value: rms)
            }
        }
        .frame(width: 22, height: 18)
        .onAppear {
            withAnimation(.linear(duration: 1.2).repeatForever(autoreverses: false)) {
                phase = .pi * 2
            }
        }
    }

    private func barHeight(for index: Int) -> CGFloat {
        switch state {
        case .listening:
            let base = 4.0
            let multiplier = (CGFloat(index + 1) * 0.25)
            let dynamic = CGFloat(rms) * 16.0 * multiplier
            return min(16, max(3, base + dynamic))
        case .speaking:
            let wave = sin(phase + Double(index) * 1.2) * 5.0
            return CGFloat(7.0 + wave)
        case .thinking:
            let wave = cos(phase * 1.5 + Double(index) * 0.8) * 3.5
            return CGFloat(5.5 + wave)
        case .idle:
            return index == 1 || index == 2 ? 6 : 4
        case .disconnected:
            return 3
        }
    }
}
