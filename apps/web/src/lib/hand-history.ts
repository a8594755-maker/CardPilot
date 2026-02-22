// Hand History — localStorage-based with 30-day auto-expiry

export interface HandRecord {
  id: string;
  createdAt: number;
  expiresAt: number;
  gameType: "NLH" | "PLO";
  stakes: string;
  tableSize: number;
  position: string;
  heroCards: string[];
  startingHandBucket?: string;
  board: string[];
  runoutBoards?: string[][];
  doubleBoardPayouts?: Array<{ run: 1 | 2 | 3; board: string[]; winners: Array<{ seat: number; amount: number; handName?: string }> }>;
  actions: HandActionRecord[];
  potSize: number;
  stackSize: number;
  result?: number;
  netByPosition?: Record<string, number>;
  isBombPotHand?: boolean;
  isDoubleBoardHand?: boolean;
  tags: string[];
  gtoAnalysis?: GTOAnalysis | null;
  // Extended fields for room-based history
  roomCode?: string;
  roomName?: string;
  tableId?: string;
  handId?: string;
  endedAt?: string; // ISO string
  heroSeat?: number;
  heroName?: string;
  smallBlind?: number;
  bigBlind?: number;
  playersCount?: number;
  didWinAnyRun?: boolean;
  // Per-player showdown info (seat -> cards or "mucked")
  showdownHands?: Record<number, [string, string] | "mucked">;
  playerNames?: Record<number, string>;
  buttonSeat?: number;
  positionsBySeat?: Record<number, string>;
  stacksBySeatAtStart?: Record<number, number>;
  actionTimeline?: HandActionTimelineRecord[];
  potLayers?: unknown;
  payoutLedger?: unknown;
  source?: "local" | "cloud";
}

export interface HandActionRecord {
  seat: number;
  street: string;
  type: string;
  amount: number;
}

export interface HandActionTimelineRecord {
  idx: number;
  street: "PREFLOP" | "FLOP" | "TURN" | "RIVER";
  seat: number;
  type: "fold" | "check" | "call" | "bet" | "raise" | "all_in";
  amount: number;
  betTo?: number;
  raiseTo?: number;
  potBefore: number;
  toCallBefore: number;
  committedThisStreetBefore: number;
  effectiveStackBefore: number;
  at?: number;
}

export interface GTOAnalysis {
  overallScore: number; // 0-100
  streets: StreetAnalysis[];
  analyzedAt: number;
  spots?: LocalGTOSpot[];
  streetScores?: {
    flop: number | null;
    turn: number | null;
    river: number | null;
  };
  precision?: "fast" | "deep";
}

