import SwiftUI

// MARK: - All-In Equity Overlay

struct AllInEquityOverlay: View {
    let allInLock: AllInLockState
    let heroSeat: Int?
    let myRunPreference: Int?
    let onSubmitRunCount: (Int) -> Void

    var body: some View {
        CPGlassCard {
            VStack(spacing: CPLayout.space4) {
                Text("All-In")
                    .font(CPTypography.heading)
                    .foregroundColor(CPColors.allinColor)

                // Equities
                if let equities = allInLock.equities {
                    VStack(spacing: CPLayout.space2) {
                        ForEach(equities, id: \.seat) { eq in
                            let name = allInLock.eligiblePlayers.first { $0.seat == eq.seat }?.name ?? "Seat \(eq.seat)"
                            let isHero = eq.seat == heroSeat
                            HStack {
                                Text(name)
                                    .font(isHero ? CPTypography.bodySemibold : CPTypography.body)
                                    .foregroundColor(isHero ? CPColors.gold : CPColors.textPrimary)
                                Spacer()
                                Text("\(Int(eq.winRate * 100))%")
                                    .font(CPTypography.mono)
                                    .foregroundColor(eq.winRate > 0.5 ? CPColors.success : CPColors.danger)
                            }
                        }
                    }
                }

                // Run count selection (if hero is eligible)
                if heroSeat != nil, !allInLock.submittedPlayerIds.contains(heroSeat ?? -1) {
                    VStack(spacing: CPLayout.space2) {
                        Text("Run it how many times?")
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textSecondary)

                        HStack(spacing: CPLayout.space3) {
                            ForEach([1, 2, 3], id: \.self) { count in
                                Button {
                                    HapticManager.action()
                                    onSubmitRunCount(count)
                                } label: {
                                    Text("\(count)x")
                                        .font(CPTypography.bodySemibold)
                                        .foregroundColor(myRunPreference == count ? .white : CPColors.textPrimary)
                                        .frame(width: 56, height: 44)
                                        .background(myRunPreference == count ? CPColors.accent : CPColors.bgElevated)
                                        .cornerRadius(CPLayout.radiusMd)
                                }
                            }
                        }
                    }
                } else if let target = allInLock.targetRunCount {
                    Text("Running it \(target)x")
                        .font(CPTypography.bodySemibold)
                        .foregroundColor(CPColors.accent)
                }
            }
        }
        .frame(maxWidth: 320)
        .shadow(color: .black.opacity(0.5), radius: 24)
    }
}

// MARK: - Seven-Two Bounty Reveal Overlay

struct SevenTwoBountyOverlay: View {
    let bounty: SevenTwoBountyInfo
    let players: [TablePlayer]

    var body: some View {
        VStack(spacing: CPLayout.space4) {
            Text("7-2 BOUNTY!")
                .font(CPTypography.hero)
                .foregroundColor(CPColors.gold)
                .shadow(color: CPColors.goldGlow, radius: 12)

            let winnerName = players.first { $0.seat == bounty.winnerSeat }?.name ?? "Seat \(bounty.winnerSeat)"

            Text("\(winnerName) wins!")
                .font(CPTypography.heading)
                .foregroundColor(CPColors.textPrimary)

            // Winner cards
            HStack(spacing: 4) {
                ForEach(bounty.winnerCards, id: \.self) { card in
                    CardView(notation: card, size: .large)
                }
            }

            Text("+\(CardParser.formatChips(bounty.totalBounty))")
                .font(CPTypography.displayLarge)
                .foregroundColor(CPColors.gold)

            Text("\(CardParser.formatChips(bounty.bountyPerPlayer)) per player")
                .font(CPTypography.label)
                .foregroundColor(CPColors.textSecondary)
        }
        .padding(CPLayout.space6)
        .background(CPColors.bgElevated.opacity(0.95))
        .cornerRadius(CPLayout.radiusXl)
        .shadow(color: CPColors.goldGlow, radius: 32)
    }
}

// MARK: - Bomb Pot Overlay

struct BombPotOverlay: View {
    let anteAmount: Double

