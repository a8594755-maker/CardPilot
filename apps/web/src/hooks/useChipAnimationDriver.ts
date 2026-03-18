import { useRef, useCallback, useState, useEffect } from 'react';
import type { TableState, SettlementResult, SevenTwoBountyInfo } from '@cardpilot/shared-types';
import {
  type ChipTransfer,
  type AnimationSpeed,
  getTiming,
  getAnchorCenter,
  nextTransferId,
} from '../lib/chip-animation.js';

export interface ChipAnimationAnchors {
  container: HTMLElement | null;
  pot: HTMLElement | null;
  seats: Record<number, HTMLElement | null>;
}

interface UseChipAnimationDriverResult {
  transfers: ChipTransfer[];
  removeTransfer: (id: string) => void;
  /** Call when a new table_snapshot arrives */
  onSnapshot: (next: TableState) => void;
  /** Call when hand_ended with settlement fires */
  onSettlement: (settlement: SettlementResult) => void;
  /** Call when 7-2 bounty is claimed — animates chips from paying seats to winner */
  onBountyClaim: (bounty: SevenTwoBountyInfo) => void;
}

/**
 * Drives chip-movement animations by comparing consecutive snapshots
 * to detect bet deltas (seat→pot) and settlement payouts (pot→seat).
 */
