import SwiftUI

// MARK: - Fast Battle View Model

@Observable
final class FastBattleViewModel {
    // Session
    var sessionId: String?
    var phase: FastBattlePhase = .setup
    var handsPlayed: Int = 0
    var targetHandCount: Int = 0
    var cumulativeResult: Double = 0
    var decisionsPerHour: Double = 0

    // Current table
    var currentTableId: String?
    var currentRoomCode: String?

    // Results
    var lastHandResult: FastBattleHandResultEntry?
    var handResults: [FastBattleHandResultEntry] = []
    var report: FastBattleReport?
    var error: String?

    private let socket = CPSocketManager.shared
    private let router: SocketEventRouter

    init(router: SocketEventRouter) {
        self.router = router
        registerEvents()
    }

    // MARK: - Actions

    func warmup() {
        socket.emit(SocketEvent.Client.fastBattleWarmup)
    }

    func startSession(targetHandCount: Int, bigBlind: Double = 3) {
        self.targetHandCount = targetHandCount
        error = nil
        socket.emit(SocketEvent.Client.fastBattleStart, [
            "targetHandCount": targetHandCount,
            "bigBlind": bigBlind
        ])
    }

    func endSession() {
        socket.emit(SocketEvent.Client.fastBattleEnd)
    }

    func resetToSetup() {
        phase = .setup
        sessionId = nil
        handsPlayed = 0
        cumulativeResult = 0
        handResults = []
        lastHandResult = nil
        report = nil
        error = nil
    }

    // MARK: - Events

    private func registerEvents() {
        router.on("fast_battle_session_started", type: FBSessionStartedPayload.self) { [weak self] payload in
            self?.sessionId = payload.sessionId
            self?.targetHandCount = payload.targetHandCount
            self?.phase = .switching
            self?.handsPlayed = 0
            self?.cumulativeResult = 0
            self?.handResults = []
        }

        router.on("fast_battle_table_assigned", type: FBTableAssignedPayload.self) { [weak self] payload in
            self?.currentTableId = payload.tableId
            self?.currentRoomCode = payload.roomCode
            self?.phase = .playing
        }

        router.on("fast_battle_hand_result", type: FBHandResultPayload.self) { [weak self] payload in
            let entry = FastBattleHandResultEntry(
                id: payload.handId,
                handId: payload.handId,
                handNumber: payload.handNumber,
                result: payload.result,
                heroPosition: payload.heroPosition,
                holeCards: payload.holeCards,
                board: payload.board,
                wentToShowdown: payload.wentToShowdown,
                cumulativeResult: payload.cumulativeResult,
                timestamp: Date.timeIntervalSinceReferenceDate
            )
            self?.lastHandResult = entry
            self?.handResults.append(entry)
            self?.cumulativeResult = payload.cumulativeResult

            // Auto-clear toast
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(3))
                if self?.lastHandResult?.id == entry.id {
                    self?.lastHandResult = nil
                }
            }
        }

        router.on("fast_battle_progress", type: FBProgressPayload.self) { [weak self] payload in
            self?.handsPlayed = payload.handsPlayed
            self?.cumulativeResult = payload.cumulativeResult
            self?.decisionsPerHour = payload.decisionsPerHour
        }

        router.on("fast_battle_session_ended", type: FBSessionEndedPayload.self) { [weak self] payload in
            self?.report = payload.report
            self?.phase = .report
            self?.currentTableId = nil
            self?.sessionId = nil

            // Persist session to UserDefaults (mirrors useFastBattle.ts localStorage)
            FastBattleSessionStore.save(payload.report)
        }

        router.on("fast_battle_error", type: FBErrorPayload.self) { [weak self] payload in
            self?.error = payload.message
        }
    }
}

// MARK: - Fast Battle Page

