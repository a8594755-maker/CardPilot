import SwiftUI

// MARK: - Training View Model

@Observable
final class TrainingViewModel {
    var handAudits: [HandAuditSummary] = []
    var sessionLeak: SessionLeakSummary?
    var hasData = false
    var selectedHandId: String?
    var selectedAudit: HandAuditSummary?

    private let socket = CPSocketManager.shared
    private let userId: String?

    init(router: SocketEventRouter, userId: String? = nil) {
        self.userId = userId
        // Filter by userId to only show current user's audits (mirrors useAuditEvents.ts)
        router.on("hand_audit_complete", type: HandAuditCompletePayload.self) { [weak self] payload in
            guard let self else { return }
            if let uid = self.userId, payload.userId != uid { return }
            self.handAudits.insert(payload.summary, at: 0)
            if self.handAudits.count > 50 { self.handAudits = Array(self.handAudits.prefix(50)) }
            self.hasData = true
        }
        router.on("session_leak_update", type: SessionLeakUpdatePayload.self) { [weak self] payload in
            guard let self else { return }
            if let uid = self.userId, payload.userId != uid { return }
            self.sessionLeak = payload.summary
            self.hasData = true
        }
    }
}

struct HandAuditCompletePayload: Codable {
    let userId: String
    let summary: HandAuditSummary
}

struct SessionLeakUpdatePayload: Codable {
    let userId: String
    let summary: SessionLeakSummary
}

// MARK: - Training Dashboard View

struct TrainingDashboardView: View {
    @Bindable var viewModel: TrainingViewModel

