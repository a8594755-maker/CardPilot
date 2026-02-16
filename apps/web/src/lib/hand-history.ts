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
  // Per-player showdown info (seat -> cards or "mucked")
  showdownHands?: Record<number, [string, string] | "mucked">;
  playerNames?: Record<number, string>;
  buttonSeat?: number;
  positionsBySeat?: Record<number, string>;
  stacksBySeatAtStart?: Record<number, number>;
  actionTimeline?: HandActionTimelineRecord[];
  potLayers?: unknown;
  payoutLedger?: unknown;
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
  if (!Array.isArray(raw.actions) || !Array.isArray(raw.heroCards) || raw.heroCards.length !== 2) return null;

  const record: HandRecord = {
    ...raw,
    id: raw.id,
    createdAt: Number(raw.createdAt ?? Date.now()),
    expiresAt: Number(raw.expiresAt ?? Date.now() + RETENTION_MS),
    gameType: raw.gameType === "PLO" ? "PLO" : "NLH",
    stakes: typeof raw.stakes === "string" ? raw.stakes : "0/0",
    tableSize: Number(raw.tableSize ?? 0),
    position: typeof raw.position === "string" ? raw.position : "?",
    heroCards: [String(raw.heroCards[0]), String(raw.heroCards[1])],
    board: Array.isArray(raw.board) ? raw.board.map(String) : [],
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
    actionTimeline: Array.isArray(raw.actionTimeline) ? raw.actionTimeline : undefined,
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

/** Room summary derived from local hand records */
export interface LocalRoomSummary {
  roomCode: string;
  roomName: string;
  stakes: string;
  lastPlayedAt: number;
  handsCount: number;
  netResult: number;
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
    return {
      roomCode: code,
      roomName: last.roomName || (code === "_local" ? "Local / Unknown" : code),
      stakes: last.stakes,
      lastPlayedAt: last.createdAt,
      handsCount: hands.length,
      netResult: net,
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
  lines.push(`Table '${hand.roomName || hand.roomCode || "CardPilot"}' ${hand.tableSize}-max Seat #${hand.heroSeat ?? "?"} is the button`);

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
