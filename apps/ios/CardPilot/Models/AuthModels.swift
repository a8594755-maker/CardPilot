import Foundation

// MARK: - Auth Session

struct AuthSession: Codable {
    let accessToken: String
    let userId: String
    let email: String?
    let displayName: String
    let isGuest: Bool

    static func guest() -> AuthSession {
        let guestId = "guest-\(String(UUID().uuidString.prefix(8)).lowercased())"
        return AuthSession(
            accessToken: "",
            userId: guestId,
            email: nil,
            displayName: "Guest",
            isGuest: true
        )
    }
}

// MARK: - Persistence

extension AuthSession {
    private static let storageKey = "cardpilot_auth_session"

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }

    static func load() -> AuthSession? {
        guard let data = UserDefaults.standard.data(forKey: storageKey),
              let session = try? JSONDecoder().decode(AuthSession.self, from: data)
        else { return nil }
        return session
    }

    static func clear() {
        UserDefaults.standard.removeObject(forKey: storageKey)
    }
}
