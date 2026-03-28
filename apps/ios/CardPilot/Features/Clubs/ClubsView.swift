import SwiftUI

// MARK: - Clubs View Model

@Observable
final class ClubsViewModel {
    var clubs: [ClubListItem] = []
    var selectedClub: ClubDetail?
    var members: [ClubMember] = []
    var pendingMembers: [ClubMember] = []
    var tables: [ClubTable] = []
    var invites: [ClubInvite] = []
    var rulesets: [ClubRuleset] = []
    var auditLog: [ClubAuditLogEntry] = []
    var leaderboard: [ClubLeaderboardEntry] = []
    var myRank: Int?
    var walletBalance: Double = 0
    var transactions: [ClubWalletTransaction] = []
    var isLoading = false
    var error: String?

    // Table join navigation
    var joinedTableId: String?
    var joinedRoomName: String?

    // Join
    var joinCode = ""
    var inviteCode = ""

    // Create
    var newClubName = ""
    var newClubDescription = ""
    var newClubBadgeColor = "#15803D"
    var requireApproval = true

    private let socket = CPSocketManager.shared
    private let router: SocketEventRouter

    init(router: SocketEventRouter) {
        self.router = router
        registerEvents()
    }

    // MARK: - Actions

    func loadMyClubs() {
        isLoading = true
        socket.emit("club_list_my_clubs")
    }

    func createClub() {
        guard !newClubName.isEmpty else { return }
        socket.emit("club_create", [
            "name": newClubName,
            "description": newClubDescription,
            "badgeColor": newClubBadgeColor,
            "requireApprovalToJoin": requireApproval
        ])
    }

    func joinClub() {
        guard !joinCode.isEmpty else { return }
        var payload: [String: Any] = ["clubCode": joinCode]
        if !inviteCode.isEmpty { payload["inviteCode"] = inviteCode }
        socket.emit("club_join_request", payload)
    }

    func loadClubDetail(_ clubId: String) {
        isLoading = true
        socket.emit("club_get_detail", ["clubId": clubId])
    }

    func createTable(clubId: String, name: String) {
        socket.emit("club_table_create", ["clubId": clubId, "name": name])
    }

    func joinTable(clubId: String, tableId: String) {
        socket.emit("club_table_join", ["clubId": clubId, "tableId": tableId])
    }

    func closeTable(clubId: String, tableId: String) {
        socket.emit("club_table_close", ["clubId": clubId, "tableId": tableId])
    }

    func approveJoin(clubId: String, userId: String) {
        socket.emit("club_join_approve", ["clubId": clubId, "userId": userId, "approve": true])
    }

    func rejectJoin(clubId: String, userId: String) {
        socket.emit("club_join_reject", ["clubId": clubId, "userId": userId, "approve": false])
    }

    func changeRole(clubId: String, userId: String, newRole: String) {
        socket.emit("club_member_update_role", ["clubId": clubId, "userId": userId, "newRole": newRole])
    }

    func kickMember(clubId: String, userId: String) {
        socket.emit("club_member_kick", ["clubId": clubId, "userId": userId])
    }

    func banMember(clubId: String, userId: String, reason: String = "Banned by admin") {
        socket.emit("club_member_ban", ["clubId": clubId, "userId": userId, "reason": reason])
    }

    func unbanMember(clubId: String, userId: String) {
        socket.emit("club_member_unban", ["clubId": clubId, "userId": userId])
    }

    func grantCredits(clubId: String, userId: String, amount: Double) {
        socket.emit("club_wallet_admin_deposit", ["clubId": clubId, "userId": userId, "amount": amount])
    }

    func adjustCredits(clubId: String, userId: String, amount: Double, note: String = "") {
        socket.emit("club_wallet_admin_adjust", ["clubId": clubId, "userId": userId, "amount": amount, "note": note])
    }

    func renameTable(clubId: String, tableId: String, name: String) {
        socket.emit("club_table_update", ["clubId": clubId, "tableId": tableId, "name": name])
    }

    func pauseTable(clubId: String, tableId: String) {
        socket.emit("club_table_pause", ["clubId": clubId, "tableId": tableId])
    }

