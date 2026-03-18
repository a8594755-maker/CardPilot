import { create } from 'zustand';

// --- Types ---

export type GameType = 'cash' | 'sng' | 'mtt';

export interface CashConfig {
  startingPot: number;
  effectiveStack: number;
  rakePercent: number;
  rakeCap: number;
}

export interface SngPlayerRow {
  chipCount: number;
  prize: number;
}

export interface SngConfig {
  players: SngPlayerRow[];
  startingPot: number;
}

export interface MttPlayerRow {
  chipCount: number;
  chipMultiplier: number;
  prize: number;
  prizeMultiplier: number;
}

export interface MttConfig {
  players: MttPlayerRow[];
  startingPot: number;
}

export interface GeometricBetConfig {
  allInBetIndex: number;
  betAmounts: number[];
  betPotPcts: number[];
}

export interface AdvancedPlayerConfig {
  defaultBetPct: number;
  autoAllocateLastTwo: boolean;
  noDonkBet: boolean;
  allInThresholdEnabled: boolean;
  allInThresholdPct: number;
  remainingBetAllIn: boolean;
  remainingBetPct: number;
  useCustomFlop: boolean;
  useCustomTurn: boolean;
  useCustomRiver: boolean;
}

export interface LimitConfig {
  flopBet: number;
  flopCap: number;
  turnBet: number;
  turnCap: number;
  riverBet: number;
  riverCap: number;
}

const defaultAdvancedPlayer: AdvancedPlayerConfig = {
  defaultBetPct: 75,
  autoAllocateLastTwo: true,
  noDonkBet: false,
  allInThresholdEnabled: false,
  allInThresholdPct: 120,
  remainingBetAllIn: false,
  remainingBetPct: 40,
  useCustomFlop: false,
  useCustomTurn: false,
  useCustomRiver: false,
};

const defaultLimitConfig: LimitConfig = {
  flopBet: 1,
  flopCap: 4,
  turnBet: 2,
  turnCap: 4,
  riverBet: 2,
  riverCap: 4,
};

export interface TreeProfile {
  id: string;
  name: string;
  config: TreeConfigLocal;
  betSizeCode?: string;
  createdAt: string;
}

interface TreeConfigLocal {
  startingPot: number;
  effectiveStack: number;
  betSizes: { flop: number[]; turn: number[]; river: number[] };
  raiseCapPerStreet: number;
  numPlayers: number;
  rake?: { percentage: number; cap: number };
  smoothMode?: boolean;
  smoothGradation?: number;
  flopCbet?: number[];
  flopDonk?: number[];
  turnProbe?: number[];
  raiseMultipliers?: {
    flop?: number[];
    turn?: number[];
    river?: number[];
  };
  advancedConfig?: {
    oop: {
      noDonkBet: boolean;
      allInThresholdEnabled: boolean;
      allInThresholdPct: number;
      remainingBetAllIn: boolean;
      remainingBetPct: number;
    };
    ip: {
      noDonkBet: boolean;
      allInThresholdEnabled: boolean;
      allInThresholdPct: number;
      remainingBetAllIn: boolean;
      remainingBetPct: number;
    };
  };
  limitMode?: boolean;
  limitConfig?: {
    flopBet: number;
    flopCap: number;
    turnBet: number;
    turnCap: number;
    riverBet: number;
    riverCap: number;
  };
  /** Per-level pot fractions from geometric bet sizing.
   *  Index 0 = opening bet fraction, index 1+ = raise fractions. */
  perLevelBetFractions?: number[];
}

type TreeConfig = TreeConfigLocal;

// --- Geometric calculation ---

