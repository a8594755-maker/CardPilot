import SwiftUI

// MARK: - Lobby View
// Room list, quick play, create room, join by code

struct LobbyView: View {
    @Bindable var viewModel: LobbyViewModel
    @State private var showCreateRoom = false
    @State private var showJoinByCode = false

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            ScrollView {
                VStack(spacing: CPLayout.space4) {
                    // MARK: Action Cards
                    HStack(spacing: CPLayout.space3) {
                        // Create Room
                        actionCard(
                            icon: "plus.circle.fill",
                            title: "Create Room",
                            color: CPColors.accent
                        ) {
                            showCreateRoom = true
                        }

                        // Join by Code
                        actionCard(
                            icon: "number.circle.fill",
                            title: "Join by Code",
                            color: CPColors.callColor
                        ) {
                            showJoinByCode = true
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)

                    // MARK: Open Rooms Header
                    HStack {
                        Text("Open Rooms")
                            .font(CPTypography.heading)
                            .foregroundColor(CPColors.textPrimary)

                        Spacer()

                        Button {
                            viewModel.requestLobby()
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(CPColors.textSecondary)
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)

                    // MARK: Room List
                    if viewModel.isLoading {
                        ProgressView()
                            .tint(CPColors.accent)
                            .padding(.top, CPLayout.space8)
                    } else if viewModel.rooms.isEmpty {
                        emptyState
                    } else {
                        LazyVStack(spacing: CPLayout.space3) {
                            ForEach(viewModel.rooms) { room in
                                RoomRow(room: room) {
                                    HapticManager.action()
                                    viewModel.joinRoom(room)
                                }
                            }
                        }
                        .padding(.horizontal, CPLayout.space4)
                    }
                }
                .padding(.top, CPLayout.space4)
            }
        }
        .onAppear {
            viewModel.requestLobby()
        }
        .sheet(isPresented: $showCreateRoom) {
            CreateRoomSheet(viewModel: viewModel, isPresented: $showCreateRoom)
                .presentationDetents([.medium])
                .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showJoinByCode) {
            JoinByCodeSheet(viewModel: viewModel, isPresented: $showJoinByCode)
                .presentationDetents([.height(280)])
                .presentationDragIndicator(.visible)
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Action Card

    private func actionCard(icon: String, title: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            CPGlassCard {
                VStack(spacing: CPLayout.space2) {
                    Image(systemName: icon)
                        .font(.system(size: 28))
                        .foregroundColor(color)

                    Text(title)
                        .font(CPTypography.bodySemibold)
                        .foregroundColor(CPColors.textPrimary)
                }
                .frame(maxWidth: .infinity)
                .frame(height: 80)
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: CPLayout.space4) {
            Image(systemName: "table.furniture")
                .font(.system(size: 48))
                .foregroundColor(CPColors.textMuted)

            Text("No open rooms")
                .font(CPTypography.title)
                .foregroundColor(CPColors.textSecondary)

            Text("Create a room or join by code")
                .font(CPTypography.label)
                .foregroundColor(CPColors.textMuted)
        }
        .padding(.top, CPLayout.space12)
    }
}

// MARK: - Room Row

struct RoomRow: View {
    let room: LobbyRoomSummary
    let onJoin: () -> Void

    var body: some View {
        Button(action: onJoin) {
            CPCard {
                HStack {
                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text(room.roomName)
                            .font(CPTypography.bodySemibold)
                            .foregroundColor(CPColors.textPrimary)

                        HStack(spacing: CPLayout.space3) {
                            // Blinds
                            Label {
                                Text("\(CardParser.formatChips(room.smallBlind))/\(CardParser.formatChips(room.bigBlind))")
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(CPColors.gold)
                            } icon: {
                                Image(systemName: "dollarsign.circle")
                                    .foregroundColor(CPColors.gold)
                                    .font(.system(size: 12))
                            }

                            // Players
                            Label {
                                Text("\(room.playerCount)/\(room.maxPlayers)")
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(CPColors.textSecondary)
                            } icon: {
                                Image(systemName: "person.2")
                                    .foregroundColor(CPColors.textSecondary)
                                    .font(.system(size: 12))
                            }
                        }
                    }

                    Spacer()

                    // Room code badge
                    Text(room.roomCode)
                        .font(CPTypography.monoSmall)
                        .foregroundColor(CPColors.textMuted)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(CPColors.bgBase)
                        .cornerRadius(CPLayout.radiusSm)

                    Image(systemName: "chevron.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(CPColors.textMuted)
                }
            }
        }
    }
}
