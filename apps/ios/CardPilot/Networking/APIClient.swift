import Foundation

// MARK: - REST API Client
// For /api/gto/* and /api/cfr/* endpoints

actor APIClient {
    static let shared = APIClient()

    private let session = URLSession.shared
    private let decoder = JSONDecoder()

    private var baseURL: String {
        AppEnvironment.serverURL
    }

    // MARK: - Generic Fetch

    func fetch<T: Decodable>(_ type: T.Type, path: String, query: [String: String] = [:]) async throws -> T {
        var components = URLComponents(string: "\(baseURL)\(path)")!
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 15

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError.httpError(httpResponse.statusCode)
        }

        return try decoder.decode(type, from: data)
    }

    // MARK: - POST

    func post<T: Decodable, B: Encodable>(_ type: T.Type, path: String, body: B) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0)
        }

        return try decoder.decode(type, from: data)
    }

    // MARK: - Health Check

    func healthCheck() async -> Bool {
        do {
            struct HealthResponse: Decodable { let ok: Bool }
            let result = try await fetch(HealthResponse.self, path: "/health")
            return result.ok
        } catch {
            return false
        }
    }
}

// MARK: - API Errors

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .invalidResponse: return "Invalid server response"
        case .httpError(let code): return "HTTP error \(code)"
        }
    }
}
