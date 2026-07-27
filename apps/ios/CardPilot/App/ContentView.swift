import SwiftUI

// MARK: - Content View
// Full tab router: Lobby / Table / Clubs / Training / Fast Battle / History / Profile
// With onboarding support

struct ContentView: View {
    @State private var authViewModel = AuthViewModel()
    @State private var router = SocketEventRouter()
    @State private var selectedTab: Tab = .lobby
    @State private var onboardingManager = OnboardingManager()
    @State private var showOnboarding = false

    // View Models
    @State private var lobbyViewModel: LobbyViewModel?
    @State private var tableViewModel: PokerTableViewModel?
    @State private var historyViewModel: HistoryViewModel?
    @State private var profileViewModel = ProfileViewModel()
    @State private var trainingViewModel: TrainingViewModel?
    @State private var fastBattleViewModel: FastBattleViewModel?
    @State private var clubsViewModel: ClubsViewModel?

    enum Tab: Hashable {
        case lobby, table, clubs, training, fastBattle, history, profile
    }

    var body: some View {
        ZStack {
            Group {
                if authViewModel.isAuthenticated {
                    mainTabView
                } else {
                    AuthView(viewModel: authViewModel)
                }
            }

            // Onboarding overlay
            if showOnboarding {
                OnboardingView {
                    withAnimation {
                        showOnboarding = false
                        onboardingManager.completeOnboarding()
                    }
                }
                .transition(.opacity)
                .zIndex(100)
            }
        }
        .onAppear {
            authViewModel.restoreSessionIfNeeded()
            initializeViewModels()
        }
        .onChange(of: authViewModel.isAuthenticated) { _, isAuth in
            if isAuth && onboardingManager.isOnboardingNeeded {
                showOnboarding = true
            }
        }
        .onChange(of: lobbyViewModel?.shouldNavigateToTable ?? false) { _, shouldNav in
            if shouldNav, let lobby = lobbyViewModel,
               let tableId = lobby.joinedTableId,
               let code = lobby.joinedRoomCode,
               let name = lobby.joinedRoomName {
                tableViewModel = PokerTableViewModel(
                    tableId: tableId,
                    roomCode: code,
                    roomName: name,
                    router: router,
                    authUserId: authViewModel.authSession?.userId
                )
                selectedTab = .table
                lobby.shouldNavigateToTable = false
            }
        }
        // Club table join → navigate to table
        .onChange(of: clubsViewModel?.joinedTableId) { _, tableId in
            if let tableId, let clubs = clubsViewModel {
                tableViewModel = PokerTableViewModel(
                    tableId: tableId,
                    roomCode: "",
                    roomName: clubs.joinedRoomName ?? "Club Table",
                    router: router,
                    authUserId: authViewModel.authSession?.userId
                )
                selectedTab = .table
                clubs.joinedTableId = nil
            }
        }
        // Fast Battle: auto-switch to table when playing
        .onChange(of: fastBattleViewModel?.currentTableId) { _, tableId in
            if let tableId, let code = fastBattleViewModel?.currentRoomCode {
                tableViewModel = PokerTableViewModel(
                    tableId: tableId,
                    roomCode: code,
                    roomName: "Fast Battle",
                    router: router,
                    authUserId: authViewModel.authSession?.userId
                )
                selectedTab = .table
            }
        }
    }

    // MARK: - Initialize View Models

    private func initializeViewModels() {
        lobbyViewModel = LobbyViewModel(router: router)
        historyViewModel = HistoryViewModel(router: router)
        trainingViewModel = TrainingViewModel(router: router, userId: authViewModel.authSession?.userId)
        fastBattleViewModel = FastBattleViewModel(router: router)
        clubsViewModel = ClubsViewModel(router: router)
    }

    // MARK: - Main Tab View

    private var mainTabView: some View {
        TabView(selection: $selectedTab) {
            // Lobby
            NavigationStack {
                if let lobby = lobbyViewModel {
                    LobbyView(viewModel: lobby)
                }
            }
            .tabItem {
                Image(systemName: "house.fill")
                Text("Lobby")
            }
            .tag(Tab.lobby)

            // Table
            NavigationStack {
                if let table = tableViewModel {
                    ZStack {
                        PokerTableView(viewModel: table)

                        // Fast Battle HUD overlay
                        if let fb = fastBattleViewModel,
                           fb.phase == .playing || fb.phase == .switching {
                            VStack {
                                FastBattleHUD(
                                    handsPlayed: fb.handsPlayed,
                                    targetHandCount: fb.targetHandCount,
                                    cumulativeResult: fb.cumulativeResult,
                                    onEnd: { fb.endSession() }
                                )
                                Spacer()
                            }

                            if let result = fb.lastHandResult {
                                VStack {
                                    FastBattleHandResultToast(result: result)
                                        .padding(.top, 56)
                                    Spacer()
                                }
                            }
                        }
                    }
                } else {
                    noTableView
                }
            }
            .tabItem {
                Image(systemName: "suit.spade.fill")
                Text("Table")
            }
            .tag(Tab.table)

            // Clubs
            NavigationStack {
                if let clubs = clubsViewModel {
                    ClubsListView(viewModel: clubs)
                }
            }
            .tabItem {
                Image(systemName: "person.3.fill")
                Text("Clubs")
            }
            .tag(Tab.clubs)

            // Training
            NavigationStack {
                if let training = trainingViewModel {
                    TrainingDashboardView(viewModel: training)
                }
            }
            .tabItem {
                Image(systemName: "brain.head.profile")
                Text("Training")
            }
            .tag(Tab.training)

            // Fast Battle
            NavigationStack {
                if let fb = fastBattleViewModel {
                    FastBattlePage(
                        viewModel: fb,
                        onExit: {
                            fb.resetToSetup()
                            selectedTab = .lobby
                        }
                    )
                }
            }
            .tabItem {
                Image(systemName: "bolt.fill")
                Text("Battle")
            }
            .tag(Tab.fastBattle)

            // History
            NavigationStack {
                if let history = historyViewModel {
                    HistoryRoomsView(viewModel: history)
                        .navigationDestination(for: HistoryRoomSummary.self) { room in
                            HistoryHandsView(viewModel: history, roomSessionId: room.roomId)
                        }
                }
            }
            .tabItem {
                Image(systemName: "clock.fill")
                Text("History")
            }
            .tag(Tab.history)

            // Profile
            NavigationStack {
                ProfileView(viewModel: profileViewModel, authViewModel: authViewModel)
            }
            .tabItem {
                Image(systemName: "person.fill")
                Text("Profile")
            }
            .tag(Tab.profile)
        }
        .tint(CPColors.accent)
        .preferredColorScheme(.dark)
    }

    // MARK: - No Table Placeholder

    private var noTableView: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()
            VStack(spacing: CPLayout.space4) {
                Image(systemName: "suit.spade.fill")
                    .font(.system(size: 48))
                    .foregroundColor(CPColors.textMuted)
                Text("No Active Table")
                    .font(CPTypography.heading)
                    .foregroundColor(CPColors.textSecondary)
                Text("Join or create a room from the Lobby")
                    .font(CPTypography.label)
                    .foregroundColor(CPColors.textMuted)
                Button { selectedTab = .lobby } label: {
                    Text("Go to Lobby")
                }
                .buttonStyle(.cpPrimary)
            }
        }
    }
}