    // Bulk Operations
    func bulkApprove(clubId: String, userIds: [String]) {
        socket.emit("club_bulk_approve", ["clubId": clubId, "userIds": userIds])
    }

    func bulkGrantCredits(clubId: String, userIds: [String], amount: Double) {
        socket.emit("club_bulk_grant_credits", ["clubId": clubId, "userIds": userIds, "amount": amount])
    }

    func bulkRoleChange(clubId: String, userIds: [String], newRole: String) {
        socket.emit("club_bulk_role_change", ["clubId": clubId, "userIds": userIds, "newRole": newRole])
    }

    func bulkKick(clubId: String, userIds: [String]) {
        socket.emit("club_bulk_kick", ["clubId": clubId, "userIds": userIds])
    }

    // Rulesets
    func createRuleset(clubId: String, name: String) {
        socket.emit("club_ruleset_create", ["clubId": clubId, "name": name])
    }

    func setDefaultRuleset(clubId: String, rulesetId: String) {
        socket.emit("club_ruleset_set_default", ["clubId": clubId, "rulesetId": rulesetId])
    }

    func fetchLeaderboard(clubId: String, timeRange: String = "all", metric: String = "net") {
        socket.emit("club_leaderboard_get", ["clubId": clubId, "timeRange": timeRange, "metric": metric])
    }

    func fetchTransactions(clubId: String) {
        socket.emit("club_wallet_transactions_list", ["clubId": clubId])
    }

    func fetchBalance(clubId: String) {
        socket.emit("club_wallet_balance_get", ["clubId": clubId])
    }

    func createInvite(clubId: String) {
        socket.emit("club_invite_create", ["clubId": clubId])
    }

    func revokeInvite(clubId: String, inviteId: String) {
        socket.emit("club_invite_revoke", ["clubId": clubId, "inviteId": inviteId])
    }

    func updateClub(clubId: String, name: String? = nil, description: String? = nil, badgeColor: String? = nil) {
        var payload: [String: Any] = ["clubId": clubId]
        if let name { payload["name"] = name }
        if let description { payload["description"] = description }
        if let badgeColor { payload["badgeColor"] = badgeColor }
        socket.emit("club_update", payload)
    }

    // MARK: - Permissions

    var myRole: ClubRole? { selectedClub?.myMembership?.role }
    var isOwner: Bool { myRole == .owner }
    var isAdmin: Bool { myRole == .owner || myRole == .admin }

    // MARK: - Events

    private func registerEvents() {
        router.on("club_list", type: ClubListPayload.self) { [weak self] payload in
            self?.clubs = payload.clubs
            self?.isLoading = false
        }

        router.on("club_created", type: ClubCreatedPayload.self) { [weak self] payload in
            self?.loadMyClubs()
        }

        router.on("club_detail", type: ClubDetailPayload.self) { [weak self] payload in
            self?.selectedClub = payload.detail
            self?.members = payload.members
            self?.pendingMembers = payload.pendingMembers ?? []
            self?.tables = payload.tables ?? []
            self?.invites = payload.invites ?? []
            self?.rulesets = payload.rulesets ?? []
            self?.auditLog = payload.auditLog ?? []
            self?.isLoading = false
        }

        router.on("club_join_result", type: ClubJoinResultPayload.self) { [weak self] payload in
            if payload.status == "joined" {
                self?.loadMyClubs()
            }
            self?.error = payload.status == "error" ? payload.message : nil
        }

        router.on("club_table_created", type: ClubTableCreatedPayload.self) { [weak self] payload in
            self?.tables.append(payload.table)
        }

        router.on("club_table_joined", type: ClubTableJoinedPayload.self) { [weak self] payload in
            self?.joinedTableId = payload.tableId
            self?.joinedRoomName = payload.roomName
        }

        router.on("club_error", type: ClubErrorPayload.self) { [weak self] payload in
            self?.error = payload.message
        }

        router.on("club_leaderboard", type: ClubLeaderboardPayload.self) { [weak self] payload in
            self?.leaderboard = payload.entries
            self?.myRank = payload.myRank
        }

        router.on("club_wallet_balance", type: ClubWalletBalancePayload.self) { [weak self] payload in
            self?.walletBalance = payload.balance.balance
        }

        router.on("club_wallet_transactions", type: ClubWalletLedgerPayload.self) { [weak self] payload in
            self?.transactions = payload.transactions
        }
    }
}

