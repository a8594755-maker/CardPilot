import SwiftUI

// MARK: - Action Bar View
// Full port of BottomActionBar.tsx — fold/check/call/raise + slider + presets +
// all-in confirm + pre-action row + fold confirmation + GTO advice badge

struct ActionBarView: View {
    let legalActions: LegalActions
    let pot: Double
    let bigBlind: Double
    let currentBet: Double
    let street: Street
    var actionPending: Bool = false
    var advice: AdvicePayload?
    var preAction: PreAction?
    var preActionOptions: [PreActionOption] = []
    var shouldShowFoldConfirm: Bool = false

    let onFold: () -> Void
    let onCheck: () -> Void
    let onCall: () -> Void
    let onRaise: (Double) -> Void
    let onAllIn: () -> Void
    var onSetPreAction: ((PreActionType?) -> Void)?

    @State private var raiseAmount: Double = 0
    @State private var showRaiseSlider = false
    @State private var confirmingAllIn = false
    @State private var showFoldConfirmAlert = false
    @State private var foldConfirmSuppressed = false

    var body: some View {
        VStack(spacing: CPLayout.space2) {
            // GTO advice mini-badge (when advice available)
            if let advice {
                adviceMiniBar(advice)
            }

            // Raise slider + presets
            if showRaiseSlider && legalActions.canRaise {
                raiseSliderView
                betPresets
            }

            // Main action buttons
            mainActionRow
                .opacity(actionPending ? 0.5 : 1.0)
                .allowsHitTesting(!actionPending)

            // Pre-action row (when NOT hero's turn)
            if !preActionOptions.isEmpty {
                preActionRow
            }
        }
        .padding(.horizontal, CPLayout.space3)
        .padding(.top, CPLayout.space2)
        .padding(.bottom, CPLayout.space3)
        .background(CPColors.bgSurface)
        .onAppear {
            raiseAmount = legalActions.minRaise
        }
        .alert("Fold with free check?", isPresented: $showFoldConfirmAlert) {
            Button("Fold Anyway", role: .destructive) {
                onFold()
            }
            Button("Cancel", role: .cancel) {}
            Button("Don't ask again") {
                foldConfirmSuppressed = true
                onFold()
            }
        } message: {
            Text("You can check for free. Are you sure you want to fold?")
        }
    }

    // MARK: - Main Action Row

    private var mainActionRow: some View {
        HStack(spacing: CPLayout.space2) {
            // Fold (suppress when free check available, unless forced)
            if legalActions.canFold {
                let freeCheck = legalActions.canCheck
                actionButton(
                    "Fold",
                    style: .cpFold,
                    enabled: !freeCheck
                ) {
                    if freeCheck && shouldShowFoldConfirm && !foldConfirmSuppressed {
                        showFoldConfirmAlert = true
                    } else {
                        HapticManager.fold()
                        onFold()
                    }
                }
            }

            // Check
            if legalActions.canCheck {
                actionButton("Check", style: .cpPrimary) {
                    HapticManager.action()
                    onCheck()
                }
            }

            // Call
            if legalActions.canCall {
                actionButton(
                    "Call \(CardParser.formatChips(legalActions.callAmount))",
                    style: .cpCall
                ) {
                    HapticManager.action()
                    onCall()
                }
            }

            // Raise / Bet
            if legalActions.canRaise {
                let isBet = currentBet == 0 && street != .preflop
                if showRaiseSlider {
                    actionButton(
                        "\(isBet ? "Bet" : "Raise") \(CardParser.formatChips(raiseAmount))",
                        style: .cpRaise
                    ) {
                        HapticManager.action()
                        onRaise(raiseAmount)
                        showRaiseSlider = false
                    }
                } else {
                    actionButton(isBet ? "Bet" : "Raise", style: .cpRaise) {
                        HapticManager.selection()
                        raiseAmount = legalActions.minRaise
                        showRaiseSlider = true
                    }
                }
            }

            // All-in (two-click confirmation)
            if legalActions.canRaise {
                if confirmingAllIn {
                    HStack(spacing: 4) {
                        actionButton("Confirm", style: .cpAllIn) {
                            HapticManager.allIn()
                            confirmingAllIn = false
                            onAllIn()
                        }
                        Button {
                            confirmingAllIn = false
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(CPColors.textMuted)
                                .frame(width: 32, height: 32)
                                .background(CPColors.bgElevated)
                                .cornerRadius(CPLayout.radiusSm)
                        }
                    }
                } else {
                    actionButton("All In", style: .cpAllIn) {
                        HapticManager.selection()
                        confirmingAllIn = true
                    }
                }
            }
        }
    }

