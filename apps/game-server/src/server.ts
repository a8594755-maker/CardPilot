import express from "express";
import cors from "cors";
import { createServer } from "node:http";
import { randomInt, randomUUID } from "node:crypto";
import { Server } from "socket.io";
import { GameTable } from "@cardpilot/game-engine";
import { getPreflopAdvice, getPostflopAdvice, calculateDeviation } from "@cardpilot/advice-engine";
import { calculateEquity, type Card } from "@cardpilot/poker-evaluator";
import { SHOWDOWN_SPEED_DELAYS_MS } from "@cardpilot/shared-types";
import type {
  ActionSubmitPayload, AdvicePayload, LobbyRoomSummary, TableState,
  UpdateSettingsPayload, KickPlayerPayload, TransferOwnershipPayload,
  SetCoHostPayload, GameControlPayload, JoinRoomWithPasswordPayload, AllInPrompt,
  RoomFullState, TimerState, HistoryHandDetailCore, HistoryHandPlayerSummary, HistoryHandSummaryCore,
} from "@cardpilot/shared-types";
import { getRuntimeConfig } from "./config";
import { logError, logInfo, logWarn } from "./logger";
import { SupabasePersistence, type PersistHandHistoryPayload, type RoomRecord, type SessionContextMetadata, type VerifiedIdentity } from "./supabase";
import { RoomManager } from "./room-manager";
import { ClubManager } from "./club-manager";
import type {
  ClubCreatePayload,
  ClubUpdatePayload,
  ClubJoinRequestPayload,
  ClubJoinDecisionPayload,
  ClubInviteCreatePayload,
  ClubInviteRevokePayload,
  ClubMemberUpdateRolePayload,
  ClubMemberKickPayload,
  ClubMemberBanPayload,
  ClubMemberUnbanPayload,
  ClubRulesetCreatePayload,
  ClubRulesetUpdatePayload,
  ClubRulesetSetDefaultPayload,
  ClubTableCreatePayload,
  ClubTableClosePayload,
  ClubTablePausePayload,
  ClubRules,
} from "@cardpilot/shared-types";

const runtimeConfig = getRuntimeConfig();
const app = express();
app.use(cors({ origin: runtimeConfig.corsOrigin, credentials: true }));
app.get("/health", (_req, res) => res.json({ ok: true }));
const DEPLOY_COMMIT_REF =
  process.env.RAILWAY_GIT_COMMIT_SHA ||
  process.env.NETLIFY_COMMIT_REF ||
  process.env.COMMIT_REF ||
  process.env.GIT_COMMIT ||
  "";
app.get("/version", (_req, res) => res.json({ ok: true, commit: DEPLOY_COMMIT_REF || null }));

const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: runtimeConfig.corsOrigin,
    credentials: true
  }
});

type SeatBinding = {
  tableId: string;
  seat: number;
  userId: string;
  name: string;
};

type RoomInfo = RoomRecord & {
  createdAt: string;
};

const ROOM_CODE_CHARS = runtimeConfig.roomCodeAlphabet;

const tables = new Map<string, GameTable>();
const roomsByTableId = new Map<string, RoomInfo>();
const roomCodeToTableId = new Map<string, string>();
const socketSeat = new Map<string, SeatBinding>();
const socketIdentity = new Map<string, VerifiedIdentity>();
const lastAdvice = new Map<string, AdvicePayload>(); // key: `${tableId}:${seat}`

// Pending seat requests: orderId -> request data
type SeatRequest = { orderId: string; tableId: string; seat: number; buyIn: number; userId: string; userName: string; socketId: string; isRestore: boolean };
const pendingSeatRequests = new Map<string, SeatRequest>();
const autoDealSchedule = new Map<string, ReturnType<typeof setTimeout>>();
const pendingAllInPrompts = new Map<string, { handId: string; prompt: AllInPrompt }>();
const pendingRunCountTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
const pendingShowdownTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
const handIdleWatchdogs = new Map<string, ReturnType<typeof setTimeout>>();
const HAND_IDLE_TIMEOUT_MS = runtimeConfig.handIdleTimeoutMs;

// Deferred actions: stand-up seats and pause requests that wait for hand to end
const pendingStandUps = new Map<string, Set<number>>(); // tableId → set of seats
const pendingTableLeaves = new Map<string, Set<string>>(); // tableId -> socketIds that leave once hand ends
const pendingPause = new Map<string, { userId: string; displayName: string }>(); // tableId → who requested

// Session stats: persisted per roomCode+userId for the life of the room
type PlayerSessionEntry = {
  userId: string;
  name: string;
  totalBuyIn: number;
  handsPlayed: number;
  lastStack: number;
  lastStackUpdatedAt: number;
};
const sessionStatsByRoomCode = new Map<string, Map<string, PlayerSessionEntry>>(); // roomCode -> userId -> entry

// Deposit requests: seated player asks for more chips, host approves, credited at next hand start
type DepositRequest = { orderId: string; tableId: string; seat: number; userId: string; userName: string; amount: number; approved: boolean };
const pendingDeposits = new Map<string, DepositRequest>(); // orderId → request
const supabase = new SupabasePersistence();
if (!supabase.enabled()) {
  logWarn({
    event: "supabase.disabled",
    message: "Supabase persistence is DISABLED — hand history, room persistence, and player profiles will not be saved. Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to enable.",
  });
}

app.get("/healthz", (_req, res) => {
  res.status(200).json({
    ok: true,
    service: "cardpilot-game-server",
    configVersion: runtimeConfig.version,
    env: runtimeConfig.envName,
    uptimeSec: Math.floor(process.uptime()),
    commit: DEPLOY_COMMIT_REF || null,
    supabaseEnabled: supabase.enabled(),
    activeTables: tables.size,
    activeRooms: roomsByTableId.size,
  });
});

// Room manager handles ownership, settings, timers, kick/ban, auto-close
const roomManager = new RoomManager((tableId, event, data) => {
  io.to(tableId).emit(event, data);
});

// Club manager handles club lifecycle, membership, permissions, rulesets
const clubManager = new ClubManager();

io.use(async (socket, next) => {
  const auth = (socket.handshake.auth ?? {}) as {
    accessToken?: string;
    displayName?: string;
    userId?: string; // Accept userId from client
  };

  try {
    const identity = await supabase.verifyAccessToken(auth.accessToken, auth.displayName);
    // If client sends userId and server uses guest fallback, use client's userId instead
    if (auth.userId && identity.userId.startsWith('guest-')) {
      logInfo({
        event: "auth.identity.override_guest",
        userId: auth.userId,
        message: "Using client-provided userId in guest fallback mode.",
      });
      socketIdentity.set(socket.id, {
        userId: auth.userId,
        displayName: identity.displayName
      });
    } else {
      socketIdentity.set(socket.id, identity);
    }
    next();
  } catch {
    next(new Error("unauthorized"));
  }
});

function registerRoom(room: RoomInfo): void {
  roomsByTableId.set(room.tableId, room);
  roomCodeToTableId.set(room.roomCode, room.tableId);
}

function createTableIfNeeded(room: RoomInfo): GameTable {
  let table = tables.get(room.tableId);
  if (!table) {
    const settings = roomManager.getRoom(room.tableId)?.settings;
    const simulatedFeeEnabled = settings?.simulatedFeeEnabled ?? false;
    const simulatedFeeCap = settings?.simulatedFeeCap ?? 0;
    table = new GameTable({
      tableId: room.tableId,
      smallBlind: room.smallBlind,
      bigBlind: room.bigBlind,
      ante: settings?.ante ?? 0,
      rakeEnabled: simulatedFeeEnabled,
      rakePercent: simulatedFeeEnabled ? (settings?.simulatedFeePercent ?? 0) : 0,
      rakeCap: simulatedFeeEnabled && simulatedFeeCap > 0 ? simulatedFeeCap : undefined,
    });
    tables.set(room.tableId, table);
  }
  return table;
}

function bindingByUser(tableId: string, userId: string): SeatBinding | undefined {
  for (const binding of socketSeat.values()) {
    if (binding.tableId === tableId && binding.userId === userId) {
      return binding;
    }
  }
  return undefined;
}

function bindingsByTable(tableId: string): Array<{ socketId: string; binding: SeatBinding }> {
  const result: Array<{ socketId: string; binding: SeatBinding }> = [];
  for (const [socketId, binding] of socketSeat.entries()) {
    if (binding.tableId === tableId) {
      result.push({ socketId, binding });
    }
  }
  return result;
}

function socketIdBySeat(tableId: string, seat: number): string {
  for (const [sid, binding] of socketSeat.entries()) {
    if (binding.tableId === tableId && binding.seat === seat) return sid;
  }
  return "";
}

function roomCodeForTable(tableId: string): string | null {
  return roomsByTableId.get(tableId)?.roomCode ?? null;
}

function getRoomSessionStats(tableId: string, create = false): Map<string, PlayerSessionEntry> | undefined {
  const roomCode = roomCodeForTable(tableId);
  if (!roomCode) return undefined;
  if (!create) return sessionStatsByRoomCode.get(roomCode);
  let stats = sessionStatsByRoomCode.get(roomCode);
  if (!stats) {
    stats = new Map<string, PlayerSessionEntry>();
    sessionStatsByRoomCode.set(roomCode, stats);
  }
  return stats;
}

function recordSessionBuyIn(tableId: string, userId: string, name: string, amount: number): void {
  const roomStats = getRoomSessionStats(tableId, true);
  if (!roomStats) return;
  const existing = roomStats.get(userId);
  if (existing) {
    existing.totalBuyIn += amount;
    existing.name = name;
  } else {
    roomStats.set(userId, {
      userId,
      name,
      totalBuyIn: amount,
      handsPlayed: 0,
      lastStack: 0,
      lastStackUpdatedAt: 0,
    });
  }
}

function setSessionLastStack(tableId: string, userId: string, name: string, stack: number): void {
  const roomStats = getRoomSessionStats(tableId, true);
  if (!roomStats) return;
  const existing = roomStats.get(userId);
  const updatedAt = Date.now();
  if (existing) {
    existing.lastStack = stack;
    existing.name = name;
    existing.lastStackUpdatedAt = updatedAt;
    return;
  }
  roomStats.set(userId, {
    userId,
    name,
    totalBuyIn: 0,
    handsPlayed: 0,
    lastStack: stack,
    lastStackUpdatedAt: updatedAt,
  });
}

function getRestorableStack(tableId: string, userId: string): number | null {
  const room = roomManager.getRoom(tableId);
  if (!room?.settings.roomFundsTracking) return null;

  const roomStats = getRoomSessionStats(tableId, false);
  if (!roomStats) return null;
  const existing = roomStats.get(userId);
  if (!existing) return null;

  if (existing.lastStack <= 0) return null;
  if (existing.lastStackUpdatedAt <= 0) return null;

  const ageMs = Date.now() - existing.lastStackUpdatedAt;
  if (ageMs > runtimeConfig.tableBalanceRejoinWindowMs) return null;

  return existing.lastStack;
}

function incrementHandsPlayed(tableId: string, playerUserIds: string[]): void {
  const roomStats = getRoomSessionStats(tableId, false);
  if (!roomStats) return;
  for (const uid of playerUserIds) {
    const entry = roomStats.get(uid);
    if (entry) entry.handsPlayed += 1;
  }
}

function syncSessionStacksFromState(tableId: string, state: TableState): void {
  for (const player of state.players) {
    setSessionLastStack(tableId, player.userId, player.name, player.stack);
  }
}

function applyApprovedDeposits(tableId: string): void {
  const table = tables.get(tableId);
  if (!table) return;
  const room = roomManager.getRoom(tableId);
  if (!room) return;
  const toRemove: string[] = [];
  const stateBefore = table.getPublicState();
  const stackBySeatBefore = new Map<number, number>(stateBefore.players.map((player) => [player.seat, player.stack]));
  for (const [orderId, deposit] of pendingDeposits.entries()) {
    if (deposit.tableId !== tableId || !deposit.approved) continue;
    try {
      const currentStack = stackBySeatBefore.get(deposit.seat);
      if (currentStack == null) {
        toRemove.push(orderId);
        continue;
      }
      if (currentStack + deposit.amount > room.settings.buyInMax) {
        const seatSocket = socketIdBySeat(tableId, deposit.seat);
        if (seatSocket) {
          io.to(seatSocket).emit("system_message", { message: "Rebuy approval skipped: exceeds max buy-in for next hand." });
        }
        io.to(tableId).emit("system_message", { message: `Rebuy approval for ${deposit.userName} skipped (exceeds max buy-in).` });
        toRemove.push(orderId);
        continue;
      }
      table.addStack(deposit.seat, deposit.amount);
      recordSessionBuyIn(tableId, deposit.userId, deposit.userName, deposit.amount);
      setSessionLastStack(tableId, deposit.userId, deposit.userName, currentStack + deposit.amount);
      const sid = socketIdBySeat(tableId, deposit.seat);
      if (sid) io.to(sid).emit("system_message", { message: `Rebuy of ${deposit.amount} credited for this hand.` });
      io.to(tableId).emit("system_message", { message: `${deposit.userName} (Seat ${deposit.seat}) rebuy credited: ${deposit.amount}` });
      stackBySeatBefore.set(deposit.seat, currentStack + deposit.amount);
    } catch (err) {
      console.warn("applyApprovedDeposits: addStack failed:", (err as Error).message);
    }
    toRemove.push(orderId);
  }
  for (const id of toRemove) pendingDeposits.delete(id);
}

function getPendingDepositsForTable(tableId: string): Array<{ orderId: string; seat: number; userId: string; userName: string; amount: number }> {
  const result: Array<{ orderId: string; seat: number; userId: string; userName: string; amount: number }> = [];
  for (const [, deposit] of pendingDeposits.entries()) {
    if (deposit.tableId === tableId && !deposit.approved) {
      result.push({ orderId: deposit.orderId, seat: deposit.seat, userId: deposit.userId, userName: deposit.userName, amount: deposit.amount });
    }
  }
  return result;
}

function hasVoluntaryPreflopAction(state: TableState): boolean {
  const blindSeats = new Set<number>();
  for (const action of state.actions) {
    if (action.street !== "PREFLOP") continue;
    if ((action.type === "call" || action.type === "raise") && !blindSeats.has(action.seat)) {
      blindSeats.add(action.seat);
      continue;
    }
    if (action.type === "raise" || action.type === "call") {
      return true;
    }
  }
  return false;
}