struct FastBattlePage: View {
    @Bindable var viewModel: FastBattleViewModel
    let onExit: () -> Void

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            switch viewModel.phase {
            case .setup:
                FastBattleSetupView(
                    onStart: { count in viewModel.startSession(targetHandCount: count) },
                    onBack: onExit,
                    error: viewModel.error
                )

            case .playing, .switching:
                // Table is shown via main ContentView, HUD is overlay
                VStack {
                    FastBattleHUD(
                        handsPlayed: viewModel.handsPlayed,
                        targetHandCount: viewModel.targetHandCount,
                        cumulativeResult: viewModel.cumulativeResult,
                        onEnd: { viewModel.endSession() }
                    )
                    Spacer()
                }

                // Hand result toast
                if let result = viewModel.lastHandResult {
                    VStack {
                        FastBattleHandResultToast(result: result)
                            .transition(.move(edge: .top).combined(with: .opacity))
                            .padding(.top, 60)
                        Spacer()
                    }
                }

            case .report:
                if let report = viewModel.report {
                    FastBattleReviewView(
                        report: report,
                        onPlayAgain: { viewModel.resetToSetup() },
                        onExit: onExit
                    )
                }
            }
        }
        .onAppear { viewModel.warmup() }
        .preferredColorScheme(.dark)
    }
}

// MARK: - Setup View

struct FastBattleSetupView: View {
    let onStart: (Int) -> Void
    let onBack: () -> Void
    var error: String?
    @State private var selectedCount: Int?

    var body: some View {
        VStack(spacing: CPLayout.space6) {
            Spacer()

            VStack(spacing: CPLayout.space3) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 48))
                    .foregroundColor(CPColors.allinColor)

                Text("Fast Battle")
                    .font(CPTypography.hero)
                    .foregroundColor(CPColors.textPrimary)

                Text("Rapid-fire hands against GTO bots")
                    .font(CPTypography.label)
                    .foregroundColor(CPColors.textSecondary)
            }

            // Hand count selector
            CPCard {
                VStack(spacing: CPLayout.space3) {
                    Text("How many hands?")
                        .font(CPTypography.title)
                        .foregroundColor(CPColors.textPrimary)

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: CPLayout.space2) {
                        ForEach([12, 100, 500, 1000], id: \.self) { count in
                            Button {
                                HapticManager.selection()
                                selectedCount = count
                            } label: {
                                Text("\(count)")
                                    .font(CPTypography.bodySemibold)
                                    .foregroundColor(selectedCount == count ? .white : CPColors.textPrimary)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, CPLayout.space3)
                                    .background(selectedCount == count ? CPColors.accent : CPColors.bgElevated)
                                    .cornerRadius(CPLayout.radiusMd)
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, CPLayout.space4)

            // Game info
            CPCard {
                VStack(spacing: CPLayout.space2) {
                    infoRow("Stakes", "1/3 blinds")
                    infoRow("Buy-in", "100bb per table")
                    infoRow("Opponents", "5 GTO bots (V4)")
                    infoRow("Format", "6-max NLH")
                }
            }
            .padding(.horizontal, CPLayout.space4)

            if let error {
                Text(error)
                    .font(CPTypography.caption)
                    .foregroundColor(CPColors.danger)
            }

            // Start button
            Button {
                HapticManager.action()
                if let count = selectedCount { onStart(count) }
            } label: {
                Text("Start Battle").frame(maxWidth: .infinity)
            }
            .buttonStyle(.cpPrimary)
            .disabled(selectedCount == nil)
            .padding(.horizontal, CPLayout.space4)

            Button("Back") { onBack() }
                .foregroundColor(CPColors.textSecondary)

            Spacer()
        }
    }

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(CPTypography.label).foregroundColor(CPColors.textSecondary)
            Spacer()
            Text(value).font(CPTypography.monoSmall).foregroundColor(CPColors.textMuted)
        }
    }
}

// MARK: - HUD

struct FastBattleHUD: View {
    let handsPlayed: Int
    let targetHandCount: Int
    let cumulativeResult: Double
    let onEnd: () -> Void

