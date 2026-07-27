import Foundation

// MARK: - Poker Table View Model
// Full game state management — mirrors useGameSocketEvents.ts completely

@Observable
final class PokerTableViewModel {
    // MARK: Core Game State
    var tableState: TableState?
    var roomState: RoomFullState?
    var holeCards: [String] = []
    var heroSeat: Int?
    var board: [String] = []
    var pot: Double = 0
    var currentBet: Double = 0
    var legalActions: LegalActions?
    var actorSeat: Int?
    var street: Street = .preflop
    var handId: String?
    var players: [TablePlayer] = []
    var positions: [String: String] = [:]
    var winners: [HandWinner] = []

    // MARK: Settlement
    var settlement: SettlementResult?
    var showdownResults: ShowdownResultsPayload?
    var isShowingSettlement = false

    // MARK: All-In & Run-It-Twice
    var allInLock: AllInLockState?
    var myRunPreference: Int? // 1, 2, or 3
    var boardReveal: BoardRevealState?

    // MARK: Advice & GTO
    var advice: AdvicePayload?
    var deviation: DeviationState?

    // MARK: Pre-Actions
    var preAction: PreAction?
    var actionPending = false

    // MARK: Post-Hand State
    var postHandShowAvailable = false
    var postHandRevealedCards: [Int: [String]] = [:]

    // MARK: Special Modes
    var sevenTwoBountyPrompt: SevenTwoBountyPrompt?
    var sevenTwoBountyResult: SevenTwoBountyInfo?
    var sevenTwoRevealActive: SevenTwoBountyInfo?
    var bombPotOverlayActive: BombPotOverlay?

    // MARK: UI State
    var lastActionBySeat: [Int: LastAction] = [:]
    var revealedHoles: [Int: [String]] = [:]
    var errorMessage: String?
    var toastMessage: String?

    // MARK: Navigation
    var tableId: String
    var roomCode: String
    var roomName: String

    // MARK: Timer
    var timerState: TimerState?

    // MARK: Private
    private var latestSnapshotVersion: Int = -1
    private var authUserId: String?
    private let socket = CPSocketManager.shared
    private let router: SocketEventRouter

    init(tableId: String, roomCode: String, roomName: String, router: SocketEventRouter, authUserId: String? = nil) {
        self.tableId = tableId
        self.roomCode = roomCode
        self.roomName = roomName
        self.router = router
        self.authUserId = authUserId
        registerEvents()
    }

    // MARK: - Player Actions

    func submitAction(_ action: PlayerActionType, amount: Double? = nil) {
        guard let handId, !actionPending else { return }
        actionPending = true

        var payload: [String: Any] = [
            "tableId": tableId,
            "handId": handId,
            "action": action.rawValue
        ]
        if let amount { payload["amount"] = amount }

        socket.emit(SocketEvent.Client.actionSubmit, payload)
        HapticManager.action()
    }

    func fold() { submitAction(.fold) }
    func check() { submitAction(.check) }
    func call() { submitAction(.call) }
    func raise(to amount: Double) { submitAction(.raise, amount: amount) }
    func allIn() { submitAction(.all_in) }

    func sitDown(seat: Int, buyIn: Double) {
        socket.emit(SocketEvent.Client.sitDown, [
            "tableId": tableId, "seat": seat, "buyIn": buyIn
        ])
    }

    func standUp() {
        guard let seat = heroSeat else { return }
        socket.emit(SocketEvent.Client.standUp, ["tableId": tableId, "seat": seat])
    }

    func sitIn() {
        socket.emit("sit_in", ["tableId": tableId])
    }

    func sitOut() {
        socket.emit("sit_out", ["tableId": tableId])
    }

    func startHand() {
        socket.emit(SocketEvent.Client.startHand, ["tableId": tableId])
    }

    func leaveTable() {
        socket.emit(SocketEvent.Client.leaveTable, ["tableId": tableId])
    }

