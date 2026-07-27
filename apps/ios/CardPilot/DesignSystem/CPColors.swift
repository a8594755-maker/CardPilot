import SwiftUI

// MARK: - Color Extension for Hex Init

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 6:
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - CardPilot Color Tokens
// Direct port of design-tokens.css — OLED Dark + Card & Board Game palette
// UI/UX Pro Max: Dark Mode (OLED) + felt green #15803D + gold #D97706

enum CPColors {
    // MARK: Background
    static let bgBase = Color(hex: "#080D19")
    static let bgSurface = Color(hex: "#0F1724")
    static let bgElevated = Color(hex: "#192134")
    static let bgOverlay = Color.black.opacity(0.7)

    // MARK: Border
    static let borderSubtle = Color.white.opacity(0.07)
    static let borderDefault = Color.white.opacity(0.12)
    static let borderStrong = Color.white.opacity(0.22)
    static let borderGlow = Color(hex: "#D97706").opacity(0.25)

    // MARK: Text
    static let textPrimary = Color(hex: "#F8FAFC")
    static let textSecondary = Color(hex: "#94A3B8")
    static let textMuted = Color(hex: "#64748B")
    static let textDisabled = Color(hex: "#475569")

    // MARK: Semantic
    static let accent = Color(hex: "#15803D")       // felt green
    static let accentHover = Color(hex: "#16A34A")
    static let accentLight = Color(hex: "#15803D").opacity(0.15)
    static let success = Color(hex: "#22C55E")
    static let successHover = Color(hex: "#4ADE80")
    static let danger = Color(hex: "#DC2626")
    static let dangerHover = Color(hex: "#EF4444")
    static let warning = Color(hex: "#D97706")
    static let gold = Color(hex: "#D97706")
    static let goldLight = Color(hex: "#F59E0B")
    static let goldGlow = Color(hex: "#D97706").opacity(0.2)

    // MARK: Poker-specific
    static let potColor = Color(hex: "#D97706")
    static let feltGreen = Color(hex: "#15803D")
    static let feltDark = Color(hex: "#0D4526")
    static let callColor = Color(hex: "#38BDF8")     // cyan
    static let raiseColor = Color(hex: "#EF4444")     // red
    static let foldColor = Color(hex: "#64748B")      // muted
    static let checkColor = Color(hex: "#22C55E")     // green
    static let allinColor = Color(hex: "#F97316")     // orange

    // MARK: Card Suits (4-color deck)
    static let suitSpade = Color(hex: "#F8FAFC")      // white
    static let suitHeart = Color(hex: "#EF4444")      // red
    static let suitDiamond = Color(hex: "#38BDF8")    // blue
    static let suitClub = Color(hex: "#22C55E")       // green

    // MARK: CFR / GTO Strategy
    static let bet0Color = Color(hex: "#FBBF24")      // small bet (33%)
    static let bet1Color = Color(hex: "#F59E0B")      // medium bet (66%)
    static let bet2Color = Color(hex: "#F97316")      // large bet (75%+)
    static let raise0Color = Color(hex: "#E879F9")    // min-raise
    static let raise1Color = Color(hex: "#C084FC")    // large raise
}
