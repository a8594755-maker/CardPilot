import { create } from 'zustand';

interface CategoryBreakdown {
  category: string;
  count: number;
  percentage: number;
}

interface RangeVsRangeResult {
  range1Equity: number;
  range2Equity: number;
  range1Combos: number;
  range2Combos: number;
  simulations: number;
  categories1: CategoryBreakdown[];
  categories2: CategoryBreakdown[];
  overlap: number;
  overlapHands: string[];
}

interface RangeVsRangeStore {
  range1: Set<string>;
  range2: Set<string>;
  board: string[];
  activeRange: 1 | 2;
  result: RangeVsRangeResult | null;
  isComputing: boolean;

  setRange1: (hands: string[]) => void;
  setRange2: (hands: string[]) => void;
  toggleRange1Hand: (hand: string) => void;
  toggleRange2Hand: (hand: string) => void;
  setBoard: (board: string[]) => void;
  setActiveRange: (range: 1 | 2) => void;
  setResult: (result: RangeVsRangeResult | null) => void;
  setIsComputing: (computing: boolean) => void;
  clearAll: () => void;
}

export const useRangeVsRange = create<RangeVsRangeStore>((set) => ({
  range1: new Set<string>(),
  range2: new Set<string>(),
  board: [],
  activeRange: 1,
  result: null,
  isComputing: false,

  setRange1: (hands) => set({ range1: new Set(hands) }),
  setRange2: (hands) => set({ range2: new Set(hands) }),

  toggleRange1Hand: (hand) =>
    set((s) => {
      const next = new Set(s.range1);
      if (next.has(hand)) next.delete(hand);
      else next.add(hand);
      return { range1: next };
    }),

  toggleRange2Hand: (hand) =>
    set((s) => {
      const next = new Set(s.range2);
      if (next.has(hand)) next.delete(hand);
      else next.add(hand);
      return { range2: next };
    }),

  setBoard: (board) => set({ board }),
  setActiveRange: (activeRange) => set({ activeRange }),
  setResult: (result) => set({ result }),
  setIsComputing: (isComputing) => set({ isComputing }),
  clearAll: () =>
    set({
      range1: new Set<string>(),
      range2: new Set<string>(),
      board: [],
      result: null,
    }),
}));
