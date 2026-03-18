/**
 * Play engine: manages a single play-against-solution hand.
 * Handles dealing, GTO opponent actions, street progression, and showdown.
 */

import { usePlayMode } from '../stores/play-mode';
import type { PlayAction, PlayRole, CoachingDecisionFeedback } from '../stores/play-mode';
import { createDeck, dealCards, sampleHandFromGrid, sampleGtoAction } from './range-sampler';
import { fetchGtoPlusGrid, evaluateCoachingAction } from './api-client';

/**
 * Start a new hand: deal board and hole cards.
 */
export async function dealNewHand(
  oopGridFile: string,
  ipGridFile: string,
  heroRole: PlayRole,
  startingPot: number,
  effectiveStack: number,
) {
  const store = usePlayMode.getState();

  // Load grids for both players
  const [oopData, ipData] = await Promise.all([
    fetchGtoPlusGrid(oopGridFile),
    fetchGtoPlusGrid(ipGridFile),
  ]);

  // Deal board (flop only for now)
  const deck = createDeck();
  const flop = dealCards(deck, 3);

  // Deal hero hand from their grid
  const heroGrid = heroRole === 'oop' ? oopData.grid : ipData.grid;
  const villainGrid = heroRole === 'oop' ? ipData.grid : oopData.grid;

  const deadCards = new Set(flop);
  const heroHand = sampleHandFromGrid(heroGrid, deadCards);
  if (!heroHand) return;

  deadCards.add(heroHand[0]);
  deadCards.add(heroHand[1]);

  const villainHand = sampleHandFromGrid(villainGrid, deadCards);
  if (!villainHand) return;

  // Set GTO data for villain's decision making
  const villainActions = heroRole === 'oop' ? ipData.actions : oopData.actions;
  const activeGrid = heroRole === 'oop' ? oopData.grid : ipData.grid;

  store.setHeroCards(heroHand);
  store.setVillainCards(villainHand);
  store.setBoard(flop);
  store.setStreet('flop');
  store.setPot(startingPot);
  store.setStacks(effectiveStack, effectiveStack);
  store.setCommitted(0, 0);
  store.setToCall(0);
  store.setCurrentGrid(activeGrid, oopData.actions);
  store.setLastAction(null);

  // OOP acts first on the flop
  store.setIsHeroTurn(heroRole === 'oop');

  // Set legal actions for OOP (first to act)
  updateLegalActions(effectiveStack, 0, startingPot, 0);

  // If villain acts first, make their move
  if (heroRole === 'ip') {
    await executeVillainAction(villainGrid, villainHand, villainActions);
  }
}

/**
 * Handle hero action
 */
export async function handleHeroAction(action: string, amount: number = 0) {
  const store = usePlayMode.getState();

  const heroAction: PlayAction = {
    player: store.heroRole,
    action: amount > 0 ? `${action} ${amount}` : action,
    amount,
    street: store.street,
  };
  store.addAction(heroAction);

  if (action === 'fold') {
    if (store.coachingEnabled && store.heroCards) {
      requestCoachingFeedback(store, 'fold', 0).catch(() => {});
    }
    finishHand(false);
    return;
  }

  // Apply the action
  let newHeroCommitted = store.heroCommitted;
  let newHeroStack = store.heroStack;
  let newPot = store.pot;

  if (action === 'call') {
    const callAmount = store.toCall;
    newHeroCommitted += callAmount;
    newHeroStack -= callAmount;
    newPot += callAmount;
  } else if (action === 'bet' || action === 'raise') {
    const betAmount = amount;
    const additionalCost = betAmount - store.heroCommitted;
    newHeroCommitted = betAmount;
    newHeroStack -= additionalCost;
    newPot += additionalCost;
  } else if (action === 'check') {
    // No money changes
  }

  store.setPot(newPot);
  store.setStacks(newHeroStack, store.villainStack);
  store.setCommitted(newHeroCommitted, store.villainCommitted);

  // Request coaching feedback (fire-and-forget, don't block gameplay)
  if (store.coachingEnabled && store.heroCards) {
    requestCoachingFeedback(store, action, amount).catch(() => {});
  }

  // Check if street is complete (both players have acted and bets are matched)
  if (action === 'check' && store.villainCommitted === newHeroCommitted) {
    // Both checked or check-check
    if (store.actionHistory.length > 0 || store.heroRole === 'ip') {
      advanceStreet();
      return;
    }
  }

  if (action === 'call') {
    // Call completes the betting round
    advanceStreet();
    return;
  }

  // Villain's turn
  store.setIsHeroTurn(false);

  // Small delay for villain action
  await new Promise((r) => setTimeout(r, 500));

  // Get villain grid and execute action
  const villainGrid = store.currentGrid; // For simplicity, use current grid
  const villainHand = store.villainCards;
  if (!villainHand) return;

  const villainActions = store.currentActions;
  await executeVillainAction(villainGrid, villainHand, villainActions);
}

