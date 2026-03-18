import { useCallback, useEffect, useRef, useState } from 'react';
import type { Socket } from 'socket.io-client';
import type {
  ClubRole,
  ClubLeaderboardEntry,
  ClubLeaderboardMetric,
  ClubLeaderboardRange,
  ClubWalletTransaction,
  ClubWalletLedgerPayload,
} from '@cardpilot/shared-types';

export interface ClubSocketActions {
  refresh: () => void;
  createTable: (name: string, templateRulesetId?: string) => void;
  renameTable: (tableId: string, name: string) => void;
  closeTable: (tableId: string) => void;
  joinTable: (tableId: string) => void;
  approveJoin: (userId: string) => void;
  rejectJoin: (userId: string) => void;
  changeRole: (userId: string, newRole: ClubRole) => void;
  kickMember: (userId: string) => void;
  banMember: (userId: string) => void;
  grantCredits: (userId: string, amount: number) => void;
  adjustCredits: (userId: string, amount: number, note?: string) => void;
  refreshCredits: () => void;
  createInvite: () => void;
  revokeInvite: (inviteId: string) => void;
  createRuleset: (payload: unknown) => void;
  setDefaultRuleset: (rulesetId: string) => void;
  updateClub: (payload: {
    name?: string;
    description?: string;
    requireApprovalToJoin?: boolean;
    badgeColor?: string;
  }) => void;
  fetchLeaderboard: (timeRange: ClubLeaderboardRange, metric: ClubLeaderboardMetric) => void;
  fetchTransactions: (offset?: number) => void;
  bulkApprove: (userIds: string[]) => void;
  bulkGrantCredits: (userIds: string[], amount: number) => void;
  bulkRoleChange: (userIds: string[], newRole: ClubRole) => void;
  bulkKick: (userIds: string[]) => void;
}

export interface ClubSocketState {
  creditBalance: number;
  leaderboardRows: ClubLeaderboardEntry[];
  myRank: number | null;
  transactions: ClubWalletTransaction[];
  txLoading: boolean;
  txHasMore: boolean;
}