    var body: some View {
        HStack {
            Button {
                HapticManager.action()
                onEnd()
            } label: {
                Text("End")
                    .font(CPTypography.labelBold)
                    .foregroundColor(CPColors.danger)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(CPColors.bgElevated)
                    .cornerRadius(CPLayout.radiusFull)
            }

            Spacer()

            HStack(spacing: CPLayout.space3) {
                Text("\(handsPlayed)/\(targetHandCount)")
                    .font(CPTypography.mono)
                    .foregroundColor(CPColors.textPrimary)

                Text(cumulativeResult >= 0 ? "+\(CardParser.formatChips(cumulativeResult))" : CardParser.formatChips(cumulativeResult))
                    .font(CPTypography.mono)
                    .foregroundColor(cumulativeResult >= 0 ? CPColors.success : CPColors.danger)
            }

            Spacer()
        }
        .padding(.horizontal, CPLayout.space4)
        .padding(.vertical, CPLayout.space2)
        .background(CPColors.bgSurface.opacity(0.9))
    }
}

// MARK: - Hand Result Toast

struct FastBattleHandResultToast: View {
    let result: FastBattleHandResultEntry

    var body: some View {
        HStack(spacing: CPLayout.space2) {
            Text("#\(result.handNumber)")
                .font(CPTypography.captionBold)
                .foregroundColor(CPColors.textMuted)

            Text(result.heroPosition)
                .font(CPTypography.caption)
                .foregroundColor(CPColors.gold)

            HStack(spacing: 2) {
                ForEach(result.holeCards, id: \.self) { card in
                    CardView(notation: card, size: .small)
                }
            }

            Spacer()

            Text(result.result >= 0 ? "+\(CardParser.formatChips(result.result))" : CardParser.formatChips(result.result))
                .font(CPTypography.mono)
                .foregroundColor(result.result >= 0 ? CPColors.success : CPColors.danger)
        }
        .padding(.horizontal, CPLayout.space3)
        .padding(.vertical, CPLayout.space2)
        .background(result.result >= 0 ? CPColors.success.opacity(0.1) : CPColors.danger.opacity(0.1))
        .cornerRadius(CPLayout.radiusMd)
        .padding(.horizontal, CPLayout.space4)
    }
}

// MARK: - Review View

struct FastBattleReviewView: View {
    let report: FastBattleReport
    let onPlayAgain: () -> Void
    let onExit: () -> Void
    @State private var showHandHistory = false

    // GTO reference ranges (server sends as 0.0-1.0 decimals, except AF)
    // Web uses decimal: vpip 0.20-0.28; if server sends percentage (20-28) we normalize
    private let gtoRanges: [(String, Double, Double, Bool)] = [
        // (label, low, high, isPercentageRange)
        ("VPIP", 0.20, 0.28, true), ("PFR", 0.16, 0.22, true), ("3-Bet", 0.07, 0.12, true),
        ("Fold 3B", 0.50, 0.65, true), ("AF", 2.0, 4.0, false),
        ("CB Flop", 0.55, 0.75, true), ("CB Turn", 0.45, 0.65, true),
        ("WTSD", 0.25, 0.35, true), ("W$SD", 0.48, 0.58, true)
    ]

    /// Normalize value: if > 1 and isPercentageRange, treat as already percentage and divide by 100
    private func isInGtoRange(_ label: String, _ value: Double) -> Bool {
        guard let range = gtoRanges.first(where: { $0.0 == label }) else { return true }
        let normalized = (range.3 && value > 1.0) ? value / 100.0 : value
        return normalized >= range.1 && normalized <= range.2
    }

    private func formatStatValue(_ label: String, _ value: Double) -> String {
        if label == "AF" { return String(format: "%.1f", value) }
        // Display as percentage
        let pct = value > 1.0 ? value : value * 100
        return String(format: "%.0f%%", pct)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: CPLayout.space4) {
                // Header
                VStack(spacing: CPLayout.space2) {
                    Text("Battle Complete")
                        .font(CPTypography.hero)
                        .foregroundColor(CPColors.textPrimary)

                    HStack(spacing: CPLayout.space4) {
                        Text("\(report.handCount) hands")
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textSecondary)
                        Text(formatDuration(report.durationMs))
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textMuted)
                    }

