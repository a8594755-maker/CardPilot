import Foundation
import SocketIO

// MARK: - CardPilot Socket Manager
// Manages Socket.IO connection lifecycle, auth handshake, and reconnection.
// Mirrors SocketContext.tsx behavior.

@Observable
final class CPSocketManager {
    // MARK: State
    private(set) var isConnected = false
    private(set) var isReconnecting = false
    private(set) var serverUserId: String?
    private(set) var supabaseEnabled = false

    // MARK: Private
    private var manager: SocketIO.SocketManager?
    private(set) var socket: SocketIOClient?
    private var authSession: AuthSession?

    // Rejoin state (for reconnection)
    private(set) var lastJoinedTableId: String?
    private var lastConnectErrorToast: Date = .distantPast

    // MARK: Singleton
    static let shared = CPSocketManager()
    private init() {}

    // MARK: - Connect

    func connect(with session: AuthSession) {
        disconnect()
        self.authSession = session

        guard let url = URL(string: AppEnvironment.serverURL) else {
            print("[Socket] Invalid server URL: \(AppEnvironment.serverURL)")
            return
        }

        manager = SocketIO.SocketManager(socketURL: url, config: [
            .log(AppEnvironment.isDevelopment),
            .compress,
            .forceWebsockets(true),
            .reconnects(true),
            .reconnectAttempts(-1),  // unlimited
            .reconnectWait(1),
            .reconnectWaitMax(5),
            .connectParams([
                "accessToken": session.accessToken,
                "displayName": session.displayName,
                "userId": session.userId
            ])
        ])

        socket = manager?.defaultSocket
        setupEventHandlers()
        socket?.connect()
    }

    // MARK: - Disconnect

    func disconnect() {
        socket?.disconnect()
        socket?.removeAllHandlers()
        manager?.disconnect()
        manager = nil
        socket = nil
        isConnected = false
        isReconnecting = false
        serverUserId = nil
    }

    // MARK: - Emit Helpers

    func emit(_ event: String, _ data: [String: Any]) {
        // Track table joins for auto-rejoin on reconnect
        if event == SocketEvent.Client.joinTable, let tableId = data["tableId"] as? String {
            lastJoinedTableId = tableId
        }
        if event == SocketEvent.Client.leaveTable {
            lastJoinedTableId = nil
        }
        socket?.emit(event, data)
    }

    func emit(_ event: String) {
        socket?.emit(event)
    }

    // MARK: - Event Registration

    func on(_ event: String, callback: @escaping ([Any]) -> Void) {
        socket?.on(event) { data, _ in
            callback(data)
        }
    }

    func off(_ event: String) {
        socket?.off(event)
    }

    // MARK: - Private Setup

    private func setupEventHandlers() {
        guard let socket else { return }

        socket.on(clientEvent: .connect) { [weak self] _, _ in
            Task { @MainActor in
                self?.isConnected = true
                self?.isReconnecting = false
                print("[Socket] Connected")

                // Auto-rejoin table on reconnect
                if let tableId = self?.lastJoinedTableId {
                    self?.emit(SocketEvent.Client.joinTable, ["tableId": tableId])
                    self?.emit(SocketEvent.Client.requestTableSnapshot, ["tableId": tableId])
                    print("[Socket] Auto-rejoining table: \(tableId)")
                }
            }
        }

        socket.on(clientEvent: .disconnect) { [weak self] _, _ in
            Task { @MainActor in
                self?.isConnected = false
                self?.isReconnecting = true
                print("[Socket] Disconnected")
            }
        }

        socket.on(clientEvent: .reconnectAttempt) { [weak self] _, _ in
            Task { @MainActor in
                self?.isReconnecting = true
                print("[Socket] Reconnecting...")
            }
        }

        socket.on(clientEvent: .error) { [weak self] _, _ in
            Task { @MainActor in
                // Throttle error logging (max once per 10 seconds, mirrors SocketContext.tsx)
                let now = Date()
                if now.timeIntervalSince(self?.lastConnectErrorToast ?? .distantPast) >= 10 {
                    self?.lastConnectErrorToast = now
                    print("[Socket] Connection error")
                }
            }
        }

        // Server handshake acknowledgment
        socket.on(SocketEvent.Server.connected) { [weak self] data, _ in
            guard let dict = data.first as? [String: Any] else { return }
            Task { @MainActor in
                self?.serverUserId = dict["userId"] as? String
                self?.supabaseEnabled = dict["supabaseEnabled"] as? Bool ?? false
                print("[Socket] Server confirmed: userId=\(dict["userId"] ?? "nil")")
            }
        }
    }
}