/**
 * Execute villain's GTO action
 */
async function executeVillainAction(
  grid: Record<string, Record<string, number>>,
  hand: [string, string],
  actions: string[],
) {
  const store = usePlayMode.getState();
  const villainRole: PlayRole = store.heroRole === 'oop' ? 'ip' : 'oop';

  // Sample action from GTO strategy
  const gtoAction = sampleGtoAction(grid, hand, actions);

  // Interpret the action
  let actionType = 'check';
  let amount = 0;

  const lowerAction = gtoAction.toLowerCase();
  if (lowerAction.includes('fold')) {
    actionType = 'fold';
  } else if (lowerAction.includes('call')) {
    actionType = 'call';
    amount = store.toCall;
  } else if (
    lowerAction.includes('raise') ||
    lowerAction.includes('bet') ||
    lowerAction.includes('b')
  ) {
    // Extract bet size from action name (e.g., "Bet 75%", "Raise 2x", "B33")
    const match = gtoAction.match(/(\d+)/);
    if (match) {
      const pctOrSize = parseInt(match[1], 10);
      if (pctOrSize <= 200) {
        // Percentage of pot
        amount = Math.round((store.pot * pctOrSize) / 100);
      } else {
        amount = pctOrSize;
      }
    } else {
      amount = Math.round(store.pot * 0.67); // Default 67% pot
    }
    actionType = store.heroCommitted > 0 || store.villainCommitted > 0 ? 'raise' : 'bet';
  } else if (lowerAction.includes('check') || lowerAction === 'x') {
    actionType = 'check';
  } else {
    // Try to parse as bet/raise if has a number
    const match = gtoAction.match(/(\d+)/);
    if (match) {
      const pctOrSize = parseInt(match[1], 10);
      amount = Math.round((store.pot * pctOrSize) / 100);
      actionType = 'bet';
    }
  }

  const villainAction: PlayAction = {
    player: villainRole,
    action: amount > 0 ? `${actionType} ${amount}` : actionType,
    amount,
    street: store.street,
  };
  store.addAction(villainAction);
  store.setLastAction(`Villain: ${villainAction.action}`);

  if (actionType === 'fold') {
    finishHand(true); // Hero wins
    return;
  }

  // Apply villain action
  let newVillainCommitted = store.villainCommitted;
  let newVillainStack = store.villainStack;
  let newPot = store.pot;

  if (actionType === 'call') {
    const callAmount = Math.min(store.toCall, newVillainStack);
    newVillainCommitted += callAmount;
    newVillainStack -= callAmount;
    newPot += callAmount;
    store.setPot(newPot);
    store.setStacks(store.heroStack, newVillainStack);
    store.setCommitted(store.heroCommitted, newVillainCommitted);
    advanceStreet();
    return;
  }

  if (actionType === 'bet' || actionType === 'raise') {
    const additionalCost = amount - newVillainCommitted;
    newVillainCommitted = amount;
    newVillainStack -= additionalCost;
    newPot += additionalCost;
    store.setPot(newPot);
    store.setStacks(store.heroStack, newVillainStack);
    store.setCommitted(store.heroCommitted, newVillainCommitted);
    store.setToCall(newVillainCommitted - store.heroCommitted);
  }

  if (actionType === 'check') {
    // Check - if hero already checked, advance street
    const heroActed = store.actionHistory.some(
      (a) => a.street === store.street && a.player === store.heroRole,
    );
    if (heroActed) {
      advanceStreet();
      return;
    }
  }

  // Hero's turn
  store.setIsHeroTurn(true);
  const toCall = newVillainCommitted - store.heroCommitted;
  updateLegalActions(store.heroStack, store.heroCommitted, newPot, toCall);
}

/**
 * Advance to the next street
 */
