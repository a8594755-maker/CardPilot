import SwiftUI

// MARK: - CardPilot Typography
// SF Pro with weight hierarchy matching Chakra Petch from web

enum CPTypography {
    // MARK: Size Scale (matching design-tokens.css)
    static let text2xs: CGFloat = 10
    static let textXs: CGFloat = 11
    static let textSm: CGFloat = 13
    static let textBase: CGFloat = 14
    static let textMd: CGFloat = 16
    static let textLg: CGFloat = 18
    static let textXl: CGFloat = 24
    static let text2xl: CGFloat = 30
    static let text3xl: CGFloat = 36

    // MARK: Prebuilt Fonts
    static let caption = Font.system(size: textXs, weight: .regular)
    static let captionBold = Font.system(size: textXs, weight: .semibold)
    static let body = Font.system(size: textBase, weight: .regular)
    static let bodyMedium = Font.system(size: textBase, weight: .medium)
    static let bodySemibold = Font.system(size: textBase, weight: .semibold)
    static let label = Font.system(size: textSm, weight: .medium)
    static let labelBold = Font.system(size: textSm, weight: .bold)
    static let title = Font.system(size: textMd, weight: .semibold)
    static let heading = Font.system(size: textLg, weight: .bold)
    static let display = Font.system(size: textXl, weight: .bold)
    static let displayLarge = Font.system(size: text2xl, weight: .heavy)
    static let hero = Font.system(size: text3xl, weight: .heavy)

    // MARK: Monospace (for chip counts, pot, numbers)
    static let mono = Font.system(size: textBase, weight: .medium, design: .monospaced)
    static let monoSmall = Font.system(size: textSm, weight: .medium, design: .monospaced)
    static let monoLarge = Font.system(size: textMd, weight: .bold, design: .monospaced)

    // MARK: Line Heights
    static let leadingTight: CGFloat = 1.2
    static let leadingNormal: CGFloat = 1.5
}