export function useChipAnimationDriver(
  anchors: ChipAnimationAnchors,
  speed: AnimationSpeed,
): UseChipAnimationDriverResult {
  const [transfers, setTransfers] = useState<ChipTransfer[]>([]);
  const prevCommitted = useRef<Record<number, number>>({});
  const prevHandId = useRef<string | null>(null);
  // Keep latest anchors/speed in refs so stable callbacks always read current values
  const anchorsRef = useRef(anchors);
  anchorsRef.current = anchors;
  const speedRef = useRef(speed);
  speedRef.current = speed;

  const removeTransfer = useCallback((id: string) => {
    setTransfers((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ── Snapshot-driven: detect streetCommitted deltas → seat→pot ──
  const onSnapshot = useCallback(
    (next: TableState) => {
      const spd = speedRef.current;
      if (spd === 'off') {
        // Still track state so switching speed mid-hand works
        const committed: Record<number, number> = {};
        for (const p of next.players) committed[p.seat] = p.streetCommitted;
        prevCommitted.current = committed;
        prevHandId.current = next.handId;
        return;
      }

      const { container, pot, seats } = anchorsRef.current;
      if (!container || !pot) {
        // No anchors yet — just track
        const committed: Record<number, number> = {};
        for (const p of next.players) committed[p.seat] = p.streetCommitted;
        prevCommitted.current = committed;
        prevHandId.current = next.handId;
        return;
      }

      // If hand changed, reset tracking
      if (next.handId !== prevHandId.current) {
        const committed: Record<number, number> = {};
        for (const p of next.players) committed[p.seat] = p.streetCommitted;
        prevCommitted.current = committed;
        prevHandId.current = next.handId;

        // Bomb pot ante animation: ante uses countToStreet=false so streetCommitted
        // stays at 0 — detect from the actions array instead
        if (next.isBombPotHand && next.actions && next.actions.length > 0) {
          const anteActions = next.actions.filter((a) => a.type === 'ante' && a.amount > 0);
          if (anteActions.length > 0) {
            const potPos = getAnchorCenter(pot, container);
            if (potPos) {
              const timing = getTiming(spd, 'bombPotAnte');
              const STAGGER_MS = 60;
              anteActions.forEach((action, idx) => {
                const seatEl = seats[action.seat];
                const fromPos = getAnchorCenter(seatEl, container);
                if (!fromPos) return;
                const tid = setTimeout(() => {
                  pendingTimeouts.current.delete(tid);
                  setTransfers((prev) => [
                    ...prev,
                    {
                      id: nextTransferId(),
                      from: fromPos,
                      to: potPos,
                      amount: action.amount,
                      kind: 'bombPotAnte' as const,
                      seat: action.seat,
                      createdAt: Date.now(),
                      timing,
                    },
                  ]);
                }, idx * STAGGER_MS);
                pendingTimeouts.current.add(tid);
              });
            }
          }
        }

        return;
      }

      const newTransfers: ChipTransfer[] = [];
      const committed: Record<number, number> = {};

      for (const p of next.players) {
        committed[p.seat] = p.streetCommitted;
        const prev = prevCommitted.current[p.seat] ?? 0;
        const delta = p.streetCommitted - prev;

        if (delta > 0) {
          const seatEl = seats[p.seat];
          const fromPos = getAnchorCenter(seatEl, container);
          const toPos = getAnchorCenter(pot, container);
          if (fromPos && toPos) {
            newTransfers.push({
              id: nextTransferId(),
              from: fromPos,
              to: toPos,
              amount: delta,
              kind: 'toPot',
              seat: p.seat,
              createdAt: Date.now(),
              timing: getTiming(spd, 'toPot'),
            });
          }
        }
      }

      prevCommitted.current = committed;
      prevHandId.current = next.handId;

      if (newTransfers.length > 0) {
        setTransfers((prev) => [...prev, ...newTransfers]);
      }
    },
    [], // stable — reads from refs
  );

  // ── Settlement-driven: pot→winner payouts ──
  const onSettlement = useCallback(
    (settlement: SettlementResult) => {
      const spd = speedRef.current;
      if (spd === 'off') return;

      const { container, pot, seats } = anchorsRef.current;
      if (!container || !pot) return;

      const potPos = getAnchorCenter(pot, container);
      if (!potPos) return;

      const timing = getTiming(spd, 'toWinner');

      // Aggregate payouts by seat (handles split pot / run-it-twice)
      const payouts: Record<number, number> = { ...settlement.payoutsBySeat };

      const entries = Object.entries(payouts)
        .map(([s, amt]) => ({ seat: Number(s), amount: amt }))
        .filter((e) => e.amount > 0);

      // Stagger: each winner starts 150ms after the previous
      entries.forEach((entry, idx) => {
        const seatEl = seats[entry.seat];
        const toPos = getAnchorCenter(seatEl, container);
        if (!toPos) return;

        const staggerDelay = idx * 150;

        // We add the transfer after a brief delay to stagger visually
        const tid = setTimeout(() => {
          pendingTimeouts.current.delete(tid);
          setTransfers((prev) => [
            ...prev,
            {
              id: nextTransferId(),
              from: potPos,
              to: toPos,
              amount: entry.amount,
              kind: 'toWinner',
              seat: entry.seat,
              createdAt: Date.now(),
              timing,
            },
          ]);
        }, staggerDelay);
        pendingTimeouts.current.add(tid);
      });
    },
    [], // stable — reads from refs
  );

  // ── Bounty-driven: paying seats → winner seat ──
  const onBountyClaim = useCallback(
    (bounty: SevenTwoBountyInfo) => {
      const spd = speedRef.current;
      if (spd === 'off') return;

      const { container, seats } = anchorsRef.current;
      if (!container) return;

      const winnerSeatEl = seats[bounty.winnerSeat];
      const toPos = getAnchorCenter(winnerSeatEl, container);
      if (!toPos) return;

      const timing = getTiming(spd, 'bountyToWinner');

      bounty.payingSeats.forEach((payerSeat, idx) => {
        const payerEl = seats[payerSeat];
        const fromPos = getAnchorCenter(payerEl, container);
        if (!fromPos) return;

        const amount = Math.abs(bounty.bountyBySeat[payerSeat] ?? bounty.bountyPerPlayer);

        // Stagger: each payer chip launches 200ms after the previous
        const tid = setTimeout(() => {
          pendingTimeouts.current.delete(tid);
          setTransfers((prev) => [
            ...prev,
            {
              id: nextTransferId(),
              from: fromPos,
              to: toPos,
              amount,
              kind: 'bountyToWinner' as const,
              seat: payerSeat,
              createdAt: Date.now(),
              timing,
            },
          ]);
        }, idx * 200);
        pendingTimeouts.current.add(tid);
      });
    },
    [], // stable — reads from refs
  );

  // Track pending setTimeout IDs so we can clean them up on unmount
  const pendingTimeouts = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  // Clean up stale transfers (safety: remove any older than 8s)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setTransfers((prev) => prev.filter((t) => now - t.createdAt < 8000));
    }, 3000);
    return () => {
      clearInterval(interval);
      for (const id of pendingTimeouts.current) clearTimeout(id);
      pendingTimeouts.current.clear();
    };
  }, []);

  return { transfers, removeTransfer, onSnapshot, onSettlement, onBountyClaim };
}
