import SwiftUI

// MARK: - Onboarding Modal
// Shown after first sign-up — matches OnboardingModal.tsx

struct OnboardingView: View {
    let onComplete: () -> Void

    @State private var isVisible = false

    var body: some View {
        ZStack {
            // Backdrop
            Color.black.opacity(0.75)
                .ignoresSafeArea()
                .blur(radius: 2)

            // Card
            CPGlassCard {
                VStack(spacing: CPLayout.space5) {
                    // Icon
                    ZStack {
                        Circle()
                            .fill(
                                LinearGradient(
                                    colors: [CPColors.gold, CPColors.allinColor],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 56, height: 56)
                            .shadow(color: CPColors.goldGlow, radius: 12)

                        Image(systemName: "checkmark")
                            .font(.system(size: 28, weight: .bold))
                            .foregroundColor(.white)
                    }

                    // Title
                    Text("You're All Set!")
                        .font(CPTypography.display)
                        .foregroundColor(CPColors.textPrimary)

                    // Description
                    Text("Head to the lobby to create or join a room and start playing.\nThe host will decide the table settings.")
                        .font(CPTypography.body)
                        .foregroundColor(CPColors.textSecondary)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)

                    // Button
                    Button {
                        HapticManager.action()
                        onComplete()
                    } label: {
                        Text("Start Playing")
                            .font(CPTypography.bodySemibold)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpPrimary)
                }
                .padding(CPLayout.space4)
            }
            .frame(maxWidth: 360)
            .padding(.horizontal, CPLayout.space6)
            .scaleEffect(isVisible ? 1 : 0.9)
            .opacity(isVisible ? 1 : 0)
        }
        .onAppear {
            withAnimation(.spring(duration: 0.3)) {
                isVisible = true
            }
        }
        .preferredColorScheme(.dark)
    }
}

// MARK: - Onboarding State

@Observable
final class OnboardingManager {
    private static let key = "cardpilot_onboarding_completed"

    var isOnboardingNeeded: Bool {
        !UserDefaults.standard.bool(forKey: Self.key)
    }

    func completeOnboarding() {
        UserDefaults.standard.set(true, forKey: Self.key)
    }

    static func reset() {
        UserDefaults.standard.removeObject(forKey: key)
    }
}
