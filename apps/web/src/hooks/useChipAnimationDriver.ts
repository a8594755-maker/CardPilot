import { useRef, useCallback, useState, useEffect } from "react";
import type { TableState, SettlementResult } from "@cardpilot/shared-types";
import {
  type ChipTransfer,
  type AnimationSpeed,
  getDuration,
  getAnchorCenter,
  nextTransferId,
} from "../lib/chip-animation.js";

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
      if (spd === "off") {
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
              kind: "toPot",
              seat: p.seat,
              createdAt: Date.now(),
              duration: getDuration(spd, "toPot"),
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
      if (spd === "off") return;

      const { container, pot, seats } = anchorsRef.current;
      if (!container || !pot) return;

      const potPos = getAnchorCenter(pot, container);
      if (!potPos) return;

      const baseDuration = getDuration(spd, "toWinner");

      // Aggregate payouts by seat (handles split pot / run-it-twice)
      const payouts: Record<number, number> = { ...settlement.payoutsBySeat };

      const entries = Object.entries(payouts)
        .map(([s, amt]) => ({ seat: Number(s), amount: amt }))
        .filter((e) => e.amount > 0);

      // Stagger: each winner starts 120ms after the previous
      entries.forEach((entry, idx) => {
        const seatEl = seats[entry.seat];
        const toPos = getAnchorCenter(seatEl, container);
        if (!toPos) return;

        const staggerDelay = idx * 120;

        // We add the transfer after a brief delay to stagger visually
        setTimeout(() => {
          setTransfers((prev) => [
            ...prev,
            {
              id: nextTransferId(),
              from: potPos,
              to: toPos,
              amount: entry.amount,
              kind: "toWinner",
              seat: entry.seat,
              createdAt: Date.now(),
              duration: baseDuration,
            },
          ]);
        }, staggerDelay);
      });
    },
    [], // stable — reads from refs
  );

  // Clean up stale transfers (safety: remove any older than 5s)
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setTransfers((prev) => prev.filter((t) => now - t.createdAt < 5000));
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  return { transfers, removeTransfer, onSnapshot, onSettlement };
}