    var body: some View {
        ZStack {
            CPColors.bgBase.ignoresSafeArea()

            if !viewModel.hasData {
                emptyState
            } else {
                ScrollView {
                    VStack(spacing: CPLayout.space4) {
                        // Session Summary
                        if let leak = viewModel.sessionLeak {
                            sessionSummaryCard(leak)
                        }

                        // Street Breakdown
                        if let leak = viewModel.sessionLeak {
                            streetBreakdownCard(leak)
                        }

                        // Deviation Breakdown
                        if let leak = viewModel.sessionLeak {
                            deviationBreakdownCard(leak)
                        }

                        // Top Leaks
                        if let leaks = viewModel.sessionLeak?.topLeaks, !leaks.isEmpty {
                            topLeaksCard(leaks)
                        }

                        // Hand Audit List
                        if !viewModel.handAudits.isEmpty {
                            handAuditList
                        }
                    }
                    .padding(CPLayout.space4)
                }
            }
        }
        .navigationTitle("Training")
        .sheet(item: $viewModel.selectedAudit) { audit in
            HandAuditDetailSheet(audit: audit)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: CPLayout.space4) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 48))
                .foregroundColor(CPColors.textMuted)
            Text("GTO Coach Mode")
                .font(CPTypography.heading)
                .foregroundColor(CPColors.textPrimary)
            Text("Play hands in Coach mode to get real-time GTO analysis.\nYour leaks and deviations will appear here.")
                .font(CPTypography.body)
                .foregroundColor(CPColors.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, CPLayout.space8)
        }
    }

    // MARK: - Session Summary

    private func sessionSummaryCard(_ leak: SessionLeakSummary) -> some View {
        CPCard {
            VStack(spacing: CPLayout.space3) {
                Text("Session Summary")
                    .font(CPTypography.heading)
                    .foregroundColor(CPColors.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: CPLayout.space3) {
                    statCell("Leaked BB", value: String(format: "%.1f", leak.totalLeakedBb),
                             color: leak.totalLeakedBb < -1 ? CPColors.danger : CPColors.success)
                    statCell("BB/100", value: String(format: "%.1f", leak.leakedBbPer100),
                             color: leak.leakedBbPer100 < -1 ? CPColors.danger : CPColors.success)
                    statCell("Audited", value: "\(leak.handsAudited)/\(leak.handsPlayed)", color: CPColors.textSecondary)
                    let totalDecisions = viewModel.handAudits.reduce(0) { $0 + $1.decisionCount }
                    statCell("Decisions", value: "\(totalDecisions)", color: CPColors.textSecondary)
                }
            }
        }
    }

    // MARK: - Street Breakdown

    private func streetBreakdownCard(_ leak: SessionLeakSummary) -> some View {
        CPCard {
            VStack(alignment: .leading, spacing: CPLayout.space2) {
                Text("Leak by Street")
                    .font(CPTypography.label)
                    .foregroundColor(CPColors.textSecondary)

                ForEach(["PREFLOP", "FLOP", "TURN", "RIVER"], id: \.self) { street in
                    if let bucket = leak.byStreet[street] {
                        HStack {
                            Text(street.prefix(3))
                                .font(CPTypography.monoSmall)
                                .foregroundColor(CPColors.textMuted)
                                .frame(width: 36, alignment: .leading)

                            GeometryReader { geo in
                                let maxBb = max(abs(leak.totalLeakedBb), 1)
                                let width = min(abs(bucket.leakedBb) / maxBb, 1.0) * geo.size.width
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(bucket.leakedBb < 0 ? CPColors.danger : CPColors.success)
                                    .frame(width: max(width, 2), height: 16)
                            }
                            .frame(height: 16)

                            Text(String(format: "%.1f", bucket.leakedBb))
                                .font(CPTypography.monoSmall)
                                .foregroundColor(bucket.leakedBb < 0 ? CPColors.danger : CPColors.success)
                                .frame(width: 44, alignment: .trailing)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Deviation Breakdown

    private func deviationBreakdownCard(_ leak: SessionLeakSummary) -> some View {
        CPCard {
            VStack(alignment: .leading, spacing: CPLayout.space2) {
                Text("Deviation Types")
                    .font(CPTypography.label)
                    .foregroundColor(CPColors.textSecondary)

                let types = ["OVERFOLD", "UNDERFOLD", "OVERBLUFF", "UNDERBLUFF", "OVERCALL", "UNDERCALL"]
                FlowLayout(spacing: 6) {
                    ForEach(types, id: \.self) { type in
                        if let bucket = leak.byDeviation[type], bucket.count > 0 {
                            HStack(spacing: 4) {
                                Text(type.replacingOccurrences(of: "OVER", with: "Over-")
                                          .replacingOccurrences(of: "UNDER", with: "Under-"))
                                    .font(.system(size: 10, weight: .semibold))
                                Text("\(bucket.count)")
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                            }
                            .foregroundColor(CPColors.textPrimary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(CPColors.bgElevated)
                            .cornerRadius(CPLayout.radiusFull)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Top Leaks

    private func topLeaksCard(_ leaks: [LeakCategory]) -> some View {
        CPCard {
            VStack(alignment: .leading, spacing: CPLayout.space2) {
                Text("Top Leaks")
                    .font(CPTypography.label)
                    .foregroundColor(CPColors.textSecondary)

                ForEach(leaks) { leak in
                    HStack {
                        Text("#\(leak.rank)")
                            .font(CPTypography.captionBold)
                            .foregroundColor(CPColors.gold)
                            .frame(width: 24)

                        VStack(alignment: .leading, spacing: 2) {
                            Text(leak.label)
                                .font(CPTypography.bodySemibold)
                                .foregroundColor(CPColors.textPrimary)
                            Text(leak.description)
                                .font(CPTypography.caption)
                                .foregroundColor(CPColors.textMuted)
                                .lineLimit(1)
                        }

                        Spacer()

                        Text(String(format: "%.1f BB", leak.leakedBb))
                            .font(CPTypography.monoSmall)
                            .foregroundColor(CPColors.danger)
                    }
                }
            }
        }
    }

    // MARK: - Hand Audit List

    private var handAuditList: some View {
        CPCard {
            VStack(alignment: .leading, spacing: CPLayout.space2) {
                Text("Audited Hands")
                    .font(CPTypography.label)
                    .foregroundColor(CPColors.textSecondary)

                ForEach(viewModel.handAudits) { audit in
                    Button {
                        viewModel.selectedHandId = audit.handId
                        viewModel.selectedAudit = audit
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Hand \(audit.handId.prefix(8))...")
                                    .font(CPTypography.body)
                                    .foregroundColor(CPColors.textPrimary)
                                Text("\(audit.decisionCount) decisions")
                                    .font(CPTypography.caption)
                                    .foregroundColor(CPColors.textMuted)
                            }

                            Spacer()

                            Text(String(format: "%.1f BB", audit.totalLeakedBb))
                                .font(CPTypography.mono)
                                .foregroundColor(audit.totalLeakedBb < -0.1 ? CPColors.danger : CPColors.success)
                        }
                        .padding(.vertical, 4)
                    }

                    if audit.id != viewModel.handAudits.last?.id {
                        Divider().background(CPColors.borderSubtle)
                    }
                }
            }
        }
    }

    // MARK: - Stat Cell

    private func statCell(_ label: String, value: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(CPTypography.mono)
                .foregroundColor(color)
            Text(label)
                .font(CPTypography.caption)
                .foregroundColor(CPColors.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, CPLayout.space2)
        .background(CPColors.bgBase)
        .cornerRadius(CPLayout.radiusSm)
    }
}

// MARK: - Hand Audit Detail Sheet (per-decision GTO mix bars)

struct HandAuditDetailSheet: View {
    let audit: HandAuditSummary

    var body: some View {
        NavigationStack {
            ZStack {
                CPColors.bgBase.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: CPLayout.space4) {
                        // Header
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Hand \(audit.handId.prefix(12))...")
                                    .font(CPTypography.heading)
                                    .foregroundColor(CPColors.textPrimary)
                                HStack(spacing: CPLayout.space3) {
                                    Text("\(audit.decisionCount) decisions")
                                        .font(CPTypography.label)
                                        .foregroundColor(CPColors.textSecondary)
                                    Text(String(format: "%.1f BB leaked", audit.totalLeakedBb))
                                        .font(CPTypography.mono)
                                        .foregroundColor(audit.totalLeakedBb < -0.1 ? CPColors.danger : CPColors.success)
                                }
                            }
                            Spacer()
                        }

                        // Per-decision audit rows
                        ForEach(audit.audits) { result in
                            CPCard {
                                VStack(alignment: .leading, spacing: CPLayout.space2) {
                                    // Street + position
                                    HStack {
                                        Text(result.street)
                                            .font(CPTypography.captionBold)
                                            .foregroundColor(CPColors.gold)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(CPColors.gold.opacity(0.15))
                                            .cornerRadius(3)

                                        if let pos = result.heroPosition {
                                            Text(pos)
                                                .font(CPTypography.caption)
                                                .foregroundColor(CPColors.textMuted)
                                        }

                                        Spacer()

                                        // Deviation score
                                        Text(String(format: "%.0f%% dev", result.deviationScore * 100))
                                            .font(CPTypography.monoSmall)
                                            .foregroundColor(result.deviationScore > 0.15 ? CPColors.danger : CPColors.success)
                                    }

                                    // Action comparison
                                    HStack(spacing: CPLayout.space3) {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text("Your action")
                                                .font(.system(size: 9))
                                                .foregroundColor(CPColors.textMuted)
                                            Text(result.actualAction.uppercased())
                                                .font(CPTypography.bodySemibold)
                                                .foregroundColor(CPColors.textPrimary)
                                        }

                                        Image(systemName: "arrow.right")
                                            .font(.system(size: 12))
                                            .foregroundColor(CPColors.textMuted)

                                        VStack(alignment: .leading, spacing: 2) {
                                            Text("GTO recommends")
                                                .font(.system(size: 9))
                                                .foregroundColor(CPColors.textMuted)
                                            Text(result.recommendedAction.uppercased())
                                                .font(CPTypography.bodySemibold)
                                                .foregroundColor(CPColors.accent)
                                        }

                                        Spacer()

                                        // EV diff
                                        VStack(alignment: .trailing, spacing: 2) {
                                            Text("EV diff")
                                                .font(.system(size: 9))
                                                .foregroundColor(CPColors.textMuted)
                                            Text(String(format: "%.2f BB", result.evDiffBb))
                                                .font(CPTypography.mono)
                                                .foregroundColor(result.evDiffBb < -0.1 ? CPColors.danger : CPColors.success)
                                        }
                                    }

                                    // GTO Mix Bar
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("GTO Mix")
                                            .font(.system(size: 9))
                                            .foregroundColor(CPColors.textMuted)

                                        GeometryReader { geo in
                                            let total = result.gtoMix.raise + result.gtoMix.call + result.gtoMix.fold
                                            let rW = total > 0 ? (result.gtoMix.raise / total) * geo.size.width : 0
                                            let cW = total > 0 ? (result.gtoMix.call / total) * geo.size.width : 0
                                            let fW = total > 0 ? (result.gtoMix.fold / total) * geo.size.width : 0

                                            HStack(spacing: 0) {
                                                if rW > 0 {
                                                    Rectangle().fill(CPColors.raiseColor)
                                                        .frame(width: rW, height: 16)
                                                }
                                                if cW > 0 {
                                                    Rectangle().fill(CPColors.callColor)
                                                        .frame(width: cW, height: 16)
                                                }
                                                if fW > 0 {
                                                    Rectangle().fill(CPColors.foldColor)
                                                        .frame(width: fW, height: 16)
                                                }
                                            }
                                            .cornerRadius(4)
                                        }
                                        .frame(height: 16)

                                        // Mix percentages
                                        HStack(spacing: CPLayout.space3) {
                                            mixLabel("R", pct: result.gtoMix.raise, color: CPColors.raiseColor)
                                            mixLabel("C", pct: result.gtoMix.call, color: CPColors.callColor)
                                            mixLabel("F", pct: result.gtoMix.fold, color: CPColors.foldColor)
                                        }
                                    }

                                    // Deviation type badge
                                    HStack {
                                        Text(result.deviationType.rawValue.replacingOccurrences(of: "OVER", with: "Over-")
                                                .replacingOccurrences(of: "UNDER", with: "Under-"))
                                            .font(.system(size: 10, weight: .semibold))
                                            .foregroundColor(result.deviationType == .correct ? CPColors.success : CPColors.warning)
                                            .padding(.horizontal, 8)
                                            .padding(.vertical, 3)
                                            .background((result.deviationType == .correct ? CPColors.success : CPColors.warning).opacity(0.15))
                                            .cornerRadius(CPLayout.radiusFull)
                                        Spacer()
                                    }
                                }
                            }
                        }
                    }
                    .padding(CPLayout.space4)
                }
            }
            .navigationTitle("Hand Audit")
            .navigationBarTitleDisplayMode(.inline)
        }
        .preferredColorScheme(.dark)
    }

    private func mixLabel(_ label: String, pct: Double, color: Color) -> some View {
        HStack(spacing: 2) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text("\(label) \(Int(pct))%")
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundColor(CPColors.textMuted)
        }
    }
}

// MARK: - Flow Layout (for pills)

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrange(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(proposal: proposal, subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return (CGSize(width: maxWidth, height: y + rowHeight), positions)
    }
}