async function pushAdviceIfNeeded(tableId: string, state: TableState): Promise<void> {
  if (!state.handId || state.actorSeat == null) return;

  const table = tables.get(tableId);
  if (!table) return;

  // Only push advice in COACH mode immediately; REVIEW mode waits until hand end
  if (table.getMode() === "REVIEW") return;

  const seat = state.actorSeat;
  const binding = bindingsByTable(tableId).find((entry) => entry.binding.seat === seat)?.binding;
  if (!binding) return;

  const heroPos = table.getPosition(seat);
  const heroHand = table.getHeroHandCode(seat);
  
  let advice: any;

  // Preflop advice
  if (state.street === "PREFLOP") {
    const line = hasVoluntaryPreflopAction(state) ? "facing_open" : "unopened";
    let villainPos = "BB";
    let villainSeat: number | null = null;
    
    if (line === "facing_open") {
      for (const action of state.actions) {
        if (action.street === "PREFLOP" && action.type === "raise" && action.seat !== seat) {
          villainPos = table.getPosition(action.seat);
          villainSeat = action.seat;
          break;
        }
      }
    }

    const effectiveStackBb = calculateEffectiveStackBb(state, seat, villainSeat);

    advice = getPreflopAdvice({
      tableId,
      handId: state.handId,
      seat,
      heroPos,
      villainPos,
      line,
      heroHand,
      effectiveStackBb
    });
  } 
  // Postflop advice (flop/turn/river)
  else if (["FLOP", "TURN", "RIVER"].includes(state.street)) {
    const heroHandCards = table.getHoleCards(seat);
    if (!heroHandCards) return;

    const context = buildPostflopContext(tableId, state, seat, heroPos, heroHandCards);
    if (!context) return;

    try {
      advice = await getPostflopAdvice(context);
    } catch (error) {
      console.error(`[advice] postflop error for ${tableId}:${seat}:`, error);
      return;
    }
  } else {
    return; // Showdown or invalid street
  }

  // Store for deviation calc
  lastAdvice.set(`${tableId}:${seat}`, advice);

  io.to(socketIdBySeat(tableId, seat)).emit("advice_payload", advice);
}

function buildPostflopContext(tableId: string, state: TableState, seat: number, heroPos: string, heroHand: string[]) {
  const table = tables.get(tableId);
  if (!table || !state.handId) return null;

  // Find villain position (last aggressor or first active opponent)
  let villainPos = "BTN";
  let villainSeat: number | null = null;
  let aggressor: "hero" | "villain" | "none" = "none";
  
  const streetActions = state.actions.filter(a => a.street === state.street);
  let lastRaiserSeat: number | null = null;
  
  for (const action of streetActions) {
    if (action.type === "raise") {
      lastRaiserSeat = action.seat;
      aggressor = action.seat === seat ? "hero" : "villain";
    }
  }
  
  if (lastRaiserSeat !== null && lastRaiserSeat !== seat) {
    villainPos = table.getPosition(lastRaiserSeat);
    villainSeat = lastRaiserSeat;
  }

  if (villainSeat == null) {
    const fallbackVillain = state.players.find((player) =>
      player.inHand && !player.folded && player.seat !== seat
    );
    if (fallbackVillain) {
      villainSeat = fallbackVillain.seat;
      villainPos = table.getPosition(fallbackVillain.seat);
    }
  }

  // Count active opponents
  const numVillains = state.players.filter(p => 
    p.inHand && !p.folded && p.seat !== seat
  ).length;

  let preflopAggressorSeat: number | null = null;
  for (const action of state.actions) {
    if (
      action.street === "PREFLOP"
      && (action.type === "raise" || action.type === "all_in")
    ) {
      preflopAggressorSeat = action.seat;
    }
  }

  const preflopAggressor: "hero" | "villain" | "none" = preflopAggressorSeat == null
    ? "none"
    : preflopAggressorSeat === seat
      ? "hero"
      : "villain";

  const villainPosForIp = villainSeat != null ? table.getPosition(villainSeat) : villainPos;
  const heroInPosition = comparePositionOrder(heroPos, villainPosForIp) > 0;

  // Calculate pot size and amount to call
  const potSize = state.pot;
  const toCall = Math.max(0, state.currentBet - (state.players.find(p => p.seat === seat)?.streetCommitted ?? 0));
  const effectiveStack = calculateEffectiveStack(state, seat, villainSeat);
  const effectiveStackBb = state.bigBlind > 0 ? round2(effectiveStack / state.bigBlind) : 0;

  return {
    tableId,
    handId: state.handId,
    seat,
    street: state.street as "FLOP" | "TURN" | "RIVER",
    heroHand: [heroHand[0], heroHand[1]] as [string, string],
    board: state.board,
    heroPosition: heroPos,
    villainPosition: villainPos,
    potSize,
    toCall,
    effectiveStack,
    effectiveStackBb,
    aggressor,
    preflopAggressor,
    heroInPosition,
    numVillains,
    actionHistory: state.actions
  };
}

function comparePositionOrder(heroPos: string, villainPos: string): number {
  const order: Record<string, number> = {
    SB: 0,
    BB: 1,
    UTG: 2,
    MP: 3,
    HJ: 4,
    CO: 5,
    BTN: 6,
  };

  const heroRank = order[heroPos] ?? 0;
  const villainRank = order[villainPos] ?? 0;
  return heroRank - villainRank;
}

function calculateEffectiveStackBb(state: TableState, heroSeat: number, villainSeat?: number | null): number {
  const effectiveStack = calculateEffectiveStack(state, heroSeat, villainSeat ?? null);
  if (state.bigBlind <= 0) return 100;
  return round2(effectiveStack / state.bigBlind);
}

function calculateEffectiveStack(state: TableState, heroSeat: number, villainSeat: number | null): number {
  const heroStack = state.players.find((player) => player.seat === heroSeat)?.stack ?? 0;
  if (heroStack <= 0) return 0;

  if (villainSeat != null) {
    const villainStack = state.players.find((player) => player.seat === villainSeat)?.stack;
    if (villainStack != null) {
      return Math.min(heroStack, villainStack);
    }
  }

  const activeVillainStacks = state.players
    .filter((player) => player.inHand && !player.folded && player.seat !== heroSeat)
    .map((player) => player.stack);
  if (activeVillainStacks.length === 0) return heroStack;
  const shortestVillain = Math.min(...activeVillainStacks);
  return Math.min(heroStack, shortestVillain);
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function emitPresence(tableId: string) {
  const presence = bindingsByTable(tableId).map(({ binding }) => ({
    seat: binding.seat,
    userId: binding.userId,
    name: binding.name
  }));
  io.to(tableId).emit("table_presence", { tableId, presence });
}

function currentPlayerCount(tableId: string): number {
  return tables.get(tableId)?.getPublicState().players.length ?? 0;
}

function toLobbySummary(room: RoomInfo): LobbyRoomSummary {
  const managed = roomManager.getRoom(room.tableId);
  const clubInfo = clubManager.getClubForTable(room.roomCode);
  const club = clubInfo ? clubManager.getClub(clubInfo.clubId) : null;
  return {
    tableId: room.tableId,
    roomCode: room.roomCode,
    roomName: room.roomName,
    smallBlind: room.smallBlind,
    bigBlind: room.bigBlind,
    maxPlayers: room.maxPlayers,
    playerCount: currentPlayerCount(room.tableId),
    status: room.status,
    visibility: managed?.settings.visibility ?? "public",
    updatedAt: room.updatedAt ?? room.createdAt,
    ...(clubInfo && {
      clubId: clubInfo.clubId,
      clubName: club?.name,
      isClubTable: true,
    }),
  };
}

async function emitLobbySnapshot(targetSocketId?: string): Promise<void> {
  const localRooms = [...roomsByTableId.values()].map(toLobbySummary);
  const roomMap = new Map(localRooms.map((room) => [room.tableId, room]));

  if (supabase.enabled()) {
    const remoteRooms = await supabase.listLobbyRooms(50);
    for (const room of remoteRooms) {
      if (!roomMap.has(room.tableId)) {
        roomMap.set(room.tableId, room);
      }
    }
  }

  // Filter out private rooms from lobby list
  const payload = {
    rooms: [...roomMap.values()]
      .filter((room) => room.status === "OPEN" && room.visibility === "public")
      .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
      .slice(0, 50)
  };

  if (targetSocketId) {
    io.to(targetSocketId).emit("lobby_snapshot", payload);
  } else {
    io.emit("lobby_snapshot", payload);
  }
}

function broadcastSnapshot(tableId: string) {
  const table = tables.get(tableId);
  if (!table) return;
  const snapshot = table.getPublicState();
  const pendingPrompt = pendingAllInPrompts.get(tableId);
  if (pendingPrompt && pendingPrompt.handId === snapshot.handId) {
    snapshot.allInPrompt = pendingPrompt.prompt;
  }
  // Attach deferred stand-up seats and pending pause for client UI
  const deferredSeats = pendingStandUps.get(tableId);
  if (deferredSeats && deferredSeats.size > 0) {
    snapshot.pendingStandUp = [...deferredSeats];
  }
  if (pendingPause.has(tableId)) {
    snapshot.pendingPause = true;
  }
  const deposits = getPendingDepositsForTable(tableId);
  if (deposits.length > 0) {
    snapshot.pendingDeposits = deposits;
  }
  io.to(tableId).emit("table_snapshot", snapshot);
  emitPresence(tableId);
  // Defer advice computation so it never blocks snapshot delivery or timer updates
  setImmediate(() => {
    void pushAdviceIfNeeded(tableId, snapshot).catch((err) => {
      console.warn("[advice] deferred push error:", (err as Error).message);
    });
  });
}

function buildAllInPrompt(table: GameTable, actorSeat: number): AllInPrompt {
  const state = table.getPublicState();
  const heroCards = table.getHoleCards(actorSeat);
  const opponentSeats = state.players
    .filter((p) => p.inHand && !p.folded && p.seat !== actorSeat)
    .map((p) => p.seat);

  let winRate = 0.5;
  if (heroCards && opponentSeats.length > 0) {
    const villainHands = opponentSeats
      .map((seat) => table.getHoleCards(seat))
      .filter((cards): cards is [string, string] => Array.isArray(cards) && cards.length === 2)
      .map((cards) => [cards[0], cards[1]] as [Card, Card]);

    if (villainHands.length > 0) {
      const equity = calculateEquity({
        heroHand: [heroCards[0], heroCards[1]] as [Card, Card],
        villainHands,
        board: [...state.board] as Card[],
        simulations: 1200,
      });
      winRate = equity.equity;
    }
  }

  const roundedWinRate = Math.round(winRate * 1000) / 1000;
  const isHighWinRate = roundedWinRate >= 0.55;

  return {
    actorSeat,
    winRate: roundedWinRate,
    recommendedRunCount: isHighWinRate ? 2 : 1,
    defaultRunCount: isHighWinRate ? 2 : 1,
    allowedRunCounts: [1, 2],
    reason: isHighWinRate
      ? "High win rate: recommend run it twice. If you disagree, run once."
      : "Lower win rate: you may choose to run once or run twice.",
  };
}

function calculateAllPlayersEquity(table: GameTable, board: Card[]): Array<{ seat: number; winRate: number; tieRate: number }> {
  const state = table.getPublicState();
  const activeSeats = state.players
    .filter((p) => p.inHand && !p.folded)
    .map((p) => p.seat);

  const equities: Array<{ seat: number; winRate: number; tieRate: number }> = [];

  for (const seat of activeSeats) {
    const heroCards = table.getHoleCards(seat);
    const opponentSeats = activeSeats.filter((s) => s !== seat);

    if (!heroCards || opponentSeats.length === 0) {
      equities.push({ seat, winRate: 0.5, tieRate: 0 });
      continue;
    }

    const villainHands = opponentSeats
      .map((s) => table.getHoleCards(s))
      .filter((cards): cards is [string, string] => Array.isArray(cards) && cards.length === 2)
      .map((cards) => [cards[0], cards[1]] as [Card, Card]);

    if (villainHands.length === 0) {
      equities.push({ seat, winRate: 1.0, tieRate: 0 });
      continue;
    }

    const equity = calculateEquity({
      heroHand: [heroCards[0], heroCards[1]] as [Card, Card],
      villainHands,
      board,
      simulations: 1200,
    });

    equities.push({
      seat,
      winRate: Math.round(equity.win * 1000) / 1000,
      tieRate: Math.round(equity.tie * 1000) / 1000,
    });
  }

  return equities;
}

function clearShowdownDecisionTimeout(tableId: string): void {
  const timeout = pendingShowdownTimeouts.get(tableId);
  if (timeout) {
    clearTimeout(timeout);
    pendingShowdownTimeouts.delete(tableId);
  }
}

function settleShowdownDecision(tableId: string, table: GameTable, expectedHandId: string): void {
  const state = table.getPublicState();
  if (!state.handId || state.handId !== expectedHandId) return;

  if (state.showdownPhase === "decision") {
    const settings = roomManager.getRoom(tableId)?.settings;
    table.finalizeShowdownReveals({
      autoMuckLosingHands: settings?.autoMuckLosingHands ?? true,
    });
  }

  finalizeHandEnd(tableId, table.getPublicState());
}

function maybeFinalizeShowdownDecision(tableId: string, table: GameTable): void {
  const state = table.getPublicState();
  if (state.showdownPhase !== "decision" || !state.handId) return;

  const contenders = table.getShowdownContenderSeats();
  if (contenders.length === 0) return;

  const revealed = state.revealedHoles ?? {};
  const mucked = new Set(state.muckedSeats ?? []);
  const allDecided = contenders.every((seat) => Boolean(revealed[seat]) || mucked.has(seat));
  if (!allDecided) return;

  clearShowdownDecisionTimeout(tableId);
  settleShowdownDecision(tableId, table, state.handId);
}

function isRiverCallShowdown(state: TableState): boolean {
  for (let i = state.actions.length - 1; i >= 0; i -= 1) {
    const action = state.actions[i];
    if (action.street !== "RIVER") continue;
    if (action.type === "call") return true;
  }
  return false;
}

function shouldForceRevealAtShowdown(tableId: string, state: TableState): boolean {
  const room = roomManager.getRoom(tableId);
  if (!room?.settings.revealAllAtShowdown) return false;

  const contenders = state.players.filter((player) => player.inHand && !player.folded);
  if (contenders.length < 2) return false;

  const everyoneAllIn = contenders.every((player) => player.allIn);
  return everyoneAllIn || isRiverCallShowdown(state);
}

function beginShowdownDecision(tableId: string, table: GameTable, state: TableState): void {
  if (state.showdownPhase !== "decision" || !state.handId) {
    finalizeHandEnd(tableId, state);
    return;
  }

  if (shouldForceRevealAtShowdown(tableId, state)) {
    const contenders = table.getShowdownContenderSeats();
    for (const seat of contenders) {
      table.revealPublicHand(seat);
    }
    state = table.getPublicState();
    if (state.showdownPhase !== "decision") {
      finalizeHandEnd(tableId, state);
      return;
    }
  }

  clearShowdownDecisionTimeout(tableId);
  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);

  const expectedHandId = state.handId;
  if (!expectedHandId) return;
  const handIdForTimeout: string = expectedHandId;
  const timeout = setTimeout(() => {
    pendingShowdownTimeouts.delete(tableId);
    const liveTable = tables.get(tableId);
    if (!liveTable) return;
    settleShowdownDecision(tableId, liveTable, handIdForTimeout);
  }, runtimeConfig.showdownDecisionTimeoutMs);

  pendingShowdownTimeouts.set(tableId, timeout);
}