    var body: some View {
        VStack(spacing: CPLayout.space3) {
            Text("BOMB POT")
                .font(CPTypography.hero)
                .foregroundColor(CPColors.allinColor)

            Text("Ante: \(CardParser.formatChips(anteAmount))")
                .font(CPTypography.display)
                .foregroundColor(CPColors.gold)

            Text("Everyone antes, deal flop")
                .font(CPTypography.label)
                .foregroundColor(CPColors.textSecondary)
        }
        .padding(CPLayout.space6)
        .background(CPColors.bgElevated.opacity(0.95))
        .cornerRadius(CPLayout.radiusXl)
        .shadow(color: CPColors.allinColor.opacity(0.3), radius: 24)
    }
}

// MARK: - Post-Hand Show/Muck Bar

struct PostHandShowMuckBar: View {
    let onShow: () -> Void
    let onMuck: () -> Void

    var body: some View {
        HStack(spacing: CPLayout.space3) {
            Button {
                HapticManager.action()
                onShow()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "eye")
                    Text("Show")
                }
                .font(CPTypography.labelBold)
                .foregroundColor(CPColors.callColor)
                .frame(maxWidth: .infinity)
                .padding(.vertical, CPLayout.space2)
                .background(CPColors.callColor.opacity(0.15))
                .cornerRadius(CPLayout.radiusMd)
            }

            Button {
                HapticManager.fold()
                onMuck()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "eye.slash")
                    Text("Muck")
                }
                .font(CPTypography.labelBold)
                .foregroundColor(CPColors.textMuted)
                .frame(maxWidth: .infinity)
                .padding(.vertical, CPLayout.space2)
                .background(CPColors.bgElevated)
                .cornerRadius(CPLayout.radiusMd)
            }
        }
        .padding(.horizontal, CPLayout.space3)
        .padding(.vertical, CPLayout.space2)
        .background(CPColors.bgSurface)
    }
}

// MARK: - Settlement Overlay

struct SettlementOverlay: View {
    let winners: [HandWinner]
    let settlement: SettlementResult?
    let players: [TablePlayer]
    let heroSeat: Int?

    var body: some View {
        VStack(spacing: CPLayout.space3) {
            if let settlement, settlement.runCount > 1 {
                // Multi-run results
                ForEach(Array(settlement.winnersByRun.enumerated()), id: \.offset) { idx, run in
                    VStack(spacing: 4) {
                        Text("Run \(run.run)")
                            .font(CPTypography.captionBold)
                            .foregroundColor(CPColors.textMuted)

                        ForEach(run.winners, id: \.seat) { winner in
                            winnerRow(winner)
                        }
                    }
                }
            } else {
                ForEach(winners, id: \.seat) { winner in
                    winnerRow(winner)
                }
            }

            // Hero net result
            if let heroSeat, let ledger = settlement?.ledger.first(where: { $0.seat == heroSeat }) {
                Divider().background(CPColors.borderDefault)
                HStack {
                    Text("Your result")
                        .font(CPTypography.label)
                        .foregroundColor(CPColors.textSecondary)
                    Spacer()
                    Text(ledger.net >= 0 ? "+\(CardParser.formatChips(ledger.net))" : CardParser.formatChips(ledger.net))
                        .font(CPTypography.mono)
                        .foregroundColor(ledger.net >= 0 ? CPColors.success : CPColors.danger)
                }
            }
        }
        .padding(CPLayout.space4)
        .background(CPColors.bgElevated.opacity(0.95))
        .cornerRadius(CPLayout.radiusLg)
        .shadow(color: CPColors.goldGlow, radius: 20)
    }

    private func winnerRow(_ winner: HandWinner) -> some View {
        HStack(spacing: CPLayout.space2) {
            let name = players.first { $0.seat == winner.seat }?.name ?? "Seat \(winner.seat)"
            let isHero = winner.seat == heroSeat

            Text(name)
                .font(isHero ? CPTypography.bodySemibold : CPTypography.body)
                .foregroundColor(isHero ? CPColors.gold : CPColors.textPrimary)

            Text("+\(CardParser.formatChips(winner.amount))")
                .font(CPTypography.mono)
                .foregroundColor(CPColors.gold)

            if let handName = winner.handName {
                Text(handName)
                    .font(CPTypography.caption)
                    .foregroundColor(CPColors.textSecondary)
            }
        }
    }
}