function advanceStreet() {
  const store = usePlayMode.getState();
  const currentStreet = store.street;

  // Reset committed amounts for new street
  store.setCommitted(0, 0);
  store.setToCall(0);

  if (currentStreet === 'flop') {
    // Deal turn
    const deck = createDeck([
      ...store.board,
      ...(store.heroCards || []),
      ...(store.villainCards || []),
    ]);
    const turn = dealCards(deck, 1);
    store.setBoard([...store.board, ...turn]);
    store.setStreet('turn');
  } else if (currentStreet === 'turn') {
    // Deal river
    const deck = createDeck([
      ...store.board,
      ...(store.heroCards || []),
      ...(store.villainCards || []),
    ]);
    const river = dealCards(deck, 1);
    store.setBoard([...store.board, ...river]);
    store.setStreet('river');
  } else if (currentStreet === 'river') {
    // Showdown
    store.setStreet('showdown');
    resolveShowdown();
    return;
  }

  // OOP acts first on new streets
  store.setIsHeroTurn(store.heroRole === 'oop');
  updateLegalActions(store.heroStack, 0, store.pot, 0);

  // If villain acts first, schedule their action
  if (store.heroRole === 'ip') {
    setTimeout(async () => {
      const s = usePlayMode.getState();
      const grid = s.currentGrid;
      const hand = s.villainCards;
      if (!hand) return;
      await executeVillainAction(grid, hand, s.currentActions);
    }, 500);
  }
}

/**
 * Resolve showdown - determine winner
 */
function resolveShowdown() {
  const store = usePlayMode.getState();
  const heroCards = store.heroCards;
  const villainCards = store.villainCards;

  if (!heroCards || !villainCards) return;

  // Simple rank-based comparison using card values
  const heroStrength = evaluateHandStrength(heroCards, store.board);
  const villainStrength = evaluateHandStrength(villainCards, store.board);

  const heroWon =
    heroStrength > villainStrength
      ? store.pot
      : heroStrength === villainStrength
        ? store.pot / 2
        : 0;

  const feedback = store.handFeedback;
  const totalEVLost = feedback.reduce((s, f) => s + Math.abs(Math.min(0, f.deltaEV)), 0);
  const avgPctPot =
    feedback.length > 0
      ? feedback.reduce((s, f) => s + Math.abs(f.deltaEV) / Math.max(f.potSize, 0.01), 0) /
        feedback.length
      : 0;
  const handScore = Math.max(0, Math.min(100, 100 * (1 - avgPctPot)));

  store.addHandResult({
    id: store.handId,
    heroCards: heroCards,
    villainCards: villainCards,
    board: store.board,
    actions: store.actionHistory,
    pot: store.pot,
    heroWon,
    villainWon: store.pot - heroWon,
    heroRole: store.heroRole,
    handScore: feedback.length > 0 ? handScore : undefined,
    totalEVLost: feedback.length > 0 ? totalEVLost : undefined,
    decisionFeedback: feedback.length > 0 ? [...feedback] : undefined,
  });
}

/**
 * Finish hand (via fold)
 */
function finishHand(heroWins: boolean) {
  const store = usePlayMode.getState();

  store.setStreet('showdown');
  const feedback = store.handFeedback;
  const totalEVLost = feedback.reduce((s, f) => s + Math.abs(Math.min(0, f.deltaEV)), 0);
  const avgPctPot =
    feedback.length > 0
      ? feedback.reduce((s, f) => s + Math.abs(f.deltaEV) / Math.max(f.potSize, 0.01), 0) /
        feedback.length
      : 0;
  const handScore = Math.max(0, Math.min(100, 100 * (1 - avgPctPot)));

  store.addHandResult({
    id: store.handId,
    heroCards: store.heroCards || (['??', '??'] as [string, string]),
    villainCards: store.villainCards || (['??', '??'] as [string, string]),
    board: store.board,
    actions: store.actionHistory,
    pot: store.pot,
    heroWon: heroWins ? store.pot : 0,
    villainWon: heroWins ? 0 : store.pot,
    heroRole: store.heroRole,
    handScore: feedback.length > 0 ? handScore : undefined,
    totalEVLost: feedback.length > 0 ? totalEVLost : undefined,
    decisionFeedback: feedback.length > 0 ? [...feedback] : undefined,
  });
}

/**
 * Update legal actions for the current player
 */
function updateLegalActions(stack: number, committed: number, pot: number, toCall: number) {
  const store = usePlayMode.getState();

  const canCall = toCall > 0;
  const canCheck = toCall === 0;
  const canFold = toCall > 0;
  const canBet = toCall === 0 && stack > 0;
  const canRaise = toCall > 0 && stack > toCall;
  const minBet = Math.max(1, toCall > 0 ? toCall * 2 : Math.round(pot * 0.25));
  const maxBet = stack;

  store.setLegalActions({ canCheck, canCall, canBet, canRaise, canFold, minBet, maxBet });
  store.setToCall(toCall);
}

