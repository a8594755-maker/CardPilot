import Foundation

// MARK: - App Environment Configuration
// Values come from xcconfig files (Secrets.xcconfig / Release.xcconfig)
// For development, these can also be set as scheme environment variables

enum AppEnvironment {
    // MARK: Server
    static var serverURL: String {
        ProcessInfo.processInfo.environment["SERVER_URL"]
            ?? Bundle.main.infoDictionary?["SERVER_URL"] as? String
            ?? "http://127.0.0.1:4000"
    }

    // MARK: Supabase
    static var supabaseURL: String {
        ProcessInfo.processInfo.environment["SUPABASE_URL"]
            ?? Bundle.main.infoDictionary?["SUPABASE_URL"] as? String
            ?? ""
    }

    static var supabaseAnonKey: String {
        ProcessInfo.processInfo.environment["SUPABASE_ANON_KEY"]
            ?? Bundle.main.infoDictionary?["SUPABASE_ANON_KEY"] as? String
            ?? ""
    }

    // MARK: Flags
    static var isSupabaseEnabled: Bool {
        !supabaseURL.isEmpty && !supabaseAnonKey.isEmpty
    }

    static var isDevelopment: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }
}
