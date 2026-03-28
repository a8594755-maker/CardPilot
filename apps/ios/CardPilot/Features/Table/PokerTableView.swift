import SwiftUI

// MARK: - Poker Table View
// Main game screen — full parity with web TableContainer + all overlays

struct PokerTableView: View {
    @Bindable var viewModel: PokerTableViewModel
    @State private var showBuyInSheet = false
    @State private var selectedSeat: Int?
    @State private var showOptions = false

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            VStack(spacing: 0) {
                // MARK: Top Bar
                tableTopBar

                // MARK: Table Area
                GeometryReader { geometry in
                    ZStack {
                        FeltBackground()

                        // Pot display
                        if viewModel.pot > 0 {
                            PotView(amount: viewModel.pot)
                                .position(x: geometry.size.width / 2, y: geometry.size.height * 0.28)
                        }

                        // Community cards
                        CommunityCardsView(cards: viewModel.board)
                            .position(x: geometry.size.width / 2, y: geometry.size.height * 0.42)

                        // Board equity display (all-in)
                        if let reveal = viewModel.boardReveal, !reveal.equities.isEmpty {
                            equityBar(reveal.equities)
                                .position(x: geometry.size.width / 2, y: geometry.size.height * 0.55)
                        }

                        // Seats
                        let maxSeats = max(viewModel.tableState?.players.count ?? 6, 6)
                        ForEach(0..<maxSeats, id: \.self) { seatIndex in
                            let player = viewModel.players.first { $0.seat == seatIndex }
                            let position = viewModel.seatPosition(for: seatIndex, maxSeats: maxSeats, in: geometry.size)
                            let postRevealCards = viewModel.postHandRevealedCards[seatIndex]

                            SeatView(
                                player: player,
                                seatIndex: seatIndex,
                                isHero: seatIndex == viewModel.heroSeat,
                                isActor: seatIndex == viewModel.actorSeat,
                                isButton: seatIndex == viewModel.tableState?.buttonSeat,
                                holeCards: seatIndex == viewModel.heroSeat ? viewModel.holeCards : [],
                                revealedCards: viewModel.revealedHoles[seatIndex] ?? postRevealCards,
                                lastAction: seatIndex == viewModel.heroSeat ? nil :
                                    (viewModel.lastActionBySeat[seatIndex].map {
                                        ActionAppliedPayload(seat: seatIndex, action: $0.action, amount: $0.amount, pot: viewModel.pot)
                                    }),
                                positionLabel: viewModel.positions[String(seatIndex)],
                                isWinner: viewModel.winners.contains { $0.seat == seatIndex },
                                onTapEmpty: {
                                    if player == nil && viewModel.heroSeat == nil {
                                        selectedSeat = seatIndex
                                        showBuyInSheet = true
                                    }
                                }
                            )
                            .position(position)
                        }

                        // Timer arc
                        if let timer = viewModel.timerState {
                            TimerArcView(timer: timer)
                                .position(viewModel.seatPosition(for: timer.seat, maxSeats: maxSeats, in: geometry.size))
                        }
                    }
                }

                // MARK: Action Bar (hero's turn)
                if viewModel.isHeroTurn, let actions = viewModel.legalActions {
                    ActionBarView(
                        legalActions: actions,
                        pot: viewModel.pot,
                        bigBlind: viewModel.tableState?.bigBlind ?? 2,
                        currentBet: viewModel.currentBet,
                        street: viewModel.street,
                        actionPending: viewModel.actionPending,
                        advice: viewModel.advice,
                        shouldShowFoldConfirm: viewModel.shouldShowFoldConfirm,
                        onFold: { viewModel.fold() },
                        onCheck: { viewModel.check() },
                        onCall: { viewModel.call() },
                        onRaise: { viewModel.raise(to: $0) },
                        onAllIn: { viewModel.allIn() }
                    )
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
                // Pre-action bar (not hero's turn, but in hand)
                else if !viewModel.isHeroTurn && !viewModel.derivedPreActionOptions.isEmpty {
                    ActionBarView(
                        legalActions: LegalActions(canFold: false, canCheck: false, canCall: false, callAmount: 0, canRaise: false, minRaise: 0, maxRaise: 0),
                        pot: viewModel.pot,
                        bigBlind: viewModel.tableState?.bigBlind ?? 2,
                        currentBet: viewModel.currentBet,
                        street: viewModel.street,
                        preAction: viewModel.preAction,
                        preActionOptions: viewModel.derivedPreActionOptions,
                        onFold: {}, onCheck: {}, onCall: {}, onRaise: { _ in }, onAllIn: {},
                        onSetPreAction: { viewModel.setPreAction($0) }
                    )
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
                // Post-hand show/muck
                else if viewModel.postHandShowAvailable {
                    PostHandShowMuckBar(
                        onShow: { viewModel.showHandPost() },
                        onMuck: { viewModel.muckHand() }
                    )
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }

            // MARK: Overlays

            // Settlement overlay
            if viewModel.isShowingSettlement, !viewModel.winners.isEmpty {
                Color.black.opacity(0.3).ignoresSafeArea()
                    .onTapGesture { viewModel.isShowingSettlement = false }

                SettlementOverlay(
                    winners: viewModel.winners,
                    settlement: viewModel.settlement,
                    players: viewModel.players,
                    heroSeat: viewModel.heroSeat
                )
                .transition(.scale.combined(with: .opacity))
            }

            // All-in lock overlay
            if let allInLock = viewModel.allInLock {
                Color.black.opacity(0.4).ignoresSafeArea()

                AllInEquityOverlay(
                    allInLock: allInLock,
                    heroSeat: viewModel.heroSeat,
                    myRunPreference: viewModel.myRunPreference,
                    onSubmitRunCount: { viewModel.submitRunPreference($0) }
                )
                .transition(.scale.combined(with: .opacity))
            }

            // Seven-two bounty reveal
            if let bounty = viewModel.sevenTwoRevealActive {
                Color.black.opacity(0.5).ignoresSafeArea()
                    .onTapGesture { viewModel.sevenTwoRevealActive = nil }

                SevenTwoBountyOverlay(bounty: bounty, players: viewModel.players)
                    .transition(.scale.combined(with: .opacity))
                    .onAppear {
                        Task {
                            try? await Task.sleep(for: .seconds(4))
                            viewModel.sevenTwoRevealActive = nil
                        }
                    }
            }

            // Bomb pot overlay
            if let bombPot = viewModel.bombPotOverlayActive {
                Color.black.opacity(0.4).ignoresSafeArea()
                    .onTapGesture { viewModel.bombPotOverlayActive = nil }

                BombPotOverlay(anteAmount: bombPot.anteAmount)
                    .transition(.scale.combined(with: .opacity))
            }

            // Toast
            if let toast = viewModel.toastMessage {
                VStack {
                    CPToast(message: toast)
                        .transition(.move(edge: .top).combined(with: .opacity))
                        .onAppear {
                            Task {
                                try? await Task.sleep(for: .seconds(2.5))
                                viewModel.toastMessage = nil
                            }
                        }
                    Spacer()
                }
                .padding(.top, CPLayout.space8)
            }

            // Deviation badge
            if let dev = viewModel.deviation {
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        deviationBadge(dev)
                    }
                }
                .padding(CPLayout.space4)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: viewModel.isHeroTurn)
        .animation(.spring(duration: 0.4), value: viewModel.board.count)
        .animation(.easeInOut(duration: 0.2), value: viewModel.isShowingSettlement)
        .sheet(isPresented: $showBuyInSheet) {
            BuyInSheet(
                seat: selectedSeat ?? 0,
                onConfirm: { buyIn in
                    if let seat = selectedSeat {
                        viewModel.sitDown(seat: seat, buyIn: buyIn)
                    }
                    showBuyInSheet = false
                },
                onCancel: { showBuyInSheet = false }
            )
            .presentationDetents([.height(240)])
            .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showOptions) {
            TableOptionsSheet(viewModel: viewModel, isPresented: $showOptions)
                .presentationDetents([.medium])
                .presentationDragIndicator(.visible)
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Top Bar

    private var tableTopBar: some View {
        HStack {
            Button { viewModel.leaveTable() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(CPColors.textSecondary)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(viewModel.roomName)
                    .font(CPTypography.bodySemibold)
                    .foregroundColor(CPColors.textPrimary)

                HStack(spacing: CPLayout.space2) {
                    Text(viewModel.roomCode)
                        .font(CPTypography.monoSmall)
                        .foregroundColor(CPColors.textMuted)

                    if let state = viewModel.tableState {
                        Text("\(CardParser.formatChips(state.smallBlind))/\(CardParser.formatChips(state.bigBlind))")
                            .font(CPTypography.monoSmall)
                            .foregroundColor(CPColors.gold)
                    }
                }
            }

            Spacer()

            CPConnectionBadge(connected: CPSocketManager.shared.isConnected)

            Button { showOptions = true } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.system(size: 20))
                    .foregroundColor(CPColors.textSecondary)
            }
        }
        .padding(.horizontal, CPLayout.space4)
        .padding(.vertical, CPLayout.space2)
        .background(CPColors.bgSurface)
    }

