import SwiftUI

// MARK: - Felt Background
// Green felt oval table with vignette effect

struct FeltBackground: View {
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Dark background
                CPColors.bgBase

                // Felt oval
                Ellipse()
                    .fill(
                        RadialGradient(
                            gradient: Gradient(colors: [
                                CPColors.feltGreen,
                                CPColors.feltDark,
                                CPColors.bgBase
                            ]),
                            center: .center,
                            startRadius: 0,
                            endRadius: max(geometry.size.width, geometry.size.height) * 0.5
                        )
                    )
                    .frame(
                        width: geometry.size.width * 0.88,
                        height: geometry.size.height * 0.82
                    )
                    .position(
                        x: geometry.size.width / 2,
                        y: geometry.size.height / 2
                    )

                // Table rim
                Ellipse()
                    .stroke(
                        LinearGradient(
                            colors: [
                                Color(hex: "#5D4E37").opacity(0.6),
                                Color(hex: "#3E2F1C").opacity(0.4),
                                Color(hex: "#5D4E37").opacity(0.6)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 3
                    )
                    .frame(
                        width: geometry.size.width * 0.88,
                        height: geometry.size.height * 0.82
                    )
                    .position(
                        x: geometry.size.width / 2,
                        y: geometry.size.height / 2
                    )

                // Vignette overlay
                RadialGradient(
                    gradient: Gradient(colors: [
                        .clear,
                        CPColors.bgBase.opacity(0.3)
                    ]),
                    center: .center,
                    startRadius: geometry.size.width * 0.25,
                    endRadius: geometry.size.width * 0.55
                )
            }
        }
    }
}

// MARK: - Pot View

struct PotView: View {
    let amount: Double

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(CPColors.potColor)
                .frame(width: 10, height: 10)

            Text(CardParser.formatChips(amount))
                .font(CPTypography.monoSmall)
                .foregroundColor(CPColors.potColor)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(CPColors.bgElevated.opacity(0.85))
        .cornerRadius(CPLayout.radiusFull)
    }
}

// MARK: - Timer Arc View

struct TimerArcView: View {
    let timer: TimerState
    @State private var progress: Double = 1.0

    var body: some View {
        Circle()
            .trim(from: 0, to: progress)
            .stroke(
                timerColor,
                style: StrokeStyle(lineWidth: 3, lineCap: .round)
            )
            .frame(width: 50, height: 50)
            .rotationEffect(.degrees(-90))
            .animation(.linear(duration: timer.remaining), value: progress)
            .onAppear {
                progress = timer.remaining / max(timer.remaining + 0.01, 30) // approx
                withAnimation(.linear(duration: timer.remaining)) {
                    progress = 0
                }
            }
    }

    private var timerColor: Color {
        if progress < 0.2 { return CPColors.danger }
        if progress < 0.5 { return CPColors.warning }
        return CPColors.callColor
    }
}
