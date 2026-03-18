import { create } from 'zustand';

export type PlayStreet = 'preflop' | 'flop' | 'turn' | 'river' | 'showdown' | 'finished';
export type PlayRole = 'oop' | 'ip';

export interface PlayAction {
  player: PlayRole;
  action: string; // 'fold' | 'check' | 'call' | 'bet X' | 'raise X'
  amount: number;
  street: PlayStreet;
}

export interface CoachingDecisionFeedback {
  street: PlayStreet;
  action: string;
  gtoPolicy: Record<string, number>;
  qValues: Record<string, number>;
  deltaEV: number;
  severity: 'optimal' | 'minor' | 'moderate' | 'major' | 'blunder';
  bestAction: string;
  userActionEV: number;
  bestActionEV: number;
  potSize: number;
}

export interface PlayHandResult {
  id: number;
  heroCards: [string, string];
  villainCards: [string, string];
  board: string[];
  actions: PlayAction[];
  pot: number;
  heroWon: number;
  villainWon: number;
  heroRole: PlayRole;
  handScore?: number;
  totalEVLost?: number;
  decisionFeedback?: CoachingDecisionFeedback[];
}

interface PlayModeStore {
  // Setup
  isActive: boolean;
  heroRole: PlayRole; // OOP or IP
  oopGridFile: string; // GTO+ file for OOP player
  ipGridFile: string; // GTO+ file for IP player
  startingPot: number;
  effectiveStack: number;

  // Current hand state
  handId: number;
  heroCards: [string, string] | null;
  villainCards: [string, string] | null;
  board: string[];
  street: PlayStreet;
  pot: number;
  heroStack: number;
  villainStack: number;
  heroCommitted: number; // committed this street
  villainCommitted: number;
  toCall: number; // amount hero needs to call
  isHeroTurn: boolean;
  actionHistory: PlayAction[];
  lastAction: string | null;

  // Available actions for hero
  canCheck: boolean;
  canCall: boolean;
  canBet: boolean;
  canRaise: boolean;
  canFold: boolean;
  minBet: number;
  maxBet: number;

  // Auto-play mode
  autoPlay: boolean;
  autoPlaySpeed: number; // ms between actions

  // Hand history
  handResults: PlayHandResult[];
  totalHeroProfit: number;

  // GTO data (loaded for the current hand)
  currentGrid: Record<string, Record<string, number>>;
  currentActions: string[];

  // Coaching feedback
  coachingEnabled: boolean;
  coachingModelReady: boolean;
  currentFeedback: CoachingDecisionFeedback | null;
  handFeedback: CoachingDecisionFeedback[];
  showFeedback: boolean;

  // Methods
  startSession: (config: {
    heroRole: PlayRole;
    oopGridFile: string;
    ipGridFile: string;
    startingPot: number;
    effectiveStack: number;
  }) => void;
  endSession: () => void;
  setHeroCards: (cards: [string, string]) => void;
  setVillainCards: (cards: [string, string]) => void;
  setBoard: (board: string[]) => void;
  setStreet: (street: PlayStreet) => void;
  setPot: (pot: number) => void;
  setStacks: (hero: number, villain: number) => void;
  setCommitted: (hero: number, villain: number) => void;
  setToCall: (amount: number) => void;
  setIsHeroTurn: (isHero: boolean) => void;
  setLegalActions: (actions: {
    canCheck: boolean;
    canCall: boolean;
    canBet: boolean;
    canRaise: boolean;
    canFold: boolean;
    minBet: number;
    maxBet: number;
  }) => void;
  addAction: (action: PlayAction) => void;
  setLastAction: (action: string | null) => void;
  setCurrentGrid: (grid: Record<string, Record<string, number>>, actions: string[]) => void;
  addHandResult: (result: PlayHandResult) => void;
  setAutoPlay: (auto: boolean) => void;
  setAutoPlaySpeed: (speed: number) => void;
  nextHand: () => void;
  setCoachingEnabled: (enabled: boolean) => void;
  setCoachingModelReady: (ready: boolean) => void;
  setCurrentFeedback: (feedback: CoachingDecisionFeedback | null) => void;
  addHandFeedback: (feedback: CoachingDecisionFeedback) => void;
  setShowFeedback: (show: boolean) => void;
}

