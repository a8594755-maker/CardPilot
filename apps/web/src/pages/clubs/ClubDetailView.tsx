import { useState, useCallback, useMemo, lazy, Suspense } from 'react';
import type { Socket } from 'socket.io-client';
import type { ClubDetailPayload } from '@cardpilot/shared-types';
import { useIsMobile } from '../../hooks/useIsMobile';
import { useClubPermissions } from './hooks/useClubPermissions';
import { useClubTab, buildVisibleTabs } from './hooks/useClubTab';
import { useClubSocket } from './hooks/useClubSocket';
import { useChat } from './hooks/useChat';
import { useAnalytics } from './hooks/useAnalytics';
import { ClubAvatar } from './shared/ClubAvatar';
import { RoleBadge } from './shared/RoleBadge';
import { TabSkeleton } from './shared/SkeletonRow';
import { ConfirmActionModal } from './modals/ConfirmActionModal';
import { GrantCreditsModal } from './modals/GrantCreditsModal';
import { AdjustCreditsModal } from './modals/AdjustCreditsModal';
import { RenameTableModal } from './modals/RenameTableModal';

// Lazy-loaded tabs
const OverviewTab = lazy(() => import('./tabs/OverviewTab'));
const TablesTab = lazy(() => import('./tabs/TablesTab'));
const MembersTab = lazy(() => import('./tabs/MembersTab'));
const CreditsTab = lazy(() => import('./tabs/CreditsTab'));
const TransactionsTab = lazy(() => import('./tabs/TransactionsTab'));
const LeaderboardTab = lazy(() => import('./tabs/LeaderboardTab'));
const RulesetsTab = lazy(() => import('./tabs/RulesetsTab'));
const InvitesTab = lazy(() => import('./tabs/InvitesTab'));
const AuditTab = lazy(() => import('./tabs/AuditTab'));
const SettingsTab = lazy(() => import('./tabs/SettingsTab'));
const ChatTab = lazy(() => import('./tabs/ChatTab'));
const AnalyticsTab = lazy(() => import('./tabs/AnalyticsTab'));

interface ClubDetailViewProps {
  socket: Socket | null;
  isConnected: boolean;
  userId: string;
  detail: ClubDetailPayload;
  onBack: () => void;
  onJoinTable: (clubId: string, tableId: string) => void;
  showToast: (msg: string) => void;
}

// ── Modal state ──
interface ModalState {
  type: 'confirm' | 'grant' | 'adjust' | 'rename' | null;
  title?: string;
  message?: string;
  confirmLabel?: string;
  onConfirm?: () => void;
  preselectedUserId?: string;
  preselectedDisplayName?: string;
  tableId?: string;
  currentName?: string;
}

const ONLINE_THRESHOLD_MIN = 15;
function isRecentlyOnline(lastSeenAt: string): boolean {
  return Date.now() - new Date(lastSeenAt).getTime() < ONLINE_THRESHOLD_MIN * 60 * 1000;
}

