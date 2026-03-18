import { create } from 'zustand';
import type {
  DatabaseSummary,
  DatabaseFull,
  DatabaseReport,
  FlopSubsetInfo,
} from '../lib/api-client';

interface DatabaseStore {
  // List view
  databases: DatabaseSummary[];
  selectedId: string | null;

  // Detail view
  currentDatabase: DatabaseFull | null;
  report: DatabaseReport | null;
  subsets: FlopSubsetInfo[];

  // Filters
  flopFilter: {
    textureFilter: 'all' | 'paired' | 'monotone' | 'rainbow' | 'twotone';
    statusFilter: 'all' | 'pending' | 'solved' | 'ignored' | 'error';
    sortBy: 'cards' | 'weight' | 'status' | 'oopEquity' | 'ipEquity';
    sortDir: 'asc' | 'desc';
  };

  // UI state
  showCreateDialog: boolean;
  showAddFlopsDialog: boolean;
  showReport: boolean;

  // Methods
  setDatabases: (databases: DatabaseSummary[]) => void;
  setSelectedId: (id: string | null) => void;
  setCurrentDatabase: (db: DatabaseFull | null) => void;
  setReport: (report: DatabaseReport | null) => void;
  setSubsets: (subsets: FlopSubsetInfo[]) => void;
  setFlopFilter: (filter: Partial<DatabaseStore['flopFilter']>) => void;
  setShowCreateDialog: (show: boolean) => void;
  setShowAddFlopsDialog: (show: boolean) => void;
  setShowReport: (show: boolean) => void;
}

export const useDatabaseStore = create<DatabaseStore>((set) => ({
  databases: [],
  selectedId: null,
  currentDatabase: null,
  report: null,
  subsets: [],

  flopFilter: {
    textureFilter: 'all',
    statusFilter: 'all',
    sortBy: 'cards',
    sortDir: 'asc',
  },

  showCreateDialog: false,
  showAddFlopsDialog: false,
  showReport: false,

  setDatabases: (databases) => set({ databases }),
  setSelectedId: (selectedId) => set({ selectedId }),
  setCurrentDatabase: (currentDatabase) => set({ currentDatabase }),
  setReport: (report) => set({ report }),
  setSubsets: (subsets) => set({ subsets }),
  setFlopFilter: (filter) => set((s) => ({ flopFilter: { ...s.flopFilter, ...filter } })),
  setShowCreateDialog: (showCreateDialog) => set({ showCreateDialog }),
  setShowAddFlopsDialog: (showAddFlopsDialog) => set({ showAddFlopsDialog }),
  setShowReport: (showReport) => set({ showReport }),
}));
