import Foundation

// MARK: - Socket Event Router
// Decodes raw Socket.IO payloads into typed Swift structs
// and dispatches to registered handlers.

@Observable
final class SocketEventRouter {
    private let socketManager: CPSocketManager
    private let decoder = JSONDecoder()

    init(socketManager: CPSocketManager = .shared) {
        self.socketManager = socketManager
    }

    // MARK: - Generic Decode Helper

    func decode<T: Decodable>(_ type: T.Type, from data: [Any]) -> T? {
        guard let dict = data.first else { return nil }
        do {
            let jsonData: Data
            if let d = dict as? Data {
                jsonData = d
            } else {
                jsonData = try JSONSerialization.data(withJSONObject: dict)
            }
            return try decoder.decode(type, from: jsonData)
        } catch {
            print("[SocketRouter] Decode error for \(T.self): \(error)")
            return nil
        }
    }

    // MARK: - Register Typed Handler

    func on<T: Decodable>(_ event: String, type: T.Type, handler: @escaping (T) -> Void) {
        socketManager.on(event) { [weak self] data in
            guard let payload = self?.decode(type, from: data) else { return }
            Task { @MainActor in
                handler(payload)
            }
        }
    }

    // MARK: - Register Raw Handler (for events with no payload)

    func on(_ event: String, handler: @escaping () -> Void) {
        socketManager.on(event) { _ in
            Task { @MainActor in
                handler()
            }
        }
    }

    // MARK: - Bulk Registration for Game Events

    func registerLobbyEvents(
        onLobbySnapshot: @escaping ([LobbyRoomSummary]) -> Void,
        onRoomCreated: @escaping (RoomCreatedPayload) -> Void,
        onRoomJoined: @escaping (RoomJoinedPayload) -> Void
    ) {
        on(SocketEvent.Server.lobbySnapshot, type: LobbySnapshotPayload.self) { payload in
            onLobbySnapshot(payload.rooms)
        }
        on(SocketEvent.Server.roomCreated, type: RoomCreatedPayload.self) { payload in
            onRoomCreated(payload)
        }
        on(SocketEvent.Server.roomJoined, type: RoomJoinedPayload.self) { payload in
            onRoomJoined(payload)
        }
    }

    func registerTableEvents(
        onSnapshot: @escaping (TableState) -> Void,
        onHoleCards: @escaping (HoleCardsPayload) -> Void,
        onHandStarted: @escaping (HandStartedPayload) -> Void,
        onActionApplied: @escaping (ActionAppliedPayload) -> Void,
        onStreetAdvanced: @escaping (StreetAdvancedPayload) -> Void,
        onBoardReveal: @escaping (BoardRevealEvent) -> Void,
        onShowdownResults: @escaping (ShowdownResultsPayload) -> Void,
        onHandEnded: @escaping (HandEndedPayload) -> Void,
        onAdvice: @escaping (AdvicePayload) -> Void,
        onError: @escaping (String) -> Void
    ) {
        on(SocketEvent.Server.tableSnapshot, type: TableState.self, handler: onSnapshot)
        on(SocketEvent.Server.holeCards, type: HoleCardsPayload.self, handler: onHoleCards)
        on(SocketEvent.Server.handStarted, type: HandStartedPayload.self, handler: onHandStarted)
        on(SocketEvent.Server.actionApplied, type: ActionAppliedPayload.self, handler: onActionApplied)
        on(SocketEvent.Server.streetAdvanced, type: StreetAdvancedPayload.self, handler: onStreetAdvanced)
        on(SocketEvent.Server.boardReveal, type: BoardRevealEvent.self, handler: onBoardReveal)
        on(SocketEvent.Server.showdownResults, type: ShowdownResultsPayload.self, handler: onShowdownResults)
        on(SocketEvent.Server.handEnded, type: HandEndedPayload.self, handler: onHandEnded)
        on(SocketEvent.Server.advicePayload, type: AdvicePayload.self, handler: onAdvice)
        on(SocketEvent.Server.errorEvent, type: ErrorPayload.self) { payload in
            onError(payload.message)
        }
    }

    func registerHistoryEvents(
        onRooms: @escaping ([HistoryRoomSummary]) -> Void,
        onSessions: @escaping (String, [HistorySessionSummary]) -> Void,
        onHands: @escaping (HistoryHandsPayload) -> Void,
        onHandDetail: @escaping (HistoryHandDetailPayload) -> Void
    ) {
        on(SocketEvent.Server.historyRooms, type: HistoryRoomsPayload.self) { payload in
            onRooms(payload.rooms)
        }
        on(SocketEvent.Server.historySessions, type: HistorySessionsPayload.self) { payload in
            onSessions(payload.roomId, payload.sessions)
        }
        on(SocketEvent.Server.historyHands, type: HistoryHandsPayload.self, handler: onHands)
        on(SocketEvent.Server.historyHandDetail, type: HistoryHandDetailPayload.self, handler: onHandDetail)
    }

    // MARK: - Cleanup

    func removeAllHandlers() {
        // Socket-level cleanup is handled by CPSocketManager.disconnect()
    }
}