export function useClubSocket(
  socket: Socket | null,
  clubId: string,
  userId: string,
  onJoinTable: (clubId: string, tableId: string) => void,
  showToast: (msg: string) => void,
  initialBalance: number,
): { actions: ClubSocketActions; state: ClubSocketState } {
  const [creditBalance, setCreditBalance] = useState(initialBalance);
  const [leaderboardRows, setLeaderboardRows] = useState<ClubLeaderboardEntry[]>([]);
  const [myRank, setMyRank] = useState<number | null>(null);
  const [transactions, setTransactions] = useState<ClubWalletTransaction[]>([]);
  const [txLoading, setTxLoading] = useState(false);
  const [txHasMore, setTxHasMore] = useState(true);
  const txPendingOffsetRef = useRef(0);

  // Sync initial balance
  useEffect(() => {
    setCreditBalance(initialBalance);
  }, [initialBalance]);

  // Socket listeners
  useEffect(() => {
    if (!socket) return;

    const onCreditBalance = (payload: {
      balance: { clubId: string; userId: string; balance: number };
    }) => {
      if (payload.balance.clubId !== clubId || payload.balance.userId !== userId) return;
      setCreditBalance(payload.balance.balance);
    };

    const onLeaderboard = (payload: {
      clubId: string;
      entries: ClubLeaderboardEntry[];
      myRank: number | null;
    }) => {
      if (payload.clubId !== clubId) return;
      setLeaderboardRows(payload.entries ?? []);
      setMyRank(payload.myRank ?? null);
    };

    const onWalletTransactions = (payload: ClubWalletLedgerPayload) => {
      if (payload.clubId !== clubId) return;
      const incoming = payload.transactions ?? [];
      const pageLimit = payload.limit || 50;

      // If offset > 0 we are loading more: append to existing list
      if (txPendingOffsetRef.current > 0) {
        setTransactions((prev) => [...prev, ...incoming]);
      } else {
        setTransactions(incoming);
      }

      // If we received fewer items than the page limit, there are no more pages
      setTxHasMore(incoming.length >= pageLimit);
      setTxLoading(false);
    };

    socket.on('club_wallet_balance', onCreditBalance);
    socket.on('club_leaderboard', onLeaderboard);
    socket.on('club_wallet_transactions', onWalletTransactions);
    return () => {
      socket.off('club_wallet_balance', onCreditBalance);
      socket.off('club_leaderboard', onLeaderboard);
      socket.off('club_wallet_transactions', onWalletTransactions);
    };
  }, [socket, clubId, userId]);

  // Actions
  const actions: ClubSocketActions = {
    refresh: useCallback(() => {
      socket?.emit('club_get_detail', { clubId });
      showToast('Refreshing...');
    }, [socket, clubId, showToast]),

    createTable: useCallback(
      (name: string, templateRulesetId?: string) => {
        socket?.emit('club_table_create', {
          clubId,
          name,
          templateRulesetId: templateRulesetId || undefined,
        });
        showToast('Creating table...');
      },
      [socket, clubId, showToast],
    ),

    renameTable: useCallback(
      (tableId: string, name: string) => {
        socket?.emit('club_table_update', { clubId, tableId, name });
        showToast('Updating table...');
      },
      [socket, clubId, showToast],
    ),

    closeTable: useCallback(
      (tableId: string) => {
        socket?.emit('club_table_close', { clubId, tableId });
        showToast('Closing table...');
      },
      [socket, clubId, showToast],
    ),

    joinTable: useCallback(
      (tableId: string) => {
        onJoinTable(clubId, tableId);
      },
      [clubId, onJoinTable],
    ),

    approveJoin: useCallback(
      (targetUserId: string) => {
        socket?.emit('club_join_approve', { clubId, userId: targetUserId, approve: true });
        showToast('Approving...');
      },
      [socket, clubId, showToast],
    ),

    rejectJoin: useCallback(
      (targetUserId: string) => {
        socket?.emit('club_join_reject', { clubId, userId: targetUserId, approve: false });
        showToast('Rejecting...');
      },
      [socket, clubId, showToast],
    ),

    changeRole: useCallback(
      (targetUserId: string, newRole: ClubRole) => {
        socket?.emit('club_member_update_role', { clubId, userId: targetUserId, newRole });
        showToast('Updating role...');
      },
      [socket, clubId, showToast],
    ),

    kickMember: useCallback(
      (targetUserId: string) => {
        socket?.emit('club_member_kick', { clubId, userId: targetUserId });
        showToast('Removing member...');
      },
      [socket, clubId, showToast],
    ),

    banMember: useCallback(
      (targetUserId: string) => {
        socket?.emit('club_member_ban', {
          clubId,
          userId: targetUserId,
          reason: 'Banned by admin',
        });
        showToast('Banning member...');
      },
      [socket, clubId, showToast],
    ),

    grantCredits: useCallback(
      (targetUserId: string, amount: number) => {
        socket?.emit('club_wallet_admin_deposit', {
          clubId,
          userId: targetUserId,
          amount,
          note: 'Admin credit grant',
        });
        showToast('Granting credits...');
      },
      [socket, clubId, showToast],
    ),

    adjustCredits: useCallback(
      (targetUserId: string, amount: number, note?: string) => {
        socket?.emit('club_wallet_admin_adjust', {
          clubId,
          userId: targetUserId,
          amount,
          note: note ?? 'Admin credit adjustment',
        });
        showToast('Adjusting credits...');
      },
      [socket, clubId, showToast],
    ),

    refreshCredits: useCallback(() => {
      socket?.emit('club_wallet_balance_get', { clubId });
      showToast('Refreshing credits...');
    }, [socket, clubId, showToast]),

    createInvite: useCallback(() => {
      socket?.emit('club_invite_create', { clubId, maxUses: 50, expiresInHours: 168 });
      showToast('Creating invite link...');
    }, [socket, clubId, showToast]),

    revokeInvite: useCallback(
      (inviteId: string) => {
        socket?.emit('club_invite_revoke', { clubId, inviteId });
        showToast('Revoking invite...');
      },
      [socket, clubId, showToast],
    ),

    createRuleset: useCallback(
      (payload: unknown) => {
        socket?.emit('club_ruleset_create', payload);
        showToast('Creating ruleset...');
      },
      [socket, showToast],
    ),

    setDefaultRuleset: useCallback(
      (rulesetId: string) => {
        socket?.emit('club_ruleset_set_default', { clubId, rulesetId });
        showToast('Updating default ruleset...');
      },
      [socket, clubId, showToast],
    ),

    updateClub: useCallback(
      (payload) => {
        socket?.emit('club_update', { clubId, ...payload });
        showToast('Saving settings...');
      },
      [socket, clubId, showToast],
    ),

    fetchLeaderboard: useCallback(
      (timeRange: ClubLeaderboardRange, metric: ClubLeaderboardMetric) => {
        socket?.emit('club_leaderboard_get', { clubId, timeRange, metric, limit: 50 });
      },
      [socket, clubId],
    ),

    fetchTransactions: useCallback(
      (offset?: number) => {
        const off = offset ?? 0;
        txPendingOffsetRef.current = off;
        if (off === 0) {
          setTxHasMore(true);
        }
        setTxLoading(true);
        socket?.emit('club_wallet_transactions_list', { clubId, limit: 50, offset: off });
      },
      [socket, clubId],
    ),

    bulkApprove: useCallback(
      (userIds: string[]) => {
        for (const uid of userIds) {
          socket?.emit('club_join_approve', { clubId, userId: uid, approve: true });
        }
        showToast(`Approving ${userIds.length} member(s)...`);
      },
      [socket, clubId, showToast],
    ),

    bulkGrantCredits: useCallback(
      (userIds: string[], amount: number) => {
        for (const uid of userIds) {
          socket?.emit('club_wallet_admin_deposit', {
            clubId,
            userId: uid,
            amount,
            note: 'Bulk admin credit grant',
          });
        }
        showToast(`Granting credits to ${userIds.length} member(s)...`);
      },
      [socket, clubId, showToast],
    ),

    bulkRoleChange: useCallback(
      (userIds: string[], newRole: ClubRole) => {
        for (const uid of userIds) {
          socket?.emit('club_member_update_role', { clubId, userId: uid, newRole });
        }
        showToast(`Updating role for ${userIds.length} member(s)...`);
      },
      [socket, clubId, showToast],
    ),

    bulkKick: useCallback(
      (userIds: string[]) => {
        for (const uid of userIds) {
          socket?.emit('club_member_kick', { clubId, userId: uid });
        }
        showToast(`Removing ${userIds.length} member(s)...`);
      },
      [socket, clubId, showToast],
    ),
  };

  return {
    actions,
    state: { creditBalance, leaderboardRows, myRank, transactions, txLoading, txHasMore },
  };
}
