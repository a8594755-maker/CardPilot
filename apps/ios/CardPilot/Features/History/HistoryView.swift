import SwiftUI

// MARK: - History View Model

@Observable
final class HistoryViewModel {
    var rooms: [HistoryRoomSummary] = []
    var sessions: [HistorySessionSummary] = []
    var hands: [HistoryHandSummary] = []
    var selectedHandDetail: HistoryHandDetail?
    var isLoading = false
    var hasMore = false

    private let socket = CPSocketManager.shared
    private let router: SocketEventRouter

    init(router: SocketEventRouter) {
        self.router = router
        registerEvents()
    }

    func requestRooms() {
        isLoading = true
        socket.emit(SocketEvent.Client.requestHistoryRooms, ["limit": 50])
    }

    func requestSessions(roomId: String) {
        isLoading = true
        socket.emit(SocketEvent.Client.requestHistorySessions, [
            "roomId": roomId,
            "limit": 50
        ])
    }

    func requestHands(roomSessionId: String) {
        isLoading = true
        socket.emit(SocketEvent.Client.requestHistoryHands, [
            "roomSessionId": roomSessionId,
            "limit": 50
        ])
    }

    func requestHandDetail(handHistoryId: String) {
        isLoading = true
        socket.emit(SocketEvent.Client.requestHistoryHandDetail, [
            "handHistoryId": handHistoryId
        ])
    }

    private func registerEvents() {
        router.registerHistoryEvents(
            onRooms: { [weak self] rooms in
                self?.rooms = rooms
                self?.isLoading = false
            },
            onSessions: { [weak self] _, sessions in
                self?.sessions = sessions
                self?.isLoading = false
            },
            onHands: { [weak self] payload in
                self?.hands = payload.hands
                self?.hasMore = payload.hasMore
                self?.isLoading = false
            },
            onHandDetail: { [weak self] payload in
                self?.selectedHandDetail = payload.hand
                self?.isLoading = false
            }
        )
    }
}

// MARK: - History Rooms View

struct HistoryRoomsView: View {
    @Bindable var viewModel: HistoryViewModel

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            if viewModel.isLoading && viewModel.rooms.isEmpty {
                ProgressView().tint(CPColors.accent)
            } else if viewModel.rooms.isEmpty {
                VStack(spacing: CPLayout.space3) {
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.system(size: 40))
                        .foregroundColor(CPColors.textMuted)
                    Text("No hand history yet")
                        .font(CPTypography.title)
                        .foregroundColor(CPColors.textSecondary)
                }
            } else {
                List(viewModel.rooms) { room in
                    NavigationLink(value: room) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(room.roomName)
                                    .font(CPTypography.bodySemibold)
                                    .foregroundColor(CPColors.textPrimary)

                                Text(room.roomCode)
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(CPColors.textMuted)
                            }

                            Spacer()

                            VStack(alignment: .trailing, spacing: 4) {
                                Text("\(room.totalHands) hands")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)

                                Text(room.lastPlayedAt.prefix(10))
                                    .font(CPTypography.caption)
                                    .foregroundColor(CPColors.textMuted)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .listRowBackground(CPColors.bgSurface)
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
            }
        }
        .navigationTitle("History")
        .onAppear { viewModel.requestRooms() }
        .preferredColorScheme(.dark)
    }
}

// MARK: - History Hands View

struct HistoryHandsView: View {
    @Bindable var viewModel: HistoryViewModel
    let roomSessionId: String

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            if viewModel.isLoading && viewModel.hands.isEmpty {
                ProgressView().tint(CPColors.accent)
            } else {
                List(viewModel.hands) { hand in
                    NavigationLink(value: hand) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Hand #\(hand.handNo)")
                                    .font(CPTypography.bodySemibold)
                                    .foregroundColor(CPColors.textPrimary)

                                Text("\(CardParser.formatChips(hand.blinds.sb))/\(CardParser.formatChips(hand.blinds.bb))")
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(CPColors.gold)
                            }

                            Spacer()

                            VStack(alignment: .trailing, spacing: 4) {
                                Text("Pot \(CardParser.formatChips(hand.summary.totalPot))")
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(CPColors.potColor)

                                HStack(spacing: 4) {
                                    if hand.summary.flags.allIn {
                                        flagBadge("AI", color: CPColors.allinColor)
                                    }
                                    if hand.summary.flags.showdown {
                                        flagBadge("SD", color: CPColors.callColor)
                                    }
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .listRowBackground(CPColors.bgSurface)
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
            }
        }
        .navigationTitle("Hands")
        .onAppear { viewModel.requestHands(roomSessionId: roomSessionId) }
        .preferredColorScheme(.dark)
    }

    private func flagBadge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 9, weight: .bold))
            .foregroundColor(color)
            .padding(.horizontal, 4)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(3)
    }
}

