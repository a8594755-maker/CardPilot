import { create } from 'zustand';

interface SavedRange {
  name: string;
  hands: string[];
  color: string;
}

interface RangeCategory {
  name: string;
  ranges: SavedRange[];
}

export type WeightDisplayMode = 'intensity' | 'bar';
export type SuitFilter = 'all' | 'spade' | 'heart' | 'diamond' | 'club';

interface RangeEditorStore {
  isOpen: boolean;
  targetPlayer: 0 | 1;
  selectedHands: Set<string>;
  weight: number;
  savedCategories: RangeCategory[];
  playerRanges: [Set<string>, Set<string>];

  // Phase 6 enhancements
  topXPercent: number; // 0-100 slider for top X% of hands
  selectedSuits: SuitFilter[]; // active suit filters
  weightDisplayMode: WeightDisplayMode;
  groupColors: Record<string, string>; // hand class -> group color
  dragSource: { catIdx: number; rangeIdx: number } | null;
  dragTarget: { catIdx: number; rangeIdx: number } | null;

  getPlayerRange: (player: 0 | 1) => Set<string>;
  openEditor: (player: 0 | 1) => void;
  closeEditor: () => void;
  toggleHand: (hand: string) => void;
  selectHand: (hand: string) => void;
  deselectHand: (hand: string) => void;
  setHands: (hands: string[]) => void;
  clearHands: () => void;
  setWeight: (weight: number) => void;
  addCategory: (name: string) => void;
  addRange: (categoryIndex: number, range: SavedRange) => void;
  removeRange: (categoryIndex: number, rangeIndex: number) => void;
  renameRange: (categoryIndex: number, rangeIndex: number, name: string) => void;
  removeCategory: (categoryIndex: number) => void;
  loadSavedRanges: () => void;

  // Phase 6 methods
  setTopXPercent: (pct: number) => void;
  selectTopXPercent: (pct: number) => void;
  removeTopXPercent: (pct: number) => void;
  toggleSuitFilter: (suit: SuitFilter) => void;
  setWeightDisplayMode: (mode: WeightDisplayMode) => void;
  setGroupColor: (hand: string, color: string) => void;
  clearGroupColors: () => void;
  setDragSource: (source: { catIdx: number; rangeIdx: number } | null) => void;
  setDragTarget: (target: { catIdx: number; rangeIdx: number } | null) => void;
  executeDragDrop: () => void;
}

const STORAGE_KEY = 'cardpilot-solver-saved-ranges';

function loadFromStorage(): RangeCategory[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return getDefaultCategories();
}

function saveToStorage(categories: RangeCategory[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(categories));
}

function getDefaultCategories(): RangeCategory[] {
  return [
    {
      name: 'my ranges',
      ranges: [
        { name: 'Premium', hands: ['AA', 'KK', 'QQ', 'AKs', 'AKo'], color: '#3b82f6' },
        { name: 'Small pocket pair', hands: ['22', '33', '44', '55'], color: '#d946ef' },
        { name: 'Mid pocket pair', hands: ['66', '77', '88', '99'], color: '#d946ef' },
      ],
    },
    {
      name: 'Grouped range (example)',
      ranges: [
        { name: 'Premium', hands: ['AA', 'KK', 'QQ', 'JJ', 'AKs', 'AKo'], color: '#3b82f6' },
        { name: 'Medium', hands: ['TT', '99', 'AQs', 'AQo', 'AJs', 'KQs'], color: '#22c55e' },
        { name: 'Weak', hands: ['88', '77', 'ATs', 'A9s', 'KJs', 'QJs', 'JTs'], color: '#ef4444' },
        { name: 'Small pocket', hands: ['66', '55', '44', '33', '22'], color: '#d946ef' },
      ],
    },
  ];
}