    func showHandPost() {
        guard let seat = heroSeat else { return }
        socket.emit(SocketEvent.Client.showHandPost, ["tableId": tableId, "seat": seat])
        postHandShowAvailable = false
    }

    func muckHand() {
        guard let seat = heroSeat, let handId else { return }
        socket.emit(SocketEvent.Client.muckHand, [
            "tableId": tableId, "handId": handId, "seat": seat
        ])
        postHandShowAvailable = false
    }

    func submitRunPreference(_ count: Int) {
        guard let handId else { return }
        myRunPreference = count
        socket.emit(SocketEvent.Client.runCountSubmit, [
            "tableId": tableId, "handId": handId, "runCount": count
        ])
    }

    func requestThinkExtension() {
        socket.emit(SocketEvent.Client.requestThinkExtension, ["tableId": tableId])
    }

    func queueBombPot() {
        socket.emit("queue_bomb_pot", ["tableId": tableId])
    }

    func gameControl(_ action: String) {
        socket.emit(SocketEvent.Client.gameControl, ["tableId": tableId, "action": action])
    }

    func requestSessionStats() {
        socket.emit(SocketEvent.Client.requestSessionStats, ["tableId": tableId])
    }

    // MARK: - Pre-Action Management

    func setPreAction(_ type: PreActionType?) {
        guard let type, let handId, let userId = authUserId else {
            preAction = nil
            return
        }
        if preAction?.actionType == type {
            preAction = nil // toggle off
        } else {
            preAction = PreAction(handId: handId, playerId: userId, actionType: type, createdAt: Date.timeIntervalSinceReferenceDate)
        }
    }

    /// Auto-fires pre-action when it's hero's turn
    func checkAutoFirePreAction() {
        guard let preAction, let tableState, !actionPending, isHeroTurn else { return }
        guard preAction.handId == handId else {
            self.preAction = nil
            return
        }
        guard let legal = legalActions else { return }

        var fireAction: PlayerActionType?
        switch preAction.actionType {
        case .fold:
            fireAction = legal.canCheck ? nil : .fold // suppress fold if free check
        case .check:
            fireAction = legal.canCheck ? .check : nil
        case .call:
            fireAction = legal.canCall ? .call : nil
        case .checkFold:
            if legal.canCheck { fireAction = .check }
            else if legal.canFold { fireAction = .fold }
        }

        if let action = fireAction {
            self.preAction = nil
            submitAction(action)
        }
    }

    var derivedPreActionOptions: [PreActionOption] {
        guard let tableState, let userId = authUserId else { return [] }
        guard let _ = handId, isActionableStreet else { return [] }

        let player = players.first { $0.userId == userId }
        guard let player, player.status == .active, player.inHand, !player.folded, !player.allIn else {
            return []
        }

        let toCall = max(0, currentBet - player.streetCommitted)
        if toCall <= 0 {
            return [
                PreActionOption(type: .check, label: "Check"),
                PreActionOption(type: .checkFold, label: "Check / Fold")
            ]
        } else {
            let callAmount = min(toCall, player.stack)
            return [
                PreActionOption(type: .call, label: "Call \(CardParser.formatChips(callAmount))"),
                PreActionOption(type: .fold, label: "Fold")
            ]
        }
    }

    // MARK: - Computed Properties

    var heroPlayer: TablePlayer? {
        guard let seat = heroSeat else { return nil }
        return players.first { $0.seat == seat }
    }

    var isHeroTurn: Bool {
        guard let actor = actorSeat, let hero = heroSeat else { return false }
        return actor == hero
    }

    var isActionableStreet: Bool {
        [.preflop, .flop, .turn, .river].contains(street)
    }

    var activePlayers: [TablePlayer] {
        players.filter { $0.inHand && !$0.folded }
    }

    var seatedPlayers: [TablePlayer] {
        players.filter { $0.status == .active || $0.status == .sitting_out }
    }