// MARK: - Clubs List Page

struct ClubsListView: View {
    @Bindable var viewModel: ClubsViewModel
    @State private var showCreateSheet = false
    @State private var showJoinSheet = false
    @State private var selectedClubId: String?

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            ScrollView {
                VStack(spacing: CPLayout.space4) {
                    // Action buttons
                    HStack(spacing: CPLayout.space3) {
                        Button {
                            showCreateSheet = true
                        } label: {
                            CPGlassCard {
                                VStack(spacing: CPLayout.space2) {
                                    Image(systemName: "plus.circle.fill")
                                        .font(.system(size: 24))
                                        .foregroundColor(CPColors.accent)
                                    Text("Create Club")
                                        .font(CPTypography.label)
                                        .foregroundColor(CPColors.textPrimary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 70)
                            }
                        }

                        Button {
                            showJoinSheet = true
                        } label: {
                            CPGlassCard {
                                VStack(spacing: CPLayout.space2) {
                                    Image(systemName: "person.badge.plus")
                                        .font(.system(size: 24))
                                        .foregroundColor(CPColors.callColor)
                                    Text("Join Club")
                                        .font(CPTypography.label)
                                        .foregroundColor(CPColors.textPrimary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 70)
                            }
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)

                    // Club list
                    if viewModel.clubs.isEmpty && !viewModel.isLoading {
                        VStack(spacing: CPLayout.space3) {
                            Image(systemName: "person.3")
                                .font(.system(size: 40))
                                .foregroundColor(CPColors.textMuted)
                            Text("No clubs yet")
                                .font(CPTypography.title)
                                .foregroundColor(CPColors.textSecondary)
                        }
                        .padding(.top, CPLayout.space12)
                    } else {
                        LazyVStack(spacing: CPLayout.space3) {
                            ForEach(viewModel.clubs) { club in
                                NavigationLink(value: club.id) {
                                    clubRow(club)
                                }
                            }
                        }
                        .padding(.horizontal, CPLayout.space4)
                    }
                }
                .padding(.top, CPLayout.space4)
            }
        }
        .navigationTitle("Clubs")
        .onAppear { viewModel.loadMyClubs() }
        .navigationDestination(for: String.self) { clubId in
            ClubDetailPage(viewModel: viewModel, clubId: clubId)
        }
        .sheet(isPresented: $showCreateSheet) {
            createClubSheet
        }
        .sheet(isPresented: $showJoinSheet) {
            joinClubSheet
        }
        .preferredColorScheme(.dark)
    }

    private func clubRow(_ club: ClubListItem) -> some View {
        CPCard {
            HStack {
                // Avatar
                ZStack {
                    Circle()
                        .fill(Color(hex: club.badgeColor ?? "#15803D"))
                        .frame(width: 40, height: 40)
                    Text(String(club.name.prefix(1)).uppercased())
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)
                }

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(club.name)
                            .font(CPTypography.bodySemibold)
                            .foregroundColor(CPColors.textPrimary)
                        if let role = club.myRole {
                            Text(role.rawValue.uppercased())
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(role == .owner ? CPColors.gold : CPColors.accent)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background((role == .owner ? CPColors.gold : CPColors.accent).opacity(0.15))
                                .cornerRadius(3)
                        }
                    }
                    Text("\(club.memberCount) members \(club.tableCount ?? 0 > 0 ? "· \(club.tableCount!) tables" : "")")
                        .font(CPTypography.caption)
                        .foregroundColor(CPColors.textMuted)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .foregroundColor(CPColors.textMuted)
            }
        }
    }

    // MARK: - Create Sheet

    private var createClubSheet: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()
                VStack(spacing: CPLayout.space4) {
                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text("Club Name").font(CPTypography.label).foregroundColor(CPColors.textSecondary)
                        TextField("My Poker Club", text: $viewModel.newClubName)
                            .textFieldStyle(CPTextFieldStyle())
                    }
                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text("Description").font(CPTypography.label).foregroundColor(CPColors.textSecondary)
                        TextField("Optional description", text: $viewModel.newClubDescription)
                            .textFieldStyle(CPTextFieldStyle())
                    }
                    Toggle("Require approval to join", isOn: $viewModel.requireApproval)
                        .tint(CPColors.accent)
                        .foregroundColor(CPColors.textPrimary)

                    Button {
                        viewModel.createClub()
                        showCreateSheet = false
                    } label: {
                        Text("Create Club").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpPrimary)
                    .disabled(viewModel.newClubName.isEmpty)

                    Spacer()
                }
                .padding(CPLayout.space4)
            }
            .navigationTitle("Create Club")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showCreateSheet = false }.foregroundColor(CPColors.textSecondary)
                }
            }
        }
        .presentationDetents([.medium])
        .preferredColorScheme(.dark)
    }

    // MARK: - Join Sheet

    private var joinClubSheet: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()
                VStack(spacing: CPLayout.space4) {
                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text("Club Code").font(CPTypography.label).foregroundColor(CPColors.textSecondary)
                        TextField("Enter club code", text: $viewModel.joinCode)
                            .textFieldStyle(CPTextFieldStyle())
                            .autocapitalization(.allCharacters)
                    }
                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text("Invite Code (optional)").font(CPTypography.label).foregroundColor(CPColors.textSecondary)
                        TextField("If you have one", text: $viewModel.inviteCode)
                            .textFieldStyle(CPTextFieldStyle())
                    }

                    if let error = viewModel.error {
                        Text(error).font(CPTypography.caption).foregroundColor(CPColors.danger)
                    }

                    Button {
                        viewModel.joinClub()
                        showJoinSheet = false
                    } label: {
                        Text("Join Club").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpPrimary)
                    .disabled(viewModel.joinCode.isEmpty)

                    Spacer()
                }
                .padding(CPLayout.space4)
            }
            .navigationTitle("Join Club")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showJoinSheet = false }.foregroundColor(CPColors.textSecondary)
                }
            }
        }
        .presentationDetents([.height(320)])
        .preferredColorScheme(.dark)
    }
}