                    Text(report.stats.netChips >= 0 ? "+\(CardParser.formatChips(report.stats.netChips))" : CardParser.formatChips(report.stats.netChips))
                        .font(CPTypography.displayLarge)
                        .foregroundColor(report.stats.netChips >= 0 ? CPColors.success : CPColors.danger)

                    Text(String(format: "%.1f BB/100", report.stats.netBb / max(Double(report.stats.handsPlayed), 1) * 100))
                        .font(CPTypography.mono)
                        .foregroundColor(CPColors.textSecondary)
                }
                .padding(.top, CPLayout.space4)

                // Behavior Stats
                CPCard {
                    VStack(alignment: .leading, spacing: CPLayout.space3) {
                        Text("Behavior Overview")
                            .font(CPTypography.heading)
                            .foregroundColor(CPColors.textPrimary)

                        let stats = report.stats
                        let values: [(String, Double)] = [
                            ("VPIP", stats.vpip), ("PFR", stats.pfr), ("3-Bet", stats.threeBet),
                            ("Fold 3B", stats.foldTo3Bet), ("AF", stats.aggressionFactor),
                            ("CB Flop", stats.cbetFlop), ("CB Turn", stats.cbetTurn),
                            ("WTSD", stats.wtsd), ("W$SD", stats.wsd)
                        ]

                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: CPLayout.space2) {
                            ForEach(Array(values.enumerated()), id: \.offset) { idx, item in
                                let inRange = isInGtoRange(item.0, item.1)
                                VStack(spacing: 2) {
                                    Text(formatStatValue(item.0, item.1))
                                        .font(CPTypography.mono)
                                        .foregroundColor(inRange ? CPColors.success : CPColors.danger)
                                    Text(item.0)
                                        .font(.system(size: 9))
                                        .foregroundColor(CPColors.textMuted)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                                .background(CPColors.bgBase)
                                .cornerRadius(CPLayout.radiusSm)
                            }
                        }
                    }
                }
                .padding(.horizontal, CPLayout.space4)

                // GTO Leak Summary
                if let leak = report.sessionLeak {
                    CPCard {
                        VStack(alignment: .leading, spacing: CPLayout.space2) {
                            Text("GTO Leak Summary")
                                .font(CPTypography.heading)
                                .foregroundColor(CPColors.textPrimary)

                            HStack(spacing: CPLayout.space4) {
                                statPill("BB/100 Leaked", String(format: "%.1f", leak.leakedBbPer100))
                                statPill("Total BB", String(format: "%.1f", leak.totalLeakedBb))
                                statPill("Audited", "\(leak.handsAudited)")
                            }
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)
                }

                // Problem Hands
                if !report.problemHands.isEmpty {
                    CPCard {
                        VStack(alignment: .leading, spacing: CPLayout.space2) {
                            Text("Problem Hands (Top 10)")
                                .font(CPTypography.heading)
                                .foregroundColor(CPColors.textPrimary)

                            ForEach(report.problemHands.prefix(10)) { hand in
                                HStack {
                                    Text("#\(hand.rank)")
                                        .font(CPTypography.captionBold)
                                        .foregroundColor(CPColors.gold)
                                        .frame(width: 24)

                                    Text(hand.heroPosition)
                                        .font(CPTypography.caption)
                                        .foregroundColor(CPColors.textMuted)

                                    HStack(spacing: 2) {
                                        ForEach(hand.holeCards, id: \.self) { c in
                                            CardView(notation: c, size: .small)
                                        }
                                    }

                                    Spacer()

                                    Text(String(format: "%.1f BB", hand.totalLeakedBb))
                                        .font(CPTypography.monoSmall)
                                        .foregroundColor(CPColors.danger)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)
                }

                // Recommendations
                if let recs = report.recommendations, !recs.isEmpty {
                    CPCard {
                        VStack(alignment: .leading, spacing: CPLayout.space2) {
                            Text("Recommendations")
                                .font(CPTypography.heading)
                                .foregroundColor(CPColors.textPrimary)

                            ForEach(recs) { rec in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(rec.title)
                                        .font(CPTypography.bodySemibold)
                                        .foregroundColor(CPColors.accent)
                                    Text(rec.description)
                                        .font(CPTypography.caption)
                                        .foregroundColor(CPColors.textMuted)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)
                }

                // Collapsible Hand History (mirrors FastBattleReview.tsx)
                if !report.handRecords.isEmpty {
                    CPCard {
                        VStack(alignment: .leading, spacing: CPLayout.space2) {
                            Button {
                                withAnimation { showHandHistory.toggle() }
                            } label: {
                                HStack {
                                    Text("Hand History (\(report.handRecords.count))")
                                        .font(CPTypography.heading)
                                        .foregroundColor(CPColors.textPrimary)
                                    Spacer()
                                    Image(systemName: showHandHistory ? "chevron.up" : "chevron.down")
                                        .foregroundColor(CPColors.textMuted)
                                }
                            }

                            if showHandHistory {
                                ForEach(report.handRecords) { hand in
                                    HStack {
                                        Text(hand.heroPosition)
                                            .font(CPTypography.caption)
                                            .foregroundColor(CPColors.textMuted)
                                            .frame(width: 28)
                                        HStack(spacing: 2) {
                                            ForEach(hand.holeCards, id: \.self) { c in
                                                CardView(notation: c, size: .small)
                                            }
                                        }
                                        if !hand.board.isEmpty {
                                            HStack(spacing: 1) {
                                                ForEach(hand.board, id: \.self) { c in
                                                    CardView(notation: c, size: .small)
                                                }
                                            }
                                        }
                                        Spacer()
                                        Text(hand.result >= 0 ? "+\(CardParser.formatChips(hand.result))" : CardParser.formatChips(hand.result))
                                            .font(CPTypography.monoSmall)
                                            .foregroundColor(hand.result >= 0 ? CPColors.success : CPColors.danger)
                                    }
                                    .padding(.vertical, 2)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)
                }

                // Action buttons
                VStack(spacing: CPLayout.space3) {
                    Button {
                        HapticManager.action()
                        onPlayAgain()
                    } label: {
                        Text("Play Again").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpPrimary)

                    Button {
                        onExit()
                    } label: {
                        Text("Exit").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpSecondary)
                }
                .padding(.horizontal, CPLayout.space4)
                .padding(.bottom, CPLayout.space8)
            }
        }
    }

    private func statPill(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(CPTypography.monoSmall).foregroundColor(CPColors.textPrimary)
            Text(label).font(.system(size: 9)).foregroundColor(CPColors.textMuted)
        }
        .frame(maxWidth: .infinity)
    }

    private func formatDuration(_ ms: Double) -> String {
        let seconds = Int(ms / 1000)
        let minutes = seconds / 60
        let secs = seconds % 60
        return "\(minutes)m \(secs)s"
    }
}

// MARK: - Fast Battle Session Persistence (mirrors useFastBattle.ts localStorage)

enum FastBattleSessionStore {
    private static let key = "cardpilot_fb_sessions"
    private static let maxSessions = 50

    static func save(_ report: FastBattleReport) {
        var sessions = loadAll()
        sessions.append(report)
        if sessions.count > maxSessions {
            sessions = Array(sessions.suffix(maxSessions))
        }
        if let data = try? JSONEncoder().encode(sessions) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    static func loadAll() -> [FastBattleReport] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let sessions = try? JSONDecoder().decode([FastBattleReport].self, from: data)
        else { return [] }
        return sessions
    }

    static func clear() {
        UserDefaults.standard.removeObject(forKey: key)
    }
}
