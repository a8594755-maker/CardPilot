import SwiftUI

// MARK: - Seat View
// Individual player seat with avatar, stack, cards, status

struct SeatView: View {
    let player: TablePlayer?
    let seatIndex: Int
    let isHero: Bool
    let isActor: Bool
    let isButton: Bool
    let holeCards: [String]
    let revealedCards: [String]?
    let lastAction: ActionAppliedPayload?
    let positionLabel: String?
    let isWinner: Bool
    let onTapEmpty: () -> Void

    var body: some View {
        VStack(spacing: 2) {
            if let player {
                // Occupied seat
                occupiedSeat(player)
            } else {
                // Empty seat
                emptySeat
            }
        }
        .frame(width: 90, height: 100)
    }

    // MARK: - Occupied Seat

    private func occupiedSeat(_ player: TablePlayer) -> some View {
        VStack(spacing: 2) {
            // Hole cards (hero or revealed)
            let cards = !holeCards.isEmpty ? holeCards : (revealedCards ?? [])
            if !cards.isEmpty {
                HStack(spacing: 2) {
                    ForEach(cards, id: \.self) { card in
                        CardView(notation: card, size: .small)
                    }
                }
                .transition(.scale.combined(with: .opacity))
            }

            // Avatar & name
            ZStack {
                RoundedRectangle(cornerRadius: CPLayout.radiusMd)
                    .fill(isHero ? CPColors.accent.opacity(0.2) : CPColors.bgElevated)
                    .overlay(
                        RoundedRectangle(cornerRadius: CPLayout.radiusMd)
                            .stroke(borderColor, lineWidth: borderWidth)
                    )

                VStack(spacing: 1) {
                    HStack(spacing: 2) {
                        // Position badge
                        if let pos = positionLabel {
                            Text(pos)
                                .font(.system(size: 8, weight: .bold, design: .monospaced))
                                .foregroundColor(CPColors.gold)
                        }

                        Text(player.name)
                            .font(CPTypography.caption)
                            .foregroundColor(CPColors.textPrimary)
                            .lineLimit(1)
                    }

                    Text(CardParser.formatChips(player.stack))
                        .font(CPTypography.monoSmall)
                        .foregroundColor(player.allIn ? CPColors.allinColor : CPColors.textSecondary)
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
            }
            .frame(width: 86, height: 38)

            // Action label
            if let action = lastAction {
                actionLabel(action)
                    .transition(.scale.combined(with: .opacity))
            }

            // Button marker
            if isButton {
                Text("D")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.black)
                    .frame(width: 18, height: 18)
                    .background(Circle().fill(.white))
            }
        }
        .opacity(player.folded ? 0.4 : 1.0)
        .shadow(color: isWinner ? CPColors.goldGlow : .clear, radius: isWinner ? 12 : 0)
    }

    // MARK: - Empty Seat

    private var emptySeat: some View {
        Button(action: onTapEmpty) {
            ZStack {
                RoundedRectangle(cornerRadius: CPLayout.radiusMd)
                    .stroke(CPColors.borderSubtle, style: StrokeStyle(lineWidth: 1, dash: [4]))
                    .frame(width: 86, height: 38)

                VStack(spacing: 2) {
                    Image(systemName: "plus")
                        .font(.system(size: 14))
                        .foregroundColor(CPColors.textMuted)
                    Text("Sit")
                        .font(CPTypography.caption)
                        .foregroundColor(CPColors.textMuted)
                }
            }
        }
    }

    // MARK: - Action Label

    private func actionLabel(_ action: ActionAppliedPayload) -> some View {
        HStack(spacing: 2) {
            Text(action.action.capitalized)
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(actionColor(action.action))

            if action.amount > 0 && action.action != "fold" && action.action != "check" {
                Text(CardParser.formatChips(action.amount))
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundColor(CPColors.textSecondary)
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(CPColors.bgElevated.opacity(0.8))
        .cornerRadius(CPLayout.radiusSm)
    }

    // MARK: - Helpers

    private var borderColor: Color {
        if isWinner { return CPColors.gold }
        if isActor { return CPColors.callColor }
        if isHero { return CPColors.accent }
        return CPColors.borderDefault
    }

    private var borderWidth: CGFloat {
        (isActor || isWinner) ? 2 : 1
    }

    private func actionColor(_ action: String) -> Color {
        switch action {
        case "fold": return CPColors.foldColor
        case "check": return CPColors.checkColor
        case "call": return CPColors.callColor
        case "raise", "bet": return CPColors.raiseColor
        case "all_in": return CPColors.allinColor
        default: return CPColors.textSecondary
        }
    }
}