// MARK: - Club Detail Page

struct ClubDetailPage: View {
    @Bindable var viewModel: ClubsViewModel
    let clubId: String
    @State private var selectedTab = "tables"

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            if viewModel.isLoading && viewModel.selectedClub == nil {
                ProgressView().tint(CPColors.accent)
            } else if let detail = viewModel.selectedClub {
                VStack(spacing: 0) {
                    // Pending approvals banner
                    if viewModel.isAdmin && !viewModel.pendingMembers.isEmpty {
                        pendingBanner(detail.club.id)
                    }

                    // Tab bar
                    tabBar

                    // Tab content
                    ScrollView {
                        switch selectedTab {
                        case "overview": overviewContent(detail)
                        case "tables": tablesContent(detail.club.id)
                        case "members": membersContent(detail.club.id)
                        case "chat": chatContent(detail.club.id)
                        case "credits": creditsContent(detail.club.id)
                        case "transactions": transactionsContent(detail.club.id)
                        case "leaderboard": leaderboardContent(detail.club.id)
                        case "analytics": analyticsContent(detail.club.id)
                        case "rulesets": rulesetsContent(detail.club.id)
                        case "invites": invitesContent(detail.club.id)
                        case "activity": activityContent(detail.club.id)
                        case "settings": settingsContent(detail.club)
                        default: tablesContent(detail.club.id)
                        }
                    }
                }
            }
        }
        .navigationTitle(viewModel.selectedClub?.club.name ?? "Club")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { viewModel.loadClubDetail(clubId) }
        .preferredColorScheme(.dark)
    }

    // MARK: - Tab Bar

    private var tabBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: CPLayout.space1) {
                if viewModel.isAdmin { tabButton("Overview", tab: "overview") }
                tabButton("Tables", tab: "tables")
                tabButton("Members", tab: "members")
                tabButton("Chat", tab: "chat")
                tabButton("Credits", tab: "credits")
                tabButton("Transactions", tab: "transactions")
                tabButton("Leaderboard", tab: "leaderboard")
                tabButton("Analytics", tab: "analytics")
                if viewModel.isAdmin {
                    tabButton("Rulesets", tab: "rulesets")
                    tabButton("Invites", tab: "invites")
                    tabButton("Activity", tab: "activity")
                    tabButton("Settings", tab: "settings")
                }
            }
            .padding(.horizontal, CPLayout.space4)
            .padding(.vertical, CPLayout.space2)
        }
        .background(CPColors.bgSurface)
    }

    private func tabButton(_ title: String, tab: String) -> some View {
        Button {
            selectedTab = tab
        } label: {
            Text(title)
                .font(CPTypography.label)
                .foregroundColor(selectedTab == tab ? CPColors.textPrimary : CPColors.textMuted)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(selectedTab == tab ? CPColors.bgElevated : .clear)
                .cornerRadius(CPLayout.radiusFull)
        }
    }

    // MARK: - Pending Banner

    private func pendingBanner(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space2) {
            Text("\(viewModel.pendingMembers.count) pending join requests")
                .font(CPTypography.label)
                .foregroundColor(CPColors.warning)

            ForEach(viewModel.pendingMembers) { member in
                HStack {
                    Text(member.displayName ?? member.userId.prefix(8).description)
                        .font(CPTypography.body)
                        .foregroundColor(CPColors.textPrimary)
                    Spacer()
                    Button("Approve") {
                        viewModel.approveJoin(clubId: clubId, userId: member.userId)
                    }
                    .font(CPTypography.captionBold)
                    .foregroundColor(CPColors.success)

                    Button("Reject") {
                        viewModel.rejectJoin(clubId: clubId, userId: member.userId)
                    }
                    .font(CPTypography.captionBold)
                    .foregroundColor(CPColors.danger)
                }
            }
        }
        .padding(CPLayout.space3)
        .background(CPColors.warning.opacity(0.1))
    }

    // MARK: - Tables Tab

    private func tablesContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            if viewModel.isAdmin {
                Button {
                    viewModel.createTable(clubId: clubId, name: "Table \(viewModel.tables.count + 1)")
                } label: {
                    HStack {
                        Image(systemName: "plus")
                        Text("Create Table")
                    }
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.cpPrimary)
            }

            ForEach(viewModel.tables) { table in
                CPCard {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(table.name)
                                .font(CPTypography.bodySemibold)
                                .foregroundColor(CPColors.textPrimary)
                            HStack(spacing: CPLayout.space2) {
                                Text(table.status.uppercased())
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundColor(table.status == "open" ? CPColors.success : CPColors.textMuted)
                                if let stakes = table.stakes {
                                    Text(stakes).font(CPTypography.monoSmall).foregroundColor(CPColors.gold)
                                }
                                Text("\(table.playerCount ?? 0)/\(table.maxPlayers ?? 6)")
                                    .font(CPTypography.monoSmall).foregroundColor(CPColors.textSecondary)
                            }
                        }
                        Spacer()
                        if table.status == "open" {
                            Button("Join") {
                                viewModel.joinTable(clubId: clubId, tableId: table.id)
                            }
                            .font(CPTypography.labelBold)
                            .foregroundColor(CPColors.accent)
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
    }

    // MARK: - Members Tab

    private func membersContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            ForEach(viewModel.members) { member in
                CPCard {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(member.displayName ?? member.userId.prefix(8).description)
                                    .font(CPTypography.bodySemibold)
                                    .foregroundColor(CPColors.textPrimary)
                                Text(member.role.rawValue.uppercased())
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundColor(member.role == .owner ? CPColors.gold : CPColors.accent)
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background((member.role == .owner ? CPColors.gold : CPColors.accent).opacity(0.15))
                                    .cornerRadius(3)
                            }
                            if let balance = member.balance {
                                Text("Balance: \(CardParser.formatChips(balance))")
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(CPColors.textMuted)
                            }
                        }
                        Spacer()
                        if viewModel.isAdmin && member.role != .owner {
                            Menu {
                                Button("Make Admin") { viewModel.changeRole(clubId: clubId, userId: member.userId, newRole: "admin") }
                                Button("Make Member") { viewModel.changeRole(clubId: clubId, userId: member.userId, newRole: "member") }
                                Button("Grant Credits") { viewModel.grantCredits(clubId: clubId, userId: member.userId, amount: 1000) }
                                Button("Adjust Credits") { viewModel.adjustCredits(clubId: clubId, userId: member.userId, amount: -500, note: "Admin adjustment") }
                                Divider()
                                Button("Kick", role: .destructive) { viewModel.kickMember(clubId: clubId, userId: member.userId) }
                                Button("Ban", role: .destructive) { viewModel.banMember(clubId: clubId, userId: member.userId) }
                            } label: {
                                Image(systemName: "ellipsis").foregroundColor(CPColors.textMuted)
                            }
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
    }

    // MARK: - Leaderboard Tab

    private func leaderboardContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            ForEach(viewModel.leaderboard) { entry in
                HStack {
                    Text("#\(entry.rank)")
                        .font(CPTypography.monoSmall)
                        .foregroundColor(entry.rank <= 3 ? CPColors.gold : CPColors.textMuted)
                        .frame(width: 30)
                    Text(entry.displayName)
                        .font(CPTypography.body)
                        .foregroundColor(CPColors.textPrimary)
                    Spacer()
                    if let net = entry.net {
                        Text(net >= 0 ? "+\(CardParser.formatChips(net))" : CardParser.formatChips(net))
                            .font(CPTypography.mono)
                            .foregroundColor(net >= 0 ? CPColors.success : CPColors.danger)
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .padding(CPLayout.space4)
        .onAppear { viewModel.fetchLeaderboard(clubId: clubId) }
    }

    // MARK: - Credits Tab

    private func creditsContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space4) {
            CPCard {
                VStack(spacing: CPLayout.space2) {
                    Text("Your Balance")
                        .font(CPTypography.label)
                        .foregroundColor(CPColors.textSecondary)
                    Text(CardParser.formatChips(viewModel.walletBalance))
                        .font(CPTypography.displayLarge)
                        .foregroundColor(CPColors.gold)
                }
            }

            if !viewModel.transactions.isEmpty {
                CPCard {
                    VStack(alignment: .leading, spacing: CPLayout.space2) {
                        Text("Recent Transactions")
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textSecondary)

                        ForEach(viewModel.transactions.prefix(20)) { tx in
                            HStack {
                                Text(tx.type).font(CPTypography.caption).foregroundColor(CPColors.textMuted)
                                Spacer()
                                Text(tx.amount >= 0 ? "+\(CardParser.formatChips(tx.amount))" : CardParser.formatChips(tx.amount))
                                    .font(CPTypography.monoSmall)
                                    .foregroundColor(tx.amount >= 0 ? CPColors.success : CPColors.danger)
                            }
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
        .onAppear {
            viewModel.fetchBalance(clubId: clubId)
            viewModel.fetchTransactions(clubId: clubId)
        }
    }

    // MARK: - Invites Tab

    private func invitesContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            Button {
                viewModel.createInvite(clubId: clubId)
            } label: {
                HStack {
                    Image(systemName: "link.badge.plus")
                    Text("Create Invite Link")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.cpPrimary)

            ForEach(viewModel.invites) { invite in
                CPCard {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(invite.inviteCode)
                                .font(CPTypography.mono)
                                .foregroundColor(CPColors.textPrimary)
                            Text("Uses: \(invite.usesCount ?? 0)/\(invite.maxUses ?? 0)")
                                .font(CPTypography.caption)
                                .foregroundColor(CPColors.textMuted)
                        }
                        Spacer()
                        if !(invite.revoked ?? false) {
                            Button("Revoke") {
                                viewModel.revokeInvite(clubId: clubId, inviteId: invite.id)
                            }
                            .font(CPTypography.captionBold)
                            .foregroundColor(CPColors.danger)
                        } else {
                            Text("Revoked").font(CPTypography.caption).foregroundColor(CPColors.textMuted)
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
    }

    // MARK: - Settings Tab

    private func settingsContent(_ club: Club) -> some View {
        VStack(spacing: CPLayout.space4) {
            CPCard {
                VStack(alignment: .leading, spacing: CPLayout.space3) {
                    Text("Club Info")
                        .font(CPTypography.heading)
                        .foregroundColor(CPColors.textPrimary)

                    infoRow("Code", club.code)
                    infoRow("Owner", club.ownerUserId.prefix(12).description)
                    infoRow("Visibility", club.visibility ?? "private")
                    infoRow("Approval", (club.requireApprovalToJoin ?? true) ? "Required" : "Auto-join")
                }
            }
        }
        .padding(CPLayout.space4)
    }

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(CPTypography.label).foregroundColor(CPColors.textSecondary)
            Spacer()
            Text(value).font(CPTypography.monoSmall).foregroundColor(CPColors.textMuted)
        }
    }

    // MARK: - Overview Tab (admin only)

    private func overviewContent(_ detail: ClubDetail) -> some View {
        VStack(spacing: CPLayout.space4) {
            // Stats grid
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: CPLayout.space3) {
                overviewStat("Members", "\(detail.memberCount)")
                overviewStat("Pending", "\(detail.pendingCount ?? 0)")
                overviewStat("Tables", "\(detail.tableCount ?? 0)")
            }

            // Recent tables
            if !viewModel.tables.isEmpty {
                CPCard {
                    VStack(alignment: .leading, spacing: CPLayout.space2) {
                        Text("Recent Tables").font(CPTypography.label).foregroundColor(CPColors.textSecondary)
                        ForEach(viewModel.tables.prefix(5)) { table in
                            HStack {
                                Text(table.name).font(CPTypography.body).foregroundColor(CPColors.textPrimary)
                                Spacer()
                                Text(table.status).font(CPTypography.caption).foregroundColor(CPColors.textMuted)
                            }
                        }
                    }
                }
            }

            // Recent audit entries
            if !viewModel.auditLog.isEmpty {
                CPCard {
                    VStack(alignment: .leading, spacing: CPLayout.space2) {
                        Text("Recent Activity").font(CPTypography.label).foregroundColor(CPColors.textSecondary)
                        ForEach(viewModel.auditLog.prefix(5)) { entry in
                            HStack {
                                Text(entry.actionType).font(CPTypography.caption).foregroundColor(CPColors.textPrimary)
                                Spacer()
                                Text(entry.actorDisplayName ?? "System").font(CPTypography.caption).foregroundColor(CPColors.textMuted)
                            }
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
    }

    private func overviewStat(_ label: String, _ value: String) -> some View {
        VStack(spacing: 4) {
            Text(value).font(CPTypography.display).foregroundColor(CPColors.textPrimary)
            Text(label).font(CPTypography.caption).foregroundColor(CPColors.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, CPLayout.space3)
        .background(CPColors.bgSurface)
        .cornerRadius(CPLayout.radiusMd)
    }

    // MARK: - Chat Tab

    private func chatContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space4) {
            // Chat is a complex real-time feature — placeholder with socket emit support
            CPCard {
                VStack(spacing: CPLayout.space3) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 36))
                        .foregroundColor(CPColors.textMuted)
                    Text("Club Chat")
                        .font(CPTypography.title)
                        .foregroundColor(CPColors.textPrimary)
                    Text("Real-time messaging with club members")
                        .font(CPTypography.caption)
                        .foregroundColor(CPColors.textSecondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, CPLayout.space6)
            }
            // TODO: Full chat implementation with message list, input, history loading
        }
        .padding(CPLayout.space4)
    }

    // MARK: - Transactions Tab

    private func transactionsContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            if viewModel.transactions.isEmpty {
                VStack(spacing: CPLayout.space3) {
                    Image(systemName: "list.bullet.rectangle")
                        .font(.system(size: 36))
                        .foregroundColor(CPColors.textMuted)
                    Text("No transactions yet")
                        .font(CPTypography.title)
                        .foregroundColor(CPColors.textSecondary)
                }
                .padding(.top, CPLayout.space8)
            } else {
                ForEach(viewModel.transactions) { tx in
                    CPCard {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(tx.type.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(CPTypography.bodySemibold)
                                    .foregroundColor(CPColors.textPrimary)
                                Text(tx.createdAt.prefix(19).description)
                                    .font(CPTypography.caption)
                                    .foregroundColor(CPColors.textMuted)
                                if let note = tx.note, !note.isEmpty {
                                    Text(note)
                                        .font(CPTypography.caption)
                                        .foregroundColor(CPColors.textSecondary)
                                }
                            }
                            Spacer()
                            Text(tx.amount >= 0 ? "+\(CardParser.formatChips(tx.amount))" : CardParser.formatChips(tx.amount))
                                .font(CPTypography.mono)
                                .foregroundColor(tx.amount >= 0 ? CPColors.success : CPColors.danger)
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
        .onAppear { viewModel.fetchTransactions(clubId: clubId) }
    }

    // MARK: - Analytics Tab

    private func analyticsContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space4) {
            CPCard {
                VStack(spacing: CPLayout.space3) {
                    Image(systemName: "chart.bar.xaxis")
                        .font(.system(size: 36))
                        .foregroundColor(CPColors.accent)
                    Text("Club Analytics")
                        .font(CPTypography.title)
                        .foregroundColor(CPColors.textPrimary)
                    Text("Player activity heatmaps, revenue trends, session analysis")
                        .font(CPTypography.caption)
                        .foregroundColor(CPColors.textSecondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, CPLayout.space6)
            }
            // TODO: Charts (profit, heatmap, active players trend) require charting library
        }
        .padding(CPLayout.space4)
    }

    // MARK: - Rulesets Tab (admin)

    private func rulesetsContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            Button {
                viewModel.createRuleset(clubId: clubId, name: "Ruleset \(viewModel.rulesets.count + 1)")
            } label: {
                HStack { Image(systemName: "plus"); Text("Create Ruleset") }.frame(maxWidth: .infinity)
            }
            .buttonStyle(.cpPrimary)

            ForEach(viewModel.rulesets) { ruleset in
                CPCard {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(ruleset.name)
                                    .font(CPTypography.bodySemibold)
                                    .foregroundColor(CPColors.textPrimary)
                                if ruleset.isDefault ?? false {
                                    Text("DEFAULT")
                                        .font(.system(size: 9, weight: .bold))
                                        .foregroundColor(CPColors.gold)
                                        .padding(.horizontal, 4)
                                        .padding(.vertical, 1)
                                        .background(CPColors.gold.opacity(0.15))
                                        .cornerRadius(3)
                                }
                            }
                        }
                        Spacer()
                        if !(ruleset.isDefault ?? false) {
                            Button("Set Default") {
                                viewModel.setDefaultRuleset(clubId: clubId, rulesetId: ruleset.id)
                            }
                            .font(CPTypography.captionBold)
                            .foregroundColor(CPColors.accent)
                        }
                    }
                }
            }
        }
        .padding(CPLayout.space4)
    }

    // MARK: - Activity Tab (admin audit log)

    private func activityContent(_ clubId: String) -> some View {
        VStack(spacing: CPLayout.space3) {
            if viewModel.auditLog.isEmpty {
                VStack(spacing: CPLayout.space3) {
                    Image(systemName: "clock.badge.checkmark")
                        .font(.system(size: 36))
                        .foregroundColor(CPColors.textMuted)
                    Text("No activity yet")
                        .font(CPTypography.title)
                        .foregroundColor(CPColors.textSecondary)
                }
                .padding(.top, CPLayout.space8)
            } else {
                ForEach(viewModel.auditLog) { entry in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.actionType.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(CPTypography.body)
                                .foregroundColor(CPColors.textPrimary)
                            Text("by \(entry.actorDisplayName ?? "System")")
                                .font(CPTypography.caption)
                                .foregroundColor(CPColors.textMuted)
                        }
                        Spacer()
                        Text(entry.createdAt.prefix(16).description)
                            .font(CPTypography.caption)
                            .foregroundColor(CPColors.textMuted)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .padding(CPLayout.space4)
    }
}
