import SwiftUI

// MARK: - Card Parser
// Parses card notation like "Ah", "Ks", "Td", "2c" into display components

struct CardInfo {
    let rank: String
    let suit: Suit
    let notation: String

    enum Suit: String {
        case spade = "s"
        case heart = "h"
        case diamond = "d"
        case club = "c"

        var symbol: String {
            switch self {
            case .spade: return "\u{2660}"
            case .heart: return "\u{2665}"
            case .diamond: return "\u{2666}"
            case .club: return "\u{2663}"
            }
        }

        var color: Color {
            switch self {
            case .spade: return CPColors.suitSpade
            case .heart: return CPColors.suitHeart
            case .diamond: return CPColors.suitDiamond
            case .club: return CPColors.suitClub
            }
        }

        var isRed: Bool {
            self == .heart || self == .diamond
        }
    }
}

enum CardParser {
    static func parse(_ notation: String) -> CardInfo? {
        guard notation.count >= 2 else { return nil }
        let rank = String(notation.prefix(notation.count - 1))
        let suitChar = String(notation.suffix(1))
        guard let suit = CardInfo.Suit(rawValue: suitChar) else { return nil }
        return CardInfo(rank: rank, suit: suit, notation: notation)
    }

    static func parseMany(_ notations: [String]) -> [CardInfo] {
        notations.compactMap { parse($0) }
    }

    /// Format a chip amount for display (e.g., 1500 → "1.5K", 2000000 → "2M")
    static func formatChips(_ amount: Double) -> String {
        if amount >= 1_000_000 {
            let m = amount / 1_000_000
            return m.truncatingRemainder(dividingBy: 1) == 0
                ? "\(Int(m))M"
                : String(format: "%.1fM", m)
        } else if amount >= 10_000 {
            let k = amount / 1_000
            return k.truncatingRemainder(dividingBy: 1) == 0
                ? "\(Int(k))K"
                : String(format: "%.1fK", k)
        } else if amount.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(amount))"
        } else {
            return String(format: "%.2f", amount)
        }
    }

    /// Format as big blinds (e.g., 150 with bb=10 → "15 BB")
    static func formatBB(_ amount: Double, bb: Double) -> String {
        guard bb > 0 else { return formatChips(amount) }
        let bbs = amount / bb
        if bbs.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(bbs)) BB"
        } else {
            return String(format: "%.1f BB", bbs)
        }
    }
}
