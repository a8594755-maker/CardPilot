import { create } from 'zustand';

type MatrixMode = 'strategy' | 'equity' | 'ev';
type TableDisplayMode = 'combos' | 'percentages' | 'ev';

interface DisplaySettingsStore {
  matrixMode: MatrixMode;
  normalized: boolean;
  locked: boolean;
  tableDisplayMode: TableDisplayMode;
  cardRemoval: boolean;
  setMatrixMode: (mode: MatrixMode) => void;
  setNormalized: (value: boolean) => void;
  toggleNormalize: () => void;
  toggleLock: () => void;
  setTableDisplayMode: (mode: TableDisplayMode) => void;
  toggleCardRemoval: () => void;
  reset: () => void;
}

export const useDisplaySettings = create<DisplaySettingsStore>((set) => ({
  matrixMode: 'strategy',
  normalized: false,
  locked: false,
  tableDisplayMode: 'combos',
  cardRemoval: false,
  setMatrixMode: (matrixMode) => set({ matrixMode }),
  setNormalized: (normalized) => set({ normalized }),
  toggleNormalize: () => set((s) => ({ normalized: !s.normalized })),
  toggleLock: () => set((s) => ({ locked: !s.locked })),
  setTableDisplayMode: (tableDisplayMode) => set({ tableDisplayMode }),
  toggleCardRemoval: () => set((s) => ({ cardRemoval: !s.cardRemoval })),
  reset: () =>
    set({
      matrixMode: 'strategy',
      normalized: false,
      locked: false,
      tableDisplayMode: 'combos',
      cardRemoval: false,
    }),
}));

export type { TableDisplayMode };