export function computeGeometricBets(
  startingPot: number,
  effectiveStack: number,
  allInBetIndex: number,
): GeometricBetConfig {
  const N = allInBetIndex + 1;
  const P = startingPot;
  const S = effectiveStack;

  if (P <= 0 || S <= 0 || N < 1) {
    return {
      allInBetIndex,
      betAmounts: [0, 0, 0, 0, 0],
      betPotPcts: [0, 0, 0, 0, 0],
    };
  }

  const g = Math.pow((2 * S) / P + 1, 1 / N);
  const betAmounts: number[] = [];
  const betPotPcts: number[] = [];

  for (let i = 0; i < 5; i++) {
    if (i < N) {
      const totalInvested = (P * (Math.pow(g, i + 1) - 1)) / 2;
      const roundedAmount = Math.round(totalInvested * 100) / 100;
      betAmounts.push(roundedAmount);

      // Compute pot % as raise_amount / pot_after_calling
      if (i === 0) {
        betPotPcts.push(Math.round((roundedAmount / P) * 1000) / 10);
      } else {
        const prevTotal = betAmounts[i - 1];
        const potAfterCall = P + 2 * prevTotal;
        const raiseAmount = roundedAmount - prevTotal;
        betPotPcts.push(Math.round((raiseAmount / potAfterCall) * 1000) / 10);
      }
    } else {
      betAmounts.push(0);
      betPotPcts.push(0);
    }
  }

  return { allInBetIndex, betAmounts, betPotPcts };
}

/** Recompute pot percentages from manually edited bet amounts */
export function recomputePotPcts(
  startingPot: number,
  betAmounts: number[],
  allInBetIndex: number,
): number[] {
  const P = startingPot;
  const pcts: number[] = [];

  for (let i = 0; i < 5; i++) {
    if (i > allInBetIndex || betAmounts[i] <= 0) {
      pcts.push(0);
    } else if (i === 0) {
      pcts.push(Math.round((betAmounts[0] / P) * 1000) / 10);
    } else {
      const prevTotal = betAmounts[i - 1];
      const potAfterCall = P + 2 * prevTotal;
      const raiseAmount = betAmounts[i] - prevTotal;
      pcts.push(Math.round((raiseAmount / potAfterCall) * 1000) / 10);
    }
  }

  return pcts;
}

// --- Store ---

interface SolverConfigStore {
  // Existing fields (backward compat)
  configName: string;
  label: string;
  treeConfig: TreeConfig;
  iterations: number;
  buckets: number;

  // Game type + configs
  gameType: GameType;
  cashConfig: CashConfig;
  sngConfig: SngConfig;
  mttConfig: MttConfig;

  // Geometric bet sizing
  geometricConfig: GeometricBetConfig;

  // Bet sizes (per-street, from Advanced tab)
  betSizes: { flop: number[]; turn: number[]; river: number[] };

  // Tree builder enhancements
  smoothMode: boolean;
  smoothGradation: number;
  betSizeCode: string; // R/M/B code text
  flopCbet: number[];
  flopDonk: number[];
  turnProbe: number[];
  raiseMultipliers: { flop: number[]; turn: number[]; river: number[] };
  profiles: TreeProfile[];

  // Board selector
  boardCards: string[];
  boardSelectorOpen: boolean;

  // Advanced tree config (OOP/IP)
  advancedConfig: { oop: AdvancedPlayerConfig; ip: AdvancedPlayerConfig };

  // Limit config
  limitMode: boolean;
  limitConfig: LimitConfig;

  // Dialog visibility
  stacksDialogOpen: boolean;
  treeDialogOpen: boolean;

  // Actions - presets
  setPreset: (
    name: string,
    label: string,
    config: TreeConfig,
    iterations: number,
    buckets: number,
  ) => void;
  setTreeConfig: (config: Partial<TreeConfig>) => void;
  setIterations: (n: number) => void;
  setBuckets: (n: number) => void;

  // Actions - dialogs
  openStacksDialog: () => void;
  closeStacksDialog: () => void;
  openTreeDialog: () => void;
  closeTreeDialog: () => void;

  // Actions - game type
  setGameType: (type: GameType) => void;

  // Actions - cash config
  setCashConfig: (config: Partial<CashConfig>) => void;

  // Actions - SNG
  updateSngPlayer: (index: number, changes: Partial<SngPlayerRow>) => void;
  addSngPlayer: () => void;
  removeSngPlayer: (index: number) => void;
  setSngStartingPot: (pot: number) => void;

  // Actions - MTT
  updateMttPlayer: (index: number, changes: Partial<MttPlayerRow>) => void;
  addMttPlayer: () => void;
  removeMttPlayer: (index: number) => void;
  setMttStartingPot: (pot: number) => void;

  // Actions - geometric
  setAllInBetIndex: (index: number) => void;
  updateGeometricBetAmount: (index: number, amount: number) => void;
  recalcGeometric: () => void;