    var shouldShowFoldConfirm: Bool {
        legalActions?.canCheck ?? false
    }

    // MARK: - Seat Layout

    func seatPosition(for seatIndex: Int, maxSeats: Int, in size: CGSize) -> CGPoint {
        let heroOffset = heroSeat ?? 0
        let adjustedIndex = (seatIndex - heroOffset + maxSeats) % maxSeats
        let angle = (Double(adjustedIndex) / Double(maxSeats)) * 2 * .pi - .pi / 2
        let centerX = size.width / 2
        let centerY = size.height / 2
        let radiusX = size.width * 0.38
        let radiusY = size.height * 0.38
        return CGPoint(
            x: centerX + radiusX * cos(angle + .pi),
            y: centerY + radiusY * sin(angle + .pi)
        )
    }

    // MARK: - Full Event Registration

    private func registerEvents() {
        router.registerTableEvents(
            onSnapshot: { [weak self] state in
                self?.applySnapshot(state)
            },
            onHoleCards: { [weak self] payload in
                self?.holeCards = payload.cards
                self?.heroSeat = payload.seat
                self?.handId = payload.handId
                SoundManager.shared.play(.deal)
                HapticManager.deal()
            },
            onHandStarted: { [weak self] payload in
                guard let self else { return }
                self.handId = payload.handId
                // Reset all hand-level state (mirrors useGameSocketEvents.ts onHandStarted)
                self.actionPending = false
                self.advice = nil
                self.deviation = nil
                self.winners = []
                self.allInLock = nil
                self.myRunPreference = nil
                self.boardReveal = nil
                self.holeCards = []
                self.settlement = nil
                self.preAction = nil
                self.lastActionBySeat = [:]
                self.postHandShowAvailable = false
                self.sevenTwoBountyPrompt = nil
                self.sevenTwoBountyResult = nil
                self.postHandRevealedCards = [:]
                self.isShowingSettlement = false
                self.timerState = nil
                self.revealedHoles = [:]
                self.bombPotOverlayActive = nil
            },
            onActionApplied: { [weak self] payload in
                guard let self else { return }
                if payload.seat == self.heroSeat {
                    self.actionPending = false
                }
                self.lastActionBySeat[payload.seat] = LastAction(
                    action: payload.action, amount: payload.amount
                )
                self.pot = payload.pot
                SoundManager.shared.play(.chipBet)
            },
            onStreetAdvanced: { [weak self] payload in
                self?.street = payload.street
                self?.board = payload.board
                self?.lastActionBySeat = [:]
            },
            onBoardReveal: { [weak self] payload in
                self?.street = payload.street
                self?.board = payload.board
                self?.boardReveal = BoardRevealState(
                    street: payload.street.rawValue,
                    equities: payload.equities,
                    hints: payload.hints
                )
                SoundManager.shared.play(.deal)
            },
            onShowdownResults: { [weak self] payload in
                guard let self else { return }
                if let liveHandId = self.tableState?.handId, payload.handId != liveHandId { return }
                self.showdownResults = payload
                let winnersFromPayouts = payload.totalPayouts
                    .compactMap { (seatStr, amount) -> HandWinner? in
                        guard let seat = Int(seatStr), amount > 0 else { return nil }
                        return HandWinner(seat: seat, amount: amount)
                    }
                if !winnersFromPayouts.isEmpty {
                    self.winners = winnersFromPayouts
                }
            },
            onHandEnded: { [weak self] payload in
                guard let self else { return }
                self.actionPending = false
                self.myRunPreference = nil
                self.boardReveal = nil
                self.preAction = nil

                if let w = payload.winners { self.winners = w }
                if let finalState = payload.finalState {
                    self.applySnapshot(finalState)
                }

                if let settlement = payload.settlement {
                    self.settlement = settlement
                    self.isShowingSettlement = true

                    // Winner toast + sound
                    let winnerNames = settlement.winnersByRun
                        .flatMap { $0.winners }
                        .map { w in
                            let name = self.players.first { $0.seat == w.seat }?.name ?? "Seat \(w.seat)"
                            return "\(name) +\(CardParser.formatChips(w.amount))"
                        }
                    if !winnerNames.isEmpty {
                        self.toastMessage = winnerNames.count == 1
                            ? "Winner: \(winnerNames[0])"
                            : "Winners: \(winnerNames.joined(separator: ", "))"
                        SoundManager.shared.play(.chipWin)

                        // Hero win haptic
                        if settlement.winnersByRun.contains(where: { run in
                            run.winners.contains { $0.seat == self.heroSeat }
                        }) {
                            HapticManager.win()
                        }
                    }

                    // Seven-two bounty
                    if let bounty = settlement.sevenTwoBounty {
                        self.sevenTwoBountyResult = bounty
                        self.sevenTwoRevealActive = bounty
                    }
                }

                // Post-hand show/muck available
                if self.holeCards.count >= 2 {
                    self.postHandShowAvailable = true
                    self.postHandRevealedCards = [:]
                }

                // Save hand to local history
                self.saveHandToLocalHistory(payload)

                // Delay clearing hole cards (800ms) to show in summary
                let endedHandId = payload.handId
                Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(800))
                    if self.tableState?.handId == endedHandId || self.tableState?.handId == nil {
                        self.holeCards = []
                    }
                }

                // Auto-dismiss settlement
                Task { @MainActor in
                    try? await Task.sleep(for: .seconds(3))
                    self.isShowingSettlement = false
                }
            },
            onAdvice: { [weak self] payload in
                self?.advice = payload
            },
            onError: { [weak self] message in
                self?.errorMessage = message
                self?.toastMessage = message
            }
        )

        // Advice deviation
        router.on(SocketEvent.Server.adviceDeviation, type: AdviceDeviationPayload.self) { [weak self] payload in
            self?.deviation = DeviationState(deviation: payload.deviation, playerAction: payload.playerAction)
        }

        // All-in locked
        router.on(SocketEvent.Server.allinLocked, type: AllInLockedPayload.self) { [weak self] payload in
            guard let self else { return }
            let liveHandId = self.tableState?.handId
            if let liveHandId, payload.handId != liveHandId { return }
            self.allInLock = AllInLockState(
                handId: payload.handId,
                eligiblePlayers: payload.eligiblePlayers,
                submittedPlayerIds: payload.submittedPlayerIds ?? [],
                underdogSeat: payload.underdogSeat,
                targetRunCount: payload.targetRunCount,
                equities: payload.equities
            )
            if let heroSeat = self.heroSeat, !(payload.submittedPlayerIds ?? []).contains(heroSeat) {
                self.myRunPreference = nil
            }
        }

        // Run-twice reveal
        router.on(SocketEvent.Server.runTwiceReveal, type: RunTwiceRevealPayload.self) { [weak self] payload in
            guard let self else { return }
            self.boardReveal = BoardRevealState(
                street: payload.street,
                equities: payload.equities ?? self.boardReveal?.equities ?? [],
                hints: payload.hints ?? self.boardReveal?.hints
            )
        }

        // Reveal hole cards
        router.on(SocketEvent.Server.revealHoleCards, type: RevealHoleCardsPayload.self) { [weak self] payload in
            for (seatStr, cards) in payload.revealed {
                if let seat = Int(seatStr) {
                    self?.revealedHoles[seat] = cards
                }
            }
        }

        // Post-hand reveal (8s auto-dismiss)
        router.on(SocketEvent.Server.postHandReveal, type: PostHandRevealPayload.self) { [weak self] payload in
            self?.postHandRevealedCards[payload.seat] = payload.cards
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(8))
                self?.postHandRevealedCards.removeValue(forKey: payload.seat)
            }
        }

        // Seven-two bounty claimed
        router.on(SocketEvent.Server.sevenTwoBountyClaimed, type: SevenTwoBountyClaimedPayload.self) { [weak self] payload in
            self?.sevenTwoBountyResult = payload.bounty
            self?.sevenTwoBountyPrompt = nil
            self?.sevenTwoRevealActive = payload.bounty
            self?.toastMessage = "7-2 Bounty! +\(CardParser.formatChips(payload.bounty.totalBounty))"
            HapticManager.win()
        }

        // Bomb pot queued
        router.on("bomb_pot_queued") { [weak self] in
            self?.toastMessage = "Bomb Pot queued for next hand"
        }

        // Room state update
        router.on(SocketEvent.Server.roomStateUpdate, type: RoomFullState.self) { [weak self] state in
            self?.roomState = state
        }

        // Timer update
        router.on(SocketEvent.Server.timerUpdate, type: TimerState.self) { [weak self] timer in
            self?.timerState = timer
        }

        // Left table
        router.on(SocketEvent.Server.leftTable, type: LeftTablePayload.self) { [weak self] _ in
            self?.tableState = nil
            self?.holeCards = []
            self?.heroSeat = nil
        }

        // Kicked
        router.on(SocketEvent.Server.kicked, type: KickedPayload.self) { [weak self] payload in
            self?.toastMessage = "You were kicked: \(payload.reason)"
            self?.tableState = nil
            self?.holeCards = []
            self?.heroSeat = nil
        }

        // Player disconnected / reconnected
        router.on(SocketEvent.Server.playerDisconnected, type: PlayerDisconnectedPayload.self) { [weak self] payload in
            self?.toastMessage = "Player at seat \(payload.seat) disconnected (\(payload.graceSeconds)s grace)"
        }

        router.on(SocketEvent.Server.playerReconnected, type: PlayerReconnectedPayload.self) { [weak self] payload in
            self?.toastMessage = "Player at seat \(payload.seat) reconnected"
        }
    }

    // MARK: - Snapshot Application (with version deduplication)

    private func applySnapshot(_ state: TableState) {
        let incoming = state.stateVersion
        let current = latestSnapshotVersion

        // Ignore stale snapshots (exception: fast-battle tables always apply)
        if incoming < current {
            if state.tableId.hasPrefix("fb_") && !state.players.isEmpty {
                latestSnapshotVersion = incoming
            } else {
                return
            }
        }

        latestSnapshotVersion = incoming
        tableState = state
        players = state.players
        board = state.board
        pot = state.pot
        currentBet = state.currentBet
        legalActions = state.legalActions
        actorSeat = state.actorSeat
        street = state.street
        handId = state.handId
        positions = state.positions
        winners = state.winners ?? []

        // Auto-detect hero seat from userId
        if let userId = authUserId, let heroPlayer = state.players.first(where: { $0.userId == userId }) {
            if heroPlayer.seat != heroSeat {
                heroSeat = heroPlayer.seat
            }
        }

        // Auto-fire pre-action if it's now our turn
        if isHeroTurn {
            checkAutoFirePreAction()
        }
    }

    // MARK: - Hand History Saving

    private func saveHandToLocalHistory(_ payload: HandEndedPayload) {
        guard let fs = payload.finalState ?? tableState,
              holeCards.count >= 2,
              let heroSeat = heroSeat, heroSeat > 0
        else { return }

        let heroPlayer = fs.players.first { $0.seat == heroSeat }
        let heroLedger = payload.settlement?.ledger.first { $0.seat == heroSeat }
        let position = fs.positions[String(heroSeat)] ?? "BTN"

        let actions: [LocalHandAction] = (fs.actions).map { a in
            LocalHandAction(seat: a.seat, street: a.street.rawValue, type: a.type.rawValue, amount: a.amount)
        }

        let tags = HandHistoryManager.autoTag(actions)

        var playerNames: [Int: String] = [:]
        var showdownHands: [Int: [String]] = [:]
        for p in fs.players {
            playerNames[p.seat] = p.name
            if let revealed = fs.revealedHoles?[String(p.seat)], !revealed.isEmpty {
                showdownHands[p.seat] = revealed
            }
        }

        let record = LocalHandRecord(
            gameType: fs.gameType == .omaha ? "PLO" : "NLH",
            stakes: "\(fs.smallBlind)/\(fs.bigBlind)",
            tableSize: fs.players.count,
            position: position,
            heroCards: holeCards,
            board: fs.board,
            runoutBoards: fs.runoutBoards,
            actions: actions,
            potSize: payload.settlement?.totalPot ?? fs.pot,
            stackSize: heroPlayer?.stack ?? 0,
            result: heroLedger?.net ?? 0,
            tags: tags,
            roomCode: roomCode,
            roomName: roomName,
            tableId: tableId,
            handId: fs.handId,
            endedAt: ISO8601DateFormatter().string(from: Date()),
            heroSeat: heroSeat,
            heroName: heroPlayer?.name,
            smallBlind: fs.smallBlind,
            bigBlind: fs.bigBlind,
            playersCount: fs.players.count,
            didWinAnyRun: payload.settlement?.winnersByRun.contains { run in
                run.winners.contains { $0.seat == heroSeat }
            } ?? false,
            showdownHands: showdownHands.isEmpty ? nil : showdownHands,
            playerNames: playerNames,
            buttonSeat: fs.buttonSeat,
            isBombPotHand: fs.isBombPotHand ?? false,
            isDoubleBoardHand: fs.isDoubleBoardHand ?? false
        )

        HandHistoryManager.saveHand(record)
    }
}

