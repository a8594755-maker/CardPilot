import { useState, useCallback, useMemo } from 'react';

/**
 * Overlay priority levels (higher = more important).
 * Only one overlay per priority can be active.
 * Opening a higher-priority overlay auto-closes lower ones.
 */
export const OVERLAY_PRIORITY = {
  none: 0,
  drawer: 10, // Options drawer
  panel: 20, // GTO sidebar, session stats, room log
  modal: 30, // Buy-in, rebuy, fold confirm
  roomSettings: 40, // Room Settings (full-screen surface)
} as const;

export type OverlayId =
  | 'optionsDrawer'
  | 'roomSettings'
  | 'buyIn'
  | 'rebuy'
  | 'foldConfirm'
  | 'revealedZoom'
  | 'mobileGto'
  | 'handSummary'
  | 'allInPrompt';

export interface OverlayEntry {
  id: OverlayId;
  priority: number;
}

export const OVERLAY_CONFIG: Record<OverlayId, number> = {
  optionsDrawer: OVERLAY_PRIORITY.drawer,
  handSummary: OVERLAY_PRIORITY.drawer,
  roomSettings: OVERLAY_PRIORITY.roomSettings,
  buyIn: OVERLAY_PRIORITY.modal,
  rebuy: OVERLAY_PRIORITY.modal,
  foldConfirm: OVERLAY_PRIORITY.modal,
  revealedZoom: OVERLAY_PRIORITY.modal,
  mobileGto: OVERLAY_PRIORITY.modal,
  allInPrompt: OVERLAY_PRIORITY.modal,
};

/* ── Pure overlay stack logic (testable without React) ── */

export function overlayOpen(prev: OverlayEntry[], id: OverlayId): OverlayEntry[] {
  const priority = OVERLAY_CONFIG[id];
  const filtered = prev.filter((o) => o.id !== id && o.priority > priority);
  const next = [...filtered, { id, priority }];
  next.sort((a, b) => b.priority - a.priority);
  return next;
}

export function overlayClose(prev: OverlayEntry[], id: OverlayId): OverlayEntry[] {
  return prev.filter((o) => o.id !== id);
}

export function overlayIsOpen(stack: OverlayEntry[], id: OverlayId): boolean {
  return stack.some((o) => o.id === id);
}

export function overlayTop(stack: OverlayEntry[]): OverlayId | null {
  return stack.length > 0 ? stack[0].id : null;
}

/* ── React hook (thin wrapper) ── */

export interface OverlayManager {
  activeOverlays: OverlayEntry[];
  isOpen: (id: OverlayId) => boolean;
  open: (id: OverlayId) => void;
  close: (id: OverlayId) => void;
  closeAll: () => void;
  topOverlay: OverlayId | null;
}

export function useOverlayManager(): OverlayManager {
  const [activeOverlays, setActiveOverlays] = useState<OverlayEntry[]>([]);

  const open = useCallback((id: OverlayId) => {
    setActiveOverlays((prev) => overlayOpen(prev, id));
  }, []);

  const close = useCallback((id: OverlayId) => {
    setActiveOverlays((prev) => overlayClose(prev, id));
  }, []);

  const closeAll = useCallback(() => {
    setActiveOverlays([]);
  }, []);

  const isOpen = useCallback(
    (id: OverlayId) => overlayIsOpen(activeOverlays, id),
    [activeOverlays],
  );

  const topOverlay = useMemo(() => overlayTop(activeOverlays), [activeOverlays]);

  return useMemo(
    () => ({ activeOverlays, isOpen, open, close, closeAll, topOverlay }),
    [activeOverlays, isOpen, open, close, closeAll, topOverlay],
  );
}
