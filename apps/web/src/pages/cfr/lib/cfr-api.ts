// API client functions for CFR strategy viewer endpoints.

const API_BASE = import.meta.env.DEV ? '/api/cfr' : `${import.meta.env.VITE_SERVER_URL || ''}/api/cfr`;

export interface CfrConfig {
  name: string;
  label: string;
  positions: string;
  potType: string;
  stack: string;
  players: number;
  sizes: number;
  solvedFlops: number;
  totalFlops: number;
  progress: number;
  available: boolean;
}

export interface FlopEntry {
  boardId: number;
  flopCards: number[];
  flopLabel: string;
  infoSets: number;
  iterations: number;
  texture: string;
  pairing: string;
  highCard: string;
  connectivity: string;
}

export interface BoardMeta {
  boardId: number;
  flopCards: number[];
  bucketCount: number;
  iterations: number;
  infoSets: number;
  elapsedMs: number;
  betSizes?: { flop: number[]; turn: number[]; river: number[] };
}

export interface BoardDataEntry {
  key: string;
  probs: number[];
}

export interface HandMapData {
  oop: Record<string, number>;
  ip: Record<string, number>;
}

export async function fetchConfigs(): Promise<CfrConfig[]> {
  const res = await fetch(`${API_BASE}/configs`);
  const data = await res.json();
  return data.configs ?? [];
}

export async function fetchFlops(config: string): Promise<FlopEntry[]> {
  const res = await fetch(`${API_BASE}/flops?config=${encodeURIComponent(config)}`);
  const data = await res.json();
  return data.flops ?? [];
}

export async function fetchBoardData(config: string, boardId: number): Promise<{
  meta: BoardMeta;
  entries: BoardDataEntry[];
}> {
  const res = await fetch(`${API_BASE}/board-data?config=${encodeURIComponent(config)}&boardId=${boardId}`);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'Failed to load board data');
  return { meta: data.meta, entries: data.entries };
}

export async function fetchHandMap(config: string, boardId: number): Promise<HandMapData> {
  const res = await fetch(`${API_BASE}/hand-map?config=${encodeURIComponent(config)}&boardId=${boardId}`);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'Failed to load hand map');
  return { oop: data.oop, ip: data.ip };
}

export async function fetchNearestFlop(config: string, cards: string): Promise<{
  boardId: number;
  flopCards: number[];
  flopLabel: string;
  distance: number;
}> {
  const res = await fetch(`${API_BASE}/nearest-flop?config=${encodeURIComponent(config)}&cards=${encodeURIComponent(cards)}`);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'Failed to find nearest flop');
  return data;
}
