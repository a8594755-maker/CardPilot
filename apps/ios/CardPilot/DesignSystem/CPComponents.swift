import SwiftUI

// MARK: - Spacing & Layout Constants

enum CPLayout {
    static let space0: CGFloat = 0
    static let space1: CGFloat = 4
    static let space2: CGFloat = 8
    static let space3: CGFloat = 12
    static let space4: CGFloat = 16
    static let space5: CGFloat = 20
    static let space6: CGFloat = 24
    static let space8: CGFloat = 32
    static let space10: CGFloat = 40
    static let space12: CGFloat = 48
    static let space16: CGFloat = 64

    static let radiusSm: CGFloat = 6
    static let radiusMd: CGFloat = 10
    static let radiusLg: CGFloat = 14
    static let radiusXl: CGFloat = 20
    static let radiusFull: CGFloat = 9999

    static let touchTarget: CGFloat = 44  // Apple HIG minimum
    static let headerHeight: CGFloat = 56
    static let actionBarHeight: CGFloat = 104
    static let tabBarHeight: CGFloat = 52
}

// MARK: - Button Styles

struct CPButtonStyle: ButtonStyle {
    enum Variant {
        case primary, danger, ghost, secondary, call, raise, fold, allIn
    }

    let variant: Variant

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(CPTypography.bodySemibold)
            .foregroundColor(foregroundColor)
            .padding(.horizontal, CPLayout.space4)
            .padding(.vertical, CPLayout.space3)
            .frame(minHeight: CPLayout.touchTarget)
            .background(backgroundColor)
            .cornerRadius(CPLayout.radiusMd)
            .opacity(configuration.isPressed ? 0.8 : 1.0)
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .animation(.easeOut(duration: 0.1), value: configuration.isPressed)
    }

    private var backgroundColor: Color {
        switch variant {
        case .primary: return CPColors.accent
        case .danger: return CPColors.danger
        case .ghost: return .clear
        case .secondary: return CPColors.bgElevated
        case .call: return CPColors.callColor
        case .raise: return CPColors.raiseColor
        case .fold: return CPColors.foldColor
        case .allIn: return CPColors.allinColor
        }
    }

    private var foregroundColor: Color {
        switch variant {
        case .ghost: return CPColors.textSecondary
        default: return .white
        }
    }
}

extension ButtonStyle where Self == CPButtonStyle {
    static var cpPrimary: CPButtonStyle { .init(variant: .primary) }
    static var cpDanger: CPButtonStyle { .init(variant: .danger) }
    static var cpGhost: CPButtonStyle { .init(variant: .ghost) }
    static var cpSecondary: CPButtonStyle { .init(variant: .secondary) }
    static var cpCall: CPButtonStyle { .init(variant: .call) }
    static var cpRaise: CPButtonStyle { .init(variant: .raise) }
    static var cpFold: CPButtonStyle { .init(variant: .fold) }
    static var cpAllIn: CPButtonStyle { .init(variant: .allIn) }
}

// MARK: - Card Surface

struct CPCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(CPLayout.space4)
            .background(CPColors.bgSurface)
            .cornerRadius(CPLayout.radiusLg)
            .overlay(
                RoundedRectangle(cornerRadius: CPLayout.radiusLg)
                    .stroke(CPColors.borderSubtle, lineWidth: 1)
            )
    }
}

// MARK: - Glass Card (frosted glass effect)

struct CPGlassCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(CPLayout.space4)
            .background(
                CPColors.bgSurface.opacity(0.85)
            )
            .background(.ultraThinMaterial)
            .cornerRadius(CPLayout.radiusLg)
            .overlay(
                RoundedRectangle(cornerRadius: CPLayout.radiusLg)
                    .stroke(
                        LinearGradient(
                            colors: [.white.opacity(0.12), .white.opacity(0.04)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
            )
    }
}

// MARK: - Text Field Style

struct CPTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .font(CPTypography.body)
            .foregroundColor(CPColors.textPrimary)
            .padding(CPLayout.space3)
            .background(CPColors.bgElevated)
            .cornerRadius(CPLayout.radiusMd)
            .overlay(
                RoundedRectangle(cornerRadius: CPLayout.radiusMd)
                    .stroke(CPColors.borderDefault, lineWidth: 1)
            )
    }
}

// MARK: - Toast View

struct CPToast: View {
    let message: String
    var style: ToastStyle = .info

    enum ToastStyle {
        case info, success, error, warning
    }

    var body: some View {
        HStack(spacing: CPLayout.space2) {
            Image(systemName: iconName)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(iconColor)

            Text(message)
                .font(CPTypography.label)
                .foregroundColor(CPColors.textPrimary)
        }
        .padding(.horizontal, CPLayout.space4)
        .padding(.vertical, CPLayout.space3)
        .background(CPColors.bgElevated)
        .cornerRadius(CPLayout.radiusFull)
        .overlay(
            Capsule()
                .stroke(CPColors.borderDefault, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.3), radius: 12, y: 4)
    }

    private var iconName: String {
        switch style {
        case .info: return "info.circle.fill"
        case .success: return "checkmark.circle.fill"
        case .error: return "xmark.circle.fill"
        case .warning: return "exclamationmark.triangle.fill"
        }
    }

    private var iconColor: Color {
        switch style {
        case .info: return CPColors.callColor
        case .success: return CPColors.success
        case .error: return CPColors.danger
        case .warning: return CPColors.warning
        }
    }
}

// MARK: - Connection Status Badge

struct CPConnectionBadge: View {
    let connected: Bool

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(connected ? CPColors.success : CPColors.danger)
                .frame(width: 8, height: 8)

            Text(connected ? "Connected" : "Disconnected")
                .font(CPTypography.caption)
                .foregroundColor(CPColors.textSecondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(CPColors.bgElevated)
        .cornerRadius(CPLayout.radiusFull)
    }
}