  // Actions - bet sizes
  setBetSizes: (sizes: { flop: number[]; turn: number[]; river: number[] }) => void;

  // Enhanced tree builder
  setSmoothMode: (enabled: boolean) => void;
  setSmoothGradation: (n: number) => void;
  setBetSizeCode: (code: string) => void;
  setFlopCbet: (sizes: number[]) => void;
  setFlopDonk: (sizes: number[]) => void;
  setTurnProbe: (sizes: number[]) => void;
  setRaiseMultipliers: (mults: { flop?: number[]; turn?: number[]; river?: number[] }) => void;
  saveProfile: (name: string) => void;
  loadProfile: (id: string) => void;
  deleteProfile: (id: string) => void;

  // Board selector actions
  openBoardSelector: () => void;
  closeBoardSelector: () => void;
  toggleBoardCard: (card: string) => void;
  clearBoard: () => void;
  randomBoard: (count: number) => void;

  // Advanced config actions
  setAdvancedConfig: (player: 'oop' | 'ip', config: Partial<AdvancedPlayerConfig>) => void;

  // Limit config actions
  setLimitMode: (enabled: boolean) => void;
  setLimitConfig: (config: Partial<LimitConfig>) => void;

  // Sync treeConfig from dialog state
  syncTreeConfig: () => void;
}

const defaultGeometric: GeometricBetConfig = {
  allInBetIndex: 4,
  betAmounts: [8.5, 21, 38.5, 64, 100],
  betPotPcts: recomputePotPcts(40, [8.5, 21, 38.5, 64, 100], 4),
};

