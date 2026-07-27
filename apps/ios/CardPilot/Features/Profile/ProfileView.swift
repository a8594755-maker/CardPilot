import SwiftUI

// MARK: - Profile View Model

@Observable
final class ProfileViewModel {
    var displayName: String = ""
    var email: String = ""
    var isGuest = false
    var isSoundOn = true
    var showBBValues = false

    func load(from session: AuthSession) {
        displayName = session.displayName
        email = session.email ?? ""
        isGuest = session.isGuest
    }
}

// MARK: - Profile View

struct ProfileView: View {
    @Bindable var viewModel: ProfileViewModel
    let authViewModel: AuthViewModel

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            ScrollView {
                VStack(spacing: CPLayout.space4) {
                    // MARK: Avatar Section
                    VStack(spacing: CPLayout.space3) {
                        // Avatar circle
                        ZStack {
                            Circle()
                                .fill(CPColors.accent)
                                .frame(width: 80, height: 80)

                            Text(String(viewModel.displayName.prefix(1)).uppercased())
                                .font(.system(size: 32, weight: .bold))
                                .foregroundColor(.white)
                        }

                        Text(viewModel.displayName)
                            .font(CPTypography.heading)
                            .foregroundColor(CPColors.textPrimary)

                        if viewModel.isGuest {
                            HStack(spacing: 4) {
                                Image(systemName: "person.fill.questionmark")
                                    .font(.system(size: 12))
                                Text("Guest Account")
                                    .font(CPTypography.caption)
                            }
                            .foregroundColor(CPColors.warning)
                        } else {
                            Text(viewModel.email)
                                .font(CPTypography.label)
                                .foregroundColor(CPColors.textSecondary)
                        }
                    }
                    .padding(.top, CPLayout.space4)

                    // MARK: Settings
                    CPCard {
                        VStack(spacing: 0) {
                            settingsRow(
                                icon: "speaker.wave.2",
                                title: "Sound Effects",
                                trailing: AnyView(
                                    Toggle("", isOn: $viewModel.isSoundOn)
                                        .tint(CPColors.accent)
                                )
                            )

                            Divider()
                                .background(CPColors.borderSubtle)

                            settingsRow(
                                icon: "textformat.123",
                                title: "Show Big Blinds",
                                trailing: AnyView(
                                    Toggle("", isOn: $viewModel.showBBValues)
                                        .tint(CPColors.accent)
                                )
                            )
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)

                    // MARK: Connection Info
                    CPCard {
                        VStack(spacing: CPLayout.space3) {
                            infoRow("Server", value: AppEnvironment.serverURL)
                            infoRow("User ID", value: String(authViewModel.authSession?.userId.prefix(12) ?? "N/A") + "...")
                            infoRow("Socket", value: CPSocketManager.shared.isConnected ? "Connected" : "Disconnected")
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)

                    // MARK: Sign Out
                    Button {
                        HapticManager.action()
                        authViewModel.signOut()
                    } label: {
                        HStack {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                            Text("Sign Out")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpDanger)
                    .padding(.horizontal, CPLayout.space4)
                    .padding(.top, CPLayout.space4)

                    // MARK: Version
                    Text("CardPilot iOS v1.0.0")
                        .font(CPTypography.caption)
                        .foregroundColor(CPColors.textMuted)
                        .padding(.top, CPLayout.space4)
                }
            }
        }
        .navigationTitle("Profile")
        .onAppear {
            if let session = authViewModel.authSession {
                viewModel.load(from: session)
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Settings Row

    private func settingsRow(icon: String, title: String, trailing: AnyView) -> some View {
        HStack {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundColor(CPColors.accent)
                .frame(width: 28)

            Text(title)
                .font(CPTypography.body)
                .foregroundColor(CPColors.textPrimary)

            Spacer()

            trailing
        }
        .padding(.vertical, CPLayout.space2)
    }

    // MARK: - Info Row

    private func infoRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(CPTypography.label)
                .foregroundColor(CPColors.textSecondary)
            Spacer()
            Text(value)
                .font(CPTypography.monoSmall)
                .foregroundColor(CPColors.textMuted)
                .lineLimit(1)
        }
    }
}