function maybeAutoRevealRunoutHands(tableId: string, table: GameTable): void {
  const settings = roomManager.getRoom(tableId)?.settings;
  if ((settings?.autoRevealOnAllInCall ?? true) !== true) return;
  if ((settings?.revealAllAtShowdown ?? true) !== true) return;

  const state = table.getPublicState();
  const seatsToReveal = state.players
    .filter((p) => p.inHand && !p.folded)
    .map((p) => p.seat);

  let changed = false;
  for (const seat of seatsToReveal) {
    changed = table.revealPublicHand(seat) || changed;
  }

  if (changed) {
    touchLocalRoom(tableId);
    broadcastSnapshot(tableId);
  }
}

async function handleSequentialRunout(tableId: string, table: GameTable): Promise<void> {
  try {
    // For run-it-twice: engine deals both boards atomically, then we reveal street-by-street
    if (table.getAllInRunCount() === 2) {
      const boardBefore = [...table.getPublicState().board];
      table.performRunout(); // deals both boards, computes payouts, sets runoutBoards
      const finalState = table.getPublicState();
      const boards = finalState.runoutBoards; // [board1, board2], each length 5

      if (boards && boards.length === 2) {
        // Determine how many cards were already on the board before runout
        const alreadyDealt = boardBefore.length; // 0, 3, or 4

        // Build reveal steps: each step shows new cards for that street on both boards
        type RevealStep = { street: string; boardSlice: [number, number]; delay: number };
        const steps: RevealStep[] = [];
        if (alreadyDealt < 3) steps.push({ street: "FLOP", boardSlice: [0, 3], delay: 1500 });
        if (alreadyDealt < 4) steps.push({ street: "TURN", boardSlice: [3, 4], delay: 2000 });
        if (alreadyDealt < 5) steps.push({ street: "RIVER", boardSlice: [4, 5], delay: 2000 });

        for (let i = 0; i < steps.length; i++) {
          const step = steps[i];
          const newCardsR1 = boards[0].slice(step.boardSlice[0], step.boardSlice[1]);
          const newCardsR2 = boards[1].slice(step.boardSlice[0], step.boardSlice[1]);
          const partialBoard1 = boards[0].slice(0, step.boardSlice[1]);
          const partialBoard2 = boards[1].slice(0, step.boardSlice[1]);

          io.to(tableId).emit("run_twice_reveal", {
            handId: finalState.handId,
            street: step.street,
            run1: { newCards: newCardsR1, board: partialBoard1 },
            run2: { newCards: newCardsR2, board: partialBoard2 },
          });

          if (i < steps.length - 1) {
            await new Promise((resolve) => setTimeout(resolve, step.delay));
          }
        }

        // Final showdown after last reveal delay
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }

      beginShowdownDecision(tableId, table, finalState);
      return;
    }

    const delays: Record<string, number> = { PREFLOP: 0, FLOP: 1500, TURN: 2000, RIVER: 2000, SHOWDOWN: 1500 };

    const revealNextStreetWithDelay = async (): Promise<void> => {
      const result = table.revealNextStreet();
      if (!result) return;

      const { street, newCards } = result;
      const state = table.getPublicState();

      if (street === "SHOWDOWN") {
        beginShowdownDecision(tableId, table, state);
        return;
      }

      const equities = calculateAllPlayersEquity(table, [...state.board] as Card[]);

      io.to(tableId).emit("board_reveal", {
        handId: state.handId,
        street,
        newCards,
        board: state.board,
        equities,
      });

      broadcastSnapshot(tableId);

      const delay = delays[street] || 1500;
      await new Promise((resolve) => setTimeout(resolve, delay));

      await revealNextStreetWithDelay();
    };

    await revealNextStreetWithDelay();
  } catch (error) {
    const state = table.getPublicState();
    logWarn({
      event: "runout.sequence.failed",
      tableId,
      handId: state.handId ?? undefined,
      message: (error as Error).message,
    });

    if (!state.handId) return;
    if (state.showdownPhase === "decision") {
      settleShowdownDecision(tableId, table, state.handId);
      return;
    }
    finalizeHandEnd(tableId, state);
  }
}

function clearAutoDealSchedule(tableId: string): void {
  const handle = autoDealSchedule.get(tableId);
  if (handle) {
    clearTimeout(handle);
    autoDealSchedule.delete(tableId);
  }
}

/** Start/reset the idle watchdog for an active hand.
 *  If no seated players remain connected for HAND_IDLE_TIMEOUT_MS, abort the hand. */
function resetHandIdleWatchdog(tableId: string): void {
  const existing = handIdleWatchdogs.get(tableId);
  if (existing) clearTimeout(existing);

  const table = tables.get(tableId);
  if (!table || !table.isHandActive()) return;

  // Only arm if there are fewer than 2 connected players for this table
  const connectedCount = bindingsByTable(tableId).length;
  if (connectedCount >= 2) {
    // Enough players — no need for idle watchdog; just clear
    handIdleWatchdogs.delete(tableId);
    return;
  }

  const handle = setTimeout(() => {
    handIdleWatchdogs.delete(tableId);
    const tbl = tables.get(tableId);
    if (!tbl || !tbl.isHandActive()) return;

    // Check again: if players reconnected, don't abort
    if (bindingsByTable(tableId).length >= 2) return;

    logWarn({
      event: "hand.idle_watchdog.abort",
      tableId,
      message: `No connected players for ${HAND_IDLE_TIMEOUT_MS / 1000}s; aborting stale hand.`,
    });
    tbl.abortHand();
    roomManager.setHandActive(tableId, false);
    roomManager.clearActionTimer(tableId);
    clearAutoDealSchedule(tableId);
    clearShowdownDecisionTimeout(tableId);

    io.to(tableId).emit("hand_aborted", { reason: "Hand aborted: table idle too long" });
    io.to(tableId).emit("system_message", { message: "Hand cancelled due to long inactivity. Bets have been refunded." });
    const deferredSeats = pendingStandUps.get(tableId);
    if (deferredSeats && deferredSeats.size > 0) {
      for (const seatNum of deferredSeats) {
        standUpPlayer(tableId, seatNum, "Left after hand ended");
      }
      pendingStandUps.delete(tableId);
    }
    processQueuedTableLeaves(tableId);
    touchLocalRoom(tableId);
    broadcastSnapshot(tableId);
  }, HAND_IDLE_TIMEOUT_MS);

  handIdleWatchdogs.set(tableId, handle);
}

function clearHandIdleWatchdog(tableId: string): void {
  const handle = handIdleWatchdogs.get(tableId);
  if (handle) {
    clearTimeout(handle);
    handIdleWatchdogs.delete(tableId);
  }
}

function queueLeaveTableAfterHand(tableId: string, socketId: string): void {
  let pending = pendingTableLeaves.get(tableId);
  if (!pending) {
    pending = new Set<string>();
    pendingTableLeaves.set(tableId, pending);
  }
  pending.add(socketId);
}

function processQueuedTableLeaves(tableId: string): void {
  const pending = pendingTableLeaves.get(tableId);
  if (!pending || pending.size === 0) return;
  for (const socketId of pending) {
    const seatBinding = socketSeat.get(socketId);
    if (seatBinding && seatBinding.tableId === tableId) {
      standUpPlayer(tableId, seatBinding.seat, "Left after hand ended");
    }
    const sock = io.sockets.sockets.get(socketId);
    if (sock) sock.leave(tableId);
    io.to(socketId).emit("left_table", { tableId });
  }
  pendingTableLeaves.delete(tableId);
}

function getApprovedDepositTotalsBySeat(tableId: string): Map<number, number> {
  const totals = new Map<number, number>();
  for (const deposit of pendingDeposits.values()) {
    if (deposit.tableId !== tableId || !deposit.approved) continue;
    totals.set(deposit.seat, (totals.get(deposit.seat) ?? 0) + deposit.amount);
  }
  return totals;
}

function getEligibleSeatNumbersForDeal(tableId: string, includeApprovedDeposits = false): number[] {
  const table = tables.get(tableId);
  if (!table) return [];
  const room = roomManager.getRoom(tableId);
  if (!room) return [];

  const connectedSeats = new Set(bindingsByTable(tableId).map(({ binding }) => binding.seat));
  const approvedTotals = includeApprovedDeposits ? getApprovedDepositTotalsBySeat(tableId) : new Map<number, number>();
  return table.getPublicState().players
    .filter((player) => (player.stack + (approvedTotals.get(player.seat) ?? 0)) > 0)
    .filter((player) => room.settings.dealToAwayPlayers || connectedSeats.has(player.seat))
    .map((player) => player.seat);
}

function getHandStartValidationMessage(tableId: string): string | null {
  const room = roomManager.getRoom(tableId);
  if (!room) return "Room not found";
  if (roomManager.isPaused(tableId)) return "Game is paused";

  const table = tables.get(tableId);
  if (table?.isHandActive()) return "Hand in progress";

  const eligibleSeats = getEligibleSeatNumbersForDeal(tableId, true);
  if (eligibleSeats.length < 2) {
    return `Need at least 2 eligible players to deal (currently ${eligibleSeats.length})`;
  }
  return null;
}

function getAutoStartSkipMessage(tableId: string): string | null {
  const room = roomManager.getRoom(tableId);
  if (!room) return null;
  if (!room.settings.autoStartNextHand) return "Auto-start skipped: disabled in room settings.";
  if (roomManager.isPaused(tableId)) return "Auto-start skipped: game is paused.";

  const table = tables.get(tableId);
  if (!table) return "Auto-start skipped: table not ready.";
  if (table.isHandActive()) return "Auto-start skipped: hand still active.";

  const eligibleSeats = getEligibleSeatNumbersForDeal(tableId, true);
  if (eligibleSeats.length < 2) {
    const awayHint = room.settings.dealToAwayPlayers
      ? ""
      : " (away players are excluded; enable \"Deal to away players\" to include them)";
    return `Auto-start skipped: need at least 2 eligible players (currently ${eligibleSeats.length})${awayHint}.`;
  }
  return null;
}

function startHandFlow(tableId: string, actorUserId: string, source: "manual" | "auto"): string {
  const room = roomsByTableId.get(tableId);
  if (!room) {
    throw new Error("Room not found");
  }

  const existingTable = tables.get(tableId);
  if (existingTable?.isHandActive()) {
    throw new Error("Hand in progress");
  }

  const table = createTableIfNeeded(room);
  const validationError = getHandStartValidationMessage(tableId);
  if (validationError) {
    throw new Error(validationError);
  }

  openRoomSessionIfNeeded(tableId, "start_hand").catch((e) => logWarn({
    event: "session.open.failed",
    tableId,
    message: (e as Error).message,
  }));
  applyApprovedDeposits(tableId);

  const { handId } = table.startHand();
  pendingAllInPrompts.delete(tableId);
  const rcTimeout = pendingRunCountTimeouts.get(tableId);
  if (rcTimeout) { clearTimeout(rcTimeout); pendingRunCountTimeouts.delete(tableId); }
  clearShowdownDecisionTimeout(tableId);

  roomManager.setHandActive(tableId, true);
  const playerUserIds = bindingsByTable(tableId).map((b) => b.binding.userId);
  roomManager.refillTimeBanks(tableId, playerUserIds);
  logInfo({
    event: "hand.started",
    tableId,
    handId,
    userId: actorUserId,
    source,
    seatedPlayers: playerUserIds.length,
  });

  io.to(tableId).emit("hand_started", { handId });

  for (const { socketId, binding } of bindingsByTable(tableId)) {
    const cards = table.getHoleCards(binding.seat);
    if (cards) {
      io.to(socketId).emit("hole_cards", { handId, cards, seat: binding.seat });
    }
  }

  supabase.logEvent({
    tableId,
    eventType: "HAND_STARTED",
    actorUserId,
    handId,
    payload: { buttonSeat: table.getPublicState().buttonSeat, source },
  }).catch((e) => logWarn({
    event: "supabase.log_event.failed",
    tableId,
    handId,
    message: (e as Error).message,
  }));

  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);
  startTimerForActor(tableId);
  clearHandIdleWatchdog(tableId); // Hand started with players — no idle concern

  return handId;
}

function scheduleAutoDealIfNeeded(tableId: string): void {
  clearAutoDealSchedule(tableId);

  const room = roomManager.getRoom(tableId);
  if (!room) return;
  const table = tables.get(tableId);
  if (!table) return;

  const immediateSkip = getAutoStartSkipMessage(tableId);
  if (immediateSkip) {
    io.to(tableId).emit("system_message", { message: immediateSkip });
    return;
  }

  const delayMs = SHOWDOWN_SPEED_DELAYS_MS[room.settings.showdownSpeed] ?? SHOWDOWN_SPEED_DELAYS_MS.normal;

  const handle = setTimeout(() => {
    autoDealSchedule.delete(tableId);
    const managed = roomManager.getRoom(tableId);
    if (!managed) return;

    const skipReason = getAutoStartSkipMessage(tableId);
    if (skipReason) {
      io.to(tableId).emit("system_message", { message: skipReason });
      return;
    }

    try {
      startHandFlow(tableId, managed.ownership.ownerId, "auto");
    } catch (err) {
      io.to(tableId).emit("system_message", { message: `Auto-start skipped: ${(err as Error).message}` });
    }
  }, delayMs);

  autoDealSchedule.set(tableId, handle);
}

function finalizeHandEnd(tableId: string, state: TableState): void {
  pendingAllInPrompts.delete(tableId);
  const rcTimeout = pendingRunCountTimeouts.get(tableId);
  if (rcTimeout) { clearTimeout(rcTimeout); pendingRunCountTimeouts.delete(tableId); }
  clearShowdownDecisionTimeout(tableId);
  const table = tables.get(tableId);
  const settlement = table?.getSettlementResult() ?? null;
  logInfo({
    event: "hand.ended",
    tableId,
    handId: state.handId,
    winners: (state.winners ?? []).length,
    totalPot: settlement?.totalPot ?? state.pot,
  });
  persistHandHistory(tableId, state, settlement).catch((e) => logWarn({
    event: "hand_history.persist.failed",
    tableId,
    handId: state.handId,
    message: (e as Error).message,
  }));
  io.to(tableId).emit("hand_ended", {
    handId: state.handId,
    finalState: state,
    board: state.board,
    runoutBoards: state.runoutBoards,
    runoutPayouts: state.runoutPayouts,
    players: state.players,
    pot: state.pot,
    winners: state.winners,
    settlement: settlement ?? undefined,
  });
  roomManager.clearActionTimer(tableId);
  roomManager.setHandActive(tableId, false);

  // Cleanly mark hand as done in engine (nulls handId, resets handInProgress)
  if (table) table.clearHand();

  // Increment hands played for session stats
  incrementHandsPlayed(tableId, state.players.filter((p) => p.inHand).map((p) => p.userId));
  syncSessionStacksFromState(tableId, state);

  // Bust-out auto-stand: players with no chips after hand ends
  for (const p of state.players) {
    if (p.stack <= 0) {
      const sid = socketIdBySeat(tableId, p.seat);
      if (sid) {
        io.to(sid).emit("system_message", { message: "You busted out and were stood up. Rebuy to continue." });
      }
      standUpPlayer(tableId, p.seat, "Busted out");
    }
  }

  // Process deferred stand-ups
  const deferredSeats = pendingStandUps.get(tableId);
  if (deferredSeats && deferredSeats.size > 0) {
    for (const seatNum of deferredSeats) {
      standUpPlayer(tableId, seatNum, "Left after hand ended");
    }
    pendingStandUps.delete(tableId);
  }

  // Process deferred pause
  const deferredPause = pendingPause.get(tableId);
  if (deferredPause) {
    pendingPause.delete(tableId);
    roomManager.pauseGame(tableId, deferredPause.userId, deferredPause.displayName);
  }

  processQueuedTableLeaves(tableId);

  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);
  scheduleAutoDealIfNeeded(tableId);
}

