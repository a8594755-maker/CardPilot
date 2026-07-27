import SwiftUI

// MARK: - Card View
// Renders a single playing card from notation (e.g., "Ah", "Ks")

struct CardView: View {
    let notation: String
    var size: CardSize = .medium
    var isFaceDown: Bool = false
    @State private var isFlipped = false

    enum CardSize {
        case small, medium, large

        var width: CGFloat {
            switch self {
            case .small: return 28
            case .medium: return 40
            case .large: return 60
            }
        }

        var height: CGFloat {
            width * 1.4
        }

        var fontSize: CGFloat {
            switch self {
            case .small: return 10
            case .medium: return 14
            case .large: return 20
            }
        }

        var suitSize: CGFloat {
            switch self {
            case .small: return 8
            case .medium: return 11
            case .large: return 16
            }
        }
    }

    var body: some View {
        Group {
            if isFaceDown {
                cardBack
            } else if let card = CardParser.parse(notation) {
                cardFace(card)
            } else {
                cardBack
            }
        }
        .frame(width: size.width, height: size.height)
        .rotation3DEffect(
            .degrees(isFlipped ? 0 : 180),
            axis: (x: 0, y: 1, z: 0)
        )
        .onAppear {
            if !isFaceDown {
                withAnimation(.spring(duration: 0.4, bounce: 0.2)) {
                    isFlipped = true
                }
            }
        }
    }

    // MARK: - Card Face

    private func cardFace(_ card: CardInfo) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 4)
                .fill(.white)

            VStack(spacing: 0) {
                Text(card.rank)
                    .font(.system(size: size.fontSize, weight: .bold, design: .rounded))
                    .foregroundColor(card.suit.color == CPColors.suitSpade ? .black : card.suit.color)

                Text(card.suit.symbol)
                    .font(.system(size: size.suitSize))
                    .foregroundColor(card.suit.color == CPColors.suitSpade ? .black : card.suit.color)
            }
        }
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.gray.opacity(0.3), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.2), radius: 2, y: 1)
    }

    // MARK: - Card Back

    private var cardBack: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 4)
                .fill(
                    LinearGradient(
                        colors: [Color(hex: "#1E3A5F"), Color(hex: "#0F1F33")],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            RoundedRectangle(cornerRadius: 2)
                .stroke(.white.opacity(0.15), lineWidth: 1)
                .padding(3)

            // Pattern
            Image(systemName: "suit.spade.fill")
                .font(.system(size: size.suitSize))
                .foregroundColor(.white.opacity(0.1))
        }
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .stroke(Color.gray.opacity(0.3), lineWidth: 0.5)
        )
    }
}

// MARK: - Community Cards View

struct CommunityCardsView: View {
    let cards: [String]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(Array(cards.enumerated()), id: \.offset) { index, card in
                CardView(notation: card, size: .medium)
                    .transition(.asymmetric(
                        insertion: .scale(scale: 0.5).combined(with: .opacity),
                        removal: .opacity
                    ))
                    .animation(
                        .spring(duration: 0.4, bounce: 0.3).delay(Double(index) * 0.08),
                        value: cards.count
                    )
            }
        }
    }
}
