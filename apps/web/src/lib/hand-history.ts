// Hand History — localStorage-based with 30-day auto-expiry

export interface HandRecord {
  id: string;
  createdAt: number;
  expiresAt: number;
  gameType: "NLH" | "PLO";
  stakes: string;
  tableSize: number;
  position: string;
  heroCards: [string, string];
  board: string[];
  runoutBoards?: string[][];
  actions: HandActionRecord[];
  potSize: number;
  stackSize: number;
  result?: number;
  tags: string[];
  gtoAnalysis?: GTOAnalysis | null;
}

export interface HandActionRecord {
  seat: number;
  street: string;
  type: string;
  amount: number;
}

export interface GTOAnalysis {
  overallScore: number; // 0-100
  streets: StreetAnalysis[];
  analyzedAt: number;
}

export interface StreetAnalysis {
  street: string;
  action: string;
  gtoAction: string;
  evDiff: number;
  errorType?: string;
  accuracy: "good" | "ok" | "bad";
}

const STORAGE_KEY = "cardpilot_hand_history";
const RETENTION_MS = 30 * 24 * 60 * 60 * 1000; // 30 days
const MAX_RECORDS = 500;

function generateId(): string {
  return `h_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function readAll(): HandRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as HandRecord[];
  } catch {
    return [];
  }
}

function writeAll(records: HandRecord[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
  } catch {
    // storage full — remove oldest
    if (records.length > 10) {
      writeAll(records.slice(-Math.floor(records.length / 2)));
    }
  }
}

function pruneExpired(records: HandRecord[]): HandRecord[] {
  const now = Date.now();
  return records.filter((r) => r.expiresAt > now);
}

export function saveHand(record: Omit<HandRecord, "id" | "createdAt" | "expiresAt">): HandRecord {
  const now = Date.now();
  const full: HandRecord = {
    ...record,
    id: generateId(),
    createdAt: now,
    expiresAt: now + RETENTION_MS,
  };

  let all = pruneExpired(readAll());
  all.push(full);

  // Enforce max records
  if (all.length > MAX_RECORDS) {
    all = all.slice(all.length - MAX_RECORDS);
  }

  writeAll(all);
  return full;
}

export function getHands(filters?: {
  position?: string;
  tags?: string[];
  dateFrom?: number;
  dateTo?: number;
}): HandRecord[] {
  let records = pruneExpired(readAll());

  if (filters?.position) {
    records = records.filter((r) => r.position === filters.position);
  }
  if (filters?.tags && filters.tags.length > 0) {
    records = records.filter((r) => filters.tags!.some((t) => r.tags.includes(t)));
  }
  if (filters?.dateFrom) {
    records = records.filter((r) => r.createdAt >= filters.dateFrom!);
  }
  if (filters?.dateTo) {
    records = records.filter((r) => r.createdAt <= filters.dateTo!);
  }

  return records.sort((a, b) => b.createdAt - a.createdAt);
}

export function getHand(id: string): HandRecord | null {
  return pruneExpired(readAll()).find((r) => r.id === id) ?? null;
}

export function updateHand(id: string, update: Partial<HandRecord>): void {
  const all = readAll();
  const idx = all.findIndex((r) => r.id === id);
  if (idx >= 0) {
    all[idx] = { ...all[idx], ...update };
    writeAll(all);
  }
}

export function clearAllHands(): void {
  localStorage.removeItem(STORAGE_KEY);
}

/**
 * Auto-tag a hand based on its action line.
 */
export function autoTag(actions: HandActionRecord[]): string[] {
  const tags: string[] = [];

  const preflopRaises = actions.filter((a) => a.street === "PREFLOP" && a.type === "raise");
  if (preflopRaises.length >= 2) tags.push("3bet_pot");
  if (preflopRaises.length >= 3) tags.push("4bet_pot");
  if (preflopRaises.length <= 1) tags.push("SRP");

  const allIns = actions.filter((a) => a.type === "all_in");
  if (allIns.length > 0) tags.push("all_in");

  return tags;
}
