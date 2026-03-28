import Foundation

// MARK: - Lobby View Model

@Observable
final class LobbyViewModel {
    // MARK: State
    var rooms: [LobbyRoomSummary] = []
    var isLoading = false
    var joinCode = ""
    var errorMessage: String?

    // Room creation form
    var newRoomName = ""
    var newRoomSB: Double = 1
    var newRoomBB: Double = 2
    var newRoomBuyInMin: Double = 40
    var newRoomBuyInMax: Double = 200
    var newRoomMaxPlayers = 6
    var newRoomVisibility: RoomVisibility = .public

    // Navigation
    var joinedTableId: String?
    var joinedRoomCode: String?
    var joinedRoomName: String?
    var shouldNavigateToTable = false

    // MARK: Dependencies
    private let socket = CPSocketManager.shared
    private let router: SocketEventRouter

    init(router: SocketEventRouter) {
        self.router = router
        registerEvents()
    }

    // MARK: - Actions

    func requestLobby() {
        isLoading = true
        socket.emit(SocketEvent.Client.requestLobby)
    }

    func createRoom() {
        var payload: [String: Any] = [
            "roomName": newRoomName.isEmpty ? "Room \(Int.random(in: 1000...9999))" : newRoomName,
            "maxPlayers": newRoomMaxPlayers,
            "smallBlind": newRoomSB,
            "bigBlind": newRoomBB,
            "buyInMin": newRoomBuyInMin,
            "buyInMax": newRoomBuyInMax,
            "visibility": newRoomVisibility.rawValue
        ]
        socket.emit(SocketEvent.Client.createRoom, payload)
    }

    func joinByCode() {
        guard !joinCode.isEmpty else {
            errorMessage = "Please enter a room code"
            return
        }
        errorMessage = nil
        socket.emit(SocketEvent.Client.joinRoomCode, [
            "roomCode": joinCode.uppercased()
        ])
    }

    func joinRoom(_ room: LobbyRoomSummary) {
        socket.emit(SocketEvent.Client.joinRoomCode, [
            "roomCode": room.roomCode
        ])
    }

    // MARK: - Private

    private func registerEvents() {
        router.registerLobbyEvents(
            onLobbySnapshot: { [weak self] rooms in
                self?.rooms = rooms.filter { $0.status == "OPEN" }
                self?.isLoading = false
            },
            onRoomCreated: { [weak self] payload in
                self?.handleRoomJoin(
                    tableId: payload.tableId,
                    roomCode: payload.roomCode,
                    roomName: payload.roomName
                )
            },
            onRoomJoined: { [weak self] payload in
                self?.handleRoomJoin(
                    tableId: payload.tableId,
                    roomCode: payload.roomCode,
                    roomName: payload.roomName
                )
            }
        )
    }

    private func handleRoomJoin(tableId: String, roomCode: String, roomName: String) {
        joinedTableId = tableId
        joinedRoomCode = roomCode
        joinedRoomName = roomName
        shouldNavigateToTable = true
        HapticManager.notification(.success)

        // Auto-join the table
        socket.emit(SocketEvent.Client.joinTable, ["tableId": tableId])
    }
}