// MARK: - Supporting Types

struct LastAction {
    let action: String
    let amount: Double
}

struct DeviationState {
    let deviation: Double
    let playerAction: String
}

struct AllInLockState {
    let handId: String
    let eligiblePlayers: [AllInEligiblePlayer]
    let submittedPlayerIds: [Int]
    let underdogSeat: Int?
    let targetRunCount: Int?
    let equities: [PlayerEquity]?
}

struct AllInEligiblePlayer: Codable {
    let seat: Int
    let name: String
}

struct BoardRevealState {
    let street: String
    let equities: [PlayerEquity]
    let hints: [SeatHint]?
}

struct SevenTwoBountyPrompt {
    let bountyPerPlayer: Double
    let totalBounty: Double
}

struct BombPotOverlay {
    let anteAmount: Double
}

enum PreActionType: String, Codable {
    case check, fold, call
    case checkFold = "check/fold"
}

struct PreAction {
    let handId: String
    let playerId: String
    let actionType: PreActionType
    let createdAt: TimeInterval
}

struct PreActionOption: Identifiable {
    var id: String { type.rawValue }
    let type: PreActionType
    let label: String
}

// MARK: - Additional Codable Payloads

struct AdviceDeviationPayload: Codable {
    let deviation: Double
    let playerAction: String
}

struct AllInLockedPayload: Codable {
    let handId: String
    let eligiblePlayers: [AllInEligiblePlayer]
    var submittedPlayerIds: [Int]?
    var underdogSeat: Int?
    var targetRunCount: Int?
    var equities: [PlayerEquity]?
}

struct RunTwiceRevealPayload: Codable {
    let handId: String?
    let street: String
    var equities: [PlayerEquity]?
    var hints: [SeatHint]?
    var run1: RunBoard?
    var run2: RunBoard?
}

struct RunBoard: Codable {
    let newCards: [String]
    let board: [String]
}

struct SevenTwoBountyClaimedPayload: Codable {
    let tableId: String
    let handId: String
    let bounty: SevenTwoBountyInfo
}

struct PlayerDisconnectedPayload: Codable {
    let seat: Int
    let userId: String
    let graceSeconds: Int
}

struct PlayerReconnectedPayload: Codable {
    let seat: Int
    let userId: String
}
