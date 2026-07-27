import Foundation
import Supabase

// MARK: - Auth View Model

@Observable
final class AuthViewModel {
    // MARK: State
    var email = ""
    var password = ""
    var displayName = ""
    var isLoading = false
    var errorMessage: String?
    var authSession: AuthSession?

    // MARK: Private
    private var supabaseClient: SupabaseClient?

    init() {
        if AppEnvironment.isSupabaseEnabled {
            supabaseClient = SupabaseClient(
                supabaseURL: URL(string: AppEnvironment.supabaseURL)!,
                supabaseKey: AppEnvironment.supabaseAnonKey
            )
        }
        // Try to restore saved session
        authSession = AuthSession.load()
    }

    var isAuthenticated: Bool {
        authSession != nil
    }

    // MARK: - Sign In with Email

    func signInWithEmail() async {
        guard validateInputs(requireName: false) else { return }
        isLoading = true
        errorMessage = nil

        do {
            guard let client = supabaseClient else {
                throw AuthError.supabaseNotConfigured
            }

            let response = try await client.auth.signIn(
                email: email,
                password: password
            )

            let session = AuthSession(
                accessToken: response.accessToken,
                userId: response.user.id.uuidString,
                email: response.user.email,
                displayName: response.user.userMetadata["display_name"]?.value as? String
                    ?? response.user.email ?? "Player",
                isGuest: false
            )
            session.save()
            self.authSession = session
            connectSocket()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - Sign Up with Email

    func signUpWithEmail() async {
        guard validateInputs(requireName: true) else { return }
        isLoading = true
        errorMessage = nil

        do {
            guard let client = supabaseClient else {
                throw AuthError.supabaseNotConfigured
            }

            let response = try await client.auth.signUp(
                email: email,
                password: password,
                data: ["display_name": .string(displayName)]
            )

            guard let user = response.user else {
                errorMessage = "Sign up succeeded but no user returned"
                isLoading = false
                return
            }

            let session = AuthSession(
                accessToken: response.session?.accessToken ?? "",
                userId: user.id.uuidString,
                email: user.email,
                displayName: displayName,
                isGuest: false
            )
            session.save()
            self.authSession = session
            connectSocket()
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - Continue as Guest

    func continueAsGuest() {
        let session = AuthSession.guest()
        session.save()
        self.authSession = session
        connectSocket()
    }

    // MARK: - Sign Out

    func signOut() {
        Task {
            try? await supabaseClient?.auth.signOut()
        }
        CPSocketManager.shared.disconnect()
        AuthSession.clear()
        authSession = nil
    }

    // MARK: - Restore Session on App Launch

    func restoreSessionIfNeeded() {
        guard let session = authSession else { return }
        connectSocket()

        // If authenticated, try to refresh the token
        if !session.isGuest, let client = supabaseClient {
            Task {
                do {
                    let refreshed = try await client.auth.session
                    let updated = AuthSession(
                        accessToken: refreshed.accessToken,
                        userId: refreshed.user.id.uuidString,
                        email: refreshed.user.email,
                        displayName: session.displayName,
                        isGuest: false
                    )
                    updated.save()
                    await MainActor.run {
                        self.authSession = updated
                    }
                } catch {
                    print("[Auth] Token refresh failed: \(error)")
                }
            }
        }
    }

    // MARK: - Private

    private func connectSocket() {
        guard let session = authSession else { return }
        CPSocketManager.shared.connect(with: session)
    }

    private func validateInputs(requireName: Bool) -> Bool {
        errorMessage = nil

        guard !email.isEmpty else {
            errorMessage = "Please enter your email"
            return false
        }

        guard email.contains("@") && email.contains(".") else {
            errorMessage = "Please enter a valid email"
            return false
        }

        guard password.count >= 6 else {
            errorMessage = "Password must be at least 6 characters"
            return false
        }

        if requireName && displayName.isEmpty {
            errorMessage = "Please enter a display name"
            return false
        }

        return true
    }
}

// MARK: - Auth Errors

enum AuthError: LocalizedError {
    case supabaseNotConfigured

    var errorDescription: String? {
        switch self {
        case .supabaseNotConfigured:
            return "Supabase is not configured. Please check your environment settings."
        }
    }
}