export const useRangeEditor = create<RangeEditorStore>((set, get) => ({
  isOpen: false,
  targetPlayer: 0,
  selectedHands: new Set<string>(),
  weight: 100,
  savedCategories: loadFromStorage(),
  playerRanges: [new Set<string>(), new Set<string>()],

  topXPercent: 0,
  selectedSuits: [],
  weightDisplayMode: 'intensity' as WeightDisplayMode,
  groupColors: {},
  dragSource: null,
  dragTarget: null,

  getPlayerRange: (player) => get().playerRanges[player],

  openEditor: (player) => {
    const s = get();
    // Load the player's saved range into the editor
    set({ isOpen: true, targetPlayer: player, selectedHands: new Set(s.playerRanges[player]) });
  },

  closeEditor: () => {
    const s = get();
    // Save the current selection back to the player's range
    const newPlayerRanges: [Set<string>, Set<string>] = [...s.playerRanges] as [
      Set<string>,
      Set<string>,
    ];
    newPlayerRanges[s.targetPlayer] = new Set(s.selectedHands);
    set({ isOpen: false, playerRanges: newPlayerRanges });
  },

  toggleHand: (hand) =>
    set((s) => {
      const next = new Set(s.selectedHands);
      if (next.has(hand)) next.delete(hand);
      else next.add(hand);
      return { selectedHands: next };
    }),

  selectHand: (hand) =>
    set((s) => {
      if (s.selectedHands.has(hand)) return s;
      const next = new Set(s.selectedHands);
      next.add(hand);
      return { selectedHands: next };
    }),

  deselectHand: (hand) =>
    set((s) => {
      if (!s.selectedHands.has(hand)) return s;
      const next = new Set(s.selectedHands);
      next.delete(hand);
      return { selectedHands: next };
    }),

  setHands: (hands) => set({ selectedHands: new Set(hands) }),
  clearHands: () => set({ selectedHands: new Set() }),
  setWeight: (weight) => set({ weight }),

  addCategory: (name) =>
    set((s) => {
      const cats = [...s.savedCategories, { name, ranges: [] }];
      saveToStorage(cats);
      return { savedCategories: cats };
    }),

  addRange: (categoryIndex, range) =>
    set((s) => {
      const cats = s.savedCategories.map((c, i) =>
        i === categoryIndex ? { ...c, ranges: [...c.ranges, range] } : c,
      );
      saveToStorage(cats);
      return { savedCategories: cats };
    }),

  removeRange: (categoryIndex, rangeIndex) =>
    set((s) => {
      const cats = s.savedCategories.map((c, i) =>
        i === categoryIndex ? { ...c, ranges: c.ranges.filter((_, j) => j !== rangeIndex) } : c,
      );
      saveToStorage(cats);
      return { savedCategories: cats };
    }),

  renameRange: (categoryIndex, rangeIndex, name) =>
    set((s) => {
      const cats = s.savedCategories.map((c, i) =>
        i === categoryIndex
          ? { ...c, ranges: c.ranges.map((r, j) => (j === rangeIndex ? { ...r, name } : r)) }
          : c,
      );
      saveToStorage(cats);
      return { savedCategories: cats };
    }),

  removeCategory: (categoryIndex) =>
    set((s) => {
      const cats = s.savedCategories.filter((_, i) => i !== categoryIndex);
      saveToStorage(cats);
      return { savedCategories: cats };
    }),

  loadSavedRanges: () => set({ savedCategories: loadFromStorage() }),

  // Phase 6 methods
  setTopXPercent: (topXPercent) => set({ topXPercent }),

  selectTopXPercent: (pct) => {
    // Select the top X% of hands by equity ranking
    const ranked = getHandRanking();
    const count = Math.round((pct / 100) * ranked.length);
    const selected = new Set(ranked.slice(0, count));
    set({ selectedHands: selected, topXPercent: pct });
  },

  removeTopXPercent: (pct) => {
    // Remove the top X% from current selection
    const ranked = getHandRanking();
    const count = Math.round((pct / 100) * ranked.length);
    const toRemove = new Set(ranked.slice(0, count));
    set((s) => {
      const next = new Set([...s.selectedHands].filter((h) => !toRemove.has(h)));
      return { selectedHands: next };
    });
  },

  toggleSuitFilter: (suit) =>
    set((s) => {
      const next = s.selectedSuits.includes(suit)
        ? s.selectedSuits.filter((sf) => sf !== suit)
        : [...s.selectedSuits, suit];
      return { selectedSuits: next };
    }),

  setWeightDisplayMode: (weightDisplayMode) => set({ weightDisplayMode }),

  setGroupColor: (hand, color) =>
    set((s) => ({ groupColors: { ...s.groupColors, [hand]: color } })),

  clearGroupColors: () => set({ groupColors: {} }),

  setDragSource: (dragSource) => set({ dragSource }),
  setDragTarget: (dragTarget) => set({ dragTarget }),

  executeDragDrop: () => {
    const s = get();
    if (!s.dragSource || !s.dragTarget) return;
    if (
      s.dragSource.catIdx === s.dragTarget.catIdx &&
      s.dragSource.rangeIdx === s.dragTarget.rangeIdx
    ) {
      set({ dragSource: null, dragTarget: null });
      return;
    }

    const cats = [...s.savedCategories];
    const sourceCat = { ...cats[s.dragSource.catIdx] };
    const sourceRanges = [...sourceCat.ranges];
    const [moved] = sourceRanges.splice(s.dragSource.rangeIdx, 1);
    sourceCat.ranges = sourceRanges;
    cats[s.dragSource.catIdx] = sourceCat;

    const targetCat = { ...cats[s.dragTarget.catIdx] };
    const targetRanges = [...targetCat.ranges];
    targetRanges.splice(s.dragTarget.rangeIdx, 0, moved);
    targetCat.ranges = targetRanges;
    cats[s.dragTarget.catIdx] = targetCat;

    saveToStorage(cats);
    set({ savedCategories: cats, dragSource: null, dragTarget: null });
  },
}));