// MARK: - Hand Detail View

struct HandDetailView: View {
    @Bindable var viewModel: HistoryViewModel
    let handId: String

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            if viewModel.isLoading {
                ProgressView().tint(CPColors.accent)
            } else if let detail = viewModel.selectedHandDetail {
                ScrollView {
                    VStack(alignment: .leading, spacing: CPLayout.space4) {
                        // Header
                        VStack(alignment: .leading, spacing: CPLayout.space2) {
                            Text("Hand #\(detail.handNo)")
                                .font(CPTypography.heading)
                                .foregroundColor(CPColors.textPrimary)

                            Text("\(CardParser.formatChips(detail.blinds.sb))/\(CardParser.formatChips(detail.blinds.bb)) | Pot \(CardParser.formatChips(detail.summary.totalPot))")
                                .font(CPTypography.mono)
                                .foregroundColor(CPColors.gold)
                        }

                        // Board
                        if !detail.detail.board.isEmpty {
                            CPCard {
                                VStack(alignment: .leading, spacing: CPLayout.space2) {
                                    Text("Board")
                                        .font(CPTypography.label)
                                        .foregroundColor(CPColors.textSecondary)

                                    HStack(spacing: 4) {
                                        ForEach(detail.detail.board, id: \.self) { card in
                                            CardView(notation: card, size: .medium)
                                        }
                                    }
                                }
                            }
                        }

                        // Players & Payouts
                        CPCard {
                            VStack(alignment: .leading, spacing: CPLayout.space2) {
                                Text("Players")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)

                                ForEach(detail.detail.payoutLedger, id: \.seat) { entry in
                                    HStack {
                                        Text(entry.playerName)
                                            .font(CPTypography.body)
                                            .foregroundColor(CPColors.textPrimary)

                                        Spacer()

                                        let cards = detail.detail.revealedHoles[String(entry.seat)]
                                        if let cards, !cards.isEmpty {
                                            HStack(spacing: 2) {
                                                ForEach(cards, id: \.self) { card in
                                                    CardView(notation: card, size: .small)
                                                }
                                            }
                                        }

                                        Text(entry.net >= 0 ? "+\(CardParser.formatChips(entry.net))" : CardParser.formatChips(entry.net))
                                            .font(CPTypography.mono)
                                            .foregroundColor(entry.net >= 0 ? CPColors.success : CPColors.danger)
                                    }
                                }
                            }
                        }

                        // Action Timeline
                        CPCard {
                            VStack(alignment: .leading, spacing: CPLayout.space2) {
                                Text("Actions")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)

                                ForEach(Array(detail.detail.actionTimeline.enumerated()), id: \.offset) { _, action in
                                    let playerName = detail.players.first { $0.seat == action.seat }?.name ?? "Seat \(action.seat)"
                                    HStack {
                                        Text(action.street.rawValue)
                                            .font(CPTypography.caption)
                                            .foregroundColor(CPColors.textMuted)
                                            .frame(width: 60, alignment: .leading)

                                        Text(playerName)
                                            .font(CPTypography.body)
                                            .foregroundColor(CPColors.textPrimary)

                                        Spacer()

                                        Text(action.type.rawValue)
                                            .font(CPTypography.captionBold)
                                            .foregroundColor(actionColor(action.type.rawValue))

                                        if action.amount > 0 {
                                            Text(CardParser.formatChips(action.amount))
                                                .font(CPTypography.monoSmall)
                                                .foregroundColor(CPColors.textSecondary)
                                        }
                                    }
                                }
                            }
                        }

                        // Winners
                        CPCard {
                            VStack(alignment: .leading, spacing: CPLayout.space2) {
                                Text("Winners")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)

                                ForEach(detail.summary.winners, id: \.seat) { winner in
                                    let name = detail.players.first { $0.seat == winner.seat }?.name ?? "Seat \(winner.seat)"
                                    HStack {
                                        Text(name)
                                            .font(CPTypography.bodySemibold)
                                            .foregroundColor(CPColors.textPrimary)
                                        Spacer()
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
                        }
                    }
                    .padding(CPLayout.space4)
                }
            } else {
                Text("Hand not found")
                    .foregroundColor(CPColors.textMuted)
            }
        }
        .navigationTitle("Hand Detail")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { viewModel.requestHandDetail(handHistoryId: handId) }
        .preferredColorScheme(.dark)
    }

    private func actionColor(_ action: String) -> Color {
        switch action {
        case "fold": return CPColors.foldColor
        case "check": return CPColors.checkColor
        case "call": return CPColors.callColor
        case "raise", "all_in": return CPColors.raiseColor
        case "post_sb", "post_bb", "ante": return CPColors.textMuted
        default: return CPColors.textSecondary
        }
    }
}