    // MARK: - Equity Bar

    private func equityBar(_ equities: [PlayerEquity]) -> some View {
        HStack(spacing: CPLayout.space3) {
            ForEach(equities, id: \.seat) { eq in
                let name = viewModel.players.first { $0.seat == eq.seat }?.name ?? "S\(eq.seat)"
                VStack(spacing: 2) {
                    Text(String(name.prefix(6)))
                        .font(.system(size: 9))
                        .foregroundColor(CPColors.textMuted)
                    Text("\(Int(eq.winRate * 100))%")
                        .font(CPTypography.monoSmall)
                        .foregroundColor(eq.winRate > 0.5 ? CPColors.success : CPColors.danger)
                }
            }
        }
        .padding(.horizontal, CPLayout.space3)
        .padding(.vertical, 4)
        .background(CPColors.bgElevated.opacity(0.8))
        .cornerRadius(CPLayout.radiusFull)
    }

    // MARK: - Deviation Badge

    private func deviationBadge(_ dev: DeviationState) -> some View {
        HStack(spacing: 4) {
            Image(systemName: dev.deviation > 0.15 ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                .font(.system(size: 11))
                .foregroundColor(dev.deviation > 0.15 ? CPColors.warning : CPColors.success)

            Text("\(dev.playerAction.capitalized)")
                .font(CPTypography.captionBold)
                .foregroundColor(CPColors.textPrimary)

            Text("\(Int(dev.deviation * 100))% dev")
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundColor(dev.deviation > 0.15 ? CPColors.warning : CPColors.textMuted)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(CPColors.bgElevated.opacity(0.9))
        .cornerRadius(CPLayout.radiusFull)
    }
}

// MARK: - Table Options Sheet

struct TableOptionsSheet: View {
    @Bindable var viewModel: PokerTableViewModel
    @Binding var isPresented: Bool

    var body: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()

                List {
                    Section("Player") {
                        if viewModel.heroSeat != nil {
                            Button("Sit Out") {
                                viewModel.sitOut()
                                isPresented = false
                            }
                            Button("Stand Up") {
                                viewModel.standUp()
                                isPresented = false
                            }
                            Button("Request Time") {
                                viewModel.requestThinkExtension()
                                isPresented = false
                            }
                        }
                    }

                    Section("Game") {
                        Button("Start Hand") {
                            viewModel.startHand()
                            isPresented = false
                        }
                        Button("Queue Bomb Pot") {
                            viewModel.queueBombPot()
                            isPresented = false
                        }
                    }

                    Section("Display") {
                        Toggle("Sound", isOn: Binding(
                            get: { !SoundManager.shared.isMuted },
                            set: { SoundManager.shared.isMuted = !$0 }
                        ))
                    }

                    Section {
                        Button("Leave Table", role: .destructive) {
                            viewModel.leaveTable()
                            isPresented = false
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Options")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { isPresented = false }
                        .foregroundColor(CPColors.accent)
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}

// MARK: - Buy-In Sheet

struct BuyInSheet: View {
    let seat: Int
    let onConfirm: (Double) -> Void
    let onCancel: () -> Void
    @State private var buyIn: Double = 100

    var body: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()
                VStack(spacing: CPLayout.space5) {
                    Text("Seat \(seat + 1)")
                        .font(CPTypography.heading)
                        .foregroundColor(CPColors.textPrimary)

                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text("Buy-in Amount")
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textSecondary)
                        TextField("100", value: $buyIn, format: .number)
                            .textFieldStyle(CPTextFieldStyle())
                            .keyboardType(.decimalPad)
                    }

                    Button {
                        HapticManager.action()
                        onConfirm(buyIn)
                    } label: {
                        Text("Sit Down").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpPrimary)

                    Spacer()
                }
                .padding(CPLayout.space4)
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { onCancel() }
                        .foregroundColor(CPColors.textSecondary)
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}