    // MARK: - Action Button

    private func actionButton(
        _ title: String,
        style: CPButtonStyle,
        enabled: Bool = true,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(CPTypography.labelBold)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(style)
        .opacity(enabled ? 1.0 : 0.4)
    }

    // MARK: - Raise Slider

    private var raiseSliderView: some View {
        VStack(spacing: CPLayout.space1) {
            HStack {
                Text(CardParser.formatChips(legalActions.minRaise))
                    .font(CPTypography.monoSmall)
                    .foregroundColor(CPColors.textMuted)

                Slider(
                    value: $raiseAmount,
                    in: legalActions.minRaise...legalActions.maxRaise,
                    step: bigBlind
                )
                .tint(CPColors.raiseColor)

                Text(CardParser.formatChips(legalActions.maxRaise))
                    .font(CPTypography.monoSmall)
                    .foregroundColor(CPColors.textMuted)
            }

            Text(CardParser.formatChips(raiseAmount))
                .font(CPTypography.mono)
                .foregroundColor(CPColors.raiseColor)
        }
        .padding(.horizontal, CPLayout.space2)
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - Bet Size Presets

    private var betPresets: some View {
        HStack(spacing: CPLayout.space2) {
            presetButton("Min", amount: legalActions.minRaise)

            if currentBet > 0 {
                // Facing bet: multipliers
                presetButton("2x", amount: min(currentBet * 2, legalActions.maxRaise))
                presetButton("3x", amount: min(currentBet * 3, legalActions.maxRaise))
            } else {
                // No bet: pot fractions
                presetButton("33%", amount: clampRaise(pot * 0.33))
                presetButton("50%", amount: clampRaise(pot * 0.5))
            }

            presetButton("67%", amount: clampRaise(pot * 0.67))
            presetButton("Pot", amount: clampRaise(pot))
        }
        .transition(.opacity)
    }

    private func presetButton(_ label: String, amount: Double) -> some View {
        Button {
            raiseAmount = amount
            HapticManager.selection()
        } label: {
            Text(label)
                .font(CPTypography.caption)
                .foregroundColor(CPColors.textSecondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(CPColors.bgElevated)
                .cornerRadius(CPLayout.radiusSm)
        }
    }

    private func clampRaise(_ value: Double) -> Double {
        max(legalActions.minRaise, min(value, legalActions.maxRaise))
    }

    // MARK: - Pre-Action Row (when not hero's turn)

    private var preActionRow: some View {
        HStack(spacing: CPLayout.space2) {
            ForEach(preActionOptions) { option in
                let isActive = preAction?.actionType == option.type
                Button {
                    HapticManager.selection()
                    onSetPreAction?(isActive ? nil : option.type)
                } label: {
                    Text(option.label)
                        .font(CPTypography.caption)
                        .foregroundColor(isActive ? .white : CPColors.textSecondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(isActive ? CPColors.accent.opacity(0.6) : CPColors.bgElevated)
                        .cornerRadius(CPLayout.radiusFull)
                        .overlay(
                            Capsule()
                                .stroke(isActive ? CPColors.accent : CPColors.borderSubtle, lineWidth: 1)
                        )
                }
            }

            Spacer()
        }
    }

    // MARK: - GTO Advice Mini Bar

    private func adviceMiniBar(_ advice: AdvicePayload) -> some View {
        HStack(spacing: CPLayout.space2) {
            Image(systemName: "lightbulb.fill")
                .font(.system(size: 11))
                .foregroundColor(CPColors.gold)

            if let recommended = advice.recommended {
                Text(recommended.capitalized)
                    .font(CPTypography.captionBold)
                    .foregroundColor(adviceActionColor(recommended))
            }

            Text("\(Int(advice.mix.raise))R / \(Int(advice.mix.call))C / \(Int(advice.mix.fold))F")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundColor(CPColors.textMuted)

            Spacer()
        }
        .padding(.horizontal, CPLayout.space2)
        .padding(.vertical, 4)
        .background(CPColors.bgElevated.opacity(0.6))
        .cornerRadius(CPLayout.radiusSm)
    }

    private func adviceActionColor(_ action: String) -> Color {
        switch action {
        case "raise": return CPColors.raiseColor
        case "call": return CPColors.callColor
        case "fold": return CPColors.foldColor
        default: return CPColors.textSecondary
        }
    }
}