export const usePlayMode = create<PlayModeStore>((set) => ({
  isActive: false,
  heroRole: 'oop',
  oopGridFile: '',
  ipGridFile: '',
  startingPot: 6,
  effectiveStack: 97,

  handId: 0,
  heroCards: null,
  villainCards: null,
  board: [],
  street: 'flop',
  pot: 6,
  heroStack: 97,
  villainStack: 97,
  heroCommitted: 0,
  villainCommitted: 0,
  toCall: 0,
  isHeroTurn: true,
  actionHistory: [],
  lastAction: null,

  canCheck: true,
  canCall: false,
  canBet: true,
  canRaise: false,
  canFold: false,
  minBet: 1,
  maxBet: 97,

  autoPlay: false,
  autoPlaySpeed: 1000,

  handResults: [],
  totalHeroProfit: 0,

  currentGrid: {},
  currentActions: [],

  coachingEnabled: true,
  coachingModelReady: false,
  currentFeedback: null,
  handFeedback: [],
  showFeedback: true,

  startSession: (config) =>
    set({
      isActive: true,
      heroRole: config.heroRole,
      oopGridFile: config.oopGridFile,
      ipGridFile: config.ipGridFile,
      startingPot: config.startingPot,
      effectiveStack: config.effectiveStack,
      handId: 1,
      pot: config.startingPot,
      heroStack: config.effectiveStack,
      villainStack: config.effectiveStack,
      heroCommitted: 0,
      villainCommitted: 0,
      toCall: 0,
      board: [],
      street: 'flop',
      actionHistory: [],
      handResults: [],
      totalHeroProfit: 0,
    }),

  endSession: () =>
    set({
      isActive: false,
      heroCards: null,
      villainCards: null,
      board: [],
      street: 'flop',
      actionHistory: [],
      lastAction: null,
    }),

  setHeroCards: (heroCards) => set({ heroCards }),
  setVillainCards: (villainCards) => set({ villainCards }),
  setBoard: (board) => set({ board }),
  setStreet: (street) => set({ street }),
  setPot: (pot) => set({ pot }),
  setStacks: (heroStack, villainStack) => set({ heroStack, villainStack }),
  setCommitted: (heroCommitted, villainCommitted) => set({ heroCommitted, villainCommitted }),
  setToCall: (toCall) => set({ toCall }),
  setIsHeroTurn: (isHeroTurn) => set({ isHeroTurn }),
  setLegalActions: (actions) => set(actions),
  addAction: (action) => set((s) => ({ actionHistory: [...s.actionHistory, action] })),
  setLastAction: (lastAction) => set({ lastAction }),
  setCurrentGrid: (currentGrid, currentActions) => set({ currentGrid, currentActions }),
  addHandResult: (result) =>
    set((s) => ({
      handResults: [...s.handResults, result],
      totalHeroProfit: s.totalHeroProfit + result.heroWon - s.startingPot / 2,
    })),
  setAutoPlay: (autoPlay) => set({ autoPlay }),
  setAutoPlaySpeed: (autoPlaySpeed) => set({ autoPlaySpeed }),
  setCoachingEnabled: (coachingEnabled) => set({ coachingEnabled }),
  setCoachingModelReady: (coachingModelReady) => set({ coachingModelReady }),
  setCurrentFeedback: (currentFeedback) => set({ currentFeedback }),
  addHandFeedback: (feedback) => set((s) => ({ handFeedback: [...s.handFeedback, feedback] })),
  setShowFeedback: (showFeedback) => set({ showFeedback }),
  nextHand: () =>
    set((s) => ({
      handId: s.handId + 1,
      heroCards: null,
      villainCards: null,
      board: [],
      street: 'flop',
      pot: s.startingPot,
      heroStack: s.effectiveStack,
      villainStack: s.effectiveStack,
      heroCommitted: 0,
      villainCommitted: 0,
      toCall: 0,
      isHeroTurn: s.heroRole === 'oop',
      actionHistory: [],
      lastAction: null,
      currentGrid: {},
      currentActions: [],
      currentFeedback: null,
      handFeedback: [],
    })),
}));