/**
 * Simple hand strength evaluator (0-100 scale).
 * For a proper implementation, this would use poker-evaluator package.
 */
function evaluateHandStrength(hand: [string, string], board: string[]): number {
  const RANK_VALUES: Record<string, number> = {
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    T: 10,
    J: 11,
    Q: 12,
    K: 13,
    A: 14,
  };

  const allCards = [...hand, ...board];
  const values = allCards.map((c) => RANK_VALUES[c[0]] || 0);
  const suits = allCards.map((c) => c[1]);

  // Count rank occurrences
  const rankCounts: Record<number, number> = {};
  for (const v of values) {
    rankCounts[v] = (rankCounts[v] || 0) + 1;
  }
  const counts = Object.entries(rankCounts).sort(
    (a, b) => b[1] - a[1] || Number(b[0]) - Number(a[0]),
  );

  // Count suit occurrences
  const suitCounts: Record<string, number> = {};
  for (const s of suits) {
    suitCounts[s] = (suitCounts[s] || 0) + 1;
  }
  const hasFlush = Object.values(suitCounts).some((c) => c >= 5);

  // Check for straight
  const uniqueVals = [...new Set(values)].sort((a, b) => b - a);
  let hasStraight = false;
  let straightHigh = 0;
  for (let i = 0; i <= uniqueVals.length - 5; i++) {
    if (uniqueVals[i] - uniqueVals[i + 4] === 4) {
      hasStraight = true;
      straightHigh = uniqueVals[i];
      break;
    }
  }
  // Wheel check
  if (
    !hasStraight &&
    uniqueVals.includes(14) &&
    uniqueVals.includes(5) &&
    uniqueVals.includes(4) &&
    uniqueVals.includes(3) &&
    uniqueVals.includes(2)
  ) {
    hasStraight = true;
    straightHigh = 5;
  }

  // Evaluate hand strength
  const maxCount = counts[0] ? counts[0][1] : 0;
  const secondCount = counts[1] ? counts[1][1] : 0;

  if (hasFlush && hasStraight) return 800 + straightHigh;
  if (maxCount === 4) return 700 + Number(counts[0][0]);
  if (maxCount === 3 && secondCount >= 2) return 600 + Number(counts[0][0]);
  if (hasFlush) return 500 + Math.max(...values);
  if (hasStraight) return 400 + straightHigh;
  if (maxCount === 3) return 300 + Number(counts[0][0]);
  if (maxCount === 2 && secondCount === 2)
    return 200 + Number(counts[0][0]) * 15 + Number(counts[1][0]);
  if (maxCount === 2) return 100 + Number(counts[0][0]);
  return Math.max(...values);
}

/**
 * Request coaching feedback from the API for a hero action.
 */
async function requestCoachingFeedback(
  store: ReturnType<typeof usePlayMode.getState>,
  action: string,
  amount: number,
) {
  if (!store.heroCards) return;

  const streetMap: Record<string, string> = {
    preflop: 'preflop',
    flop: 'flop',
    turn: 'turn',
    river: 'river',
  };

  // Convert action to coaching API format
  let userAction: string;
  if (action === 'fold' || action === 'check' || action === 'call') {
    userAction = action;
  } else if (action === 'bet' || action === 'raise') {
    const pctPot = store.pot > 0 ? Math.round((amount / store.pot) * 100) : 100;
    userAction = `${action} ${pctPot}%`;
  } else {
    userAction = action;
  }

  try {
    const result = await evaluateCoachingAction({
      holeCards: [...store.heroCards],
      boardCards: store.board.length > 0 ? [...store.board] : undefined,
      pot: store.pot,
      stack: store.heroStack,
      position: store.heroRole === 'ip' ? 'BTN' : 'BB',
      street: streetMap[store.street] ?? 'flop',
      facingBet: store.toCall,
      userAction,
    });

    const feedback: CoachingDecisionFeedback = {
      street: store.street,
      action: userAction,
      gtoPolicy: result.gtoPolicy,
      qValues: result.qValues,
      deltaEV: result.deltaEV,
      severity: result.severity,
      bestAction: result.bestAction,
      userActionEV: result.userActionEV,
      bestActionEV: result.bestActionEV,
      potSize: result.potSize,
    };

    const current = usePlayMode.getState();
    current.setCurrentFeedback(feedback);
    current.addHandFeedback(feedback);
  } catch {
    // Silently fail - coaching is optional
  }
}