export function ClubDetailView({
  socket,
  isConnected: _isConnected,
  userId,
  detail,
  onBack,
  onJoinTable,
  showToast,
}: ClubDetailViewProps) {
  const { club, myMembership } = detail.detail;
  const isMobile = useIsMobile();
  const permissions = useClubPermissions(myMembership?.role);
  const [tab, setTab] = useClubTab(club.id, permissions);
  const { actions, state } = useClubSocket(
    socket,
    club.id,
    userId,
    onJoinTable,
    showToast,
    myMembership?.balance ?? 0,
  );
  const { actions: chatActions, state: chatState } = useChat(socket, club.id, userId);
  const { actions: analyticsActions, state: analyticsState } = useAnalytics(
    socket,
    club.id,
    userId,
  );

  const [modal, setModal] = useState<ModalState>({ type: null });
  const closeModal = useCallback(() => setModal({ type: null }), []);

  const onlineCount = useMemo(
    () => detail.members.filter((m) => isRecentlyOnline(m.lastSeenAt)).length,
    [detail.members],
  );

  const visibleTabs = useMemo(
    () => buildVisibleTabs(permissions, detail.members.length, detail.tables.length),
    [permissions, detail.members.length, detail.tables.length],
  );

  // ── Modal openers ──
  const openRenameTable = useCallback((tableId: string, currentName: string) => {
    setModal({ type: 'rename', tableId, currentName });
  }, []);

  const openCloseTable = useCallback(
    (tableId: string, tableName: string) => {
      setModal({
        type: 'confirm',
        title: 'Close Table',
        message: `Close table "${tableName}"? This cannot be undone.`,
        confirmLabel: 'Close Table',
        onConfirm: () => {
          actions.closeTable(tableId);
          closeModal();
        },
      });
    },
    [actions, closeModal],
  );

  const openKickMember = useCallback(
    (targetUserId: string, displayName: string) => {
      setModal({
        type: 'confirm',
        title: 'Remove Member',
        message: `Remove ${displayName} from the club?`,
        confirmLabel: 'Remove',
        onConfirm: () => {
          actions.kickMember(targetUserId);
          closeModal();
        },
      });
    },
    [actions, closeModal],
  );

  const openBanMember = useCallback(
    (targetUserId: string, displayName: string) => {
      setModal({
        type: 'confirm',
        title: 'Ban Member',
        message: `Ban ${displayName} from the club? They will not be able to rejoin.`,
        confirmLabel: 'Ban',
        onConfirm: () => {
          actions.banMember(targetUserId);
          closeModal();
        },
      });
    },
    [actions, closeModal],
  );

  const openGrantCredits = useCallback((preUserId?: string, preDisplayName?: string) => {
    setModal({
      type: 'grant',
      preselectedUserId: preUserId,
      preselectedDisplayName: preDisplayName,
    });
  }, []);

  const openAdjustCredits = useCallback(() => {
    setModal({ type: 'adjust' });
  }, []);

  const copyToClipboard = useCallback(
    (text: string, label: string) => {
      void navigator.clipboard.writeText(text);
      showToast(`Copied ${label}: ${text}`);
    },
    [showToast],
  );

  // ── Tab content renderer ──
  const renderTab = () => {
    switch (tab) {
      case 'overview':
        return (
          <OverviewTab
            club={club}
            detail={detail.detail}
            members={detail.members}
            tables={detail.tables}
            auditLog={detail.auditLog}
            permissions={permissions}
            actions={actions}
            onSwitchTab={setTab as (tab: string) => void}
          />
        );
      case 'tables':
        return (
          <TablesTab
            club={club}
            tables={detail.tables}
            rulesets={detail.rulesets}
            permissions={permissions}
            actions={actions}
            onRenameTable={openRenameTable}
            onCloseTable={openCloseTable}
          />
        );
      case 'members':
        return (
          <MembersTab
            club={club}
            members={detail.members}
            userId={userId}
            permissions={permissions}
            actions={actions}
            onGrantCredits={openGrantCredits}
            onKickMember={openKickMember}
            onBanMember={openBanMember}
          />
        );
      case 'credits':
        return (
          <CreditsTab
            creditBalance={state.creditBalance}
            permissions={permissions}
            actions={actions}
            onGrantCredits={() => openGrantCredits()}
            onAdjustCredits={openAdjustCredits}
          />
        );
      case 'transactions':
        return (
          <TransactionsTab
            transactions={state.transactions}
            txLoading={state.txLoading}
            txHasMore={state.txHasMore}
            actions={actions}
          />
        );
      case 'leaderboard':
        return (
          <LeaderboardTab
            clubId={club.id}
            leaderboardRows={state.leaderboardRows}
            myRank={state.myRank}
            actions={actions}
          />
        );
      case 'rulesets':
        return (
          <RulesetsTab
            club={club}
            rulesets={detail.rulesets}
            defaultRuleset={detail.detail.defaultRuleset}
            permissions={permissions}
            actions={actions}
            showToast={showToast}
          />
        );
      case 'invites':
        return <InvitesTab invites={detail.invites} actions={actions} showToast={showToast} />;
      case 'audit':
        return <AuditTab auditLog={detail.auditLog} />;
      case 'settings':
        return (
          <SettingsTab
            club={club}
            permissions={permissions}
            actions={actions}
            showToast={showToast}
          />
        );
      case 'chat':
        return (
          <ChatTab
            chatActions={chatActions}
            chatState={chatState}
            permissions={permissions}
            members={detail.members}
            currentUserId={userId}
            currentDisplayName={myMembership?.displayName ?? 'You'}
          />
        );
      case 'analytics':
        return (
          <AnalyticsTab
            analyticsActions={analyticsActions}
            analyticsState={analyticsState}
            isAdmin={permissions.role === 'owner' || permissions.role === 'admin'}
          />
        );
      case 'admin':
        return (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="text-4xl mb-3 opacity-30">🚧</div>
            <h3 className="text-sm font-semibold text-slate-300 mb-1">Coming Soon</h3>
            <p className="text-xs text-slate-500 max-w-xs">This feature is under development.</p>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <main className="flex-1 overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-4xl space-y-4 sm:space-y-6">
        {/* ── Header ── */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-4 shadow-inner shadow-black/20 sm:p-5">
          {isMobile && (
            <div className="mb-4 flex items-center justify-between">
              <button
                onClick={onBack}
                className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors hover:text-white sm:text-sm"
              >
                <span aria-hidden="true">←</span>
                <span>Back</span>
              </button>
              <button
                onClick={actions.refresh}
                className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-slate-300 transition-colors hover:bg-white/10 sm:text-xs"
              >
                <span aria-hidden="true">↻</span> Refresh
              </button>
            </div>
          )}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-5">
            {!isMobile && (
              <button
                onClick={onBack}
                className="inline-flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors hover:text-white sm:text-sm"
              >
                <span aria-hidden="true">←</span>
                <span>Back</span>
              </button>
            )}
            <div className="flex items-center gap-3 sm:gap-4">
              <ClubAvatar name={club.name} color={club.badgeColor} />
              <div className="flex-1 space-y-1">
                <h2 className="text-lg font-bold text-white sm:text-xl">{club.name}</h2>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 sm:gap-3">
                  <span>
                    Code: <code className="font-mono text-amber-400">{club.code}</code>
                  </span>
                  <span>{detail.detail.memberCount} members</span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    {onlineCount} online
                  </span>
                  <RoleBadge role={permissions.role} size="xs" />
                </div>
              </div>
            </div>
            {!isMobile && (
              <button
                onClick={actions.refresh}
                className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold text-slate-300 transition-colors hover:bg-white/10 sm:text-xs"
              >
                <span aria-hidden="true">↻</span> Refresh
              </button>
            )}
          </div>
          {isMobile && (
            <div className="mt-4 grid grid-cols-2 gap-3 text-[11px] text-slate-300">
              <button
                className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-left font-semibold text-amber-200"
                onClick={() => copyToClipboard(club.code, 'club code')}
              >
                Share Code
                <div className="text-[10px] font-mono text-amber-400">{club.code}</div>
              </button>
              <div className="rounded-xl border border-white/10 bg-white/5 p-3">
                <div className="text-[10px] uppercase tracking-wide text-slate-500">Status</div>
                <div className="text-sm font-semibold text-white">
                  {onlineCount} online / {detail.detail.memberCount}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Pending Join Requests Banner ── */}
        {permissions.canApproveJoins && detail.pendingMembers.length > 0 && (
          <div className="glass-card p-3 bg-amber-500/10 border-amber-500/30 animate-pulse">
            <div className="text-sm font-semibold text-amber-400 mb-2">
              🎫 {detail.pendingMembers.length} pending join request
              {detail.pendingMembers.length > 1 ? 's' : ''}
            </div>
            <div className="space-y-2">
              {detail.pendingMembers.map((m) => (
                <div
                  key={m.userId}
                  className="flex flex-col gap-3 rounded-lg bg-black/20 p-3 text-sm sm:flex-row sm:items-center"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-[11px] font-bold uppercase text-white">
                      {((m.displayName ?? '').trim().charAt(0) || 'U').toUpperCase()}
                    </div>
                    <div>
                      <span className="block text-white">
                        {m.displayName ?? m.userId.slice(0, 8)}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Last seen {new Date(m.lastSeenAt).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <div className="flex w-full gap-2 sm:w-auto">
                    <button
                      onClick={() => actions.approveJoin(m.userId)}
                      className="flex-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-center text-[11px] font-semibold text-emerald-300 hover:bg-emerald-500/20"
                    >
                      ✓ Approve
                    </button>
                    <button
                      onClick={() => actions.rejectJoin(m.userId)}
                      className="flex-1 rounded border border-red-500/40 bg-red-500/10 px-3 py-1 text-center text-[11px] font-semibold text-red-300 hover:bg-red-500/20"
                    >
                      ✗ Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Tab Navigation ── */}
        <nav
          className="sticky top-0 z-10 flex gap-1 overflow-x-auto rounded-2xl bg-white/5/80 p-1 shadow-inner shadow-black/20 backdrop-blur-sm sm:static sm:bg-white/5 sm:shadow-none"
          style={{ WebkitOverflowScrolling: 'touch' }}
        >
          {visibleTabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-all sm:px-4 sm:text-sm ${
                tab === t.id
                  ? 'bg-white/10 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {/* ── Tab Content ── */}
        <div className="glass-card rounded-2xl p-4 sm:p-5">
          <Suspense fallback={<TabSkeleton rows={5} />}>{renderTab()}</Suspense>
        </div>
      </div>

      {/* ── Modals ── */}
      <ConfirmActionModal
        isOpen={modal.type === 'confirm'}
        title={modal.title ?? ''}
        message={modal.message ?? ''}
        confirmLabel={modal.confirmLabel}
        onConfirm={modal.onConfirm ?? closeModal}
        onCancel={closeModal}
      />
      <GrantCreditsModal
        isOpen={modal.type === 'grant'}
        members={detail.members}
        preselectedUserId={modal.preselectedUserId}
        preselectedDisplayName={modal.preselectedDisplayName}
        onSubmit={(uid, amount, _note) => {
          actions.grantCredits(uid, amount);
          closeModal();
        }}
        onClose={closeModal}
      />
      <AdjustCreditsModal
        isOpen={modal.type === 'adjust'}
        members={detail.members}
        onSubmit={(uid, amount, note) => {
          actions.adjustCredits(uid, amount, note);
          closeModal();
        }}
        onClose={closeModal}
      />
      <RenameTableModal
        isOpen={modal.type === 'rename'}
        currentName={modal.currentName ?? ''}
        onSubmit={(newName) => {
          if (modal.tableId) actions.renameTable(modal.tableId, newName);
          closeModal();
        }}
        onClose={closeModal}
      />
    </main>
  );
}
