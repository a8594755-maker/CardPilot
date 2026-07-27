import { useEffect, type Dispatch, type SetStateAction, type MutableRefObject } from 'react';
import type { Socket } from 'socket.io-client';
import type {
  TableState,
  RoomFullState,
  AdvicePayload,
  SettlementResult,
  SevenTwoBountyInfo,
} from '@cardpilot/shared-types';
import { playUiSfxTone } from '../lib/audio';
import { haptic } from '../lib/haptic';
import type { PreAction } from '../lib/action-derivations';
import { saveHand, autoTag, type HandActionRecord } from '../lib/hand-history';

// Define state types for complex objects to ensure safety
type AllInLockState = {
  handId: string;
  eligiblePlayers: Array<{ seat: number; name: string }>;
  maxRunCountAllowed: 3;
  submittedPlayerIds: number[];
  underdogSeat: number | null;
  targetRunCount: 1 | 2 | 3 | null;
  equities?: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
} | null;

type BoardRevealState = {
  street: string;
  equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
  hints?: Array<{ seat: number; label: string }>;
} | null;

type PostHandRevealedCardsState = Record<number, [string, string]>;
type LastActionBySeatState = Record<number, { action: string; amount: number }>;

export interface UseGameSocketEventsProps {
  socket: Socket | null;
  tableId: string | null;
  authUserId?: string;
  showToast: (msg: string) => void;

  // State Setters using Dispatch<SetStateAction<T>>
  setSnapshot: Dispatch<SetStateAction<TableState | null>>;
  setRoomState: Dispatch<SetStateAction<RoomFullState | null>>;
  setSeat: Dispatch<SetStateAction<number>>;
  setHoleCards: Dispatch<SetStateAction<string[]>>;
  setAdvice: Dispatch<SetStateAction<AdvicePayload | null>>;
  setDeviation: Dispatch<SetStateAction<{ deviation: number; playerAction: string } | null>>;
  setActionPending: Dispatch<SetStateAction<boolean>>;
  setWinners: Dispatch<
    SetStateAction<Array<{ seat: number; amount: number; handName?: string }> | null>
  >;
  setSettlement: Dispatch<SetStateAction<SettlementResult | null>>;
  setAllInLock: Dispatch<SetStateAction<AllInLockState>>;
  setMyRunPreference: Dispatch<SetStateAction<1 | 2 | 3 | null>>;
  setBoardReveal: Dispatch<SetStateAction<BoardRevealState>>;
  setLastActionBySeat: Dispatch<SetStateAction<LastActionBySeatState>>;
  setPostHandShowAvailable: Dispatch<SetStateAction<boolean>>;
  setSevenTwoBountyPrompt: Dispatch<
    SetStateAction<{ bountyPerPlayer: number; totalBounty: number } | null>
  >;
  setSevenTwoBountyResult: Dispatch<SetStateAction<SevenTwoBountyInfo | null>>;
  setSevenTwoRevealActive: Dispatch<SetStateAction<SevenTwoBountyInfo | null>>;
  setPostHandRevealedCards: Dispatch<SetStateAction<PostHandRevealedCardsState>>;
  setBombPotOverlayActive: Dispatch<SetStateAction<{ anteAmount: number } | null>>;
  setPreAction: Dispatch<SetStateAction<PreAction | null>>;
  onTimerUpdate: (t: any) => void;

  // Refs
  snapshotRef: MutableRefObject<TableState | null>;
  seatRef: MutableRefObject<number>;
  holeCardsRef: MutableRefObject<string[]>;
  latestSnapshotVersionRef: MutableRefObject<number>;
  currentRoomCodeRef: MutableRefObject<string>;
  currentRoomNameRef: MutableRefObject<string>;
}