function handleRoomAutoClose(tableId: string): void {
  const count = currentPlayerCount(tableId);
  const closed = roomManager.finalizeAutoClose(tableId, count);
  if (closed) {
    clearAutoDealSchedule(tableId);
    clearShowdownDecisionTimeout(tableId);
    pendingAllInPrompts.delete(tableId);
    const runCountTimeout = pendingRunCountTimeouts.get(tableId);
    if (runCountTimeout) {
      clearTimeout(runCountTimeout);
      pendingRunCountTimeouts.delete(tableId);
    }
    pendingStandUps.delete(tableId);
    pendingTableLeaves.delete(tableId);
    pendingPause.delete(tableId);
    for (const [orderId, request] of pendingSeatRequests.entries()) {
      if (request.tableId === tableId) pendingSeatRequests.delete(orderId);
    }
    for (const [orderId, deposit] of pendingDeposits.entries()) {
      if (deposit.tableId === tableId) pendingDeposits.delete(orderId);
    }
    io.to(tableId).emit("room_closed", { tableId, reason: "empty" });
    tables.delete(tableId);
    const room = roomsByTableId.get(tableId);
    if (room) {
      roomCodeToTableId.delete(room.roomCode);
      sessionStatsByRoomCode.delete(room.roomCode);
      roomsByTableId.delete(tableId);
      closeRoomSessionIfOpen(tableId, "auto_close").catch(() => {});
      supabase.touchRoom(tableId, "CLOSED").catch(() => {});
    }
    void emitLobbySnapshot();
  }
}

/** Start action timer for the current actor after a hand event */
function startTimerForActor(tableId: string): void {
  const table = tables.get(tableId);
  if (!table) return;
  const state = table.getPublicState();
  if (state.actorSeat == null || !state.handId) return;

  const expectedHandId = state.handId;
  const expectedSeat = state.actorSeat;

  const actorBinding = bindingsByTable(tableId).find((e) => e.binding.seat === state.actorSeat);
  if (!actorBinding) {
    // Away player was dealt in (dealToAwayPlayers=true): auto-fold so the hand cannot stall.
    try {
      const autoState = table.applyAction(state.actorSeat, "fold");
      io.to(tableId).emit("action_applied", {
        seat: state.actorSeat,
        action: "fold",
        amount: 0,
        pot: autoState.pot,
        auto: true,
      });
      handlePostAction(tableId, table, autoState);
    } catch (err) {
      console.warn("startTimerForActor: auto-fold for away actor failed:", (err as Error).message);
    }
    return;
  }

  roomManager.startActionTimer(
    tableId,
    state.actorSeat,
    actorBinding.binding.userId,
    () => {
      // Timeout: always auto-fold, then stand the player up
      const tbl = tables.get(tableId);
      if (!tbl) return;
      const s = tbl.getPublicState();
      if (!s.handId || s.handId !== expectedHandId) return;
      if (s.actorSeat == null || s.actorSeat !== expectedSeat || !s.legalActions) return;
      const timedOutSeat = s.actorSeat;
      try {
        const newState = tbl.applyAction(timedOutSeat, "fold");
        io.to(tableId).emit("action_applied", {
          seat: timedOutSeat,
          action: "fold",
          amount: 0,
          pot: newState.pot,
          auto: true,
        });

        // Stand the timed-out player up (remove from table)
        standUpPlayer(tableId, timedOutSeat, "Timed out — auto-folded and stood up");

        // Continue the hand
        handlePostAction(tableId, tbl, newState);
      } catch (err) {
        console.warn("auto-action on timeout failed:", (err as Error).message);
      }
    }
  );
}

/** Remove a player from their seat and clean up bindings */
function standUpPlayer(tableId: string, seatNum: number, reason: string): void {
  const table = tables.get(tableId);
  if (!table) return;
  const state = table.getPublicState();
  const leavingPlayer = state.players.find((player) => player.seat === seatNum);
  if (!leavingPlayer) return;

  // Find and remove socket binding
  let removedSocketId = "";
  let removedUserId = "";
  for (const [sid, binding] of socketSeat.entries()) {
    if (binding.tableId === tableId && binding.seat === seatNum) {
      removedSocketId = sid;
      removedUserId = binding.userId;
      socketSeat.delete(sid);
      break;
    }
  }

  table.removePlayer(seatNum);
  setSessionLastStack(tableId, leavingPlayer.userId, leavingPlayer.name, leavingPlayer.stack);

  io.to(tableId).emit("system_message", { message: `Seat ${seatNum}: ${reason}` });
  if (removedSocketId) {
    io.to(removedSocketId).emit("stood_up", { seat: seatNum, reason });
  }

  supabase.removeSeat(tableId, seatNum).catch((e) => console.warn("standUpPlayer: removeSeat failed:", (e as Error).message));
  supabase.logEvent({
    tableId,
    eventType: "STAND_UP",
    actorUserId: removedUserId || "system",
    payload: { seat: seatNum, reason }
  }).catch((e) => console.warn("standUpPlayer: logEvent failed:", (e as Error).message));

  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);
  roomManager.checkRoomEmpty(tableId, currentPlayerCount(tableId), () => {
    handleRoomAutoClose(tableId);
  });
  void emitLobbySnapshot();
}

/** Common post-action logic: check runout, finalize, or continue */
function handlePostAction(tableId: string, table: GameTable, newState: TableState): void {
  if (newState.actorSeat == null) {
    roomManager.clearActionTimer(tableId);
    if (table.isRunoutPending()) {
      initiateRunoutFlow(tableId, table);
    } else if (newState.showdownPhase === "decision") {
      beginShowdownDecision(tableId, table, newState);
    } else {
      finalizeHandEnd(tableId, newState);
    }
  } else {
    touchLocalRoom(tableId);
    broadcastSnapshot(tableId);
    startTimerForActor(tableId);
  }
}

/** When all-in runout is needed: decide whether to prompt for run count or just deal */
function initiateRunoutFlow(tableId: string, table: GameTable): void {
  maybeAutoRevealRunoutHands(tableId, table);
  const state = table.getPublicState();

  if (table.isEveryoneAllIn()) {
    // All players are truly all-in → calculate equities, prompt the underdog for run count
    const equities = calculateAllPlayersEquity(table, [...state.board] as Card[]);
    const lowestEquity = equities.reduce((min, e) => e.winRate < min.winRate ? e : min);

    const prompt: AllInPrompt = {
      actorSeat: lowestEquity.seat,
      winRate: lowestEquity.winRate,
      recommendedRunCount: 1,
      defaultRunCount: 1,
      allowedRunCounts: [1, 2],
      reason: `Win rate ${Math.round(lowestEquity.winRate * 100)}%. You can choose to run it once or twice.`,
    };

    pendingAllInPrompts.set(tableId, { handId: state.handId!, prompt });

    // Send prompt to the underdog player
    io.to(socketIdBySeat(tableId, lowestEquity.seat)).emit("all_in_prompt", prompt);

    // Also broadcast so the table knows we're waiting
    broadcastSnapshot(tableId);

    // Auto-default to run 1 after 15 seconds if no response
    const timeout = setTimeout(() => {
      pendingRunCountTimeouts.delete(tableId);
      const pending = pendingAllInPrompts.get(tableId);
      if (!pending || pending.handId !== state.handId) return;
      pendingAllInPrompts.delete(tableId);
      logInfo({
        event: "all_in.run_count.timeout_default",
        tableId,
        handId: state.handId,
        message: "Run-count decision timed out; defaulting to run once.",
      });
      table.setAllInRunCount(1);
      io.to(tableId).emit("run_count_chosen", { runCount: 1, seat: lowestEquity.seat, auto: true });
      void handleSequentialRunout(tableId, table);
    }, runtimeConfig.runCountDecisionTimeoutMs);
    pendingRunCountTimeouts.set(tableId, timeout);
  } else {
    // Not everyone is all-in (one player has chips but no one to bet against)
    // Skip prompt, just do sequential runout with run=1
    table.setAllInRunCount(1);
    touchLocalRoom(tableId);
    broadcastSnapshot(tableId);
    void handleSequentialRunout(tableId, table);
  }
}

function normalizeRoomCode(roomCode: string): string {
  return roomCode.trim().toUpperCase();
}

function sanitizeRoomName(name?: string): string {
  const trimmed = (name ?? runtimeConfig.defaultRoomName).trim();
  if (trimmed.length === 0) return runtimeConfig.defaultRoomName;
  return trimmed.slice(0, 48);
}

function randomRoomCode(length = runtimeConfig.roomCodeLength): string {
  let code = "";
  for (let i = 0; i < length; i += 1) {
    code += ROOM_CODE_CHARS[randomInt(ROOM_CODE_CHARS.length)];
  }
  return code;
}

async function generateUniqueRoomCode(): Promise<string> {
  for (let i = 0; i < 30; i += 1) {
    const candidate = randomRoomCode(runtimeConfig.roomCodeLength);
    if (roomCodeToTableId.has(candidate)) continue;
    try {
      const existing = await supabase.findRoomByCode(candidate);
      if (!existing) return candidate;
    } catch (err) {
      // Supabase unavailable or table missing — fall back to in-memory uniqueness only
      logWarn({
        event: "room_code.generate.fallback_in_memory",
        message: (err as Error).message,
      });
      return candidate;
    }
  }
  throw new Error("cannot generate unique room code");
}

async function ensureRoomByTableId(tableId: string): Promise<RoomInfo> {
  const local = roomsByTableId.get(tableId);
  if (local) return local;

  const remote = await supabase.findRoomByTableId(tableId);
  if (remote) {
    const hydrated: RoomInfo = {
      ...remote,
      createdAt: remote.updatedAt ?? new Date().toISOString(),
      updatedAt: remote.updatedAt ?? new Date().toISOString()
    };
    registerRoom(hydrated);
    createTableIfNeeded(hydrated);
    return hydrated;
  }

  const fallback: RoomInfo = {
    tableId,
    roomCode: await generateUniqueRoomCode(),
    roomName: `Table ${tableId.slice(0, 6)}`,
    maxPlayers: runtimeConfig.defaultCreateRoom.maxPlayers,
    smallBlind: runtimeConfig.defaultCreateRoom.smallBlind,
    bigBlind: runtimeConfig.defaultCreateRoom.bigBlind,
    status: "OPEN",
    isPublic: true,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    createdBy: null,
  };

  registerRoom(fallback);
  createTableIfNeeded(fallback);
  await supabase.upsertRoom(fallback);
  return fallback;
}

async function ensureRoomByCode(roomCode: string): Promise<RoomInfo | null> {
  const normalized = normalizeRoomCode(roomCode);
  const localTableId = roomCodeToTableId.get(normalized);
  if (localTableId) {
    return roomsByTableId.get(localTableId) ?? null;
  }

  const remote = await supabase.findRoomByCode(normalized);
  if (!remote) return null;

  const hydrated: RoomInfo = {
    ...remote,
    createdAt: remote.updatedAt ?? new Date().toISOString(),
    updatedAt: remote.updatedAt ?? new Date().toISOString()
  };
  registerRoom(hydrated);
  createTableIfNeeded(hydrated);
  return hydrated;
}

function touchLocalRoom(tableId: string): void {
  const room = roomsByTableId.get(tableId);
  if (!room) return;
  room.updatedAt = new Date().toISOString();
  roomsByTableId.set(tableId, room);
}

function ensureManagedRoom(room: RoomInfo, ownerFallback: VerifiedIdentity): void {
  if (roomManager.getRoom(room.tableId)) return;
  const ownerId = room.createdBy ?? ownerFallback.userId;
  roomManager.createRoom({
    tableId: room.tableId,
    roomCode: room.roomCode,
    roomName: room.roomName,
    ownerId,
    ownerName: ownerId === ownerFallback.userId ? ownerFallback.displayName : "Host",
    settings: {
      maxPlayers: room.maxPlayers,
      smallBlind: room.smallBlind,
      bigBlind: room.bigBlind,
      visibility: room.isPublic ? "public" : "private",
    },
  });
}

function buildSessionMetadata(tableId: string, trigger: string): SessionContextMetadata | undefined {
  const room = roomsByTableId.get(tableId);
  if (!room) return undefined;
  const managed = roomManager.getRoom(tableId);
  return {
    roomCode: room.roomCode,
    roomName: room.roomName,
    ownerId: managed?.ownership.ownerId ?? room.createdBy ?? undefined,
    ownerName: managed?.ownership.ownerName ?? undefined,
    coHostIds: managed?.ownership.coHostIds ?? [],
    trigger,
  };
}

async function openRoomSessionIfNeeded(tableId: string, trigger: string): Promise<void> {
  if (!supabase.enabled()) return;
  await supabase.openRoomSession(tableId, buildSessionMetadata(tableId, trigger));
}

async function closeRoomSessionIfOpen(tableId: string, trigger: string): Promise<void> {
  if (!supabase.enabled()) return;
  await supabase.closeRoomSession(tableId, { trigger, closedAt: new Date().toISOString() });
}

async function persistHandHistory(tableId: string, state: TableState, settlement: ReturnType<GameTable["getSettlementResult"]>): Promise<void> {
  if (!supabase.enabled()) return;
  if (!state.handId || !settlement) return;

  const managed = roomManager.getRoom(tableId);
  const playersBySeat = new Map(state.players.map((player) => [player.seat, player]));

  const playersSummary: HistoryHandPlayerSummary[] = state.players.map((player) => ({
    seat: player.seat,
    userId: player.userId,
    name: player.name,
  }));

  const winnersBySeat = new Map<number, number>();
  for (const winner of state.winners ?? []) {
    winnersBySeat.set(winner.seat, winner.amount);
  }

  const netByUser: Record<string, number> = {};
  for (const entry of settlement.ledger) {
    const player = playersBySeat.get(entry.seat);
    if (!player) continue;
    netByUser[player.userId] = entry.net;
  }

  const summary: HistoryHandSummaryCore = {
    totalPot: settlement.totalPot,
    runCount: settlement.runCount,
    winners: (state.winners ?? []).map((winner) => ({
      seat: winner.seat,
      amount: winner.amount,
      handName: winner.handName,
    })),
    myNetByUser: netByUser,
    flags: {
      allIn: state.actions.some((action) => action.type === "all_in"),
      runItTwice: settlement.runCount === 2,
      showdown: settlement.showdown,
    },
  };

  const detail: HistoryHandDetailCore = {
    board: [...state.board],
    runoutBoards: state.runoutBoards ? state.runoutBoards.map((board) => [...board]) : [],
    potLayers: settlement.potLayers.map((layer) => ({
      label: layer.label,
      amount: layer.amount,
      eligibleSeats: [...layer.eligibleSeats],
    })),
    contributionsBySeat: { ...settlement.contributions },
    actionTimeline: [...state.actions],
    revealedHoles: { ...(state.revealedHoles ?? {}) },
    payoutLedger: settlement.ledger.map((entry) => ({ ...entry })),
  };

  const viewerUserIds = [...new Set([
    ...state.players.map((player) => player.userId),
    managed?.ownership.ownerId ?? "",
    ...(managed?.ownership.coHostIds ?? []),
  ])].filter((userId) => userId.length > 0);

  const payload: PersistHandHistoryPayload = {
    roomId: tableId,
    handId: state.handId,
    endedAt: new Date(settlement.timestamp).toISOString(),
    blinds: { sb: state.smallBlind, bb: state.bigBlind },
    players: playersSummary,
    summary,
    detail,
    viewerUserIds,
    sessionMetadata: buildSessionMetadata(tableId, "hand_end"),
  };

  await supabase.recordHandHistory(payload);
}

