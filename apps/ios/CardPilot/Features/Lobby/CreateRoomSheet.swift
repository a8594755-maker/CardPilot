import SwiftUI

// MARK: - Create Room Sheet

struct CreateRoomSheet: View {
    @Bindable var viewModel: LobbyViewModel
    @Binding var isPresented: Bool

    var body: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: CPLayout.space5) {
                        // Room Name
                        VStack(alignment: .leading, spacing: CPLayout.space1) {
                            Text("Room Name")
                                .font(CPTypography.label)
                                .foregroundColor(CPColors.textSecondary)
                            TextField("My Poker Room", text: $viewModel.newRoomName)
                                .textFieldStyle(CPTextFieldStyle())
                        }

                        // Blinds
                        HStack(spacing: CPLayout.space3) {
                            VStack(alignment: .leading, spacing: CPLayout.space1) {
                                Text("Small Blind")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)
                                TextField("1", value: $viewModel.newRoomSB, format: .number)
                                    .textFieldStyle(CPTextFieldStyle())
                                    .keyboardType(.decimalPad)
                            }

                            VStack(alignment: .leading, spacing: CPLayout.space1) {
                                Text("Big Blind")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)
                                TextField("2", value: $viewModel.newRoomBB, format: .number)
                                    .textFieldStyle(CPTextFieldStyle())
                                    .keyboardType(.decimalPad)
                            }
                        }

                        // Buy-in Range
                        HStack(spacing: CPLayout.space3) {
                            VStack(alignment: .leading, spacing: CPLayout.space1) {
                                Text("Min Buy-in")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)
                                TextField("40", value: $viewModel.newRoomBuyInMin, format: .number)
                                    .textFieldStyle(CPTextFieldStyle())
                                    .keyboardType(.decimalPad)
                            }

                            VStack(alignment: .leading, spacing: CPLayout.space1) {
                                Text("Max Buy-in")
                                    .font(CPTypography.label)
                                    .foregroundColor(CPColors.textSecondary)
                                TextField("200", value: $viewModel.newRoomBuyInMax, format: .number)
                                    .textFieldStyle(CPTextFieldStyle())
                                    .keyboardType(.decimalPad)
                            }
                        }

                        // Max Players
                        VStack(alignment: .leading, spacing: CPLayout.space1) {
                            Text("Max Players")
                                .font(CPTypography.label)
                                .foregroundColor(CPColors.textSecondary)

                            Picker("Max Players", selection: $viewModel.newRoomMaxPlayers) {
                                Text("2").tag(2)
                                Text("6").tag(6)
                                Text("9").tag(9)
                            }
                            .pickerStyle(.segmented)
                        }

                        // Visibility
                        VStack(alignment: .leading, spacing: CPLayout.space1) {
                            Text("Visibility")
                                .font(CPTypography.label)
                                .foregroundColor(CPColors.textSecondary)

                            Picker("Visibility", selection: $viewModel.newRoomVisibility) {
                                Text("Public").tag(RoomVisibility.public)
                                Text("Private").tag(RoomVisibility.private)
                            }
                            .pickerStyle(.segmented)
                        }

                        // Create Button
                        Button {
                            HapticManager.action()
                            viewModel.createRoom()
                            isPresented = false
                        } label: {
                            Text("Create Room")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.cpPrimary)
                    }
                    .padding(CPLayout.space4)
                }
            }
            .navigationTitle("Create Room")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { isPresented = false }
                        .foregroundColor(CPColors.textSecondary)
                }
            }
        }
        .preferredColorScheme(.dark)
    }
}
