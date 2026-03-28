import SwiftUI

// MARK: - Auth Screen
// Login / Sign Up / Guest mode — matches AuthScreen.tsx

struct AuthView: View {
    @Bindable var viewModel: AuthViewModel
    @State private var isSignUp = false

    var body: some View {
        ZStack {
            // Background
            CPColors.bgBase.ignoresSafeArea()

            ScrollView {
                VStack(spacing: CPLayout.space8) {
                    // MARK: Logo
                    VStack(spacing: CPLayout.space2) {
                        HStack(spacing: 0) {
                            Text("Card")
                                .font(CPTypography.hero)
                                .foregroundColor(CPColors.textPrimary)
                            Text("Pilot")
                                .font(CPTypography.hero)
                                .foregroundColor(CPColors.gold)
                        }

                        Text("Online Poker Platform")
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textSecondary)
                    }
                    .padding(.top, 60)

                    // MARK: Form Card
                    CPGlassCard {
                        VStack(spacing: CPLayout.space5) {
                            // Tab Selector
                            HStack(spacing: 0) {
                                tabButton("Sign In", isActive: !isSignUp) {
                                    withAnimation(.easeInOut(duration: 0.2)) { isSignUp = false }
                                }
                                tabButton("Sign Up", isActive: isSignUp) {
                                    withAnimation(.easeInOut(duration: 0.2)) { isSignUp = true }
                                }
                            }
                            .background(CPColors.bgBase)
                            .cornerRadius(CPLayout.radiusMd)

                            // Display Name (sign up only)
                            if isSignUp {
                                VStack(alignment: .leading, spacing: CPLayout.space1) {
                                    Text("Display Name")
                                        .font(CPTypography.label)
                                        .foregroundColor(CPColors.textSecondary)
                                    TextField("Your name", text: $viewModel.displayName)
                                        .textFieldStyle(CPTextFieldStyle())
                                        .textContentType(.name)
                                        .autocorrectionDisabled()
                                }
                                .transition(.opacity.combined(with: .move(edge: .top)))
                            }

                            // Email
                            VStack(alignment: .leading, spacing: CPLayout.space1) {
                                Text("Email")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)
                                TextField("email@example.com", text: $viewModel.email)
                                    .textFieldStyle(CPTextFieldStyle())
                                    .textContentType(.emailAddress)
                                    .keyboardType(.emailAddress)
                                    .autocapitalization(.none)
                                    .autocorrectionDisabled()
                            }

                            // Password
                            VStack(alignment: .leading, spacing: CPLayout.space1) {
                                Text("Password")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)
                                SecureField("Min 6 characters", text: $viewModel.password)
                                    .textFieldStyle(CPTextFieldStyle())
                                    .textContentType(isSignUp ? .newPassword : .password)
                            }

                            // Error Message
                            if let error = viewModel.errorMessage {
                                Text(error)
                                    .font(CPTypography.caption)
                                    .foregroundColor(CPColors.danger)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }

                            // Submit Button
                            Button {
                                HapticManager.action()
                                Task {
                                    if isSignUp {
                                        await viewModel.signUpWithEmail()
                                    } else {
                                        await viewModel.signInWithEmail()
                                    }
                                }
                            } label: {
                                HStack {
                                    if viewModel.isLoading {
                                        ProgressView()
                                            .tint(.white)
                                            .scaleEffect(0.8)
                                    }
                                    Text(isSignUp ? "Create Account" : "Sign In")
                                }
                                .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.cpPrimary)
                            .disabled(viewModel.isLoading)
                        }
                    }
                    .padding(.horizontal, CPLayout.space4)

                    // MARK: Divider
                    HStack {
                        Rectangle()
                            .fill(CPColors.borderDefault)
                            .frame(height: 1)
                        Text("or")
                            .font(CPTypography.caption)
                            .foregroundColor(CPColors.textMuted)
                        Rectangle()
                            .fill(CPColors.borderDefault)
                            .frame(height: 1)
                    }
                    .padding(.horizontal, CPLayout.space8)

                    // MARK: Guest Button
                    Button {
                        HapticManager.selection()
                        viewModel.continueAsGuest()
                    } label: {
                        HStack(spacing: CPLayout.space2) {
                            Image(systemName: "person.fill.questionmark")
                            Text("Continue as Guest")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpSecondary)
                    .padding(.horizontal, CPLayout.space4)

                    Spacer(minLength: 40)
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Tab Button

    private func tabButton(_ title: String, isActive: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(CPTypography.bodySemibold)
                .foregroundColor(isActive ? CPColors.textPrimary : CPColors.textMuted)
                .frame(maxWidth: .infinity)
                .padding(.vertical, CPLayout.space3)
                .background(isActive ? CPColors.bgElevated : .clear)
                .cornerRadius(CPLayout.radiusMd)
        }
    }
}