io.on("connection", (socket) => {
  const identity = socketIdentity.get(socket.id);
  if (!identity) {
    socket.disconnect(true);
    return;
  }

  socket.emit("connected", {
    socketId: socket.id,
    userId: identity.userId,
    displayName: identity.displayName,
    supabaseEnabled: supabase.enabled()
  });
  void emitLobbySnapshot(socket.id);

  socket.on(
    "create_room",
    async (payload: { roomName?: string; maxPlayers?: number; smallBlind?: number; bigBlind?: number; isPublic?: boolean; buyInMin?: number; buyInMax?: number; visibility?: "public" | "private" }) => {
      try {
        logInfo({
          event: "room.create.requested",
          userId: identity.userId,
          message: identity.displayName,
          payload,
        });

        const ownedRoom = roomManager.getActiveRoomOwnedBy(identity.userId);
        if (ownedRoom) {
          throw new Error(`You already own a room (${ownedRoom.roomCode}). Close it or transfer ownership first.`);
        }

        const roomCode = await generateUniqueRoomCode();
        const tableId = `tbl_${randomUUID().replace(/-/g, "").slice(0, 10)}`;
        const room: RoomInfo = {
          tableId,
          roomCode,
          roomName: sanitizeRoomName(payload.roomName),
          maxPlayers: Math.min(runtimeConfig.maxPlayers, Math.max(runtimeConfig.minPlayers, Number(payload.maxPlayers ?? runtimeConfig.defaultCreateRoom.maxPlayers))),
          smallBlind: Math.max(1, Number(payload.smallBlind ?? runtimeConfig.defaultCreateRoom.smallBlind)),
          bigBlind: Math.max(2, Number(payload.bigBlind ?? runtimeConfig.defaultCreateRoom.bigBlind)),
          status: "OPEN",
          isPublic: payload.isPublic ?? true,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          createdBy: identity.userId,
        };

        if (room.bigBlind <= room.smallBlind) {
          room.bigBlind = room.smallBlind * 2;
        }

        registerRoom(room);
        const table = createTableIfNeeded(room);
        socket.join(room.tableId);

        // Register with room manager — creator is the owner
        roomManager.createRoom({
          tableId: room.tableId,
          roomCode: room.roomCode,
          roomName: room.roomName,
          ownerId: identity.userId,
          ownerName: identity.displayName,
          settings: {
            maxPlayers: room.maxPlayers,
            smallBlind: room.smallBlind,
            bigBlind: room.bigBlind,
            buyInMin: Math.max(1, Number(payload.buyInMin ?? room.bigBlind * runtimeConfig.defaultCreateRoom.buyInMinMultiplierBb)),
            buyInMax: Math.max(1, Number(payload.buyInMax ?? room.bigBlind * runtimeConfig.defaultCreateRoom.buyInMaxMultiplierBb)),
            visibility: payload.visibility ?? (payload.isPublic === false ? "private" : "public"),
          },
        });

        // Persist to Supabase in background — don't block room creation
        supabase.upsertRoom(room).catch((e) => logWarn({
          event: "room.create.persist_failed",
          tableId: room.tableId,
          message: (e as Error).message,
        }));
        openRoomSessionIfNeeded(room.tableId, "create_room").catch((e) => logWarn({
          event: "session.open.failed",
          tableId: room.tableId,
          message: (e as Error).message,
        }));
        supabase.logEvent({
          tableId: room.tableId,
          eventType: "CREATE_ROOM",
          actorUserId: identity.userId,
          payload: {
            roomCode: room.roomCode,
            roomName: room.roomName,
            maxPlayers: room.maxPlayers,
            smallBlind: room.smallBlind,
            bigBlind: room.bigBlind
          }
        }).catch((e) => logWarn({
          event: "supabase.log_event.failed",
          tableId: room.tableId,
          message: (e as Error).message,
        }));

        socket.emit("room_created", {
          tableId: room.tableId,
          roomCode: room.roomCode,
          roomName: room.roomName
        });
        socket.emit("room_joined", {
          tableId: room.tableId,
          roomCode: room.roomCode,
          roomName: room.roomName
        });
        socket.emit("table_snapshot", table.getPublicState());
        const fullState = roomManager.getFullState(room.tableId);
        if (fullState) socket.emit("room_state_update", fullState);
        emitPresence(room.tableId);
        void emitLobbySnapshot();
      } catch (error) {
        socket.emit("error_event", { message: (error as Error).message });
      }
    }
  );

  socket.on("request_lobby", async () => {
    await emitLobbySnapshot(socket.id);
  });

  socket.on("request_history_rooms", async (payload?: { limit?: number }) => {
    try {
      if (!supabase.enabled()) {
        socket.emit("history_rooms", { rooms: [], error: "Supabase persistence is not enabled on this server." });
        return;
      }
      const rooms = await supabase.listHistoryRooms(identity.userId, payload?.limit ?? 50);
      socket.emit("history_rooms", { rooms });
    } catch (error) {
      socket.emit("history_rooms", { rooms: [], error: (error as Error).message });
    }
  });

  socket.on("request_history_sessions", async (payload: { roomId: string; limit?: number }) => {
    try {
      if (!payload?.roomId) throw new Error("roomId is required");
      const sessions = await supabase.listHistorySessions(identity.userId, payload.roomId, payload.limit ?? 100);
      socket.emit("history_sessions", { roomId: payload.roomId, sessions });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("request_history_hands", async (payload: { roomSessionId: string; limit?: number; beforeEndedAt?: string }) => {
    try {
      if (!payload?.roomSessionId) throw new Error("roomSessionId is required");
      const { hands, hasMore, nextCursor } = await supabase.listHistoryHands(identity.userId, payload.roomSessionId, {
        limit: payload.limit ?? 50,
        beforeEndedAt: payload.beforeEndedAt,
      });
      socket.emit("history_hands", { roomSessionId: payload.roomSessionId, hands, hasMore, nextCursor });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("request_history_hand_detail", async (payload: { handHistoryId: string }) => {
    try {
      if (!payload?.handHistoryId) throw new Error("handHistoryId is required");
      const hand = await supabase.getHistoryHandDetail(identity.userId, payload.handHistoryId);
      socket.emit("history_hand_detail", { handHistoryId: payload.handHistoryId, hand });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("join_room_code", async (payload: { roomCode: string; password?: string }) => {
    try {
      console.log("[JOIN_ROOM_CODE] Request from", identity.userId, "payload:", payload);
      
      const room = await ensureRoomByCode(payload.roomCode);
      console.log("[JOIN_ROOM_CODE] Room found:", room ? `${room.roomName} (${room.roomCode})` : "null");
      
      if (!room) {
        console.log("[JOIN_ROOM_CODE] Room not found or closed");
        throw new Error("Room not found or closed");
      }

      if (room.status === "CLOSED") {
        if (room.createdBy && room.createdBy !== identity.userId) {
          throw new Error("Room is closed. Only the room host can reopen it.");
        }
        room.status = "OPEN";
        room.createdBy = room.createdBy ?? identity.userId;
        room.updatedAt = new Date().toISOString();
        registerRoom(room);
        ensureManagedRoom(room, identity);
        openRoomSessionIfNeeded(room.tableId, "reopen_room").catch((e) => console.warn("join_room_code: reopen openRoomSession failed:", (e as Error).message));
        supabase.upsertRoom(room).catch((e) => console.warn("join_room_code: reopen upsertRoom failed:", (e as Error).message));
      } else {
        ensureManagedRoom(room, identity);
      }

      if (room.status !== "OPEN") {
        throw new Error("Room not found or closed");
      }

      // Check ban list
      if (roomManager.isBanned(room.tableId, identity.userId)) {
        throw new Error("You are banned from this room");
      }

      // Club membership gate: if the room belongs to a club, only active members can join
      const clubInfo = clubManager.getClubForTable(room.roomCode);
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("This is a club table. Only active club members can join.");
      }

      // Check password for private rooms (non-club private rooms)
      const managed = roomManager.getRoom(room.tableId);
      if (!clubInfo && managed?.settings.visibility === "private" && managed.settings.password) {
        if (payload.password !== managed.settings.password) {
          throw new Error("Incorrect room password");
        }
      }

      socket.join(room.tableId);
      const table = createTableIfNeeded(room);

      // Cancel empty timer if someone joins
      roomManager.checkRoomEmpty(room.tableId, currentPlayerCount(room.tableId) + 1, () => {
        handleRoomAutoClose(room.tableId);
      });

      supabase.touchRoom(room.tableId, "OPEN").catch((e) => console.warn("join_room_code: touchRoom failed:", (e as Error).message));
      openRoomSessionIfNeeded(room.tableId, "join_room_code").catch((e) => console.warn("join_room_code: openRoomSession failed:", (e as Error).message));
      supabase.logEvent({
        tableId: room.tableId,
        eventType: "JOIN_BY_CODE",
        actorUserId: identity.userId,
        payload: { roomCode: room.roomCode }
      }).catch((e) => console.warn("join_room_code: logEvent failed:", (e as Error).message));

      console.log("[JOIN_ROOM_CODE] Emitting room_joined event");
      socket.emit("room_joined", {
        tableId: room.tableId,
        roomCode: room.roomCode,
        roomName: room.roomName
      });
      socket.emit("table_snapshot", table.getPublicState());
      socket.emit("room_state_update", roomManager.getFullState(room.tableId));
      emitPresence(room.tableId);
      void emitLobbySnapshot();
      console.log("[JOIN_ROOM_CODE] Successfully joined room");
    } catch (error) {
      console.log("[JOIN_ROOM_CODE] Error:", (error as Error).message);
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("join_table", async (payload: { tableId: string }) => {
    const room = await ensureRoomByTableId(payload.tableId);
    ensureManagedRoom(room, identity);

    // Club membership gate: if the room belongs to a club, only active members can join
    const joinTableRoomCode = roomCodeForTable(payload.tableId) ?? room.roomCode;
    if (joinTableRoomCode) {
      const clubInfo = clubManager.getClubForTable(joinTableRoomCode);
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        socket.emit("error_event", { message: "This is a club table. Only active club members can join." });
        return;
      }
    }

    const table = createTableIfNeeded(room);
    socket.join(payload.tableId);

    // Cancel empty timer if someone joins the room
    roomManager.checkRoomEmpty(payload.tableId, currentPlayerCount(payload.tableId) + 1, () => {
      handleRoomAutoClose(payload.tableId);
    });

    supabase.touchRoom(payload.tableId, "OPEN").catch((e) => console.warn("join_table: touchRoom failed:", (e as Error).message));
    openRoomSessionIfNeeded(payload.tableId, "join_table").catch((e) => console.warn("join_table: openRoomSession failed:", (e as Error).message));
    supabase.logEvent({
      tableId: payload.tableId,
      eventType: "JOIN_TABLE",
      actorUserId: identity.userId,
      payload: { socketId: socket.id }
    }).catch((e) => console.warn("join_table: logEvent failed:", (e as Error).message));

    socket.emit("room_joined", {
      tableId: room.tableId,
      roomCode: room.roomCode,
      roomName: room.roomName
    });
    socket.emit("table_snapshot", table.getPublicState());
    emitPresence(payload.tableId);
    void emitLobbySnapshot();
  });

  socket.on("sit_down", async (payload: { tableId: string; seat: number; buyIn: number; name?: string }) => {
    try {
      console.log("[SIT_DOWN] Request from", identity.userId, "payload:", payload);
      
      const room = await ensureRoomByTableId(payload.tableId);
      const table = createTableIfNeeded(room);
      
      console.log("[SIT_DOWN] Current players:", table.getPublicState().players.map(p => ({ seat: p.seat, name: p.name })));
      
      const existing = bindingByUser(payload.tableId, identity.userId);
      if (existing && existing.seat !== payload.seat) {
        console.log("[SIT_DOWN] User already seated at", existing.seat);
        throw new Error("You are already seated at this table. Stand up first to switch seats.");
      }

      // Club membership gate: if the room belongs to a club, only active members can sit
      const roomCode = roomCodeForTable(payload.tableId);
      if (roomCode) {
        const clubInfo = clubManager.getClubForTable(roomCode);
        if (clubInfo) {
          if (!clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
            throw new Error("Only active club members can sit at this table");
          }
        }
      }

      // Validate buy-in against room settings
      const managed = roomManager.getRoom(payload.tableId);
      if (managed) {
        if (payload.seat < 1 || payload.seat > managed.settings.maxPlayers) {
          throw new Error(`Seat must be between 1 and ${managed.settings.maxPlayers}`);
        }
      }

      const name = payload.name?.slice(0, 32) || identity.displayName;
      const restoredStack = getRestorableStack(payload.tableId, identity.userId);
      const isRestore = restoredStack != null;
      if (isRestore) {
        if (payload.buyIn < restoredStack) {
          throw new Error(`Table balance requires at least ${restoredStack} chips to rejoin this room`);
        }
      } else if (managed) {
        const { buyInMin, buyInMax } = managed.settings;
        console.log("[SIT_DOWN] Buy-in validation:", payload.buyIn, "range:", buyInMin, "-", buyInMax);
        if (payload.buyIn < buyInMin || payload.buyIn > buyInMax) {
          throw new Error(`Buy-in must be between ${buyInMin} and ${buyInMax}`);
        }
      }
      const stackToSeat = payload.buyIn;

      console.log("[SIT_DOWN] Adding player:", { seat: payload.seat, userId: identity.userId, name, stack: stackToSeat, isRestore });
      
      table.addPlayer({
        seat: payload.seat,
        userId: identity.userId,
        name,
        stack: stackToSeat
      });
      
      console.log("[SIT_DOWN] Player added successfully");

      if (!isRestore) {
        recordSessionBuyIn(payload.tableId, identity.userId, name, stackToSeat);
      }
      setSessionLastStack(payload.tableId, identity.userId, name, stackToSeat);

      socketSeat.set(socket.id, {
        tableId: payload.tableId,
        seat: payload.seat,
        userId: identity.userId,
        name
      });

      supabase.upsertSeat({
        table_id: payload.tableId,
        seat_no: payload.seat,
        user_id: identity.userId,
        display_name: name,
        stack: stackToSeat,
        is_connected: true
      }).catch((e) => console.warn("sit_down: upsertSeat failed:", (e as Error).message));

      supabase.touchRoom(payload.tableId, "OPEN").catch((e) => console.warn("sit_down: touchRoom failed:", (e as Error).message));
      supabase.logEvent({
        tableId: payload.tableId,
        eventType: "SIT_DOWN",
        actorUserId: identity.userId,
        payload: { seat: payload.seat, buyIn: stackToSeat, restored: isRestore }
      }).catch((e) => console.warn("sit_down: logEvent failed:", (e as Error).message));

      if (isRestore) {
        socket.emit("system_message", { message: `Room funds tracking restored your previous stack (${stackToSeat}).` });
      }

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ SEAT REQUEST / APPROVE / REJECT ═══════════ */

  socket.on("seat_request", (payload: { tableId: string; seat: number; buyIn: number; name?: string }) => {
    try {
      console.log("[SEAT_REQUEST] Received from", identity.userId, identity.displayName, "payload:", payload);
      
      const managed = roomManager.getRoom(payload.tableId);
      if (!managed) throw new Error("Room not found");

      if (payload.seat < 1 || payload.seat > managed.settings.maxPlayers) {
        throw new Error(`Seat must be between 1 and ${managed.settings.maxPlayers}`);
      }

      // Club membership gate
      const seatReqRoomCode = roomCodeForTable(payload.tableId);
      if (seatReqRoomCode) {
        const clubInfo = clubManager.getClubForTable(seatReqRoomCode);
        if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
          throw new Error("Only active club members can request seats at this table");
        }
      }

      console.log("[SEAT_REQUEST] Room found, owner:", managed.ownership.ownerId);

      const restoredStack = getRestorableStack(payload.tableId, identity.userId);
      const isRestore = restoredStack != null;
      if (isRestore) {
        if (payload.buyIn < restoredStack) {
          throw new Error(`Table balance requires at least ${restoredStack} chips to rejoin this room`);
        }
      } else {
        const { buyInMin, buyInMax } = managed.settings;
        if (payload.buyIn < buyInMin || payload.buyIn > buyInMax) {
          throw new Error(`Buy-in must be between ${buyInMin} and ${buyInMax}`);
        }
      }
      const requestedStack = payload.buyIn;

      // Check seat availability
      const table = tables.get(payload.tableId);
      if (table) {
        const state = table.getPublicState();
        if (state.players.some((p) => p.seat === payload.seat)) {
          throw new Error("Seat already occupied");
        }
      }

      const orderId = `req_${randomUUID().replace(/-/g, "").slice(0, 8)}`;
      const userName = payload.name?.slice(0, 32) || identity.displayName;
      const request: SeatRequest = {
        orderId,
        tableId: payload.tableId,
        seat: payload.seat,
        buyIn: requestedStack,
        userId: identity.userId,
        userName,
        socketId: socket.id,
        isRestore,
      };
      pendingSeatRequests.set(orderId, request);
      console.log("[SEAT_REQUEST] Stored request:", orderId);

      // Notify host/co-hosts currently in the room (whether seated or spectating)
      const roomSockets = io.sockets.adapter.rooms.get(payload.tableId) ?? new Set<string>();
      let notified = 0;
      for (const sid of roomSockets) {
        const id = socketIdentity.get(sid);
        if (!id) continue;
        if (!roomManager.isHostOrCoHost(payload.tableId, id.userId)) continue;
        io.to(sid).emit("seat_request_pending", {
          orderId, userId: identity.userId, userName, seat: payload.seat, buyIn: requestedStack,
        });
        notified += 1;
      }
      console.log("[SEAT_REQUEST] Notified", notified, "host/co-host sockets");

      socket.emit("seat_request_sent", { orderId, seat: payload.seat });
      if (isRestore) {
        socket.emit("system_message", { message: `Seat request sent with restored stack ${requestedStack}.` });
      }
    } catch (error) {
      console.error("[SEAT_REQUEST] Error:", (error as Error).message);
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("approve_seat", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host/co-host can approve seat requests");
      }

      const request = pendingSeatRequests.get(payload.orderId);
      if (!request || request.tableId !== payload.tableId) {
        throw new Error("Seat request not found or expired");
      }
      pendingSeatRequests.delete(payload.orderId);

      const room = roomsByTableId.get(payload.tableId);
      if (!room) throw new Error("Room not found");
      const table = createTableIfNeeded(room);
      const managed = roomManager.getRoom(payload.tableId);
      if (!managed) throw new Error("Room not found");

      if (request.seat < 1 || request.seat > managed.settings.maxPlayers) {
        throw new Error(`Seat must be between 1 and ${managed.settings.maxPlayers}`);
      }

      if (table.getPublicState().players.some((p) => p.seat === request.seat)) {
        throw new Error("Seat already occupied");
      }

      table.addPlayer({
        seat: request.seat,
        userId: request.userId,
        name: request.userName,
        stack: request.buyIn,
      });

      if (!request.isRestore) {
        recordSessionBuyIn(request.tableId, request.userId, request.userName, request.buyIn);
      }
      setSessionLastStack(request.tableId, request.userId, request.userName, request.buyIn);

      // Bind the requester's socket to the seat
      socketSeat.set(request.socketId, {
        tableId: request.tableId,
        seat: request.seat,
        userId: request.userId,
        name: request.userName,
      });

      // Notify the requester
      io.to(request.socketId).emit("seat_approved", { seat: request.seat, buyIn: request.buyIn });
      if (request.isRestore) {
        io.to(request.socketId).emit("system_message", { message: `Your previous room stack was restored (${request.buyIn}).` });
      }

      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("reject_seat", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host/co-host can reject seat requests");
      }

      const request = pendingSeatRequests.get(payload.orderId);
      if (!request || request.tableId !== payload.tableId) {
        throw new Error("Seat request not found or expired");
      }
      pendingSeatRequests.delete(payload.orderId);

      // Notify the requester
      io.to(request.socketId).emit("seat_rejected", { seat: request.seat, reason: "Host declined your request" });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ DEPOSIT REQUEST FLOW ═══════════ */

  socket.on("deposit_request", (payload: { tableId: string; amount: number }) => {
    try {
      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId) throw new Error("Not seated at this table");

      const managed = roomManager.getRoom(payload.tableId);
      if (!managed) throw new Error("Room not found");
      if (!managed.settings.rebuyAllowed) throw new Error("Rebuys are not allowed in this room");

      const { buyInMax } = managed.settings;
      const table = tables.get(payload.tableId);
      const player = table?.getPublicState().players.find((p) => p.seat === binding.seat);
      if (!player) throw new Error("Player not found");
      if (payload.amount <= 0) throw new Error("Amount must be positive");
      const pendingForSeat = [...pendingDeposits.values()]
        .filter((deposit) => deposit.tableId === payload.tableId && deposit.seat === binding.seat)
        .reduce((sum, deposit) => sum + deposit.amount, 0);
      if (player.stack + pendingForSeat + payload.amount > buyInMax) {
        throw new Error(`Rebuy would exceed max buy-in (${buyInMax})`);
      }

      const orderId = randomUUID();
      const deposit: DepositRequest = {
        orderId, tableId: payload.tableId, seat: binding.seat,
        userId: identity.userId, userName: identity.displayName,
        amount: payload.amount, approved: false,
      };
      pendingDeposits.set(orderId, deposit);

      // Notify host/co-hosts in room (seated or spectating)
      const roomSockets = io.sockets.adapter.rooms.get(payload.tableId) ?? new Set<string>();
      for (const sid of roomSockets) {
        const id = socketIdentity.get(sid);
        if (!id) continue;
        if (!roomManager.isHostOrCoHost(payload.tableId, id.userId)) continue;
        io.to(sid).emit("deposit_request_pending", {
          orderId, userId: identity.userId, userName: identity.displayName,
          seat: binding.seat, amount: payload.amount,
        });
      }

      socket.emit("system_message", { message: `Deposit request of ${payload.amount} sent to host for approval` });
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("approve_deposit", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) throw new Error("Only host/co-host can approve deposits");
      const deposit = pendingDeposits.get(payload.orderId);
      if (!deposit || deposit.tableId !== payload.tableId) throw new Error("Deposit request not found");

      deposit.approved = true;
      io.to(payload.tableId).emit("system_message", {
        message: `Rebuy of ${deposit.amount} for ${deposit.userName} approved — credits at next hand start.`,
      });
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("reject_deposit", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) throw new Error("Only host/co-host can reject deposits");
      const deposit = pendingDeposits.get(payload.orderId);
      if (!deposit || deposit.tableId !== payload.tableId) throw new Error("Deposit request not found");
      pendingDeposits.delete(payload.orderId);

      const sid = socketIdBySeat(payload.tableId, deposit.seat);
      if (sid) io.to(sid).emit("system_message", { message: "Your deposit request was declined by the host" });
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("stand_up", async (payload: { tableId: string; seat: number }) => {
    const table = tables.get(payload.tableId);
    if (!table) return;

    const binding = socketSeat.get(socket.id);
    if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
      socket.emit("error_event", { message: "You can only stand up from your own seat" });
      return;
    }

    // Defer if hand is active — mark as pending and process after hand ends
    if (table.isHandActive()) {
      let pending = pendingStandUps.get(payload.tableId);
      if (!pending) { pending = new Set(); pendingStandUps.set(payload.tableId, pending); }
      pending.add(payload.seat);
      socket.emit("system_message", { message: "Leaving after this hand." });
      broadcastSnapshot(payload.tableId);
      return;
    }

    standUpPlayer(payload.tableId, payload.seat, "Stood up");
  });

  socket.on("start_hand", async (payload: { tableId: string }) => {
    try {
      await ensureRoomByTableId(payload.tableId);
      if (!roomManager.isOwner(payload.tableId, identity.userId)) {
        throw new Error("Only the host can start the game");
      }

      clearAutoDealSchedule(payload.tableId);
      startHandFlow(payload.tableId, identity.userId, "manual");
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("action_submit", async (payload: ActionSubmitPayload) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("table not found");
      const prevState = table.getPublicState();

      if (!prevState.handId || payload.handId !== prevState.handId) {
        throw new Error("stale or invalid handId");
      }

      if (roomManager.isPaused(payload.tableId)) {
        throw new Error("Game is paused");
      }

      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId) {
        throw new Error("player seat not found");
      }

      // Check for stored advice to calculate deviation
      const adviceKey = `${payload.tableId}:${binding.seat}`;
      const storedAdvice = lastAdvice.get(adviceKey);

      // Player finalized an action in time — stop timer
      roomManager.playerActedInTime(payload.tableId, identity.userId);

      const newState = table.applyAction(binding.seat, payload.action, payload.amount);
      logInfo({
        event: "hand.action_applied",
        tableId: payload.tableId,
        handId: payload.handId,
        seat: binding.seat,
        userId: identity.userId,
        action: payload.action,
        amount: payload.amount ?? 0,
        street: newState.street,
      });

      io.to(payload.tableId).emit("action_applied", {
        seat: binding.seat,
        action: payload.action,
        amount: payload.amount ?? 0,
        pot: newState.pot
      });

      // Send deviation feedback if we had advice for this spot
      if (storedAdvice && storedAdvice.handId === payload.handId) {
        const deviation = calculateDeviation(storedAdvice.mix, payload.action);
        const deviationPayload = {
          ...storedAdvice,
          deviation,
          playerAction: payload.action
        };
        io.to(socketIdBySeat(payload.tableId, binding.seat)).emit("advice_deviation", deviationPayload);
        lastAdvice.delete(adviceKey);
      }

      if (prevState.street !== newState.street) {
        io.to(payload.tableId).emit("street_advanced", { street: newState.street, board: newState.board });
      }

      // Use shared post-action logic (handles runout, finalize, or next actor)
      handlePostAction(payload.tableId, table, newState);

      supabase.logEvent({
        tableId: payload.tableId,
        eventType: "ACTION_SUBMIT",
        actorUserId: identity.userId,
        handId: payload.handId,
        payload: {
          seat: binding.seat,
          action: payload.action,
          amount: payload.amount ?? 0,
          pot: newState.pot
        }
      }).catch((e) => logWarn({
        event: "supabase.log_event.failed",
        tableId: payload.tableId,
        handId: payload.handId,
        seat: binding.seat,
        message: (e as Error).message,
      }));

    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("show_hand", (payload: { tableId: string; handId: string; seat: number; scope: "table" }) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("table not found");
      if (payload.scope !== "table") throw new Error("unsupported show scope");

      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
        throw new Error("You can only show your own hand");
      }

      const room = roomManager.getRoom(payload.tableId);
      if (!room?.handActive) throw new Error("hand already ended");

      const state = table.getPublicState();
      if (!state.handId || state.handId !== payload.handId) {
        throw new Error("stale or invalid handId");
      }

      const player = state.players.find((p) => p.seat === payload.seat);
      if (!player) throw new Error("player not found");

      const inShowdownDecision = state.showdownPhase === "decision";
      const canShowInShowdown = inShowdownDecision && player.inHand && !player.folded;
      const canShowAfterFold = (room.settings.allowShowAfterFold ?? false) && player.folded;
      if (!canShowInShowdown && !canShowAfterFold) {
        throw new Error("show hand is not allowed right now");
      }

      if (!table.revealPublicHand(payload.seat)) {
        throw new Error("cannot reveal hand");
      }

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);

      if (state.showdownPhase === "decision") {
        maybeFinalizeShowdownDecision(payload.tableId, table);
      }
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("muck_hand", (payload: { tableId: string; handId: string; seat: number }) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("table not found");

      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
        throw new Error("You can only muck your own hand");
      }

      const room = roomManager.getRoom(payload.tableId);
      if (!room?.handActive) throw new Error("hand already ended");

      const state = table.getPublicState();
      if (!state.handId || state.handId !== payload.handId) {
        throw new Error("stale or invalid handId");
      }
      if (state.showdownPhase !== "decision") {
        throw new Error("muck is only available during showdown");
      }

      const player = state.players.find((p) => p.seat === payload.seat);
      if (!player || !player.inHand || player.folded) {
        throw new Error("only live showdown hands can muck");
      }

      if (!table.muckPublicHand(payload.seat)) {
        throw new Error("cannot muck hand");
      }

      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
      maybeFinalizeShowdownDecision(payload.tableId, table);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  // Run count decision: sent by the underdog player after all-in situation is confirmed
  socket.on("run_count_submit", (payload: { tableId: string; handId: string; runCount: 1 | 2 }) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("table not found");

      const pending = pendingAllInPrompts.get(payload.tableId);
      if (!pending || pending.handId !== payload.handId) {
        throw new Error("no pending run count decision");
      }

      // Verify the submitter is the correct player (the underdog)
      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId || binding.seat !== pending.prompt.actorSeat) {
        throw new Error("not the designated player for run count decision");
      }

      // Clear timeout and pending prompt
      const timeout = pendingRunCountTimeouts.get(payload.tableId);
      if (timeout) {
        clearTimeout(timeout);
        pendingRunCountTimeouts.delete(payload.tableId);
      }
      pendingAllInPrompts.delete(payload.tableId);

      // Apply run count choice and begin sequential runout
      const runCount = payload.runCount === 2 ? 2 : 1;
      table.setAllInRunCount(runCount);
      logInfo({
        event: "all_in.run_count.selected",
        tableId: payload.tableId,
        handId: payload.handId,
        seat: binding.seat,
        runCount,
      });

      io.to(payload.tableId).emit("run_count_chosen", { runCount, seat: binding.seat });
      void handleSequentialRunout(payload.tableId, table);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("request_think_extension", (payload: { tableId: string }) => {
    try {
      const result = roomManager.requestThinkExtension(payload.tableId, identity.userId);
      if (!result.ok) {
        socket.emit("error_event", { message: result.reason ?? "Failed to extend thinking time" });
        return;
      }

      socket.emit("think_extension_result", {
        addedSeconds: result.addedSeconds ?? 0,
        remainingUses: result.remainingUses ?? 0,
      });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("request_session_stats", (payload: { tableId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host or co-host can view session stats");
      }
      const room = roomManager.getRoom(payload.tableId);
      if (!room) throw new Error("Room not found");
      const table = tables.get(payload.tableId);
      const currentPlayers = table ? table.getPublicState().players : [];
      const roomStats = getRoomSessionStats(payload.tableId, false);
      const entries: Array<{ seat: number | null; userId: string; name: string; totalBuyIn: number; currentStack: number; net: number; handsPlayed: number; preservedBalance: number }> = [];

      if (roomStats) {
        for (const [uid, entry] of roomStats.entries()) {
          const seated = currentPlayers.find((p) => p.userId === uid);
          const currentStack = seated ? seated.stack : entry.lastStack;
          entries.push({
            seat: seated?.seat ?? null,
            userId: entry.userId,
            name: entry.name,
            totalBuyIn: entry.totalBuyIn,
            currentStack,
            net: currentStack - entry.totalBuyIn,
            handsPlayed: entry.handsPlayed,
            preservedBalance: entry.lastStack,
          });
        }
      }

      socket.emit("session_stats", { tableId: payload.tableId, entries });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("request_rejoin_stack", (payload: { tableId: string }) => {
    try {
      const room = roomManager.getRoom(payload.tableId);
      if (!room) throw new Error("Room not found");
      const stack = getRestorableStack(payload.tableId, identity.userId);
      socket.emit("rejoin_stack_info", { tableId: payload.tableId, stack });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("leave_table", async (payload: { tableId: string }) => {
    const binding = socketSeat.get(socket.id);
    const table = tables.get(payload.tableId);
    if (binding && binding.tableId === payload.tableId && table?.isHandActive()) {
      let pending = pendingStandUps.get(payload.tableId);
      if (!pending) { pending = new Set(); pendingStandUps.set(payload.tableId, pending); }
      pending.add(binding.seat);
      queueLeaveTableAfterHand(payload.tableId, socket.id);
      socket.emit("system_message", { message: "Leaving after this hand." });
      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
      return;
    }

    if (binding && binding.tableId === payload.tableId) {
      standUpPlayer(payload.tableId, binding.seat, "Left table");
    }

    socket.leave(payload.tableId);
    supabase.logEvent({
      tableId: payload.tableId,
      eventType: "LEAVE_TABLE",
      actorUserId: identity.userId,
      payload: { socketId: socket.id }
    }).catch((e) => console.warn("leave_table: logEvent failed:", (e as Error).message));
    socket.emit("left_table", { tableId: payload.tableId });
    void emitLobbySnapshot();
  });

  /* ═══════════ ROOM MANAGEMENT SOCKET HANDLERS ═══════════ */

  socket.on("request_room_state", (payload: { tableId: string }) => {
    const state = roomManager.getFullState(payload.tableId);
    if (state) socket.emit("room_state_update", state);
  });

  socket.on("update_settings", (payload: UpdateSettingsPayload) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can change settings");
      }
      const result = roomManager.updateSettings(payload.tableId, payload.settings, identity.userId, identity.displayName);
      if (!result) throw new Error("Room not found");

      // Sync key settings back to RoomInfo for lobby display
      const managed = roomManager.getRoom(payload.tableId);
      const roomInfo = roomsByTableId.get(payload.tableId);
      if (managed && roomInfo) {
        roomInfo.smallBlind = managed.settings.smallBlind;
        roomInfo.bigBlind = managed.settings.bigBlind;
        roomInfo.maxPlayers = managed.settings.maxPlayers;
        roomInfo.isPublic = managed.settings.visibility === "public";
        roomInfo.updatedAt = new Date().toISOString();
      }

      socket.emit("settings_updated", { applied: result.applied, deferred: result.deferred });
      if (Object.keys(result.deferred).length > 0) {
        socket.emit("system_message", { message: `Some settings will apply next hand: ${Object.keys(result.deferred).join(", ")}` });
      }
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("kick_player", (payload: KickPlayerPayload) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can kick players");
      }
      const table = tables.get(payload.tableId);
      if (table?.isHandActive()) {
        throw new Error("Cannot kick players during an active hand");
      }
      // Cannot kick yourself
      if (payload.targetUserId === identity.userId) {
        throw new Error("Cannot kick yourself");
      }

      // Find target's socket and binding
      let targetSocketId: string | null = null;
      let targetName = "Unknown";
      for (const [sid, b] of socketSeat.entries()) {
        if (b.tableId === payload.tableId && b.userId === payload.targetUserId) {
          targetSocketId = sid;
          targetName = b.name;
          break;
        }
      }

      roomManager.kickPlayer(
        payload.tableId, payload.targetUserId, targetName,
        payload.reason ?? "", payload.ban ?? false,
        identity.userId, identity.displayName
      );

      if (targetSocketId) {
        const targetBinding = socketSeat.get(targetSocketId);
        if (table && targetBinding) {
          table.removePlayer(targetBinding.seat);
          socketSeat.delete(targetSocketId);
        }
        io.to(targetSocketId).emit("kicked", {
          reason: payload.reason ?? "Removed by host",
          banned: payload.ban ?? false,
        });
        const targetSocket = io.sockets.sockets.get(targetSocketId);
        if (targetSocket) targetSocket.leave(payload.tableId);
      }

      broadcastSnapshot(payload.tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("transfer_ownership", (payload: TransferOwnershipPayload) => {
    try {
      if (!roomManager.isOwner(payload.tableId, identity.userId)) {
        throw new Error("Only the owner can transfer ownership");
      }
      // Find target name
      let targetName = "Unknown";
      for (const b of socketSeat.values()) {
        if (b.tableId === payload.tableId && b.userId === payload.newOwnerId) {
          targetName = b.name;
          break;
        }
      }
      const ok = roomManager.transferOwnership(payload.tableId, payload.newOwnerId, targetName, identity.userId, identity.displayName);
      if (!ok) throw new Error("Transfer failed");
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("set_cohost", (payload: SetCoHostPayload) => {
    try {
      if (!roomManager.isOwner(payload.tableId, identity.userId)) {
        throw new Error("Only the owner can manage co-hosts");
      }
      let userName = "Unknown";
      for (const b of socketSeat.values()) {
        if (b.tableId === payload.tableId && b.userId === payload.userId) {
          userName = b.name;
          break;
        }
      }
      const ok = roomManager.setCoHost(payload.tableId, payload.userId, userName, payload.add, identity.userId, identity.displayName);
      if (!ok) throw new Error("Failed to update co-host");
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("game_control", (payload: GameControlPayload) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can control the game");
      }

      switch (payload.action) {
        case "pause": {
          // Defer pause if hand is active
          const tbl = tables.get(payload.tableId);
          if (tbl && tbl.isHandActive()) {
            pendingPause.set(payload.tableId, { userId: identity.userId, displayName: identity.displayName });
            io.to(payload.tableId).emit("system_message", { message: "Game will pause after the current hand ends" });
            broadcastSnapshot(payload.tableId);
            return; // Don't broadcastSnapshot again at the end
          }
          roomManager.pauseGame(payload.tableId, identity.userId, identity.displayName);
          break;
        }
        case "resume":
          roomManager.resumeGame(payload.tableId, identity.userId, identity.displayName);
          // Restart timer if hand is active
          if (roomManager.getRoom(payload.tableId)?.handActive) {
            startTimerForActor(payload.tableId);
          }
          break;
        case "end":
          if (!roomManager.isOwner(payload.tableId, identity.userId)) {
            throw new Error("Only the host can stop auto-deal");
          }
          clearAutoDealSchedule(payload.tableId);
          clearShowdownDecisionTimeout(payload.tableId);
          roomManager.endGame(payload.tableId, identity.userId, identity.displayName);
          closeRoomSessionIfOpen(payload.tableId, "game_control_end").catch((e) => console.warn("game_control(end): closeRoomSession failed:", (e as Error).message));
          break;
        case "start":
          // Delegate to start_hand logic
          socket.emit("error_event", { message: "Use start_hand event to start a hand" });
          return;
        case "restart":
          if (!roomManager.isOwner(payload.tableId, identity.userId)) {
            throw new Error("Only the host can restart the game");
          }
          clearAutoDealSchedule(payload.tableId);
          clearShowdownDecisionTimeout(payload.tableId);
          roomManager.endGame(payload.tableId, identity.userId, identity.displayName);
          closeRoomSessionIfOpen(payload.tableId, "game_control_restart").catch((e) => console.warn("game_control(restart): closeRoomSession failed:", (e as Error).message));
          // Client should call start_hand after restart
          break;
      }

      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ CLOSE ROOM (Host only) ═══════════ */

  socket.on("close_room", (payload: { tableId: string }) => {
    try {
      if (!roomManager.isOwner(payload.tableId, identity.userId)) {
        throw new Error("Only the host can close the room");
      }

      logInfo({
        event: "room.close.requested",
        tableId: payload.tableId,
        userId: identity.userId,
        message: identity.displayName,
      });

      // Stop auto-deal and timers
      clearAutoDealSchedule(payload.tableId);
      clearShowdownDecisionTimeout(payload.tableId);
      roomManager.endGame(payload.tableId, identity.userId, identity.displayName);

      // Notify all players and send them back to lobby
      io.to(payload.tableId).emit("room_closed", { tableId: payload.tableId, reason: "Host closed the room" });

      // Remove all players from the table and clean up bindings
      const table = tables.get(payload.tableId);
      if (table) {
        const state = table.getPublicState();
        for (const player of state.players) {
          table.removePlayer(player.seat);
        }
      }

      // Clean up all socket bindings for this table
      for (const [sid, binding] of socketSeat.entries()) {
        if (binding.tableId === payload.tableId) {
          socketSeat.delete(sid);
          const sock = io.sockets.sockets.get(sid);
          if (sock) sock.leave(payload.tableId);
        }
      }

      // Remove room from all maps
      const room = roomsByTableId.get(payload.tableId);
      if (room) {
        roomCodeToTableId.delete(room.roomCode);
        sessionStatsByRoomCode.delete(room.roomCode);
        roomsByTableId.delete(payload.tableId);
      }
      pendingStandUps.delete(payload.tableId);
      pendingTableLeaves.delete(payload.tableId);
      pendingPause.delete(payload.tableId);
      pendingAllInPrompts.delete(payload.tableId);
      const runCountTimeout = pendingRunCountTimeouts.get(payload.tableId);
      if (runCountTimeout) {
        clearTimeout(runCountTimeout);
        pendingRunCountTimeouts.delete(payload.tableId);
      }
      for (const [orderId, request] of pendingSeatRequests.entries()) {
        if (request.tableId === payload.tableId) pendingSeatRequests.delete(orderId);
      }
      for (const [orderId, deposit] of pendingDeposits.entries()) {
        if (deposit.tableId === payload.tableId) pendingDeposits.delete(orderId);
      }
      tables.delete(payload.tableId);
      roomManager.deleteRoom(payload.tableId);

      closeRoomSessionIfOpen(payload.tableId, "close_room").catch(() => {});
      supabase.touchRoom(payload.tableId, "CLOSED").catch(() => {});
      supabase.logEvent({
        tableId: payload.tableId,
        eventType: "ROOM_CLOSED",
        actorUserId: identity.userId,
        payload: { reason: "host_closed" },
      }).catch(() => {});

      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ CLUBS ═══════════ */

  socket.on("club_create", (payload: ClubCreatePayload) => {
    try {
      const club = clubManager.createClub({
        ownerUserId: identity.userId,
        ownerDisplayName: identity.displayName,
        name: payload.name,
        description: payload.description,
        visibility: payload.visibility,
        requireApprovalToJoin: payload.requireApprovalToJoin,
        badgeColor: payload.badgeColor,
      });
      socket.emit("club_created", { club });
      // Refresh club list for the user
      socket.emit("club_list", { clubs: clubManager.listMyClubs(identity.userId) });
    } catch (error) {
      socket.emit("club_error", { code: "CREATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_update", (payload: ClubUpdatePayload) => {
    try {
      const club = clubManager.updateClub(payload.clubId, identity.userId, {
        name: payload.name,
        description: payload.description,
        visibility: payload.visibility,
        requireApprovalToJoin: payload.requireApprovalToJoin,
        badgeColor: payload.badgeColor,
        logoUrl: payload.logoUrl,
      });
      if (!club) {
        socket.emit("club_error", { code: "UPDATE_DENIED", message: "Cannot update club — insufficient permissions or club not found" });
        return;
      }
      socket.emit("club_updated", { club });
    } catch (error) {
      socket.emit("club_error", { code: "UPDATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_list_my_clubs", () => {
    try {
      const clubs = clubManager.listMyClubs(identity.userId);
      socket.emit("club_list", { clubs });
    } catch (error) {
      socket.emit("club_error", { code: "LIST_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_get_detail", (payload: { clubId: string }) => {
    try {
      const result = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (!result) {
        socket.emit("club_error", { code: "DETAIL_DENIED", message: "Club not found or you are not a member" });
        return;
      }
      socket.emit("club_detail", result);
    } catch (error) {
      socket.emit("club_error", { code: "DETAIL_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_join_request", (payload: ClubJoinRequestPayload) => {
    try {
      const result = clubManager.requestJoin(
        payload.clubCode,
        identity.userId,
        identity.displayName,
        payload.inviteCode,
      );
      socket.emit("club_join_result", {
        clubId: result.clubId ?? "",
        status: result.status,
        message: result.message,
      });
      if (result.status === "joined") {
        socket.emit("club_list", { clubs: clubManager.listMyClubs(identity.userId) });
      }
    } catch (error) {
      socket.emit("club_error", { code: "JOIN_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_join_approve", (payload: ClubJoinDecisionPayload) => {
    try {
      const member = clubManager.approveJoin(payload.clubId, identity.userId, payload.userId);
      if (!member) {
        socket.emit("club_error", { code: "APPROVE_DENIED", message: "Cannot approve — insufficient permissions or member not found" });
        return;
      }
      socket.emit("club_member_update", { clubId: payload.clubId, member });
      // Notify the approved user if they're online
      for (const [sid, ident] of socketIdentity.entries()) {
        if (ident.userId === payload.userId) {
          io.to(sid).emit("club_join_result", { clubId: payload.clubId, status: "joined", message: "Your join request has been approved!" });
          io.to(sid).emit("club_list", { clubs: clubManager.listMyClubs(payload.userId) });
        }
      }
    } catch (error) {
      socket.emit("club_error", { code: "APPROVE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_join_reject", (payload: ClubJoinDecisionPayload) => {
    try {
      const ok = clubManager.rejectJoin(payload.clubId, identity.userId, payload.userId);
      if (!ok) {
        socket.emit("club_error", { code: "REJECT_DENIED", message: "Cannot reject — insufficient permissions or member not found" });
        return;
      }
      // Notify the rejected user if they're online
      for (const [sid, ident] of socketIdentity.entries()) {
        if (ident.userId === payload.userId) {
          io.to(sid).emit("club_join_result", { clubId: payload.clubId, status: "error", message: "Your join request was rejected" });
        }
      }
      // Refresh detail for admin
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "REJECT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_invite_create", (payload: ClubInviteCreatePayload) => {
    try {
      const invite = clubManager.createInvite(payload.clubId, identity.userId, payload.maxUses, payload.expiresInHours);
      if (!invite) {
        socket.emit("club_error", { code: "INVITE_DENIED", message: "Cannot create invite — insufficient permissions" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "INVITE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_invite_revoke", (payload: ClubInviteRevokePayload) => {
    try {
      const ok = clubManager.revokeInvite(payload.clubId, identity.userId, payload.inviteId);
      if (!ok) {
        socket.emit("club_error", { code: "REVOKE_DENIED", message: "Cannot revoke invite" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "REVOKE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_update_role", (payload: ClubMemberUpdateRolePayload) => {
    try {
      const member = clubManager.updateMemberRole(payload.clubId, identity.userId, payload.userId, payload.newRole);
      if (!member) {
        socket.emit("club_error", { code: "ROLE_DENIED", message: "Cannot update role — insufficient permissions" });
        return;
      }
      socket.emit("club_member_update", { clubId: payload.clubId, member });
    } catch (error) {
      socket.emit("club_error", { code: "ROLE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_kick", (payload: ClubMemberKickPayload) => {
    try {
      const ok = clubManager.kickMember(payload.clubId, identity.userId, payload.userId);
      if (!ok) {
        socket.emit("club_error", { code: "KICK_DENIED", message: "Cannot kick member" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "KICK_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_ban", (payload: ClubMemberBanPayload) => {
    try {
      const ok = clubManager.banMember(payload.clubId, identity.userId, payload.userId, payload.reason, payload.expiresInHours);
      if (!ok) {
        socket.emit("club_error", { code: "BAN_DENIED", message: "Cannot ban member" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "BAN_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_unban", (payload: ClubMemberUnbanPayload) => {
    try {
      const ok = clubManager.unbanMember(payload.clubId, identity.userId, payload.userId);
      if (!ok) {
        socket.emit("club_error", { code: "UNBAN_DENIED", message: "Cannot unban member" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "UNBAN_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_ruleset_create", (payload: ClubRulesetCreatePayload) => {
    try {
      const ruleset = clubManager.createRuleset(payload.clubId, identity.userId, payload.name, payload.rules, payload.isDefault);
      if (!ruleset) {
        socket.emit("club_error", { code: "RULESET_DENIED", message: "Cannot create ruleset — insufficient permissions" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "RULESET_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_ruleset_update", (payload: ClubRulesetUpdatePayload) => {
    try {
      const ruleset = clubManager.updateRuleset(payload.clubId, identity.userId, payload.rulesetId, {
        name: payload.name,
        rules: payload.rules,
      });
      if (!ruleset) {
        socket.emit("club_error", { code: "RULESET_UPDATE_DENIED", message: "Cannot update ruleset" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "RULESET_UPDATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_ruleset_set_default", (payload: ClubRulesetSetDefaultPayload) => {
    try {
      const ok = clubManager.setDefaultRuleset(payload.clubId, identity.userId, payload.rulesetId);
      if (!ok) {
        socket.emit("club_error", { code: "RULESET_DEFAULT_DENIED", message: "Cannot set default ruleset" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "RULESET_DEFAULT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_create", async (payload: ClubTableCreatePayload) => {
    try {
      const result = clubManager.createTable(payload.clubId, identity.userId, payload.name, payload.rulesetId);
      if (!result) {
        socket.emit("club_error", { code: "TABLE_DENIED", message: "Cannot create table — insufficient permissions" });
        return;
      }

      const { clubTable, rules } = result;
      const club = clubManager.getClub(payload.clubId);

      // Create the actual game room using the club rules
      const roomCode = await generateUniqueRoomCode();
      const tableId = `tbl_${randomUUID().replace(/-/g, "").slice(0, 10)}`;
      const room: RoomInfo = {
        tableId,
        roomCode,
        roomName: `${club?.name ?? "Club"} — ${clubTable.name}`,
        maxPlayers: rules.maxSeats,
        smallBlind: rules.stakes.smallBlind,
        bigBlind: rules.stakes.bigBlind,
        status: "OPEN",
        isPublic: false, // Club tables are always private
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        createdBy: identity.userId,
      };

      registerRoom(room);
      createTableIfNeeded(room);

      // Register with room manager using club rules
      roomManager.createRoom({
        tableId: room.tableId,
        roomCode: room.roomCode,
        roomName: room.roomName,
        ownerId: identity.userId,
        ownerName: identity.displayName,
        settings: {
          maxPlayers: rules.maxSeats,
          smallBlind: rules.stakes.smallBlind,
          bigBlind: rules.stakes.bigBlind,
          buyInMin: rules.buyIn.minBuyIn,
          buyInMax: rules.buyIn.maxBuyIn,
          actionTimerSeconds: rules.time.actionTimeSec,
          timeBankSeconds: rules.time.timeBankSec,
          disconnectGracePeriod: rules.time.disconnectGraceSec,
          autoStartNextHand: rules.dealing.autoDealEnabled,
          spectatorAllowed: rules.moderation.allowSpectators,
          runItTwice: rules.runit.allowRunItTwice,
          runItTwiceMode: rules.runit.allowRunItTwice ? "ask_players" : "off",
          straddleAllowed: rules.extras.straddleAllowed,
          bombPotEnabled: rules.extras.bombPotEnabled,
          rabbitHunting: rules.extras.rabbitHuntEnabled,
          visibility: "private",
        },
      });

      // Link back to club
      clubManager.setTableRoomCode(payload.clubId, clubTable.id, roomCode);

      // Persist to Supabase
      supabase.upsertRoom(room).catch((e) => logWarn({
        event: "club_table.create.persist_failed",
        tableId: room.tableId,
        message: (e as Error).message,
      }));

      socket.emit("club_table_created", {
        clubId: payload.clubId,
        table: { ...clubTable, roomCode },
        roomCode,
      });

      // Refresh club detail
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_CREATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_list", (payload: { clubId: string }) => {
    try {
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (!detail) {
        socket.emit("club_error", { code: "TABLE_LIST_DENIED", message: "Not a member" });
        return;
      }
      // Enrich tables with live player counts
      const enrichedTables = detail.tables.map((t) => {
        if (t.roomCode) {
          const tid = roomCodeToTableId.get(t.roomCode);
          if (tid) {
            const tbl = tables.get(tid);
            const managed = roomManager.getRoom(tid);
            if (tbl) {
              const state = tbl.getPublicState();
              t.playerCount = state.players.length;
              t.maxPlayers = managed?.settings.maxPlayers ?? 6;
              t.stakes = `${state.smallBlind}/${state.bigBlind}`;
            }
          }
        }
        return t;
      });
      socket.emit("club_detail", { ...detail, tables: enrichedTables });
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_LIST_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_close", (payload: ClubTableClosePayload) => {
    try {
      const ok = clubManager.closeTable(payload.clubId, identity.userId, payload.tableId);
      if (!ok) {
        socket.emit("club_error", { code: "TABLE_CLOSE_DENIED", message: "Cannot close table" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_CLOSE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_pause", (payload: ClubTablePausePayload) => {
    try {
      // Pause is deferred until hand end (enforced by rules)
      const ok = clubManager.pauseTable(payload.clubId, identity.userId, payload.tableId);
      if (!ok) {
        socket.emit("club_error", { code: "TABLE_PAUSE_DENIED", message: "Cannot pause table" });
        return;
      }
      const detail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (detail) socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_PAUSE_FAILED", message: (error as Error).message });
    }
  });

  /* ═══════════ DISCONNECT ═══════════ */

  socket.on("disconnect", async () => {
    const binding = socketSeat.get(socket.id);
    if (binding) {
      const managed = roomManager.getRoom(binding.tableId);
      const table = tables.get(binding.tableId);

      // If hand is active, use disconnect grace period instead of immediate removal
      if (managed && table && table.isHandActive()) {
        roomManager.startDisconnectGrace(
          binding.tableId,
          binding.seat,
          identity.userId,
          () => {
            // Grace expired — auto-fold and remove player
            const tbl = tables.get(binding.tableId);
            if (tbl && tbl.isHandActive()) {
              const state = tbl.getPublicState();
              if (state.actorSeat === binding.seat) {
                try {
                  tbl.applyAction(binding.seat, "fold");
                  io.to(binding.tableId).emit("action_applied", {
                    seat: binding.seat, action: "fold", amount: 0,
                    pot: tbl.getPublicState().pot, auto: true,
                  });
                  const newState = tbl.getPublicState();
                  handlePostAction(binding.tableId, tbl, newState);
                } catch { /* already folded or hand ended */ }
              }
            }
            // Now remove the player
            const tbl2 = tables.get(binding.tableId);
            if (tbl2) {
              const stateBeforeLeave = tbl2.getPublicState();
              const leavingPlayer = stateBeforeLeave.players.find((player) => player.seat === binding.seat);
              if (leavingPlayer) {
                setSessionLastStack(binding.tableId, leavingPlayer.userId, leavingPlayer.name, leavingPlayer.stack);
              }
              tbl2.removePlayer(binding.seat);
              broadcastSnapshot(binding.tableId);
            }
            supabase.removeSeat(binding.tableId, binding.seat).catch(() => {});
            // Check room empty
            roomManager.checkRoomEmpty(binding.tableId, currentPlayerCount(binding.tableId), () => {
              handleRoomAutoClose(binding.tableId);
            });
            void emitLobbySnapshot();
          }
        );
        // Mark disconnected in Supabase but keep seat for grace period
        supabase.setDisconnected(binding.tableId, binding.seat).catch((e) => console.warn("disconnect: setDisconnected failed:", (e as Error).message));
        // Arm idle watchdog in case all players disconnect
        resetHandIdleWatchdog(binding.tableId);
      } else {
        // No active hand — remove player immediately
        if (table) {
          const stateBeforeLeave = table.getPublicState();
          const leavingPlayer = stateBeforeLeave.players.find((player) => player.seat === binding.seat);
          if (leavingPlayer) {
            setSessionLastStack(binding.tableId, leavingPlayer.userId, leavingPlayer.name, leavingPlayer.stack);
          }
          table.removePlayer(binding.seat);
          broadcastSnapshot(binding.tableId);
        }
        supabase.setDisconnected(binding.tableId, binding.seat).catch((e) => console.warn("disconnect: setDisconnected failed:", (e as Error).message));
        supabase.removeSeat(binding.tableId, binding.seat).catch(() => {});
      }

      // Ownership transfer if disconnected player is the owner
      if (roomManager.isOwner(binding.tableId, identity.userId)) {
        const onlinePlayers = bindingsByTable(binding.tableId)
          .filter(({ socketId: sid }) => sid !== socket.id)
          .map(({ binding: b }) => ({ userId: b.userId, name: b.name }));
        roomManager.autoTransferOwnership(binding.tableId, onlinePlayers);
      }

      supabase.touchRoom(binding.tableId, "OPEN").catch((e) => console.warn("disconnect: touchRoom failed:", (e as Error).message));
      supabase.logEvent({
        tableId: binding.tableId,
        eventType: "SOCKET_DISCONNECT",
        actorUserId: identity.userId,
        payload: { seat: binding.seat }
      }).catch((e) => console.warn("disconnect: logEvent failed:", (e as Error).message));

      socketSeat.delete(socket.id);
      touchLocalRoom(binding.tableId);

      // Check room empty auto-close
      roomManager.checkRoomEmpty(binding.tableId, currentPlayerCount(binding.tableId), () => {
        handleRoomAutoClose(binding.tableId);
      });

      void emitLobbySnapshot();
    }
    socketIdentity.delete(socket.id);
  });
});

const port = runtimeConfig.port;
let shutdownInProgress = false;
let forceExitTimer: ReturnType<typeof setTimeout> | null = null;

async function gracefulShutdown(signal: NodeJS.Signals): Promise<void> {
  if (shutdownInProgress) return;
  shutdownInProgress = true;

  logInfo({
    event: "server.shutdown.start",
    message: signal,
    activeTables: tables.size,
    activeRooms: roomsByTableId.size,
  });

  if (forceExitTimer) {
    clearTimeout(forceExitTimer);
  }
  forceExitTimer = setTimeout(() => {
    logError({
      event: "server.shutdown.timeout",
      message: "Forcing process exit after 12s timeout.",
    });
    process.exit(1);
  }, 12_000);

  try {
    const tableIds = [...roomsByTableId.keys()];
    for (const tableId of tableIds) {
      clearAutoDealSchedule(tableId);
      clearShowdownDecisionTimeout(tableId);
      clearHandIdleWatchdog(tableId);
      const runCountTimeout = pendingRunCountTimeouts.get(tableId);
      if (runCountTimeout) {
        clearTimeout(runCountTimeout);
      }
    }
    pendingRunCountTimeouts.clear();
    pendingAllInPrompts.clear();
    pendingStandUps.clear();
    pendingTableLeaves.clear();
    pendingPause.clear();
    pendingSeatRequests.clear();
    pendingDeposits.clear();

    await Promise.allSettled(tableIds.map((tableId) => closeRoomSessionIfOpen(tableId, "server_shutdown")));

    await new Promise<void>((resolve) => io.close(() => resolve()));
    await new Promise<void>((resolve, reject) => {
      httpServer.close((err) => {
        if (err) {
          reject(err);
          return;
        }
        resolve();
      });
    });

    if (forceExitTimer) {
      clearTimeout(forceExitTimer);
      forceExitTimer = null;
    }

    logInfo({ event: "server.shutdown.complete" });
    process.exit(0);
  } catch (error) {
    if (forceExitTimer) {
      clearTimeout(forceExitTimer);
      forceExitTimer = null;
    }
    logError({
      event: "server.shutdown.failed",
      message: (error as Error).message,
    });
    process.exit(1);
  }
}

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    void gracefulShutdown(signal);
  });
}

httpServer.listen(port, () => {
  logInfo({
    event: "server.started",
    message: `http://localhost:${port}`,
    supabaseEnabled: supabase.enabled(),
    configVersion: runtimeConfig.version,
  });
});