export const useSolverConfig = create<SolverConfigStore>((set, get) => ({
  // Existing defaults
  configName: 'hu_btn_bb_srp_100bb',
  label: 'HU BTN vs BB SRP 100bb',
  treeConfig: {
    startingPot: 5,
    effectiveStack: 97.5,
    betSizes: { flop: [0.33], turn: [0.66], river: [0.75] },
    raiseCapPerStreet: 4,
    numPlayers: 2,
  },
  iterations: 200000,
  buckets: 100,

  // Game type
  gameType: 'cash',
  cashConfig: { startingPot: 40, effectiveStack: 100, rakePercent: 0, rakeCap: 3 },
  sngConfig: {
    players: [
      { chipCount: 1000, prize: 100 },
      { chipCount: 1000, prize: 0 },
    ],
    startingPot: 100,
  },
  mttConfig: {
    players: [
      { chipCount: 1000, chipMultiplier: 1, prize: 100, prizeMultiplier: 1 },
      { chipCount: 1000, chipMultiplier: 1, prize: 0, prizeMultiplier: 1 },
    ],
    startingPot: 100,
  },

  // Geometric
  geometricConfig: defaultGeometric,

  // Bet sizes
  betSizes: { flop: [0.33], turn: [0.66], river: [0.75] },

  // Enhanced tree builder
  smoothMode: false,
  smoothGradation: 10,
  betSizeCode: '',
  flopCbet: [],
  flopDonk: [],
  turnProbe: [],
  raiseMultipliers: { flop: [], turn: [], river: [] },
  profiles: JSON.parse(
    localStorage.getItem('cardpilot-solver-tree-profiles') || '[]',
  ) as TreeProfile[],

  // Board selector
  boardCards: [],
  boardSelectorOpen: false,

  // Advanced config
  advancedConfig: { oop: { ...defaultAdvancedPlayer }, ip: { ...defaultAdvancedPlayer } },

  // Limit config
  limitMode: false,
  limitConfig: { ...defaultLimitConfig },

  // Dialogs
  stacksDialogOpen: false,
  treeDialogOpen: false,

  // --- Actions ---

  setPreset: (configName, label, treeConfig, iterations, buckets) => {
    set({
      configName,
      label,
      treeConfig,
      iterations,
      buckets,
      cashConfig: {
        startingPot: treeConfig.startingPot,
        effectiveStack: treeConfig.effectiveStack,
        rakePercent: 0,
        rakeCap: 3,
      },
      betSizes: treeConfig.betSizes,
      geometricConfig: computeGeometricBets(treeConfig.startingPot, treeConfig.effectiveStack, 4),
    });
  },

  setTreeConfig: (config) => set((s) => ({ treeConfig: { ...s.treeConfig, ...config } })),

  setIterations: (iterations) => set({ iterations }),
  setBuckets: (buckets) => set({ buckets }),

  // Dialogs
  openStacksDialog: () => set({ stacksDialogOpen: true }),
  closeStacksDialog: () => set({ stacksDialogOpen: false }),
  openTreeDialog: () => set({ treeDialogOpen: true }),
  closeTreeDialog: () => set({ treeDialogOpen: false }),

  // Game type
  setGameType: (gameType) => set({ gameType }),

  // Cash config
  setCashConfig: (config) =>
    set((s) => ({
      cashConfig: { ...s.cashConfig, ...config },
      geometricConfig: computeGeometricBets(
        config.startingPot ?? s.cashConfig.startingPot,
        config.effectiveStack ?? s.cashConfig.effectiveStack,
        s.geometricConfig.allInBetIndex,
      ),
    })),

  // SNG
  updateSngPlayer: (index, changes) =>
    set((s) => ({
      sngConfig: {
        ...s.sngConfig,
        players: s.sngConfig.players.map((p, i) => (i === index ? { ...p, ...changes } : p)),
      },
    })),
  addSngPlayer: () =>
    set((s) => {
      if (s.sngConfig.players.length >= 10) return s;
      return {
        sngConfig: {
          ...s.sngConfig,
          players: [...s.sngConfig.players, { chipCount: 0, prize: 0 }],
        },
      };
    }),
  removeSngPlayer: (index) =>
    set((s) => {
      if (s.sngConfig.players.length <= 2) return s;
      return {
        sngConfig: {
          ...s.sngConfig,
          players: s.sngConfig.players.filter((_, i) => i !== index),
        },
      };
    }),
  setSngStartingPot: (pot) => set((s) => ({ sngConfig: { ...s.sngConfig, startingPot: pot } })),

  // MTT
  updateMttPlayer: (index, changes) =>
    set((s) => ({
      mttConfig: {
        ...s.mttConfig,
        players: s.mttConfig.players.map((p, i) => (i === index ? { ...p, ...changes } : p)),
      },
    })),
  addMttPlayer: () =>
    set((s) => {
      if (s.mttConfig.players.length >= 20) return s;
      return {
        mttConfig: {
          ...s.mttConfig,
          players: [
            ...s.mttConfig.players,
            { chipCount: 0, chipMultiplier: 1, prize: 0, prizeMultiplier: 1 },
          ],
        },
      };
    }),
  removeMttPlayer: (index) =>
    set((s) => {
      if (s.mttConfig.players.length <= 2) return s;
      return {
        mttConfig: {
          ...s.mttConfig,
          players: s.mttConfig.players.filter((_, i) => i !== index),
        },
      };
    }),
  setMttStartingPot: (pot) => set((s) => ({ mttConfig: { ...s.mttConfig, startingPot: pot } })),

  // Geometric
  setAllInBetIndex: (index) => {
    const s = get();
    const pot = s.gameType === 'cash' ? s.cashConfig.startingPot : s.sngConfig.startingPot;
    const stack =
      s.gameType === 'cash'
        ? s.cashConfig.effectiveStack
        : (s.sngConfig.players[0]?.chipCount ?? 1000);
    set({ geometricConfig: computeGeometricBets(pot, stack, index) });
  },

  updateGeometricBetAmount: (index, amount) =>
    set((s) => {
      const newAmounts = [...s.geometricConfig.betAmounts];
      newAmounts[index] = amount;
      const pot = s.gameType === 'cash' ? s.cashConfig.startingPot : s.sngConfig.startingPot;
      const newPcts = recomputePotPcts(pot, newAmounts, s.geometricConfig.allInBetIndex);
      return {
        geometricConfig: {
          ...s.geometricConfig,
          betAmounts: newAmounts,
          betPotPcts: newPcts,
        },
      };
    }),

  recalcGeometric: () => {
    const s = get();
    const pot = s.gameType === 'cash' ? s.cashConfig.startingPot : s.sngConfig.startingPot;
    const stack =
      s.gameType === 'cash'
        ? s.cashConfig.effectiveStack
        : (s.sngConfig.players[0]?.chipCount ?? 1000);
    set({
      geometricConfig: computeGeometricBets(pot, stack, s.geometricConfig.allInBetIndex),
    });
  },

  // Bet sizes
  setBetSizes: (betSizes) => set({ betSizes }),

  // Enhanced tree builder
  setSmoothMode: (smoothMode) => set({ smoothMode }),
  setSmoothGradation: (smoothGradation) => set({ smoothGradation }),
  setBetSizeCode: (betSizeCode) => set({ betSizeCode }),
  setFlopCbet: (flopCbet) => set({ flopCbet }),
  setFlopDonk: (flopDonk) => set({ flopDonk }),
  setTurnProbe: (turnProbe) => set({ turnProbe }),
  setRaiseMultipliers: (mults) =>
    set((s) => ({ raiseMultipliers: { ...s.raiseMultipliers, ...mults } })),

  saveProfile: (name) => {
    const s = get();
    const profile: TreeProfile = {
      id: crypto.randomUUID(),
      name,
      config: {
        ...s.treeConfig,
        smoothMode: s.smoothMode,
        smoothGradation: s.smoothGradation,
        flopCbet: s.flopCbet.length > 0 ? s.flopCbet : undefined,
        flopDonk: s.flopDonk.length > 0 ? s.flopDonk : undefined,
        turnProbe: s.turnProbe.length > 0 ? s.turnProbe : undefined,
        raiseMultipliers:
          s.raiseMultipliers.flop.length > 0 ||
          s.raiseMultipliers.turn.length > 0 ||
          s.raiseMultipliers.river.length > 0
            ? s.raiseMultipliers
            : undefined,
      },
      betSizeCode: s.betSizeCode || undefined,
      createdAt: new Date().toISOString(),
    };
    const profiles = [...s.profiles, profile];
    localStorage.setItem('cardpilot-solver-tree-profiles', JSON.stringify(profiles));
    set({ profiles });
  },

  loadProfile: (id) => {
    const s = get();
    const profile = s.profiles.find((p) => p.id === id);
    if (!profile) return;
    set({
      treeConfig: {
        startingPot: profile.config.startingPot,
        effectiveStack: profile.config.effectiveStack,
        betSizes: profile.config.betSizes,
        raiseCapPerStreet: profile.config.raiseCapPerStreet,
        numPlayers: profile.config.numPlayers,
      },
      betSizes: profile.config.betSizes,
      smoothMode: profile.config.smoothMode ?? false,
      smoothGradation: profile.config.smoothGradation ?? 10,
      flopCbet: profile.config.flopCbet ?? [],
      flopDonk: profile.config.flopDonk ?? [],
      turnProbe: profile.config.turnProbe ?? [],
      raiseMultipliers: {
        flop: profile.config.raiseMultipliers?.flop ?? [],
        turn: profile.config.raiseMultipliers?.turn ?? [],
        river: profile.config.raiseMultipliers?.river ?? [],
      },
      betSizeCode: profile.betSizeCode ?? '',
    });
  },

  deleteProfile: (id) => {
    const s = get();
    const profiles = s.profiles.filter((p) => p.id !== id);
    localStorage.setItem('cardpilot-solver-tree-profiles', JSON.stringify(profiles));
    set({ profiles });
  },

  // Board selector
  openBoardSelector: () => set({ boardSelectorOpen: true }),
  closeBoardSelector: () => set({ boardSelectorOpen: false }),
  toggleBoardCard: (card) =>
    set((s) => {
      if (s.boardCards.includes(card)) {
        return { boardCards: s.boardCards.filter((c) => c !== card) };
      }
      if (s.boardCards.length >= 5) return s;
      return { boardCards: [...s.boardCards, card] };
    }),
  clearBoard: () => set({ boardCards: [] }),
  randomBoard: (count) => {
    const RANKS = 'AKQJT98765432';
    const SUITS = 'shdc';
    const deck: string[] = [];
    for (const r of RANKS) {
      for (const s of SUITS) {
        deck.push(`${r}${s}`);
      }
    }
    // Shuffle
    for (let i = deck.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [deck[i], deck[j]] = [deck[j], deck[i]];
    }
    set({ boardCards: deck.slice(0, count) });
  },

  // Advanced config
  setAdvancedConfig: (player, config) =>
    set((s) => ({
      advancedConfig: {
        ...s.advancedConfig,
        [player]: { ...s.advancedConfig[player], ...config },
      },
    })),

  // Limit config
  setLimitMode: (limitMode) => set({ limitMode }),
  setLimitConfig: (config) => set((s) => ({ limitConfig: { ...s.limitConfig, ...config } })),

  // Sync tree config from dialog state
  syncTreeConfig: () => {
    const s = get();
    const pot = s.gameType === 'cash' ? s.cashConfig.startingPot : s.sngConfig.startingPot;
    const stack =
      s.gameType === 'cash'
        ? s.cashConfig.effectiveStack
        : (s.sngConfig.players[0]?.chipCount ?? 1000);

    // Rake (cash game only)
    const rake =
      s.gameType === 'cash' && s.cashConfig.rakePercent > 0
        ? { percentage: s.cashConfig.rakePercent / 100, cap: s.cashConfig.rakeCap }
        : undefined;

    // Advanced config (only include if any non-default)
    const pick = (p: AdvancedPlayerConfig) => ({
      noDonkBet: p.noDonkBet,
      allInThresholdEnabled: p.allInThresholdEnabled,
      allInThresholdPct: p.allInThresholdPct,
      remainingBetAllIn: p.remainingBetAllIn,
      remainingBetPct: p.remainingBetPct,
    });
    const hasAdvanced =
      s.advancedConfig.oop.noDonkBet ||
      s.advancedConfig.oop.allInThresholdEnabled ||
      s.advancedConfig.oop.remainingBetAllIn ||
      s.advancedConfig.ip.noDonkBet ||
      s.advancedConfig.ip.allInThresholdEnabled ||
      s.advancedConfig.ip.remainingBetAllIn;

    // Context-aware bet sizes
    const betSizes = {
      ...s.betSizes,
      ...(s.flopCbet.length > 0 && { flopCbet: s.flopCbet }),
      ...(s.flopDonk.length > 0 && { flopDonk: s.flopDonk }),
      ...(s.turnProbe.length > 0 && { turnProbe: s.turnProbe }),
      ...((s.raiseMultipliers.flop.length > 0 ||
        s.raiseMultipliers.turn.length > 0 ||
        s.raiseMultipliers.river.length > 0) && {
        raiseMultipliers: s.raiseMultipliers,
      }),
    };

    // Limit mode
    const limitMode = s.limitMode ?? false;

    // Compute per-level bet fractions from geometric config
    const geo = s.geometricConfig;
    const activeAmounts = geo.betAmounts.slice(0, geo.allInBetIndex + 1);
    let perLevelBetFractions: number[] | undefined;
    let raiseCapFromGeo: number | undefined;
    if (pot > 0 && activeAmounts.length > 0 && activeAmounts[0] > 0) {
      perLevelBetFractions = [];
      for (let i = 0; i < activeAmounts.length; i++) {
        if (activeAmounts[i] <= 0) break;
        if (i === 0) {
          perLevelBetFractions.push(activeAmounts[0] / pot);
        } else {
          const prevTotal = activeAmounts[i - 1];
          const potAfterCall = pot + 2 * prevTotal;
          const raiseAmount = activeAmounts[i] - prevTotal;
          perLevelBetFractions.push(potAfterCall > 0 ? raiseAmount / potAfterCall : 1);
        }
      }
      raiseCapFromGeo = activeAmounts.length - 1; // N levels = 1 bet + (N-1) raises
    }

    set({
      treeConfig: {
        startingPot: pot,
        effectiveStack: stack,
        betSizes,
        raiseCapPerStreet: raiseCapFromGeo ?? s.treeConfig.raiseCapPerStreet,
        numPlayers: s.treeConfig.numPlayers,
        rake,
        smoothMode: s.smoothMode || undefined,
        smoothGradation: s.smoothMode ? s.smoothGradation : undefined,
        advancedConfig: hasAdvanced
          ? { oop: pick(s.advancedConfig.oop), ip: pick(s.advancedConfig.ip) }
          : undefined,
        limitMode: limitMode || undefined,
        limitConfig: limitMode ? s.limitConfig : undefined,
        perLevelBetFractions,
      },
    });
  },
}));