/**
 * Get hands ranked by playability-adjusted preflop strength.
 * Matches GTO+ diffusion order: all pairs grouped early,
 * suited connectors valued highly, weak offsuit hands pushed lower.
 */
function getHandRanking(): string[] {
  return [
    // Premium (1-10)
    'AA',
    'KK',
    'QQ',
    'AKs',
    'JJ',
    'AQs',
    'TT',
    'AKo',
    'AJs',
    'KQs',
    // Strong (11-20)
    '99',
    'ATs',
    'KJs',
    'AQo',
    '88',
    'KTs',
    'QJs',
    'AJo',
    '77',
    'QTs',
    // Good (21-30)
    '66',
    'JTs',
    'A9s',
    'KQo',
    'ATo',
    '55',
    'A8s',
    'K9s',
    'T9s',
    'KJo',
    // Playable (31-40)
    '44',
    'J9s',
    'Q9s',
    'A7s',
    '98s',
    'KTo',
    'QJo',
    '33',
    'A6s',
    '87s',
    // Marginal+ (41-50) — ~25% combo boundary
    '22',
    'A5s',
    'QTo',
    '76s',
    'A4s',
    'JTo',
    '65s',
    'A9o',
    'T9o',
    'K9o',
    // Suited expansion (51-64)
    'A3s',
    'A2s',
    'K8s',
    'K7s',
    'K6s',
    'Q8s',
    'J8s',
    'T8s',
    '97s',
    '86s',
    '75s',
    '64s',
    '54s',
    '43s',
    // Offsuit catch-up (65-77) — ~40% combo boundary
    'A8o',
    'A7o',
    'A6o',
    'A5o',
    'A4o',
    'Q9o',
    'J9o',
    '98o',
    '87o',
    '76o',
    '65o',
    '54o',
    'K8o',
    // More suited (78-100)
    'K5s',
    'K4s',
    'K3s',
    'K2s',
    'Q7s',
    'Q6s',
    'Q5s',
    'Q4s',
    'Q3s',
    'Q2s',
    'J7s',
    'J6s',
    'J5s',
    'J4s',
    'T7s',
    'T6s',
    'T5s',
    '96s',
    '95s',
    '85s',
    '74s',
    '63s',
    '53s',
    // Offsuit expansion (101-118) — ~64% combo boundary
    'A3o',
    'A2o',
    'K7o',
    'K6o',
    'K5o',
    'K4o',
    'K3o',
    'K2o',
    'Q8o',
    'J8o',
    'T8o',
    '97o',
    '86o',
    '75o',
    '64o',
    '53o',
    '43o',
    'Q7o',
    // Remaining suited (119-135)
    'J3s',
    'J2s',
    'T4s',
    'T3s',
    'T2s',
    '94s',
    '93s',
    '92s',
    '84s',
    '83s',
    '82s',
    '73s',
    '72s',
    '62s',
    '52s',
    '42s',
    '32s',
    // Remaining offsuit (136-169)
    'Q6o',
    'Q5o',
    'Q4o',
    'Q3o',
    'Q2o',
    'J7o',
    'J6o',
    'J5o',
    'J4o',
    'J3o',
    'J2o',
    'T7o',
    'T6o',
    'T5o',
    'T4o',
    'T3o',
    'T2o',
    '96o',
    '95o',
    '94o',
    '93o',
    '92o',
    '85o',
    '84o',
    '83o',
    '82o',
    '74o',
    '73o',
    '72o',
    '63o',
    '62o',
    '52o',
    '42o',
    '32o',
  ];
}