export function useGameSocketEvents({
  socket,
  tableId,
  authUserId,
  showToast,
  setSnapshot,
  setRoomState,
  setSeat,
  setHoleCards,
  setAdvice,
  setDeviation,
  setActionPending,
  setWinners,
  setSettlement,
  setAllInLock,
  setMyRunPreference,
  setBoardReveal,
  setLastActionBySeat,
  setPostHandShowAvailable,
  setSevenTwoBountyPrompt,
  setSevenTwoBountyResult,
  setSevenTwoRevealActive,
  setPostHandRevealedCards,
  setBombPotOverlayActive: _setBombPotOverlayActive,
  setPreAction,
  onTimerUpdate,
  snapshotRef,
  seatRef,
  holeCardsRef,
  latestSnapshotVersionRef,
  currentRoomCodeRef,
  currentRoomNameRef,
}: UseGameSocketEventsProps) {
  const playUiSfx = (kind: any) => {
    try {
      const muted = localStorage.getItem('cardpilot_sound_muted') === 'true';
      playUiSfxTone(kind, muted);
    } catch {
      playUiSfxTone(kind, false);
    }
  };

  useEffect(() => {
    if (!socket) return;

    const applyAuthoritativeSnapshot = (
      d: TableState,
      _source: 'table_snapshot' | 'hand_ended',
    ): boolean => {
      if (!d) return false;
      const activeTableId = (tableId ?? '').trim();
      if (!activeTableId || d.tableId !== activeTableId) {
        return false;
      }

      const incomingVersion = Number.isFinite(d.stateVersion) ? d.stateVersion : 0;
      const currentVersion = latestSnapshotVersionRef.current;

      if (incomingVersion < currentVersion) {
        if (d.tableId?.startsWith('fb_') && d.players && d.players.length > 0) {
          latestSnapshotVersionRef.current = incomingVersion;
        } else {
          return false;
        }
      }

      latestSnapshotVersionRef.current = incomingVersion;
      setSnapshot(d);

      if (authUserId && d.players) {
        const heroPlayer = d.players.find((p) => p.userId === authUserId);
        if (heroPlayer && heroPlayer.seat !== seatRef.current) {
          setSeat(heroPlayer.seat);
        }
      }
      return true;
    };

    const onHoleCards = (d: { cards: string[]; seat: number }) => {
      setHoleCards(d.cards);
      holeCardsRef.current = d.cards; // Sync ref immediately (useEffect is deferred)
      setSeat(d.seat);
      seatRef.current = d.seat; // Sync ref immediately
      playUiSfx('deal');
    };

    const onHandStarted = () => {
      setActionPending(false);
      setAdvice(null);
      setDeviation(null);
      setWinners(null);
      setAllInLock(null);
      setMyRunPreference(null);
      setBoardReveal(null);
      setHoleCards([]);
      holeCardsRef.current = []; // Sync ref immediately
      setSettlement(null);
      setPreAction(null);
      setLastActionBySeat({});
      setPostHandShowAvailable(false);
      setSevenTwoBountyPrompt(null);
      setSevenTwoBountyResult(null);
      setPostHandRevealedCards({});
      onTimerUpdate(null);
    };

    const onBoardReveal = (d: {
      handId: string;
      street: string;
      newCards: string[];
      board: string[];
      equities: any[];
      hints?: any[];
    }) => {
      setBoardReveal({ street: d.street, equities: d.equities, hints: d.hints });
      playUiSfx('flip');
    };

    const onRunTwiceReveal = (d: any) => {
      setBoardReveal((prev: BoardRevealState) => ({
        street: d.street,
        equities: d.equities ?? prev?.equities ?? [],
        hints: d.hints ?? prev?.hints,
      }));
      setSnapshot((prev: TableState | null) => {
        if (!prev || prev.handId !== d.handId) return prev;
        if (d.phase === 'top') {
          const prevRun2 = prev.runoutBoards?.[1] ?? d.run2?.board ?? [];
          return { ...prev, runoutBoards: [d.run1.board, prevRun2] };
        }
        return { ...prev, runoutBoards: [d.run1.board, d.run2?.board ?? []] };
      });
    };

    const onAllInLocked = (d: any) => {
      const liveHandId = snapshotRef.current?.handId;
      if (liveHandId && d.handId !== liveHandId) return;
      setAllInLock({
        handId: d.handId,
        eligiblePlayers: d.eligiblePlayers ?? [],
        maxRunCountAllowed: 3,
        submittedPlayerIds: d.submittedPlayerIds ?? [],
        underdogSeat: d.underdogSeat ?? null,
        targetRunCount: d.targetRunCount ?? null,
        equities: d.equities,
      });
      if (seatRef.current != null && !(d.submittedPlayerIds ?? []).includes(seatRef.current)) {
        setMyRunPreference(null);
      }
    };

    const onActionApplied = (d: {
      seat: number;
      action: string;
      amount: number;
      pot: number;
      auto?: boolean;
    }) => {
      if (d.seat === seatRef.current) setActionPending(false);
      setLastActionBySeat((prev: LastActionBySeatState) => ({
        ...prev,
        [d.seat]: { action: d.action, amount: d.amount ?? 0 },
      }));

      playUiSfx('chipBet');

      if (d.seat === seatRef.current && !d.auto) {
        const actionLabel =
          d.action === 'fold'
            ? 'Fold'
            : d.action === 'check'
              ? 'Check'
              : d.action === 'call'
                ? `Call ${d.amount.toLocaleString()}`
                : d.action === 'raise'
                  ? `Raise to ${d.amount.toLocaleString()}`
                  : d.action === 'all_in'
                    ? 'All-In'
                    : d.action;
        showToast(`You: ${actionLabel} · Pot: ${d.pot.toLocaleString()}`);
      }
    };

    const onHandEnded = (d: {
      handId?: string;
      finalState?: TableState;
      winners?: Array<{ seat: number; amount: number; handName?: string }>;
      settlement?: SettlementResult;
    }) => {
      setActionPending(false);
      setMyRunPreference(null);
      setBoardReveal(null);
      setPreAction(null);
      if (d.winners) setWinners(d.winners);
      if (d.finalState) {
        applyAuthoritativeSnapshot(d.finalState, 'hand_ended');
      }

      if (d.settlement) {
        setSettlement(d.settlement);

        const winnerNames = d.settlement.winnersByRun
          .flatMap((r) => r.winners)
          .map((w) => {
            const p = d.finalState?.players.find((pl) => pl.seat === w.seat);
            return `${p?.name ?? `Seat ${w.seat}`} +${w.amount.toLocaleString()}`;
          });
        if (winnerNames.length > 0) {
          showToast(
            winnerNames.length === 1
              ? `Winner: ${winnerNames[0]}`
              : `Winners: ${winnerNames.join(', ')}`,
          );
          playUiSfx('chipWin');
          if (
            d.settlement.winnersByRun.some((r) => r.winners.some((w) => w.seat === seatRef.current))
          ) {
            haptic('win');
          }
        }

        if (d.settlement.sevenTwoBounty) {
          setSevenTwoBountyResult(d.settlement.sevenTwoBounty);
          setSevenTwoRevealActive(d.settlement.sevenTwoBounty);
        } else {
          const heroSeatNow = seatRef.current;
          const winSeats = new Set(
            d.settlement.winnersByRun.flatMap((r) => r.winners.map((w) => w.seat)),
          );
          const heroWon = winSeats.has(heroSeatNow);
          const cards = holeCardsRef.current;
          if (heroWon && cards.length >= 2) {
            if (
              (cards[0][0] === '7' && cards[1][0] === '2') ||
              (cards[0][0] === '2' && cards[1][0] === '7')
            ) {
              // Logic to prompt bounty if not auto-claimed could go here
              // For now we rely on server event
            }
          }
        }
      }

      if (holeCardsRef.current.length >= 2) {
        setPostHandShowAvailable(true);
        setPostHandRevealedCards({});
      }

      // Save hand to localStorage for local hand history
      try {
        let heroCards = holeCardsRef.current;
        let heroSeat = seatRef.current;
        const fs = d.finalState;

        // Fallback: if refs are stale (useEffect not yet synced), try to recover
        // hero identity from finalState using authUserId
        if (fs && (heroCards.length < 2 || heroSeat <= 0) && authUserId) {
          const heroPlayer = fs.players.find((p) => p.userId === authUserId);
          if (heroPlayer) {
            if (heroSeat <= 0) heroSeat = heroPlayer.seat;
            // Try to recover hole cards from revealedHoles
            if (heroCards.length < 2) {
              const revealed = fs.revealedHoles?.[heroPlayer.seat];
              if (revealed && revealed.length >= 2) {
                heroCards = [revealed[0], revealed[1]];
              }
            }
          }
        }

        if (fs && heroCards.length >= 2 && heroSeat > 0) {
          const heroPlayer = fs.players.find((p) => p.seat === heroSeat);
          const heroLedger = d.settlement?.ledger.find((e) => e.seat === heroSeat);
          const position = fs.positions?.[heroSeat] ?? 'BTN';
          const actions: HandActionRecord[] = (fs.actions ?? []).map((a) => ({
            seat: a.seat,
            street: a.street ?? 'PREFLOP',
            type: a.type,
            amount: a.amount ?? 0,
          }));
          const playerNames: Record<number, string> = {};
          const showdownHands: Record<number, [string, string] | 'mucked'> = {};
          for (const p of fs.players) {
            playerNames[p.seat] = p.name;
            const revealed = fs.revealedHoles?.[p.seat];
            if (revealed && revealed.length >= 2) {
              showdownHands[p.seat] = [revealed[0], revealed[1]];
            }
          }

          saveHand({
            gameType: fs.gameType === 'omaha' ? 'PLO' : 'NLH',
            stakes: `${fs.smallBlind}/${fs.bigBlind}`,
            tableSize: fs.players.length,
            position,
            heroCards: [...heroCards],
            board: [...(fs.board ?? [])],
            runoutBoards: fs.runoutBoards ? fs.runoutBoards.map((b) => [...b]) : undefined,
            doubleBoardPayouts: d.settlement?.doubleBoardPayouts,
            actions,
            actionTimeline: undefined,
            potSize: d.settlement?.totalPot ?? fs.pot ?? 0,
            stackSize: heroPlayer?.stack ?? 0,
            result: heroLedger?.net ?? 0,
            tags: autoTag(actions),
            roomCode: currentRoomCodeRef.current || undefined,
            roomName: currentRoomNameRef.current || undefined,
            tableId: tableId ?? undefined,
            handId: fs.handId ?? undefined,
            endedAt: new Date().toISOString(),
            heroSeat,
            heroName: heroPlayer?.name,
            smallBlind: fs.smallBlind,
            bigBlind: fs.bigBlind,
            playersCount: fs.players.length,
            didWinAnyRun: d.settlement?.winnersByRun?.some((r) =>
              r.winners.some((w) => w.seat === heroSeat),
            ),
            showdownHands: Object.keys(showdownHands).length > 0 ? showdownHands : undefined,
            playerNames,
            buttonSeat: fs.buttonSeat,
            isBombPotHand: fs.isBombPotHand,
            isDoubleBoardHand: fs.isDoubleBoardHand,
          });
        } else if (fs) {
          console.warn(
            '[hand-history] Skipped save: heroCards=%d heroSeat=%d',
            heroCards.length,
            heroSeat,
          );
        }
      } catch (e) {
        console.warn('[hand-history] Save failed:', e);
      }

      // Delay clearing hole cards so the hand-end summary can still show them.
      // Guard against clearing a newer hand's cards by snapshotting the current handId.
      const endedHandId = d.handId;
      setTimeout(() => {
        if (snapshotRef.current?.handId === endedHandId || !snapshotRef.current?.handId) {
          setHoleCards([]);
        }
      }, 800);
    };

    const onSevenTwoBountyClaimed = (d: {
      tableId: string;
      handId: string;
      bounty: SevenTwoBountyInfo;
    }) => {
      setSevenTwoBountyResult(d.bounty);
      setSevenTwoBountyPrompt(null);
      showToast(`7-2 Bounty! collected +${d.bounty.totalBounty}`);
      setSevenTwoRevealActive(d.bounty);
      playUiSfx('bounty72');
      haptic('bounty');
    };

    const onShowdownResults = (d: { handId: string; totalPayouts: Record<number, number> }) => {
      if (snapshotRef.current?.handId && d.handId !== snapshotRef.current.handId) return;
      const winnersFromPayouts = Object.entries(d.totalPayouts ?? {})
        .map(([seatNum, amount]) => ({ seat: Number(seatNum), amount: Number(amount) || 0 }))
        .filter((winner) => winner.amount > 0);
      if (winnersFromPayouts.length > 0) {
        setWinners(winnersFromPayouts);
      }
    };

    const onBombPotQueued = (d: { queuedBy: string }) => {
      showToast(`\u{1F4A3} Bomb Pot queued for next hand by ${d.queuedBy}`);
      // Optionally update state if we had a field for this
    };

    // ── Listeners ──
    socket.on('hole_cards', onHoleCards);
    socket.on('hand_started', onHandStarted);
    socket.on('board_reveal', onBoardReveal);
    socket.on('run_twice_reveal', onRunTwiceReveal);
    socket.on('allin_locked', onAllInLocked);
    socket.on('action_applied', onActionApplied);
    socket.on('hand_ended', onHandEnded);
    socket.on('seven_two_bounty_claimed', onSevenTwoBountyClaimed);
    socket.on('showdown_results', onShowdownResults);
    socket.on('bomb_pot_queued', onBombPotQueued);

    socket.on('error_event', (d: { message: string }) => {
      console.warn('[socket] error_event:', d.message);
      showToast(d.message);
    });
    socket.on('advice_payload', (d) => setAdvice(d));
    socket.on('advice_deviation', (d) =>
      setDeviation({ deviation: d.deviation ?? 0, playerAction: d.playerAction }),
    );
    socket.on('room_state_update', (d) => setRoomState(d));
    socket.on('timer_update', (d) => onTimerUpdate(d));
    socket.on('table_snapshot', (d) => applyAuthoritativeSnapshot(d, 'table_snapshot'));

    socket.on(
      'reveal_hole_cards',
      (d: { handId: string; revealed: Record<number, [string, string]> }) => {
        setSnapshot((prev: TableState | null) => {
          if (!prev || prev.handId !== d.handId) return prev;
          return {
            ...prev,
            revealedHoles: { ...(prev.revealedHoles ?? {}), ...(d.revealed ?? {}) },
          };
        });
      },
    );

    socket.on(
      'post_hand_reveal',
      (d: { tableId: string; seat: number; cards: [string, string] }) => {
        setPostHandRevealedCards((prev: PostHandRevealedCardsState) => ({
          ...prev,
          [d.seat]: d.cards,
        }));
        setTimeout(() => {
          setPostHandRevealedCards((prev: PostHandRevealedCardsState) => {
            const next = { ...prev };
            delete next[d.seat];
            return next;
          });
        }, 8000);
      },
    );

    return () => {
      socket.off('hole_cards', onHoleCards);
      socket.off('hand_started', onHandStarted);
      socket.off('board_reveal', onBoardReveal);
      socket.off('run_twice_reveal', onRunTwiceReveal);
      socket.off('allin_locked', onAllInLocked);
      socket.off('action_applied', onActionApplied);
      socket.off('hand_ended', onHandEnded);
      socket.off('seven_two_bounty_claimed', onSevenTwoBountyClaimed);
      socket.off('showdown_results', onShowdownResults);
      socket.off('bomb_pot_queued', onBombPotQueued);
      socket.off('error_event');
      socket.off('advice_payload');
      socket.off('advice_deviation');
      socket.off('room_state_update');
      socket.off('timer_update');
      socket.off('table_snapshot');
      socket.off('reveal_hole_cards');
      socket.off('post_hand_reveal');
    };
  }, [socket, tableId, authUserId]); // Dep array: re-bind if socket or table changes
}
