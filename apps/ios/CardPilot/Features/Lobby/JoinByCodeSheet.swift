import SwiftUI

// MARK: - Join by Code Sheet

struct JoinByCodeSheet: View {
    @Bindable var viewModel: LobbyViewModel
    @Binding var isPresented: Bool
    @FocusState private var isFocused: Bool

    var body: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()

                VStack(spacing: CPLayout.space5) {
                    VStack(alignment: .leading, spacing: CPLayout.space1) {
                        Text("Room Code")
                            .font(CPTypography.label)
                            .foregroundColor(CPColors.textSecondary)

                        TextField("Enter room code", text: $viewModel.joinCode)
                            .textFieldStyle(CPTextFieldStyle())
                            .font(CPTypography.monoLarge)
                            .autocapitalization(.allCharacters)
                            .autocorrectionDisabled()
                            .focused($isFocused)
                    }

                    if let error = viewModel.errorMessage {
                        Text(error)
                            .font(CPTypography.caption)
                            .foregroundColor(CPColors.danger)
                    }

                    Button {
                        HapticManager.action()
                        viewModel.joinByCode()
                        isPresented = false
                    } label: {
                        Text("Join Room")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.cpPrimary)
                    .disabled(viewModel.joinCode.isEmpty)

                    Spacer()
                }
                .padding(CPLayout.space4)
            }
            .navigationTitle("Join by Code")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { isPresented = false }
                        .foregroundColor(CPColors.textSecondary)
                }
            }
            .onAppear { isFocused = true }
        }
        .preferredColorScheme(.dark)
    }
}