export interface LocalGTOSpot {
  street: string;
  pot: number;
  toCall?: number;
  effectiveStack?: number;
  heroAction: string;
  heroAmount: number;
  recommendedAction: string;
  recommendedMix: {
    raise: number;
    call: number;
    fold: number;
  };
  deviationScore: number;
  evLossBb?: number;
  actionTimelineIdx?: number;
  decisionIndex?: number;
  note?: string;
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

const RANK_ORDER: string[] = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"];

function rankValue(rank: string): number {
  const index = RANK_ORDER.indexOf(rank);
  return index === -1 ? -1 : index;
}

export function classifyStartingHandBucket(heroCards: string[], gameType: HandRecord["gameType"]): string {
  if (!Array.isArray(heroCards) || heroCards.length < 2) return "unknown";

  const cards = heroCards.filter((card) => typeof card === "string" && card.length >= 2);
  if (cards.length < 2) return "unknown";

  if (gameType === "PLO" || cards.length >= 4) {
    const ranks = cards.map((card) => card[0]).filter(Boolean);
    const suits = cards.map((card) => card[1]).filter(Boolean);
    const sortedRanks = [...ranks].sort((a, b) => rankValue(b) - rankValue(a));
    const top = `${sortedRanks[0] ?? "X"}${sortedRanks[1] ?? "X"}`;
    const suitCounts = new Map<string, number>();
    for (const suit of suits) {
      suitCounts.set(suit, (suitCounts.get(suit) ?? 0) + 1);
    }
    const grouped = [...suitCounts.values()].sort((a, b) => b - a);
    if ((grouped[0] ?? 0) >= 2 && (grouped[1] ?? 0) >= 2) return `${top}xx-ds`;
    if ((grouped[0] ?? 0) >= 2) return `${top}xx-ss`;
    return `${top}xx`;
  }

  const [a, b] = cards;
  const [ra, sa] = [a[0], a[1]];
  const [rb, sb] = [b[0], b[1]];
  const highFirst = rankValue(ra) >= rankValue(rb);
  const high = highFirst ? ra : rb;
  const low = highFirst ? rb : ra;

  if (high === low) return `${high}${low}`;
  if (high === "A" && low === "K") return sa === sb ? "AKs" : "AKo";
  if (high === "A") return sa === sb ? "Axs" : "Axo";
  if (high === "K") return "Kx";
  return sa === sb ? `${high}${low}s` : `${high}${low}o`;
}

function generateId(): string {
  return `h_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function readAll(): HandRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((entry) => normalizeHandRecord(entry))
      .filter((entry): entry is HandRecord => entry !== null);
  } catch {
    return [];
  }
}

function normalizeHandRecord(input: unknown): HandRecord | null {
  if (!input || typeof input !== "object") return null;
  const raw = input as Partial<HandRecord>;

  if (typeof raw.id !== "string") return null;
  if (!Array.isArray(raw.actions) || !Array.isArray(raw.heroCards) || raw.heroCards.length < 2) return null;

  const heroCards = raw.heroCards.map(String).filter((card) => card.length >= 2);
  const gameType = raw.gameType === "PLO" ? "PLO" : "NLH";

  const record: HandRecord = {
    ...raw,
    id: raw.id,
    createdAt: Number(raw.createdAt ?? Date.now()),
    expiresAt: Number(raw.expiresAt ?? Date.now() + RETENTION_MS),
    gameType,
    stakes: typeof raw.stakes === "string" ? raw.stakes : "0/0",
    tableSize: Number(raw.tableSize ?? 0),
    position: typeof raw.position === "string" ? raw.position : "Unknown",
    heroCards,
    startingHandBucket: typeof raw.startingHandBucket === "string"
      ? raw.startingHandBucket
      : classifyStartingHandBucket(heroCards, gameType),
    board: Array.isArray(raw.board) ? raw.board.map(String) : [],
    runoutBoards: Array.isArray(raw.runoutBoards)
      ? raw.runoutBoards.map((run) => Array.isArray(run) ? run.map(String) : [])
      : undefined,
    doubleBoardPayouts: Array.isArray(raw.doubleBoardPayouts)
      ? raw.doubleBoardPayouts.reduce<Array<{ run: 1 | 2 | 3; board: string[]; winners: Array<{ seat: number; amount: number; handName?: string }> }>>((acc, run) => {
          if (!run || typeof run !== "object") return acc;
          const row = run as { run?: number; board?: unknown; winners?: unknown };
          const board = Array.isArray(row.board) ? row.board.map(String) : [];
          const winners: Array<{ seat: number; amount: number; handName?: string }> = [];
          if (Array.isArray(row.winners)) {
            for (const winner of row.winners) {
              if (!winner || typeof winner !== "object") continue;
              const w = winner as { seat?: unknown; amount?: unknown; handName?: unknown };
              winners.push({
                seat: Number(w.seat ?? 0),
                amount: Number(w.amount ?? 0),
                handName: typeof w.handName === "string" ? w.handName : undefined,
              });
            }
          }
          const n = Number(row.run ?? 1);
          const runNo: 1 | 2 | 3 = n === 3 ? 3 : n === 2 ? 2 : 1;
          acc.push({ run: runNo, board, winners });
          return acc;
        }, [])
      : undefined,
    actions: raw.actions
      .filter((a): a is HandActionRecord => Boolean(a && typeof a === "object"))
      .map((a) => ({
        seat: Number(a.seat ?? 0),
        street: String(a.street ?? "PREFLOP"),
        type: String(a.type ?? "check"),
        amount: Number(a.amount ?? 0),
      })),
    potSize: Number(raw.potSize ?? 0),
    stackSize: Number(raw.stackSize ?? 0),
    tags: Array.isArray(raw.tags) ? raw.tags.map(String) : [],
    didWinAnyRun: Boolean(raw.didWinAnyRun),
    netByPosition: raw.netByPosition && typeof raw.netByPosition === "object"
      ? Object.fromEntries(
          Object.entries(raw.netByPosition as Record<string, unknown>).map(([position, net]) => [position, Number(net ?? 0)])
        )
      : undefined,
    isBombPotHand: Boolean(raw.isBombPotHand),
    isDoubleBoardHand: Boolean(raw.isDoubleBoardHand),
    actionTimeline: Array.isArray(raw.actionTimeline) ? raw.actionTimeline : undefined,
    source: raw.source === "cloud" ? "cloud" : "local",
  };

  if (!record.actionTimeline) {
    // Migration-safe default for legacy records that only had actions[].
    // Keep undefined so old records still render while consumers can branch.
    record.actionTimeline = undefined;
  }

  return record;
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
  const startingHandBucket = record.startingHandBucket
    ?? classifyStartingHandBucket(record.heroCards, record.gameType);
  const full: HandRecord = {
    ...record,
    startingHandBucket,
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

/** Room summary derived from local hand records */
export interface LocalRoomSummary {
  roomCode: string;
  roomName: string;
  stakes: string;
  lastPlayedAt: number;
  handsCount: number;
  netResult: number;
  handsWon?: number;
  smallBlind: number;
  bigBlind: number;
}

/** Group local hands by roomCode for room-based history */
export function getHandsByRoom(): { rooms: LocalRoomSummary[]; handsByRoom: Record<string, HandRecord[]> } {
  const all = pruneExpired(readAll())
    .map((hand) => ({
      ...hand,
      actionTimeline: Array.isArray(hand.actionTimeline) ? hand.actionTimeline : undefined,
    }))
    .sort((a, b) => b.createdAt - a.createdAt);
  const byRoom: Record<string, HandRecord[]> = {};

  for (const h of all) {
    const code = h.roomCode || "_local";
    if (!byRoom[code]) byRoom[code] = [];
    byRoom[code].push(h);
  }

  const rooms: LocalRoomSummary[] = Object.entries(byRoom).map(([code, hands]) => {
    const last = hands[0];
    const net = hands.reduce((sum, h) => sum + (h.result ?? 0), 0);
    const handsWon = hands.reduce((count, h) => {
      if (h.didWinAnyRun) return count + 1;
      if ((h.result ?? 0) > 0) return count + 1;
      return count;
    }, 0);
    return {
      roomCode: code,
      roomName: last.roomName || (code === "_local" ? "Local / Unknown" : code),
      stakes: last.stakes,
      lastPlayedAt: last.createdAt,
      handsCount: hands.length,
      netResult: net,
      handsWon,
      smallBlind: last.smallBlind ?? 0,
      bigBlind: last.bigBlind ?? 0,
    };
  });

  rooms.sort((a, b) => b.lastPlayedAt - a.lastPlayedAt);
  return { rooms, handsByRoom: byRoom };
}

/** Generate PokerStars-style hand history text */
export function formatHandAsPokerStars(hand: HandRecord): string {
  const lines: string[] = [];
  const ts = hand.endedAt ? new Date(hand.endedAt).toLocaleString() : new Date(hand.createdAt).toLocaleString();
  const hid = hand.handId || hand.id;
  lines.push(`PokerStars Hand #${hid}: Hold'em No Limit (${hand.stakes}) - ${ts}`);
  lines.push(`Table '${hand.roomName || hand.roomCode || "CardPilot"}' ${hand.tableSize}-max Seat #${hand.heroSeat ?? "Unknown"} is the button`);

  // Player names if available
  if (hand.playerNames) {
    for (const [seatStr, name] of Object.entries(hand.playerNames)) {
      lines.push(`Seat ${seatStr}: ${name}`);
    }
  }

  lines.push(`*** HOLE CARDS ***`);
  lines.push(`Dealt to ${hand.heroName || "Hero"} [${hand.heroCards.join(" ")}]`);

  const STREETS = ["PREFLOP", "FLOP", "TURN", "RIVER"];
  for (const street of STREETS) {
    const acts = hand.actions.filter((a) => a.street.toUpperCase() === street);
    if (!acts.length) continue;

    if (street === "FLOP" && hand.board.length >= 3) {
      lines.push(`*** FLOP *** [${hand.board.slice(0, 3).join(" ")}]`);
    } else if (street === "TURN" && hand.board.length >= 4) {
      lines.push(`*** TURN *** [${hand.board.slice(0, 3).join(" ")}] [${hand.board[3]}]`);
    } else if (street === "RIVER" && hand.board.length >= 5) {
      lines.push(`*** RIVER *** [${hand.board.slice(0, 4).join(" ")}] [${hand.board[4]}]`);
    }

    for (const a of acts) {
      const name = hand.playerNames?.[a.seat] || `Seat ${a.seat}`;
      const amt = a.amount > 0 ? ` ${a.amount}` : "";
      lines.push(`${name}: ${a.type}s${amt}`);
    }
  }

  if (hand.board.length > 0) {
    lines.push(`*** SUMMARY ***`);
    lines.push(`Total pot ${hand.potSize} | Board [${hand.board.join(" ")}]`);
  }

  if (hand.runoutBoards && hand.runoutBoards.length > 1) {
    hand.runoutBoards.forEach((b, i) => {
      lines.push(`Run ${i + 1}: [${b.join(" ")}]`);
    });
  }

  const net = hand.result ?? 0;
  lines.push(`${hand.heroName || "Hero"} ${net >= 0 ? "collected" : "lost"} ${Math.abs(net)} chips (net: ${net >= 0 ? "+" : ""}${net})`);

  return lines.join("\n");
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

/** Export all hand records as a JSON string. */
export function exportHands(): string {
  const records = pruneExpired(readAll());
  return JSON.stringify(records, null, 2);
}

/** Import hands from a JSON string, deduplicating by handId (or id). Returns count of newly added hands. */
export function importHands(json: string): number {
  const parsed = JSON.parse(json) as unknown;
  if (!Array.isArray(parsed)) throw new Error("Invalid format: expected an array of hand records.");

  const incoming = parsed
    .map((entry) => normalizeHandRecord(entry))
    .filter((entry): entry is HandRecord => entry !== null);

  if (incoming.length === 0) throw new Error("No valid hand records found in the imported file.");

  let existing = pruneExpired(readAll());

  // Build a set of existing keys for deduplication
  const existingKeys = new Set<string>();
  for (const h of existing) {
    existingKeys.add(h.handId ?? h.id);
  }

  let added = 0;
  for (const h of incoming) {
    const key = h.handId ?? h.id;
    if (!existingKeys.has(key)) {
      existing.push(h);
      existingKeys.add(key);
      added++;
    }
  }

  // Enforce max records (keep newest)
  if (existing.length > MAX_RECORDS) {
    existing.sort((a, b) => a.createdAt - b.createdAt);
    existing = existing.slice(existing.length - MAX_RECORDS);
  }

  writeAll(existing);
  return added;
}
