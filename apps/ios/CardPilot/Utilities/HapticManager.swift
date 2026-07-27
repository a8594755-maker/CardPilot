import UIKit

// MARK: - Haptic Feedback Manager

enum HapticManager {
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        let generator = UIImpactFeedbackGenerator(style: style)
        generator.prepare()
        generator.impactOccurred()
    }

    static func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        let generator = UINotificationFeedbackGenerator()
        generator.prepare()
        generator.notificationOccurred(type)
    }

    static func selection() {
        let generator = UISelectionFeedbackGenerator()
        generator.prepare()
        generator.selectionChanged()
    }

    // MARK: Poker-specific shortcuts
    static func deal() { impact(.light) }
    static func action() { impact(.medium) }
    static func fold() { impact(.soft) }
    static func allIn() { impact(.heavy) }
    static func win() { notification(.success) }
    static func lose() { notification(.error) }
    static func warning() { notification(.warning) }
}
