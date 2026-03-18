import type { TableState, PlayerActionType, Street, LegalActions } from '@cardpilot/shared-types';

export type PreActionType = 'check' | 'fold' | 'check/fold' | 'call';

export interface PreAction {
  handId: string;
  playerId: string;
  actionType: PreActionType;
  createdAt: number;
}

export interface DerivedVisibleAction {
  type: Exclude<PlayerActionType, 'vote_rit'>;
  label: string;
  amount?: number;
  enabled: boolean;
  reasonDisabled?: string;
}

export interface DerivedActionBar {
  visibleActions: DerivedVisibleAction[];
  primaryAction: DerivedVisibleAction | null;
}

export interface DerivedPreActionOption {
  type: PreActionType;
  label: string;
  amount?: number;
  enabled: boolean;
}

export interface DerivedPreActionUI {
  enabled: boolean;
  options: DerivedPreActionOption[];
}

function isActionableStreet(street: Street | null | undefined): boolean {
  return street === 'PREFLOP' || street === 'FLOP' || street === 'TURN' || street === 'RIVER';
}

export function isPlayersTurnActionable(args: {
  gameState: TableState | null;
  seat: number | null | undefined;
  playerId: string | null;
  holeCardsCount: number;
}): boolean {
  const { gameState, seat, playerId, holeCardsCount } = args;
  if (!gameState || !playerId) return false;
  if (!gameState.handId) return false;
  if (!isActionableStreet(gameState.street)) return false;
  if (gameState.showdownPhase === 'decision') return false;
  if (seat == null) return false;
  if (gameState.actorSeat == null || gameState.actorSeat !== seat) return false;
  if (!gameState.legalActions) return false;

  const player = gameState.players.find((p) => p.userId === playerId) ?? null;
  if (!player) return false;
  if ('status' in player && player.status !== 'active') return false;
  if (!player.inHand || player.folded || player.allIn) return false;

  const requiredHole = gameState.holeCardCount ?? 2;
  if (holeCardsCount < requiredHole) return false;

  return true;
}

function legalAllows(legal: LegalActions | null | undefined, action: PreActionType): boolean {
  if (!legal) return false;
  if (action === 'check') return legal.canCheck;
  if (action === 'call') return legal.canCall;
  if (action === 'fold') return legal.canFold;
  if (action === 'check/fold') return legal.canCheck || legal.canFold;
  return false;
}

export function deriveActionBar(
  gameState: TableState | null,
  playerId: string | null,
): DerivedActionBar {
  if (!gameState || !playerId) return { visibleActions: [], primaryAction: null };

  const player = gameState.players.find((p) => p.userId === playerId) ?? null;
  const actionable = Boolean(
    gameState.handId &&
    isActionableStreet(gameState.street) &&
    gameState.showdownPhase !== 'decision',
  );
  const isMyTurn =
    actionable && player && gameState.actorSeat != null && player.seat === gameState.actorSeat;
  const legal = isMyTurn ? gameState.legalActions : null;

  if (!player || !isMyTurn || !legal) {
    return { visibleActions: [], primaryAction: null };
  }

  const foldDisabledOnFreeCheck = legal.canCheck;

  const actions: DerivedVisibleAction[] = [];

  actions.push({
    type: 'fold',
    label: 'FOLD',
    enabled: Boolean(legal.canFold && !foldDisabledOnFreeCheck),
    reasonDisabled: foldDisabledOnFreeCheck ? 'Free check available' : undefined,
  });

  if (legal.canCheck) {
    actions.push({ type: 'check', label: 'CHECK', enabled: true });
  } else if (legal.canCall) {
    actions.push({ type: 'call', label: 'CALL', amount: legal.callAmount, enabled: true });
  }

  if (legal.canRaise) {
    const isBet = (gameState.currentBet ?? 0) === 0 && gameState.street !== 'PREFLOP';
    actions.push({
      type: 'raise',
      label: isBet ? 'BET' : 'RAISE',
      enabled: true,
    });

    actions.push({ type: 'all_in', label: 'ALL-IN', enabled: true });
  }

  const primary = legal.canCall
    ? (actions.find((a) => a.type === 'call') ?? null)
    : (actions.find((a) => a.type === 'check') ?? null);

  return { visibleActions: actions, primaryAction: primary };
}

export function derivePreActionUI(
  gameState: TableState | null,
  playerId: string | null,
): DerivedPreActionUI {
  if (!gameState || !playerId) return { enabled: false, options: [] };

  const player = gameState.players.find((p) => p.userId === playerId) ?? null;
  const enabled = Boolean(
    gameState.handId &&
    isActionableStreet(gameState.street) &&
    gameState.showdownPhase !== 'decision' &&
    player,
  );
  if (!enabled || !player) return { enabled: false, options: [] };
  if ('status' in player && player.status !== 'active') return { enabled: false, options: [] };
  if (!player.inHand || player.folded || player.allIn) return { enabled: false, options: [] };

  const toCall = Math.max(0, (gameState.currentBet ?? 0) - (player.streetCommitted ?? 0));
  const facingBet = toCall > 0;
  const callAmount = Math.min(toCall, player.stack ?? 0);

  if (!facingBet) {
    return {
      enabled: true,
      options: [
        { type: 'check', label: 'Check', enabled: true },
        { type: 'check/fold', label: 'Check / Fold', enabled: true },
      ],
    };
  }

  return {
    enabled: true,
    options: [
      { type: 'call', label: 'Call', amount: callAmount, enabled: true },
      { type: 'fold', label: 'Fold', enabled: true },
    ],
  };
}

export function shouldAutoFirePreAction(args: {
  preAction: PreAction | null;
  gameState: TableState | null;
  playerId: string | null;
  holeCardsCount: number;
  isPlayersTurn: boolean;
  actionPending: boolean;
}): { action: 'fold' | 'check' | 'call'; amount?: number } | null {
  const { preAction, gameState, playerId, holeCardsCount, isPlayersTurn, actionPending } = args;
  if (!preAction || !gameState || !playerId) return null;
  if (actionPending) return null;

  if (!gameState.handId || preAction.handId !== gameState.handId) return null;
  if (!isPlayersTurn) return null;
  if (!isActionableStreet(gameState.street)) return null;
  if (gameState.showdownPhase === 'decision') return null;

  const player = gameState.players.find((p) => p.userId === playerId) ?? null;
  if (!player) return null;
  if ('status' in player && player.status !== 'active') return null;
  if (!player.inHand || player.folded || player.allIn) return null;

  const requiredHole = gameState.holeCardCount ?? 2;
  if (holeCardsCount < requiredHole) return null;

  const legal = gameState.legalActions;
  if (!legal) return null;
  if (!legalAllows(legal, preAction.actionType)) return null;

  if (preAction.actionType === 'fold') return legal.canCheck ? null : { action: 'fold' };
  if (preAction.actionType === 'check') return legal.canCheck ? { action: 'check' } : null;
  if (preAction.actionType === 'call') return legal.canCall ? { action: 'call' } : null;

  if (preAction.actionType === 'check/fold') {
    if (legal.canCheck) return { action: 'check' };
    if (legal.canFold) return { action: 'fold' };
    return null;
  }

  return null;
}

export function shouldConfirmUnnecessaryFold(
  legal: LegalActions | null | undefined,
  suppressedThisSession: boolean,
): boolean {
  if (suppressedThisSession) return false;
  return Boolean(legal?.canCheck);
}
