import express from "express";
import cors from "cors";
import { createServer } from "node:http";
import { randomInt, randomUUID } from "node:crypto";
import { Server, type Socket } from "socket.io";
import { GameTable } from "@cardpilot/game-engine";
import { getPreflopAdvice, getPostflopAdvice, calculateDeviation } from "@cardpilot/advice-engine";
import { calculateEquity, type Card } from "@cardpilot/poker-evaluator";
import { DEFAULT_CLUB_RULES, SHOWDOWN_SPEED_DELAYS_MS, describeHandStrength } from "@cardpilot/shared-types";
import type {
  ActionSubmitPayload, AdvicePayload, LobbyRoomSummary, TableState,
  UpdateSettingsPayload, KickPlayerPayload, TransferOwnershipPayload,
  SetCoHostPayload, GameControlPayload, JoinRoomWithPasswordPayload, AllInPrompt,
  RoomFullState, TimerState, HistoryHandDetailCore, HistoryHandPlayerSummary, HistoryHandSummaryCore,
  HistoryGTOHandRecord, SevenTwoBountyInfo,
} from "@cardpilot/shared-types";
import { getRuntimeConfig } from "./config";
import { logError, logInfo, logWarn } from "./logger";
import { SupabasePersistence, type PersistHandHistoryPayload, type RoomRecord, type SessionContextMetadata, type VerifiedIdentity } from "./supabase";
import { RoomManager } from "./room-manager";
import { ClubManager } from "./club-manager";
import { ClubRepo, type AppendWalletTxInput } from "./services/club-repo";
import { ClubRepoJson } from "./services/club-repo-json";
import { AuditService } from "./services/audit-service";
import { syncBots, removeAllBots, shutdownAllBots, getBotUserIds } from "./services/bot-orchestrator.js";
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
  ClubTableUpdatePayload,
  ClubTableClosePayload,
  ClubTablePausePayload,
  ClubTableJoinPayload,
  ClubRules,
  ClubWalletTransaction,
  ClubLeaderboardMetric,
  ClubLeaderboardRange,
} from "@cardpilot/shared-types";

const runtimeConfig = getRuntimeConfig();
const IDENTITY_DEBUG = process.env.CARDPILOT_DEBUG_IDENTITY === "1";

type AnalyzeHandGTOFn = (
  handRecord: HistoryGTOHandRecord,
  precision?: "fast" | "deep"
) => Promise<unknown>;

let analyzeHandGTOFn: AnalyzeHandGTOFn | null = null;
let gtoAnalyzerLoadAttempted = false;

async function getAnalyzeHandGTO(): Promise<AnalyzeHandGTOFn | null> {
  if (analyzeHandGTOFn) return analyzeHandGTOFn;
  if (gtoAnalyzerLoadAttempted) return null;

  gtoAnalyzerLoadAttempted = true;
  try {
    const mod = await import("./services/gto-analyzer");
    analyzeHandGTOFn = mod.analyzeHandGTO as AnalyzeHandGTOFn;
    return analyzeHandGTOFn;
  } catch (error) {
    logWarn({
      event: "gto_analyzer.unavailable",
      message: `GTO analyzer module unavailable: ${(error as Error).message}`,
    });
    return null;
  }
}

const app = express();
app.use(cors({ origin: runtimeConfig.corsOrigin, credentials: true }));
const healthPayload = { ok: true, service: "cardpilot-game-server" };
app.get("/health", (_req, res) => res.json(healthPayload));
app.get("/healthz", (_req, res) => res.json(healthPayload));
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
// Reconnect info: userId -> { tableId, seat, roomCode } — cached on disconnect for auto-restore
const rejoinInfo = new Map<string, { tableId: string; seat: number; roomCode: string }>();
const tableSnapshotVersions = new Map<string, number>();

// Pending seat requests: orderId -> request data
type SeatRequest = { orderId: string; tableId: string; seat: number; buyIn: number; userId: string; userName: string; socketId: string; isRestore: boolean };
const pendingSeatRequests = new Map<string, SeatRequest>();
const autoDealSchedule = new Map<string, ReturnType<typeof setTimeout>>();
const tablesWithStartedHands = new Set<string>();
type RunCountPreference = 1 | 2 | 3;
type PendingRunCountDecisionState = {
  handId: string;
  eligiblePlayers: Array<{ seat: number; name: string }>;
  underdogSeat: number;
  preferencesBySeat: Record<number, RunCountPreference | null>;
  targetRunCount: RunCountPreference | null;
  equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
};
const pendingRunCountDecisions = new Map<string, PendingRunCountDecisionState>();
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
  totalCashOut: number;
  handsPlayed: number;
  lastStack: number;
  lastStackUpdatedAt: number;
};
const sessionStatsByRoomCode = new Map<string, Map<string, PlayerSessionEntry>>(); // roomCode -> userId -> entry
const clubLeaderboardRefreshTimers = new Map<string, ReturnType<typeof setTimeout>>();
const CLUB_AUTH_REQUIRED_MESSAGE = "401 Unauthorized: authentication required for club access";

// Rebuy requests: seated player asks for more chips; club tables auto-approve, non-club rooms use host approval.
type RebuyRequest = { orderId: string; tableId: string; seat: number; userId: string; userName: string; amount: number; approved: boolean; createdAt: number };
const pendingRebuys = new Map<string, RebuyRequest>(); // orderId → request
const REBUY_TTL_MS = 10 * 60 * 1000; // 10 minutes

/** Saved hole cards from the last completed hand, for post-hand reveal */
const lastHandHoleCards = new Map<string, Map<number, [string, string]>>();
/** Pending 7-2 bounty claim: tableId -> claim info */
const pendingBountyClaim = new Map<string, {
  handId: string;
  winnerSeat: number;
  cards: [string, string];
  dealtInSeats: number[];
  bountyPerPlayer: number;
  timeout: ReturnType<typeof setTimeout>;
}>();
const supabase = new SupabasePersistence();
if (!supabase.enabled()) {
  logWarn({
    event: "supabase.disabled",
    message: "Supabase persistence is DISABLED — hand history, room persistence, and player profiles will not be saved. Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY to enable.",
  });
}

// GTO audit service — runs async after each hand, never blocks gameplay
let auditService: AuditService | null = null;
function getAuditService(): AuditService {
  if (!auditService) {
    auditService = new AuditService({
      supabaseAdmin: supabase.getAdminClient(),
      io,
      maxConcurrentAudits: 4,
    });
  }
  return auditService;
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
  if (event !== "room_state_update") {
    io.to(tableId).emit(event, data);
    return;
  }

  const baseState = data as RoomFullState;
  const roomSockets = io.sockets.adapter.rooms.get(tableId);
  if (!roomSockets || roomSockets.size === 0) {
    io.to(tableId).emit("room_state_update", withClubRoomStateMetadata(baseState, tableId));
    return;
  }

  for (const sid of roomSockets) {
    const ident = socketIdentity.get(sid);
    io.to(sid).emit("room_state_update", withClubRoomStateMetadata(baseState, tableId, ident?.userId));
  }
});

// Club manager handles club lifecycle, membership, permissions, rulesets
type ClubDataRepo = ClubRepo | ClubRepoJson;
const primaryClubRepo = new ClubRepo();
const clubDataRepo: ClubDataRepo = primaryClubRepo.enabled() ? primaryClubRepo : new ClubRepoJson();
const clubManager = new ClubManager();
if (!primaryClubRepo.enabled()) {
  logInfo({ event: "club_persistence.fallback", message: "Using JSON file fallback for club persistence (dev mode)" });
}
clubManager.setRepo(clubDataRepo as unknown as ClubRepo);
void (async () => {
  await clubManager.hydrate();
  // Create runtime rooms for all open club tables (clubTable.id = room tableId).
  for (const { clubId, table } of clubManager.listOpenTables()) {
    ensureClubTableRoom(clubId, table.id);
  }
})().catch((e) => logWarn({
  event: "club_manager.hydrate_or_restore.failed",
  message: (e as Error).message,
}));

io.use(async (socket, next) => {
  const auth = (socket.handshake.auth ?? {}) as {
    accessToken?: string;
    displayName?: string;
    userId?: string; // Accept userId from client
  };

  const normalizedClientUserId = typeof auth.userId === "string" ? auth.userId.trim() : "";
  let verifiedUserId: string | null = null;

  try {
    const verifiedIdentity = await supabase.verifyAccessToken(auth.accessToken, auth.displayName);
    verifiedUserId = verifiedIdentity.userId;

    let resolvedIdentity = verifiedIdentity;
    // Only for unauthenticated identities, trust client guest id for stability.
    if (!verifiedIdentity.isAuthenticated && normalizedClientUserId) {
      resolvedIdentity = { ...verifiedIdentity, userId: normalizedClientUserId, isAuthenticated: false };
    }

    if (IDENTITY_DEBUG) {
      logInfo({
        event: "auth.identity.resolved",
        userId: resolvedIdentity.userId,
        message: JSON.stringify({
          handshakeUserId: normalizedClientUserId || null,
          verifiedUserId,
          resolvedUserId: resolvedIdentity.userId,
          isAuthenticated: resolvedIdentity.isAuthenticated,
          supabaseEnabled: supabase.enabled(),
        }),
      });
    }

    socketIdentity.set(socket.id, resolvedIdentity);
    next();
  } catch {
    // Verification unavailable/failed: fall back to client-provided guest id (if any).
    const fallbackUserId = normalizedClientUserId || `guest-${randomUUID().replace(/-/g, "").slice(0, 8)}`;
    const fallbackDisplayName = typeof auth.displayName === "string" && auth.displayName.trim()
      ? auth.displayName.trim().slice(0, 32)
      : "Guest";
    const resolvedIdentity: VerifiedIdentity = {
      userId: fallbackUserId,
      displayName: fallbackDisplayName,
      isAuthenticated: false,
    };

    if (IDENTITY_DEBUG) {
      logInfo({
        event: "auth.identity.resolved",
        userId: resolvedIdentity.userId,
        message: JSON.stringify({
          handshakeUserId: normalizedClientUserId || null,
          verifiedUserId,
          resolvedUserId: resolvedIdentity.userId,
          isAuthenticated: false,
          supabaseEnabled: supabase.enabled(),
        }),
      });
    }

    socketIdentity.set(socket.id, resolvedIdentity);
    next();
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
      runItTwiceEnabled: settings?.runItTwice ?? false,
      gameType: settings?.gameType ?? "texas",
      bombPotEnabled: settings?.bombPotEnabled ?? false,
      bombPotFrequency: settings?.bombPotFrequency ?? 0,
      doubleBoardMode: settings?.doubleBoardMode ?? "off",
      rakeEnabled: simulatedFeeEnabled,
      rakePercent: simulatedFeeEnabled ? (settings?.simulatedFeePercent ?? 0) : 0,
      rakeCap: simulatedFeeEnabled && simulatedFeeCap > 0 ? simulatedFeeCap : undefined,
      maxConsecutiveTimeouts: settings?.maxConsecutiveTimeouts ?? 3,
    });
    tables.set(room.tableId, table);
  }
  if (!tableSnapshotVersions.has(room.tableId)) {
    tableSnapshotVersions.set(room.tableId, 0);
  }
  return table;
}

function applyRoomVariantSettings(tableId: string, table: GameTable): void {
  const settings = roomManager.getRoom(tableId)?.settings;
  if (!settings) return;
  table.configureVariantSettings({
    runItTwiceEnabled: settings.runItTwice,
    gameType: settings.gameType,
    bombPotEnabled: settings.bombPotEnabled,
    bombPotTriggerMode: settings.bombPotTriggerMode,
    bombPotFrequency: settings.bombPotFrequency,
    bombPotProbability: settings.bombPotProbability,
    bombPotAnteMode: settings.bombPotAnteMode,
    bombPotAnteValue: settings.bombPotAnteValue,
    doubleBoardMode: settings.doubleBoardMode,
  });
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

function isSevenTwo(cards: string[]): boolean {
  if (!cards || cards.length < 2) return false;
  const r0 = cards[0][0], r1 = cards[1][0];
  return (r0 === "7" && r1 === "2") || (r0 === "2" && r1 === "7");
}

function applySevenTwoBounty(tableId: string, claim: {
  handId: string;
  winnerSeat: number;
  cards: [string, string];
  dealtInSeats: number[];
  bountyPerPlayer: number;
  timeout: ReturnType<typeof setTimeout>;
}): void {
  const table = tables.get(tableId);
  if (!table) return;

  clearTimeout(claim.timeout);
  pendingBountyClaim.delete(tableId);

  const state = table.getPublicState();
  const bountyBySeat: Record<number, number> = {};
  let totalBounty = 0;

  for (const payerSeat of claim.dealtInSeats) {
    const payer = state.players.find((p) => p.seat === payerSeat);
    const payerStack = payer?.stack ?? 0;
    const amount = Math.min(claim.bountyPerPlayer, payerStack);
    if (amount > 0) {
      table.addStack(payerSeat, -amount);
      totalBounty += amount;
      bountyBySeat[payerSeat] = -amount;
    }
  }

  if (totalBounty > 0) {
    table.addStack(claim.winnerSeat, totalBounty);
    bountyBySeat[claim.winnerSeat] = totalBounty;
  }

  const bountyInfo: SevenTwoBountyInfo = {
    bountyPerPlayer: claim.bountyPerPlayer,
    winnerSeat: claim.winnerSeat,
    winnerCards: claim.cards,
    payingSeats: claim.dealtInSeats,
    totalBounty,
    bountyBySeat,
  };

  // Broadcast bounty claimed and reveal the cards
  io.to(tableId).emit("seven_two_bounty_claimed", {
    tableId,
    handId: claim.handId,
    bounty: bountyInfo,
  });
  io.to(tableId).emit("post_hand_reveal", {
    tableId,
    seat: claim.winnerSeat,
    cards: claim.cards,
  });

  logInfo({
    event: "seven_two_bounty.claimed",
    tableId,
    handId: claim.handId,
    winnerSeat: claim.winnerSeat,
    totalBounty,
  });

  broadcastSnapshot(tableId);
}

function roomCodeForTable(tableId: string): string | null {
  return roomsByTableId.get(tableId)?.roomCode ?? null;
}

function getClubInfoForTableId(tableId: string): { clubId: string; clubTableId: string } | null {
  return clubManager.getClubForTableById(tableId);
}

function isPersistentClubTable(tableId: string): boolean {
  return getClubInfoForTableId(tableId) !== null;
}

function maybeCheckRoomEmpty(tableId: string, currentCount: number): void {
  if (isPersistentClubTable(tableId)) {
    // Club table runtimes are persistent: never auto-close on empty.
    roomManager.checkRoomEmpty(tableId, currentCount, () => {});
    return;
  }
  roomManager.checkRoomEmpty(tableId, currentCount, () => {
    handleRoomAutoClose(tableId);
  });
}

/**
 * If only bots remain at the table (no human players), remove all bots and clear botSeats.
 */
function checkBotsOnlyAndRemove(tableId: string): void {
  const table = tables.get(tableId);
  if (!table) return;

  const state = table.getPublicState();
  if (state.players.length === 0) return;

  const botUserIds = getBotUserIds(tableId);
  if (botUserIds.size === 0) return;

  const hasHuman = state.players.some((p) => !botUserIds.has(p.userId));
  if (hasHuman) return;

  logInfo({
    event: "bot.no_humans_remaining",
    message: `No human players remain at table=${tableId}, removing all bots`,
  });

  // Clear bot seats from settings
  const managed = roomManager.getRoom(tableId);
  if (managed) {
    managed.settings.botSeats = [];
  }

  // Remove all bot processes
  removeAllBots(tableId);

  // Stand up all bot players from the table
  for (const player of [...state.players]) {
    if (botUserIds.has(player.userId)) {
      table.removePlayer(player.seat);
      for (const [sid, binding] of socketSeat.entries()) {
        if (binding.tableId === tableId && binding.seat === player.seat) {
          socketSeat.delete(sid);
          break;
        }
      }
    }
  }

  broadcastSnapshot(tableId);
  maybeCheckRoomEmpty(tableId, currentPlayerCount(tableId));
}

function isClubOwnerOrAdmin(clubId: string, userId: string): boolean {
  const role = clubManager.getMemberRole(clubId, userId);
  return role === "owner" || role === "admin";
}

function isClubAuthenticatedIdentity(identity: VerifiedIdentity): boolean {
  // Runtime config can intentionally disable Supabase (e.g. partial env fallback),
  // so club auth must honor guest/local mode in every environment.
  if (!supabase.enabled()) {
    return true;
  }
  return identity.isAuthenticated && !identity.userId.startsWith("guest-");
}

function emitClubUnauthorized(socket: Socket, reason?: string): void {
  const msg = reason ? `${CLUB_AUTH_REQUIRED_MESSAGE}: ${reason}` : CLUB_AUTH_REQUIRED_MESSAGE;
  socket.emit("club_error", { code: "UNAUTHORIZED", message: msg });
  socket.emit("error_event", { message: msg });
}

function socketIdsForUser(userId: string): string[] {
  const ids: string[] = [];
  for (const [socketId, ident] of socketIdentity.entries()) {
    if (ident.userId === userId) ids.push(socketId);
  }
  return ids;
}

/** Ensure a runtime room exists for this club table. Uses clubTable.id as the room's tableId (1:1 mapping). */
function ensureClubTableRoom(clubId: string, clubTableId: string): string | null {
  // Already has a runtime room?
  if (roomsByTableId.has(clubTableId)) return clubTableId;

  const tableMeta = clubManager.getClubTable(clubId, clubTableId);
  if (!tableMeta || tableMeta.status === "closed" || tableMeta.status === "finished") return null;

  const rules = clubManager.getRulesForTable(clubId, clubTableId);
  if (!rules) return null;

  const club = clubManager.getClub(clubId);
  const room: RoomInfo = {
    tableId: clubTableId,
    roomCode: clubTableId, // Club tables use their own ID as roomCode (never exposed to users)
    roomName: `${club?.name ?? "Club"} — ${tableMeta.name}`,
    maxPlayers: rules.maxSeats,
    smallBlind: rules.stakes.smallBlind,
    bigBlind: rules.stakes.bigBlind,
    status: "OPEN",
    isPublic: false,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    createdBy: tableMeta.createdBy,
  };

  registerRoom(room);
  createTableIfNeeded(room);
  roomManager.createRoom({
    tableId: clubTableId,
    roomCode: clubTableId,
    roomName: room.roomName,
    ownerId: tableMeta.createdBy,
    ownerName: "Club Host",
    settings: {
      maxPlayers: rules.maxSeats,
      smallBlind: rules.stakes.smallBlind,
      bigBlind: rules.stakes.bigBlind,
      buyInMin: rules.buyIn.minBuyIn,
      buyInMax: rules.buyIn.maxBuyIn,
      actionTimerSeconds: rules.time.actionTimeSec,
      timeBankSeconds: rules.time.timeBankSec,
      disconnectGracePeriod: rules.time.disconnectGraceSec,
      autoStartNextHand: rules.dealing.autoStartNextHand && rules.dealing.autoDealEnabled,
      minPlayersToStart: Math.max(2, Math.min(rules.maxSeats, rules.dealing.minPlayersToStart ?? 2)),
      spectatorAllowed: rules.moderation.allowSpectators,
      runItTwice: rules.runit.allowRunItTwice,
      runItTwiceMode: rules.runit.allowRunItTwice ? "ask_players" : "off",
      straddleAllowed: rules.extras.straddleAllowed,
      bombPotEnabled: rules.extras.bombPotEnabled,
      rabbitHunting: rules.extras.rabbitHuntEnabled,
      visibility: "private",
    },
  });

  supabase.upsertRoom(room).catch((e) => logWarn({
    event: "club_table.create_room.persist_failed",
    tableId: clubTableId,
    message: (e as Error).message,
  }));
  return clubTableId;
}

async function buildClubDetailPayload(clubId: string, viewerUserId: string) {
  const detail = clubManager.getClubDetail(clubId, viewerUserId);
  if (!detail) return null;

  // Ensure runtime rooms exist for all open tables.
  for (const t of detail.tables) {
    if (t.status !== "closed" && t.status !== "finished") {
      ensureClubTableRoom(clubId, t.id);
    }
  }

  const memberIds = [...new Set(detail.members.map((m) => m.userId).concat(viewerUserId))];
  const walletBalances = await clubDataRepo.getWalletBalances(clubId, memberIds, "chips");
  detail.members = detail.members.map((m) => {
    const balance = walletBalances.get(m.userId) ?? 0;
    clubManager.setMemberBalance(clubId, m.userId, balance);
    return { ...m, balance };
  });
  if (detail.detail.myMembership) {
    detail.detail.myMembership.balance = walletBalances.get(detail.detail.myMembership.userId) ?? 0;
  }

  // Enrich tables with live room state (clubTable.id = room tableId)
  detail.tables = detail.tables.map((t) => {
    const enriched = { ...t };
    const tbl = tables.get(t.id);
    const managed = roomManager.getRoom(t.id);
    const cfg = t.config ?? ({} as any);
    if (tbl) {
      const state = tbl.getPublicState();
      enriched.playerCount = state.players.length;
      enriched.maxPlayers = managed?.settings.maxPlayers ?? cfg.maxSeats ?? 6;
      enriched.stakes = `${state.smallBlind}/${state.bigBlind}`;
      enriched.minPlayersToStart = managed?.settings.minPlayersToStart ?? cfg.minPlayersToStart ?? 2;
    } else {
      enriched.playerCount = 0;
      enriched.minPlayersToStart = managed?.settings.minPlayersToStart ?? cfg.minPlayersToStart ?? 2;
    }
    return enriched;
  });

  return detail;
}

async function emitClubDetail(socketId: string, clubId: string, viewerUserId: string): Promise<void> {
  const detail = await buildClubDetailPayload(clubId, viewerUserId);
  if (detail) {
    io.to(socketId).emit("club_detail", detail);
  }
}

function withClubRoomStateMetadata(state: RoomFullState, tableId: string, viewerUserId?: string): RoomFullState {
  const clubInfo = getClubInfoForTableId(tableId);
  const hasStartedHand = tablesWithStartedHands.has(tableId);
  if (!clubInfo) {
    return {
      ...state,
      hasStartedHand,
      isClubTable: false,
      clubId: undefined,
      clubRole: null,
    };
  }
  return {
    ...state,
    hasStartedHand,
    isClubTable: true,
    clubId: clubInfo.clubId,
    clubRole: viewerUserId ? clubManager.getMemberRole(clubInfo.clubId, viewerUserId) : null,
  };
}

async function emitDefaultLeaderboardToConnectedClubMembers(clubId: string): Promise<void> {
  const defaultRange: ClubLeaderboardRange = "week";
  const entries = await clubDataRepo.getClubLeaderboard(clubId, defaultRange, "net", 50);
  const rankByUser = new Map(entries.map((entry) => [entry.userId, entry.rank]));
  for (const [sid, ident] of socketIdentity.entries()) {
    if (!clubManager.isActiveMember(clubId, ident.userId)) continue;
    io.to(sid).emit("club_leaderboard", {
      clubId,
      timeRange: defaultRange,
      metric: "net",
      entries,
      myRank: rankByUser.get(ident.userId) ?? null,
    });
  }
}

function scheduleClubLeaderboardRefresh(clubId: string): void {
  if (clubLeaderboardRefreshTimers.has(clubId)) return;
  const handle = setTimeout(() => {
    clubLeaderboardRefreshTimers.delete(clubId);
    emitDefaultLeaderboardToConnectedClubMembers(clubId).catch((e) => logWarn({
      event: "club_leaderboard.refresh.failed",
      clubId,
      message: (e as Error).message,
    }));
  }, 100);
  clubLeaderboardRefreshTimers.set(clubId, handle);
}

async function emitWalletBalanceToUser(
  clubId: string,
  userId: string,
  balance: number,
  currency = "chips",
): Promise<void> {
  const payload = { balance: { clubId, userId, currency, balance } };
  for (const sid of socketIdsForUser(userId)) {
    io.to(sid).emit("club_wallet_balance", payload);
    io.to(sid).emit("club_credits_updated", { clubId, userId, newBalance: balance });
  }
  scheduleClubLeaderboardRefresh(clubId);
}

async function appendWalletTx(input: AppendWalletTxInput) {
  try {
    const result = await clubDataRepo.appendWalletTx(input);
    if (!result) {
      throw new Error("Wallet transaction returned null");
    }
    clubManager.setMemberBalance(input.clubId, input.userId, result.newBalance);
    return result;
  } catch (err) {
    const msg = (err as Error).message;
    logWarn({ event: "server.appendWalletTx.failed", message: msg, clubId: input.clubId, userId: input.userId });
    throw new Error(`Wallet transaction failed: ${msg}`);
  }
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
      totalCashOut: 0,
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
    totalCashOut: 0,
    handsPlayed: 0,
    lastStack: stack,
    lastStackUpdatedAt: updatedAt,
  });
}

function recordSessionCashOut(tableId: string, userId: string, amount: number): void {
  const roomStats = getRoomSessionStats(tableId, true);
  if (!roomStats) return;
  const existing = roomStats.get(userId);
  if (existing) {
    existing.totalCashOut += amount;
  }
}

function broadcastSessionStats(tableId: string): void {
  const table = tables.get(tableId);
  const currentPlayers = table ? table.getPublicState().players : [];
  const roomStats = getRoomSessionStats(tableId, false);
  const entries: Array<{ seat: number | null; userId: string; name: string; totalBuyIn: number; totalCashOut: number; currentStack: number; net: number; handsPlayed: number; status: string }> = [];

  if (roomStats) {
    for (const [uid, entry] of roomStats.entries()) {
      const seated = currentPlayers.find((p) => p.userId === uid);
      const currentStack = seated ? seated.stack : 0;
      entries.push({
        seat: seated?.seat ?? null,
        userId: entry.userId,
        name: entry.name,
        totalBuyIn: entry.totalBuyIn,
        totalCashOut: entry.totalCashOut,
        currentStack,
        net: currentStack + entry.totalCashOut - entry.totalBuyIn,
        handsPlayed: entry.handsPlayed,
        status: seated ? "seated" : "away",
      });
    }
  }

  io.to(tableId).emit("session_stats", { tableId, entries });
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

async function applyApprovedRebuys(tableId: string): Promise<void> {
  const table = tables.get(tableId);
  if (!table) return;
  const room = roomManager.getRoom(tableId);
  if (!room) return;
  const clubInfo = getClubInfoForTableId(tableId);
  const toRemove: string[] = [];
  const stateBefore = table.getPublicState();
  const stackBySeatBefore = new Map<number, number>(stateBefore.players.map((player) => [player.seat, player.stack]));
  for (const [orderId, deposit] of pendingRebuys.entries()) {
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

      if (clubInfo) {
        if (!clubManager.isActiveMember(clubInfo.clubId, deposit.userId)) {
          const seatSocket = socketIdBySeat(tableId, deposit.seat);
          if (seatSocket) {
            io.to(seatSocket).emit("system_message", { message: "Rebuy skipped: club membership is no longer active." });
          }
          toRemove.push(orderId);
          continue;
        }
        const walletBalance = await clubDataRepo.getWalletBalance(clubInfo.clubId, deposit.userId, "chips");
        if (walletBalance < deposit.amount) {
          const seatSocket = socketIdBySeat(tableId, deposit.seat);
          if (seatSocket) {
            io.to(seatSocket).emit("system_message", { message: "Rebuy skipped: Club has insufficient funds." });
          }
          io.to(tableId).emit("system_message", { message: `Rebuy for ${deposit.userName} skipped: Club has insufficient funds.` });
          toRemove.push(orderId);
          continue;
        }
        try {
          const tx = await appendWalletTx({
            clubId: clubInfo.clubId,
            userId: deposit.userId,
            type: "buy_in",
            amount: -Math.trunc(deposit.amount),
            currency: "chips",
            refType: "table_rebuy",
            refId: `${tableId}:${deposit.seat}:${orderId}`,
            createdBy: deposit.userId,
            note: `Rebuy for seat ${deposit.seat} at ${room.roomName}`,
            metaJson: { tableId, seat: deposit.seat, orderId },
          });
          await emitWalletBalanceToUser(clubInfo.clubId, deposit.userId, tx.newBalance, "chips");
        } catch (error) {
          const errMsg = (error as Error).message;
          logWarn({ event: "applyApprovedRebuys.wallet_failed", message: errMsg, clubId: clubInfo.clubId, userId: deposit.userId, amount: deposit.amount, orderId });
          const seatSocket = socketIdBySeat(tableId, deposit.seat);
          if (seatSocket) {
            io.to(seatSocket).emit("system_message", { message: `Rebuy failed: unable to reserve club funds. ${errMsg}` });
          }
          toRemove.push(orderId);
          continue;
        }
      }

      try {
        table.addStack(deposit.seat, deposit.amount);
      } catch (addStackErr) {
        console.warn("applyApprovedRebuys: addStack failed after wallet debit, issuing refund:", (addStackErr as Error).message);
        if (clubInfo) {
          try {
            const refundTx = await appendWalletTx({
              clubId: clubInfo.clubId,
              userId: deposit.userId,
              type: "adjustment",
              amount: Math.trunc(deposit.amount),
              currency: "chips",
              refType: "rebuy_refund",
              refId: `${tableId}:${deposit.seat}:${orderId}:refund`,
              createdBy: deposit.userId,
              note: `Refund: rebuy addStack failed for seat ${deposit.seat}`,
              metaJson: { tableId, seat: deposit.seat, orderId, reason: "addStack_failed" },
            });
            await emitWalletBalanceToUser(clubInfo.clubId, deposit.userId, refundTx.newBalance, "chips");
            const seatSocket = socketIdBySeat(tableId, deposit.seat);
            if (seatSocket) {
              io.to(seatSocket).emit("system_message", { message: "Rebuy failed to apply. Your wallet has been refunded." });
            }
          } catch (refundErr) {
            logWarn({ event: "applyApprovedRebuys.refund_failed", message: (refundErr as Error).message, clubId: clubInfo.clubId, userId: deposit.userId, amount: deposit.amount, orderId });
          }
        }
        toRemove.push(orderId);
        continue;
      }

      recordSessionBuyIn(tableId, deposit.userId, deposit.userName, deposit.amount);
      setSessionLastStack(tableId, deposit.userId, deposit.userName, currentStack + deposit.amount);
      const sid = socketIdBySeat(tableId, deposit.seat);
      if (sid) io.to(sid).emit("system_message", { message: `Rebuy of ${deposit.amount} credited for this hand.` });
      io.to(tableId).emit("system_message", { message: `${deposit.userName} (Seat ${deposit.seat}) rebuy credited: ${deposit.amount}` });
      broadcastSessionStats(tableId);
      stackBySeatBefore.set(deposit.seat, currentStack + deposit.amount);
    } catch (err) {
      console.warn("applyApprovedRebuys: unexpected error:", (err as Error).message);
    }
    toRemove.push(orderId);
  }
  for (const id of toRemove) pendingRebuys.delete(id);
}

function getPendingRebuysForTable(tableId: string): Array<{ orderId: string; seat: number; userId: string; userName: string; amount: number }> {
  const result: Array<{ orderId: string; seat: number; userId: string; userName: string; amount: number }> = [];
  for (const [, deposit] of pendingRebuys.entries()) {
    if (deposit.tableId === tableId && !deposit.approved) {
      result.push({ orderId: deposit.orderId, seat: deposit.seat, userId: deposit.userId, userName: deposit.userName, amount: deposit.amount });
    }
  }
  return result;
}

function cleanupStaleRebuys(): void {
  const now = Date.now();
  for (const [orderId, deposit] of pendingRebuys.entries()) {
    if (now - deposit.createdAt > REBUY_TTL_MS) {
      logInfo({ event: "rebuy.stale_cleanup", orderId, tableId: deposit.tableId, userId: deposit.userId, ageSeconds: Math.round((now - deposit.createdAt) / 1000) });
      const seatSocket = socketIdBySeat(deposit.tableId, deposit.seat);
      if (seatSocket) {
        io.to(seatSocket).emit("system_message", { message: "Your pending rebuy request has expired." });
      }
      pendingRebuys.delete(orderId);
    }
  }
}
setInterval(cleanupStaleRebuys, 2 * 60 * 1000);

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

// ── Stale-advice guard: per-seat request counter ──
const adviceRequestCounter = new Map<string, number>(); // key: `${tableId}:${seat}`

type AdviceReason = "actor_changed" | "street_changed" | "action_applied" | "manual_request";

async function emitAdviceIfNeeded(
  tableId: string,
  state: TableState,
  reason: AdviceReason
): Promise<void> {
  if (!state.handId || state.actorSeat == null) return;

  const table = tables.get(tableId);
  if (!table) return;

  // Only push advice in COACH mode immediately; REVIEW mode waits until hand end
  if (table.getMode() === "REVIEW") return;

  // Advice engine is currently NLH-oriented. Skip variant hands for compatibility.
  if ((state.gameType ?? "texas") !== "texas") return;

  const seat = state.actorSeat;

  // Skip if actor is folded or all-in (no decisions to make)
  const actorPlayer = state.players.find((p) => p.seat === seat);
  if (actorPlayer && (actorPlayer.folded || actorPlayer.allIn)) return;

  const binding = bindingsByTable(tableId).find((entry) => entry.binding.seat === seat)?.binding;
  if (!binding) return;

  // Increment and capture requestId for stale-guard
  const counterKey = `${tableId}:${seat}`;
  const requestId = (adviceRequestCounter.get(counterKey) ?? 0) + 1;
  adviceRequestCounter.set(counterKey, requestId);

  const heroPos = table.getPosition(seat);
  const heroHand = table.getHeroHandCode(seat);

  logInfo({
    event: "advice.requested",
    tableId,
    handId: state.handId,
    seat,
    street: state.street,
    boardLength: state.board.length,
    reason,
    requestId,
  });

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
  else if (state.street === "FLOP" || state.street === "TURN" || state.street === "RIVER") {
    const heroHandCards = table.getPrivateHoleCards(seat) ?? table.getHoleCards(seat);
    if (!heroHandCards) {
      logWarn({ event: "advice.skip.no_hole_cards", tableId, seat, street: state.street });
      return;
    }

    const context = buildPostflopContext(tableId, state, seat, heroPos, heroHandCards);
    if (!context) {
      logWarn({ event: "advice.skip.no_context", tableId, seat, street: state.street });
      return;
    }

    logInfo({
      event: "advice.postflop_context",
      tableId,
      handId: state.handId,
      seat,
      street: state.street,
      boardLength: context.board.length,
      pot: context.potSize,
      toCall: context.toCall,
      effectiveStack: context.effectiveStack,
      aggressor: context.aggressor,
    });

    try {
      advice = await getPostflopAdvice(context);
    } catch (error) {
      logWarn({
        event: "advice.postflop_error",
        tableId,
        seat,
        street: state.street,
        boardLength: context.board.length,
        message: (error as Error).message,
      });
      return;
    }
  } else {
    return; // Showdown or invalid street
  }

  // Stale-guard: only emit if this is still the latest request for this seat
  const currentRequestId = adviceRequestCounter.get(counterKey) ?? 0;
  if (requestId !== currentRequestId) {
    logInfo({
      event: "advice.stale_skipped",
      tableId,
      seat,
      street: state.street,
      requestId,
      currentRequestId,
    });
    return;
  }

  // Store for deviation calc
  lastAdvice.set(`${tableId}:${seat}`, advice);

  logInfo({
    event: "advice.emitted",
    tableId,
    handId: state.handId,
    seat,
    street: state.street,
    stage: advice.stage,
    recommended: advice.recommended,
    requestId,
  });

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
  const clubInfo = clubManager.getClubForTableById(room.tableId);
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

function ensureSnapshotVersion(tableId: string): number {
  const current = tableSnapshotVersions.get(tableId) ?? 0;
  if (!tableSnapshotVersions.has(tableId)) {
    tableSnapshotVersions.set(tableId, current);
  }
  return current;
}

function nextSnapshotVersion(tableId: string): number {
  const next = ensureSnapshotVersion(tableId) + 1;
  tableSnapshotVersions.set(tableId, next);
  return next;
}

function withSnapshotVersion(snapshot: TableState, stateVersion: number): TableState {
  if (snapshot.stateVersion === stateVersion) {
    return snapshot;
  }
  return { ...snapshot, stateVersion };
}

function buildSnapshotForSync(tableId: string, source: "hydrate" | "broadcast"): TableState | null {
  const table = tables.get(tableId);
  if (!table) return null;

  let snapshot = table.getPublicState();

  // Stamp isBot flag on bot players
  const botIds = getBotUserIds(tableId);
  if (botIds.size > 0) {
    snapshot.players = snapshot.players.map((p) =>
      botIds.has(p.userId) ? { ...p, isBot: true } : p
    );
  }

  // Attach deferred stand-up seats and pending pause for client UI
  const deferredSeats = pendingStandUps.get(tableId);
  if (deferredSeats && deferredSeats.size > 0) {
    snapshot.pendingStandUp = [...deferredSeats];
  }
  if (pendingPause.has(tableId)) {
    snapshot.pendingPause = true;
  }
  const deposits = getPendingRebuysForTable(tableId);
  if (deposits.length > 0) {
    snapshot.pendingRebuys = deposits;
  }

  const stateVersion = source === "broadcast"
    ? nextSnapshotVersion(tableId)
    : ensureSnapshotVersion(tableId);
  snapshot = withSnapshotVersion(snapshot, stateVersion);

  if (runtimeConfig.envName !== "production") {
    logInfo({
      event: "snapshot.sync",
      tableId,
      handId: snapshot.handId ?? undefined,
      street: snapshot.street,
      stateVersion: snapshot.stateVersion,
      source,
    });
  }

  return snapshot;
}

function emitHydratedSnapshot(socketId: string, tableId: string): void {
  const snapshot = buildSnapshotForSync(tableId, "hydrate");
  if (!snapshot) return;
  io.to(socketId).emit("table_snapshot", snapshot);
  const pendingDecision = pendingRunCountDecisions.get(tableId);
  if (pendingDecision && pendingDecision.handId === snapshot.handId) {
    emitAllInLocked(tableId, pendingDecision, socketId);
  }
}

function broadcastSnapshot(tableId: string) {
  const snapshot = buildSnapshotForSync(tableId, "broadcast");
  if (!snapshot) return;
  io.to(tableId).emit("table_snapshot", snapshot);
  emitPresence(tableId);
  // Defer advice computation so it never blocks snapshot delivery or timer updates
  setImmediate(() => {
    void emitAdviceIfNeeded(tableId, snapshot, "actor_changed").catch((err: unknown) => {
      console.warn("[advice] deferred push error:", (err as Error).message);
    });
  });
}

function calculateAllPlayersEquity(table: GameTable, board: Card[]): Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }> {
  const state = table.getPublicState();
  const activeSeats = state.players
    .filter((p) => p.inHand && !p.folded)
    .map((p) => p.seat);

  if ((state.gameType ?? "texas") !== "texas") {
    const fallbackEquityRate = activeSeats.length > 0 ? 1 / activeSeats.length : 0;
    return activeSeats.map((seat) => ({
      seat,
      winRate: Math.round(fallbackEquityRate * 1000) / 1000,
      tieRate: 0,
      equityRate: Math.round(fallbackEquityRate * 1000) / 1000,
    }));
  }

  const equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }> = [];

  for (const seat of activeSeats) {
    const heroCards = table.getHoleCards(seat);
    const opponentSeats = activeSeats.filter((s) => s !== seat);

    if (!heroCards || opponentSeats.length === 0) {
      equities.push({ seat, winRate: 0.5, tieRate: 0, equityRate: 0.5 });
      continue;
    }

    const villainHands = opponentSeats
      .map((s) => table.getPrivateHoleCards(s) ?? table.getHoleCards(s))
      .filter((cards): cards is [string, string] => Array.isArray(cards) && cards.length === 2)
      .map((cards) => [cards[0], cards[1]] as [Card, Card]);

    if (villainHands.length === 0) {
      equities.push({ seat, winRate: 1.0, tieRate: 0, equityRate: 1.0 });
      continue;
    }

    const equity = calculateEquity({
      heroHand: [heroCards[0], heroCards[1]] as [Card, Card],
      villainHands,
      board,
      simulations: 5000,
    });

    equities.push({
      seat,
      winRate: Math.round(equity.win * 1000) / 1000,
      tieRate: Math.round(equity.tie * 1000) / 1000,
      equityRate: Math.round(equity.equity * 1000) / 1000,
    });
  }

  return equities;
}

function calculateAllInHandHints(table: GameTable, board: Card[]): Array<{ seat: number; label: string }> {
  const state = table.getPublicState();
  return state.players
    .filter((player) => player.inHand && !player.folded)
    .map((player) => {
      const cards = table.getPrivateHoleCards(player.seat) ?? table.getHoleCards(player.seat);
      const label = cards && cards.length >= 2
        ? describeHandStrength(cards, board)
        : "Unknown hand";
      return { seat: player.seat, label };
    });
}

function clearRunCountDecisionTimeout(tableId: string): void {
  const timeout = pendingRunCountTimeouts.get(tableId);
  if (timeout) {
    clearTimeout(timeout);
    pendingRunCountTimeouts.delete(tableId);
  }
}

function clearPendingRunCountDecision(tableId: string): void {
  clearRunCountDecisionTimeout(tableId);
  pendingRunCountDecisions.delete(tableId);
}

function buildAllInLockedPayload(pending: PendingRunCountDecisionState): {
  handId: string;
  eligiblePlayers: Array<{ seat: number; name: string }>;
  maxRunCountAllowed: 3;
  submittedPlayerIds: number[];
  underdogSeat: number;
  targetRunCount: RunCountPreference | null;
  equities: Array<{ seat: number; winRate: number; tieRate: number; equityRate: number }>;
} {
  const submittedPlayerIds = pending.eligiblePlayers
    .map((player) => player.seat)
    .filter((seat) => pending.preferencesBySeat[seat] != null);

  return {
    handId: pending.handId,
    eligiblePlayers: pending.eligiblePlayers.map((player) => ({ ...player })),
    maxRunCountAllowed: 3,
    submittedPlayerIds,
    underdogSeat: pending.underdogSeat,
    targetRunCount: pending.targetRunCount,
    equities: pending.equities,
  };
}

function emitAllInLocked(tableId: string, pending: PendingRunCountDecisionState, socketId?: string): void {
  const payload = buildAllInLockedPayload(pending);
  if (socketId) {
    io.to(socketId).emit("allin_locked", payload);
    return;
  }
  io.to(tableId).emit("allin_locked", payload);
}

function resolveRunCountPreference(pending: PendingRunCountDecisionState): RunCountPreference {
  const target = pending.targetRunCount;
  if (target == null || target <= 1) return 1;

  for (const player of pending.eligiblePlayers) {
    if (player.seat === pending.underdogSeat) continue;
    if (pending.preferencesBySeat[player.seat] !== target) {
      return 1;
    }
  }

  return target;
}

function revealLockedHoleCards(
  tableId: string,
  table: GameTable,
  pending: PendingRunCountDecisionState
): Record<number, [string, string]> {
  for (const player of pending.eligiblePlayers) {
    table.revealPublicHand(player.seat);
  }

  const state = table.getPublicState();
  const revealedFromState = state.revealedHoles ?? {};
  const revealed: Record<number, [string, string]> = {};
  for (const player of pending.eligiblePlayers) {
    const cards = revealedFromState[player.seat] as [string, string] | undefined;
    if (cards && cards.length === 2) {
      revealed[player.seat] = [cards[0], cards[1]];
    }
  }

  io.to(tableId).emit("reveal_hole_cards", { handId: pending.handId, revealed });
  return revealed;
}

function finalizeRunCountDecision(
  tableId: string,
  table: GameTable,
  pending: PendingRunCountDecisionState,
  decidingSeat?: number,
  auto = false,
  forcedRunCount?: RunCountPreference,
): void {
  const liveState = table.getPublicState();
  if (!liveState.handId || liveState.handId !== pending.handId) {
    clearPendingRunCountDecision(tableId);
    return;
  }

  const runCount = forcedRunCount ?? resolveRunCountPreference(pending);
  table.setAllInRunCount(runCount);
  clearPendingRunCountDecision(tableId);

  logInfo({
    event: "all_in.run_count.finalized",
    tableId,
    handId: pending.handId,
    runCount,
    decidingSeat,
    auto,
    underdogSeat: pending.underdogSeat,
    targetRunCount: pending.targetRunCount,
    preferencesBySeat: pending.preferencesBySeat,
  });

  io.to(tableId).emit("run_count_confirmed", { handId: pending.handId, runCount });
  io.to(tableId).emit("run_count_chosen", {
    runCount,
    seat: decidingSeat ?? pending.eligiblePlayers[0]?.seat ?? 1,
    auto,
  });

  revealLockedHoleCards(tableId, table, pending);
  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);
  void handleSequentialRunout(tableId, table);
}

function scheduleRunCountDecisionTimeout(tableId: string, table: GameTable, pending: PendingRunCountDecisionState): void {
  clearRunCountDecisionTimeout(tableId);

  const expectedHandId = pending.handId;
  const timeout = setTimeout(() => {
    pendingRunCountTimeouts.delete(tableId);

    const livePending = pendingRunCountDecisions.get(tableId);
    if (!livePending || livePending.handId !== expectedHandId) return;

    logInfo({
      event: "all_in.run_count.timeout_default",
      tableId,
      handId: expectedHandId,
      message: "Run-count decision timed out; defaulting unresolved seats to run once.",
    });

    finalizeRunCountDecision(tableId, table, livePending, undefined, true, 1);
  }, runtimeConfig.runCountDecisionTimeoutMs);

  pendingRunCountTimeouts.set(tableId, timeout);
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
  if (everyoneAllIn) {
    return room.settings.autoRevealOnAllInCall ?? true;
  }
  return isRiverCallShowdown(state);
}

function beginShowdownDecision(tableId: string, table: GameTable, state: TableState): void {
  if (state.showdownPhase !== "decision" || !state.handId) {
    finalizeHandEnd(tableId, state);
    return;
  }

  // Auto-reveal bot hands for transparency (bots always show their cards)
  const showdownBotIds = getBotUserIds(tableId);
  if (showdownBotIds.size > 0) {
    const contenderSeats = table.getShowdownContenderSeats();
    for (const seat of contenderSeats) {
      const p = state.players.find((pl) => pl.seat === seat);
      if (p && showdownBotIds.has(p.userId)) {
        table.revealPublicHand(seat);
      }
    }
    state = table.getPublicState();
    if (state.showdownPhase !== "decision") {
      finalizeHandEnd(tableId, state);
      return;
    }
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

function emitShowdownResults(
  tableId: string,
  state: TableState,
  settlement: ReturnType<GameTable["getSettlementResult"]> | null
): void {
  if (!state.handId) return;

  const runCount: 1 | 2 | 3 = settlement?.runCount
    ?? (state.runoutPayouts?.length === 3 ? 3 : state.runoutPayouts?.length === 2 ? 2 : 1);
  const perRunWinners = settlement?.winnersByRun
    ?? (state.runoutPayouts
      ? state.runoutPayouts.map((run) => ({ run: run.run, board: [...run.board], winners: [...run.winners] }))
      : [{ run: 1 as const, board: [...state.board], winners: [...(state.winners ?? [])] }]);

  const totalPayouts: Record<number, number> = settlement?.payoutsBySeat
    ? { ...settlement.payoutsBySeat }
    : (state.winners ?? []).reduce<Record<number, number>>((acc, winner) => {
      acc[winner.seat] = (acc[winner.seat] ?? 0) + winner.amount;
      return acc;
    }, {});

  io.to(tableId).emit("showdown_results", {
    handId: state.handId,
    runCount,
    perRunWinners,
    totalPayouts,
  });
}

async function handleSequentialRunout(tableId: string, table: GameTable): Promise<void> {
  try {
    const room = roomManager.getRoom(tableId);
    const isTurbo = room?.settings.showdownSpeed === "turbo" || room?.settings.selfPlayTurbo === true;

    const runCount = table.getAllInRunCount();
    if (runCount > 1) {
      const boardBefore = [...table.getPublicState().board];
      table.performRunout();
      const finalState = table.getPublicState();
      const settlement = table.getSettlementResult();
      const boards = finalState.runoutBoards ?? [];

      if (boards.length === runCount) {
        const alreadyDealt = Math.min(5, boardBefore.length);
        const CARD_STAGGER_MS = isTurbo ? 0 : 320;
        const STREET_PAUSE_MS = isTurbo ? 0 : 1_500;

        for (let runIndex = 0; runIndex < runCount; runIndex += 1) {
          for (let cardIndex = alreadyDealt; cardIndex < 5; cardIndex += 1) {
            const card = boards[runIndex][cardIndex];
            if (!card) continue;
            const street = (cardIndex <= 2 ? "FLOP" : cardIndex === 3 ? "TURN" : "RIVER") as TableState["street"];
            const board = boards[runIndex].slice(0, cardIndex + 1);
            const equities = calculateAllPlayersEquity(table, [...board] as Card[]);
            const hints = (street === "FLOP" || street === "TURN")
              ? calculateAllInHandHints(table, [...board] as Card[])
              : undefined;

            io.to(tableId).emit("reveal_board_card", {
              handId: finalState.handId,
              runIndex: (runIndex + 1) as 1 | 2 | 3,
              card,
              boardSizeNow: cardIndex + 1,
              board,
              street,
              equities,
              hints,
            });

            // Backward-compatible mirror for old clients that still use run_twice_reveal.
            if (runCount === 2) {
              io.to(tableId).emit("run_twice_reveal", {
                handId: finalState.handId,
                street,
                phase: runIndex === 0 ? "top" : "both",
                run1: {
                  newCards: runIndex === 0 ? [card] : [],
                  board: runIndex === 0 ? board : boards[0],
                },
                run2: {
                  newCards: runIndex === 1 ? [card] : [],
                  board: runIndex === 1 ? board : boards[1].slice(0, alreadyDealt),
                },
                equities,
                hints,
              });
            }

            await new Promise((resolve) => setTimeout(resolve, CARD_STAGGER_MS));
            if (cardIndex === 2 || cardIndex === 3) {
              await new Promise((resolve) => setTimeout(resolve, STREET_PAUSE_MS));
            }
          }

          if (runIndex < runCount - 1 && !isTurbo) {
            await new Promise((resolve) => setTimeout(resolve, 900));
          }
        }

        if (!isTurbo) await new Promise((resolve) => setTimeout(resolve, 1_000));
      }

      emitShowdownResults(tableId, finalState, settlement);
      beginShowdownDecision(tableId, table, finalState);
      return;
    }

    const delays: Record<string, number> = isTurbo
      ? { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0, SHOWDOWN: 0 }
      : { PREFLOP: 0, FLOP: 1500, TURN: 2000, RIVER: 2000, SHOWDOWN: 1500 };

    const revealNextStreetWithDelay = async (): Promise<void> => {
      const result = table.revealNextStreet();
      if (!result) return;

      const { street, newCards } = result;
      const state = table.getPublicState();

      if (street === "SHOWDOWN") {
        emitShowdownResults(tableId, state, table.getSettlementResult());
        beginShowdownDecision(tableId, table, state);
        return;
      }

      const equities = calculateAllPlayersEquity(table, [...state.board] as Card[]);
      const hints = (street === "FLOP" || street === "TURN")
        ? calculateAllInHandHints(table, [...state.board] as Card[])
        : undefined;

      io.to(tableId).emit("board_reveal", {
        handId: state.handId,
        street,
        newCards,
        board: state.board,
        equities,
        hints,
      });
      const boardStart = state.board.length - newCards.length;
      for (let i = 0; i < newCards.length; i += 1) {
        io.to(tableId).emit("reveal_board_card", {
          handId: state.handId,
          runIndex: 1,
          card: newCards[i],
          boardSizeNow: boardStart + i + 1,
          board: state.board.slice(0, boardStart + i + 1),
          street,
          equities,
          hints,
        });
      }

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
    void (async () => {
      await flushDeferredStandUps(tableId);
      await processQueuedTableLeaves(tableId);
      touchLocalRoom(tableId);
      broadcastSnapshot(tableId);
    })().catch((e) => logWarn({
      event: "hand.idle_watchdog.cleanup_failed",
      tableId,
      message: (e as Error).message,
    }));
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

async function flushDeferredStandUps(tableId: string): Promise<void> {
  const deferredSeats = pendingStandUps.get(tableId);
  if (!deferredSeats || deferredSeats.size === 0) return;
  const remainingSeats = new Set<number>();
  for (const seatNum of deferredSeats) {
    const stoodUp = await standUpPlayer(tableId, seatNum, "Left after hand ended");
    if (!stoodUp) {
      remainingSeats.add(seatNum);
    }
  }
  if (remainingSeats.size > 0) {
    pendingStandUps.set(tableId, remainingSeats);
    return;
  }
  pendingStandUps.delete(tableId);
}

async function processQueuedTableLeaves(tableId: string): Promise<void> {
  const pending = pendingTableLeaves.get(tableId);
  if (!pending || pending.size === 0) return;
  const remaining = new Set<string>();
  for (const socketId of pending) {
    const seatBinding = socketSeat.get(socketId);
    let didStandUp = true;
    if (seatBinding && seatBinding.tableId === tableId) {
      didStandUp = await standUpPlayer(tableId, seatBinding.seat, "Left after hand ended");
    }
    if (!didStandUp) {
      remaining.add(socketId);
      continue;
    }
    const sock = io.sockets.sockets.get(socketId);
    if (sock) sock.leave(tableId);
    io.to(socketId).emit("left_table", { tableId });
  }
  if (remaining.size > 0) {
    pendingTableLeaves.set(tableId, remaining);
    return;
  }
  pendingTableLeaves.delete(tableId);
}

function getApprovedRebuyTotalsBySeat(tableId: string): Map<number, number> {
  const totals = new Map<number, number>();
  for (const deposit of pendingRebuys.values()) {
    if (deposit.tableId !== tableId || !deposit.approved) continue;
    totals.set(deposit.seat, (totals.get(deposit.seat) ?? 0) + deposit.amount);
  }
  return totals;
}

function getEligibleSeatNumbersForDeal(tableId: string, includeApprovedRebuys = false): number[] {
  const table = tables.get(tableId);
  if (!table) return [];
  const room = roomManager.getRoom(tableId);
  if (!room) return [];

  const connectedSeats = new Set(bindingsByTable(tableId).map(({ binding }) => binding.seat));
  const approvedTotals = includeApprovedRebuys ? getApprovedRebuyTotalsBySeat(tableId) : new Map<number, number>();
  return table.getPublicState().players
    .filter((player) => player.status === "active")
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
  const minPlayersToStart = Math.max(2, Math.min(room.settings.maxPlayers, room.settings.minPlayersToStart ?? 2));
  if (eligibleSeats.length < minPlayersToStart) {
    return `Need at least ${minPlayersToStart} eligible players to deal (currently ${eligibleSeats.length})`;
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
  const minPlayersToStart = Math.max(2, Math.min(room.settings.maxPlayers, room.settings.minPlayersToStart ?? 2));
  if (eligibleSeats.length < minPlayersToStart) {
    const awayHint = room.settings.dealToAwayPlayers
      ? ""
      : " (away players are excluded; enable \"Deal to away players\" to include them)";
    return `Auto-start skipped: need at least ${minPlayersToStart} eligible players (currently ${eligibleSeats.length})${awayHint}.`;
  }
  return null;
}

async function startHandFlow(tableId: string, actorUserId: string, source: "manual" | "auto"): Promise<string> {
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
  await applyApprovedRebuys(tableId);
  applyRoomVariantSettings(tableId, table);

  const { handId } = table.startHand();
  tablesWithStartedHands.add(tableId);
  clearPendingRunCountDecision(tableId);
  clearShowdownDecisionTimeout(tableId);

  // Clear any pending 7-2 bounty claim from previous hand
  const prevBounty = pendingBountyClaim.get(tableId);
  if (prevBounty) {
    clearTimeout(prevBounty.timeout);
    pendingBountyClaim.delete(tableId);
  }
  lastHandHoleCards.delete(tableId);

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
    const cards = table.getPrivateHoleCards(binding.seat) ?? table.getHoleCards(binding.seat);
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

function scheduleAutoDealIfNeeded(tableId: string, delayOverrideMs?: number): void {
  clearAutoDealSchedule(tableId);

  const room = roomManager.getRoom(tableId);
  if (!room) return;
  const table = tables.get(tableId);
  if (!table) return;

  // Normal public/private tables require an explicit first start.
  // Club tables keep their existing auto-start behavior.
  if (!isPersistentClubTable(tableId) && !tablesWithStartedHands.has(tableId)) {
    return;
  }

  const immediateSkip = getAutoStartSkipMessage(tableId);
  if (immediateSkip) {
    io.to(tableId).emit("system_message", { message: immediateSkip });
    return;
  }

  const baseDelay = SHOWDOWN_SPEED_DELAYS_MS[room.settings.showdownSpeed] ?? SHOWDOWN_SPEED_DELAYS_MS.normal;
  const delayMs = delayOverrideMs ?? (room.settings.selfPlayTurbo ? 0 : baseDelay);

  const handle = setTimeout(() => {
    autoDealSchedule.delete(tableId);
    const managed = roomManager.getRoom(tableId);
    if (!managed) return;

    const skipReason = getAutoStartSkipMessage(tableId);
    if (skipReason) {
      io.to(tableId).emit("system_message", { message: skipReason });
      return;
    }

    void startHandFlow(tableId, managed.ownership.ownerId, "auto").catch((err) => {
      io.to(tableId).emit("system_message", { message: `Auto-start skipped: ${(err as Error).message}` });
    });
  }, delayMs);

  autoDealSchedule.set(tableId, handle);
}

function finalizeHandEnd(tableId: string, state: TableState): void {
  void finalizeHandEndAsync(tableId, state).catch((error) => logWarn({
    event: "hand.finalize.failed",
    tableId,
    handId: state.handId ?? undefined,
    message: (error as Error).message,
  }));
}

async function finalizeHandEndAsync(tableId: string, state: TableState): Promise<void> {
  clearPendingRunCountDecision(tableId);
  clearShowdownDecisionTimeout(tableId);
  const table = tables.get(tableId);
  const finalState = withSnapshotVersion(state, nextSnapshotVersion(tableId));
  const settlement = table?.getSettlementResult() ?? null;

  // ── Save hole cards for post-hand reveal (before clearHand) ──
  if (table) {
    const savedCards = new Map<number, [string, string]>();
    for (const p of state.players) {
      if (!p.inHand) continue;
      const cards = table.getPrivateHoleCards(p.seat) ?? table.getHoleCards(p.seat);
      if (cards && cards.length >= 2) {
        savedCards.set(p.seat, [cards[0], cards[1]]);
      }
    }
    lastHandHoleCards.set(tableId, savedCards);
  }

  // ── 7-2 Bounty detection ──
  const room = roomsByTableId.get(tableId);
  const managedRoomForBounty = roomManager.getRoom(tableId);
  const bountyPerPlayer = managedRoomForBounty?.settings?.sevenTwoBounty ?? 0;
  const isTexas = (state.gameType ?? "texas") === "texas";
  let bountyInfo: SevenTwoBountyInfo | undefined;
  let hasPendingBountyClaim = false;

  if (bountyPerPlayer > 0 && isTexas && table && settlement) {
    // Collect unique winner seats from settlement
    const winnerSeats = new Set<number>();
    for (const runWinners of settlement.winnersByRun) {
      for (const w of runWinners.winners) winnerSeats.add(w.seat);
    }

    // All dealt-in seats (excluding the winner being checked)
    const dealtInSeats = state.players.filter((p) => p.inHand).map((p) => p.seat);
    const revealed = state.revealedHoles ?? {};

    for (const winnerSeat of winnerSeats) {
      const holeCards = lastHandHoleCards.get(tableId)?.get(winnerSeat);
      if (!holeCards || !isSevenTwo(holeCards)) continue;

      const payingSeats = dealtInSeats.filter((s) => s !== winnerSeat);
      if (payingSeats.length === 0) continue;

      // Check if winner's cards are already revealed at showdown
      const alreadyRevealed = Boolean(revealed[winnerSeat]);
      if (alreadyRevealed) {
        // Auto-apply bounty immediately
        const bountyBySeat: Record<number, number> = {};
        let totalBounty = 0;
        for (const payerSeat of payingSeats) {
          const payer = state.players.find((p) => p.seat === payerSeat);
          const payerStack = payer?.stack ?? 0;
          const amount = Math.min(bountyPerPlayer, payerStack);
          if (amount > 0) {
            table.addStack(payerSeat, -amount);
            totalBounty += amount;
            bountyBySeat[payerSeat] = -amount;
          }
        }
        if (totalBounty > 0) {
          table.addStack(winnerSeat, totalBounty);
          bountyBySeat[winnerSeat] = totalBounty;
          bountyInfo = {
            bountyPerPlayer,
            winnerSeat,
            winnerCards: holeCards,
            payingSeats,
            totalBounty,
            bountyBySeat,
          };
        }
      } else {
        // Winner has 7-2 but cards not revealed — set up pending claim
        // Clear any existing claim first
        const existing = pendingBountyClaim.get(tableId);
        if (existing) clearTimeout(existing.timeout);

        const claimTimeout = setTimeout(() => {
          pendingBountyClaim.delete(tableId);
          logInfo({ event: "seven_two_bounty.forfeited", tableId, handId: state.handId, winnerSeat });
        }, 10_000);

        pendingBountyClaim.set(tableId, {
          handId: state.handId ?? "",
          winnerSeat,
          cards: holeCards,
          dealtInSeats: payingSeats,
          bountyPerPlayer,
          timeout: claimTimeout,
        });
        hasPendingBountyClaim = true;
      }
      // Only process the first 7-2 winner (simplification for common case)
      break;
    }
  }

  // Attach bounty info to settlement if auto-applied
  if (bountyInfo && settlement) {
    settlement.sevenTwoBounty = bountyInfo;
  }

  // ── Inject bot hole cards into revealedHoles so clients see them ──
  const botIds = getBotUserIds(tableId);
  if (botIds.size > 0 && table) {
    const revealed: Record<number, [string, string]> = { ...(finalState.revealedHoles ?? {}) };
    for (const p of finalState.players) {
      if (!botIds.has(p.userId)) continue;
      if (revealed[p.seat]) continue; // already revealed at showdown
      const cards = table.getPrivateHoleCards(p.seat) ?? table.getHoleCards(p.seat);
      if (cards && cards.length >= 2) {
        revealed[p.seat] = [cards[0], cards[1]];
      }
    }
    finalState.revealedHoles = revealed;
  }

  logInfo({
    event: "hand.ended",
    tableId,
    handId: finalState.handId,
    winners: (finalState.winners ?? []).length,
    totalPot: settlement?.totalPot ?? finalState.pot,
    stateVersion: finalState.stateVersion,
  });
  persistHandHistory(tableId, finalState, settlement, table).catch((e) => logWarn({
    event: "hand_history.persist.failed",
    tableId,
    handId: finalState.handId,
    message: (e as Error).message,
  }));
  io.to(tableId).emit("hand_ended", {
    handId: finalState.handId,
    finalState,
    board: finalState.board,
    runoutBoards: finalState.runoutBoards,
    runoutPayouts: finalState.runoutPayouts,
    players: finalState.players,
    pot: finalState.pot,
    winners: finalState.winners,
    settlement: settlement ?? undefined,
  });
  roomManager.clearActionTimer(tableId);
  roomManager.setHandActive(tableId, false);

  // ── GTO audit pipeline: queue async audit for each seated hero ──
  // Must run BEFORE clearHand() so table.getPosition() is still available
  try {
    queueAuditForHand(tableId, state, table);
  } catch (e) {
    logWarn({ event: "audit.queue.failed", tableId, handId: state.handId, message: (e as Error).message });
  }

  // Cleanly mark hand as done in engine (nulls handId, resets handInProgress)
  if (table) table.clearHand();

  // Increment hands played for session stats
  incrementHandsPlayed(tableId, state.players.filter((p) => p.inHand).map((p) => p.userId));
  syncSessionStacksFromState(tableId, state);
  broadcastSessionStats(tableId);

  // Club leaderboard stats: hands + net per player are recorded at hand end.
  const clubInfo = getClubInfoForTableId(tableId);
  if (clubInfo && settlement) {
    const playerBySeat = new Map(state.players.map((p) => [p.seat, p]));
    const statWrites: Promise<void>[] = [];
    for (const entry of settlement.ledger) {
      const player = playerBySeat.get(entry.seat);
      if (!player) continue;
      statWrites.push(clubDataRepo.recordClubHandStats(
        clubInfo.clubId,
        player.userId,
        1,
        Math.trunc(entry.net),
        0,
      ).catch((e) => logWarn({
        event: "club_leaderboard.record_hand_stats.failed",
        tableId,
        clubId: clubInfo.clubId,
        userId: player.userId,
        message: (e as Error).message,
      })));
    }
    await Promise.all(statWrites);
    scheduleClubLeaderboardRefresh(clubInfo.clubId);
  }

  // Bust-out auto-stand: players with no chips after hand ends
  for (const p of state.players) {
    if (p.stack <= 0) {
      const sid = socketIdBySeat(tableId, p.seat);
      if (sid) {
        io.to(sid).emit("system_message", { message: "You busted out and were stood up. Rebuy to continue." });
      }
      await standUpPlayer(tableId, p.seat, "Busted out");
    }
  }

  // Process deferred stand-ups before auto-deal so leave-after-hand is authoritative.
  await flushDeferredStandUps(tableId);

  // Process deferred pause
  const deferredPause = pendingPause.get(tableId);
  if (deferredPause) {
    pendingPause.delete(tableId);
    roomManager.pauseGame(tableId, deferredPause.userId, deferredPause.displayName);
  }

  // Process deferred leave-table requests before scheduling a new hand.
  await processQueuedTableLeaves(tableId);

  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);
  const wasAllInHand = state.players.some((player) => player.allIn);
  scheduleAutoDealIfNeeded(tableId, wasAllInHand ? 4_000 : 2_000);
}

function handleRoomAutoClose(tableId: string): void {
  if (isPersistentClubTable(tableId)) {
    return;
  }

  const count = currentPlayerCount(tableId);
  const closed = roomManager.finalizeAutoClose(tableId, count);
  if (!closed) return;

  clearAutoDealSchedule(tableId);
  clearShowdownDecisionTimeout(tableId);
  clearPendingRunCountDecision(tableId);
  clearHandIdleWatchdog(tableId);
  removeAllBots(tableId);
  pendingStandUps.delete(tableId);
  pendingTableLeaves.delete(tableId);
  pendingPause.delete(tableId);
  tablesWithStartedHands.delete(tableId);
  for (const [orderId, request] of pendingSeatRequests.entries()) {
    if (request.tableId === tableId) pendingSeatRequests.delete(orderId);
  }
  for (const [orderId, deposit] of pendingRebuys.entries()) {
    if (deposit.tableId === tableId) pendingRebuys.delete(orderId);
  }

  io.to(tableId).emit("room_closed", { tableId, reason: "empty" });
  const roomSockets = io.sockets.adapter.rooms.get(tableId);
  if (roomSockets) {
    for (const sid of roomSockets) {
      const sock = io.sockets.sockets.get(sid);
      if (sock) sock.leave(tableId);
    }
  }

  for (const [sid, binding] of socketSeat.entries()) {
    if (binding.tableId !== tableId) continue;
    socketSeat.delete(sid);
    io.to(sid).emit("left_table", { tableId });
  }

  tables.delete(tableId);
  tableSnapshotVersions.delete(tableId);

  const room = roomsByTableId.get(tableId);
  if (room) {
    sessionStatsByRoomCode.delete(room.roomCode);
    roomCodeToTableId.delete(room.roomCode);
    roomsByTableId.delete(tableId);
    closeRoomSessionIfOpen(tableId, "auto_close").catch(() => {});
    supabase.touchRoom(tableId, "CLOSED").catch(() => {});
  }

  void emitLobbySnapshot();
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
    // Away player was dealt in (dealToAwayPlayers=true): auto-check/fold so the hand cannot stall.
    try {
      const { state: autoState, action: autoAction } = table.handleTimeout(state.actorSeat);
      io.to(tableId).emit("action_applied", {
        seat: state.actorSeat,
        action: autoAction,
        amount: 0,
        pot: autoState.pot,
        auto: true,
      });
      handlePostAction(tableId, table, autoState);
    } catch (err) {
      console.warn("startTimerForActor: auto-action for away actor failed:", (err as Error).message);
    }
    return;
  }

  roomManager.startActionTimer(
    tableId,
    state.actorSeat,
    actorBinding.binding.userId,
    () => {
      // Timeout: use engine's handleTimeout (auto-check if possible, otherwise fold)
      const tbl = tables.get(tableId);
      if (!tbl) return;
      const s = tbl.getPublicState();
      if (!s.handId || s.handId !== expectedHandId) return;
      if (s.actorSeat == null || s.actorSeat !== expectedSeat || !s.legalActions) return;
      const timedOutSeat = s.actorSeat;
      try {
        const { state: newState, action: timeoutAction, autoSatOut } = tbl.handleTimeout(timedOutSeat);
        io.to(tableId).emit("action_applied", {
          seat: timedOutSeat,
          action: timeoutAction,
          amount: 0,
          pot: newState.pot,
          auto: true,
        });

        // Engine tracks consecutive timeouts; mark as away (sitting_out) after repeated offenses
        // Player stays at the table — they can press "I'm Back" to return
        if (autoSatOut) {
          io.to(tableId).emit("system_message", {
            message: `Seat ${timedOutSeat} is away (timed out repeatedly).`,
          });
          const room = roomManager.getRoom(tableId);
          if (room) {
            roomManager.addLog(room, "PLAYER_SAT_OUT", {
              targetId: actorBinding.binding.userId,
              message: `Seat ${timedOutSeat} auto-away after consecutive timeouts`,
            });
          }
          broadcastSnapshot(tableId);
        }

        // Continue the hand
        handlePostAction(tableId, tbl, newState);
      } catch (err) {
        console.warn("auto-action on timeout failed:", (err as Error).message);
      }
    }
  );
}

/** Remove a player from their seat and clean up bindings */
async function standUpPlayer(tableId: string, seatNum: number, reason: string): Promise<boolean> {
  const table = tables.get(tableId);
  if (!table) return false;
  const state = table.getPublicState();
  const leavingPlayer = state.players.find((player) => player.seat === seatNum);
  if (!leavingPlayer) return false;

  const clubInfo = getClubInfoForTableId(tableId);
  if (clubInfo && leavingPlayer.stack > 0) {
    try {
      const tx = await appendWalletTx({
        clubId: clubInfo.clubId,
        userId: leavingPlayer.userId,
        type: "cash_out",
        amount: Math.trunc(leavingPlayer.stack),
        currency: "chips",
        refType: "table_seat",
        refId: `${tableId}:${seatNum}`,
        createdBy: leavingPlayer.userId,
        note: `Cash-out from seat ${seatNum} (${reason})`,
        metaJson: { tableId, seat: seatNum, reason },
      });
      await emitWalletBalanceToUser(clubInfo.clubId, leavingPlayer.userId, tx.newBalance, "chips");
    } catch (error) {
      logWarn({
        event: "club_wallet.cash_out.failed",
        tableId,
        seat: seatNum,
        userId: leavingPlayer.userId,
        message: (error as Error).message,
      });
      io.to(tableId).emit("system_message", { message: `Failed to cash out seat ${seatNum}. Try again.` });
      return false;
    }
  }

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
  recordSessionCashOut(tableId, leavingPlayer.userId, leavingPlayer.stack);
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
  broadcastSessionStats(tableId);
  checkBotsOnlyAndRemove(tableId);
  maybeCheckRoomEmpty(tableId, currentPlayerCount(tableId));
  void emitLobbySnapshot();
  return true;
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
  const state = table.getPublicState();
  if (!state.handId) return;

  // No cards remain to be run out on the river board.
  if (state.board.length >= 5 || state.street === "RIVER" || state.street === "SHOWDOWN") {
    table.setAllInRunCount(1);
    touchLocalRoom(tableId);
    broadcastSnapshot(tableId);
    void handleSequentialRunout(tableId, table);
    return;
  }

  const eligiblePlayers = state.players
    .filter((player) => player.inHand && !player.folded)
    .map((player) => ({ seat: player.seat, name: player.name }))
    .sort((a, b) => a.seat - b.seat);

  if (eligiblePlayers.length < 2) {
    table.setAllInRunCount(1);
    touchLocalRoom(tableId);
    broadcastSnapshot(tableId);
    void handleSequentialRunout(tableId, table);
    return;
  }

  const preferencesBySeat: Record<number, RunCountPreference | null> = {};
  for (const player of eligiblePlayers) {
    preferencesBySeat[player.seat] = null;
  }

  const equities = calculateAllPlayersEquity(table, [...state.board] as Card[]);
  const equityBySeat = new Map<number, number>(equities.map((entry) => [entry.seat, entry.equityRate]));
  const underdogSeat = [...eligiblePlayers]
    .sort((a, b) => {
      const wa = equityBySeat.get(a.seat) ?? 1;
      const wb = equityBySeat.get(b.seat) ?? 1;
      if (wa === wb) return a.seat - b.seat;
      return wa - wb;
    })[0]?.seat ?? eligiblePlayers[0].seat;

  const pending: PendingRunCountDecisionState = {
    handId: state.handId,
    eligiblePlayers,
    underdogSeat,
    preferencesBySeat,
    targetRunCount: null,
    equities,
  };
  pendingRunCountDecisions.set(tableId, pending);

  // Reveal hole cards immediately so all players can see cards + equity during all-in
  revealLockedHoleCards(tableId, table, pending);

  emitAllInLocked(tableId, pending);
  broadcastSnapshot(tableId);

  // Backward-compatible per-seat prompt for older clients that still listen to all_in_prompt.
  for (const player of eligiblePlayers) {
    const isUnderdog = player.seat === underdogSeat;
    const prompt: AllInPrompt = {
      actorSeat: player.seat,
      winRate: equityBySeat.get(player.seat) ?? 0,
      recommendedRunCount: 1,
      defaultRunCount: 1,
      allowedRunCounts: isUnderdog ? [1, 2, 3] : [1],
      promptMode: "run_count",
      reason: isUnderdog
        ? "You are currently the underdog. Choose run once, twice, or three times."
        : "Waiting for underdog run-count choice. You can approve or reject after they choose.",
    };
    const socketId = socketIdBySeat(tableId, player.seat);
    if (socketId) {
      io.to(socketId).emit("all_in_prompt", prompt);
    }
  }

  touchLocalRoom(tableId);
  broadcastSnapshot(tableId);
  scheduleRunCountDecisionTimeout(tableId, table, pending);
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
      // Race Supabase check against a 3s timeout to avoid hanging when Supabase is slow
      const existing = await Promise.race([
        supabase.findRoomByCode(candidate),
        new Promise<null>((_, rej) => setTimeout(() => rej(new Error("findRoomByCode timeout (3s)")), 3000)),
      ]);
      if (!existing) return candidate;
    } catch (err) {
      // Supabase unavailable, slow, or table missing — fall back to in-memory uniqueness only
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

  // Club tables: roomCode = clubTable.id — try direct lookup first
  const clubInfo = clubManager.getClubForTableById(normalized);
  if (clubInfo) {
    ensureClubTableRoom(clubInfo.clubId, clubInfo.clubTableId);
    return roomsByTableId.get(normalized) ?? null;
  }

  // Non-club rooms: standard lookup
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
  const clubInfo = clubManager.getClubForTableById(room.tableId);
  if (clubInfo) {
    const rules = clubManager.getRulesForTable(clubInfo.clubId, clubInfo.clubTableId);
    const club = clubManager.getClub(clubInfo.clubId);
    const tableMeta = clubManager.getClubTable(clubInfo.clubId, clubInfo.clubTableId);
    if (rules && tableMeta) {
      room.roomName = `${club?.name ?? "Club"} — ${tableMeta.name}`;
      room.maxPlayers = rules.maxSeats;
      room.smallBlind = rules.stakes.smallBlind;
      room.bigBlind = rules.stakes.bigBlind;
      room.isPublic = false;
      room.updatedAt = new Date().toISOString();
      roomsByTableId.set(room.tableId, room);

      const ownerId = room.createdBy ?? tableMeta.createdBy ?? ownerFallback.userId;
      roomManager.createRoom({
        tableId: room.tableId,
        roomCode: room.roomCode,
        roomName: room.roomName,
        ownerId,
        ownerName: ownerId === ownerFallback.userId ? ownerFallback.displayName : "Club Host",
        settings: {
          gameType: rules.extras.gameType,
          maxPlayers: rules.maxSeats,
          smallBlind: rules.stakes.smallBlind,
          bigBlind: rules.stakes.bigBlind,
          buyInMin: rules.buyIn.minBuyIn,
          buyInMax: rules.buyIn.maxBuyIn,
          actionTimerSeconds: rules.time.actionTimeSec,
          timeBankSeconds: rules.time.timeBankSec,
          disconnectGracePeriod: rules.time.disconnectGraceSec,
          autoStartNextHand: rules.dealing.autoStartNextHand && rules.dealing.autoDealEnabled,
          minPlayersToStart: Math.max(2, Math.min(rules.maxSeats, rules.dealing.minPlayersToStart ?? 2)),
          spectatorAllowed: rules.moderation.allowSpectators,
          runItTwice: rules.runit.allowRunItTwice,
          runItTwiceMode: rules.runit.allowRunItTwice ? "ask_players" : "off",
          straddleAllowed: rules.extras.straddleAllowed,
          bombPotEnabled: rules.extras.bombPotEnabled,
          rabbitHunting: rules.extras.rabbitHuntEnabled,
          sevenTwoBounty: rules.extras.sevenTwoBounty,
          visibility: "private",
        },
      });
      return;
    }
  }

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

const RANK_ORDER: string[] = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"];

function rankValue(rank: string): number {
  const index = RANK_ORDER.indexOf(rank);
  return index === -1 ? -1 : index;
}

function classifyStartingHandBucket(cards: string[], gameType: TableState["gameType"]): string {
  if (cards.length < 2) return "unknown";

  const ranks = cards.map((card) => card[0]).filter(Boolean);
  const suits = cards.map((card) => card[1]).filter(Boolean);
  if (gameType === "omaha" || cards.length >= 4) {
    const sortedRanks = [...ranks].sort((a, b) => rankValue(b) - rankValue(a));
    const topRanks = `${sortedRanks[0] ?? "X"}${sortedRanks[1] ?? "X"}`;
    const suitCounts = new Map<string, number>();
    for (const suit of suits) {
      suitCounts.set(suit, (suitCounts.get(suit) ?? 0) + 1);
    }
    const grouped = [...suitCounts.values()].sort((a, b) => b - a);
    if ((grouped[0] ?? 0) >= 2 && (grouped[1] ?? 0) >= 2) return `${topRanks}xx-ds`;
    if ((grouped[0] ?? 0) >= 2) return `${topRanks}xx-ss`;
    return `${topRanks}xx`;
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

async function persistHandHistory(
  tableId: string,
  state: TableState,
  settlement: ReturnType<GameTable["getSettlementResult"]>,
  table?: GameTable,
): Promise<void> {
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
  const netByPosition: Record<string, number> = {};
  const startingHandBucketsByUser: Record<string, string> = {};
  for (const entry of settlement.ledger) {
    const player = playersBySeat.get(entry.seat);
    if (!player) continue;
    netByUser[player.userId] = entry.net;

    const position = state.positions?.[entry.seat] ?? (table ? table.getPosition(entry.seat) : `Seat ${entry.seat}`);
    netByPosition[position] = (netByPosition[position] ?? 0) + entry.net;

    const privateCards = table?.getPrivateHoleCards(entry.seat) ?? table?.getHoleCards(entry.seat) ?? null;
    if (privateCards && privateCards.length >= 2) {
      startingHandBucketsByUser[player.userId] = classifyStartingHandBucket(privateCards, state.gameType ?? "texas");
    }
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
    netByPosition: Object.keys(netByPosition).length > 0 ? netByPosition : undefined,
    startingHandBucketsByUser: Object.keys(startingHandBucketsByUser).length > 0 ? startingHandBucketsByUser : undefined,
    gameType: state.gameType,
    flags: {
      allIn: state.actions.some((action) => action.type === "all_in"),
      runItTwice: settlement.runCount > 1,
      showdown: settlement.showdown,
      bombPot: state.isBombPotHand,
      doubleBoard: state.isDoubleBoardHand,
    },
  };

  // Collect private hole cards for each player (even if folded)
  const privateHoleCardsByUser: Record<string, [string, string]> = {};
  for (const player of state.players) {
    if (!player.userId) continue;
    const cards = table?.getPrivateHoleCards(player.seat) ?? table?.getHoleCards(player.seat);
    if (cards && cards.length >= 2) {
      privateHoleCardsByUser[player.userId] = [cards[0], cards[1]];
    }
  }

  // Ensure ALL bot hole cards are in revealedHoles for transparency
  const revealedHolesForHistory: Record<number, [string, string]> = { ...(state.revealedHoles ?? {}) };
  const persistBotIds = getBotUserIds(tableId);
  if (persistBotIds.size > 0) {
    for (const player of state.players) {
      if (!persistBotIds.has(player.userId)) continue;
      if (revealedHolesForHistory[player.seat]) continue; // already revealed
      const botCards = table?.getPrivateHoleCards(player.seat) ?? table?.getHoleCards(player.seat);
      if (botCards && botCards.length >= 2) {
        revealedHolesForHistory[player.seat] = [botCards[0], botCards[1]];
      }
    }
  }

  const detail: HistoryHandDetailCore = {
    board: [...state.board],
    runoutBoards: state.runoutBoards ? state.runoutBoards.map((board) => [...board]) : [],
    doubleBoardPayouts: settlement.doubleBoardPayouts
      ? settlement.doubleBoardPayouts.map((run) => ({ run: run.run, board: [...run.board], winners: [...run.winners] }))
      : undefined,
    potLayers: settlement.potLayers.map((layer) => ({
      label: layer.label,
      amount: layer.amount,
      eligibleSeats: [...layer.eligibleSeats],
    })),
    contributionsBySeat: { ...settlement.contributions },
    actionTimeline: [...state.actions],
    revealedHoles: revealedHolesForHistory,
    privateHoleCardsByUser: Object.keys(privateHoleCardsByUser).length > 0 ? privateHoleCardsByUser : undefined,
    payoutLedger: settlement.ledger.map((entry) => ({ ...entry })),
  };

  const viewerBotIds = getBotUserIds(tableId);
  const viewerUserIds = [...new Set([
    ...state.players.map((player) => player.userId),
    managed?.ownership.ownerId ?? "",
    ...(managed?.ownership.coHostIds ?? []),
  ])].filter((userId) => userId.length > 0 && !viewerBotIds.has(userId));

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

function queueAuditForHand(tableId: string, state: TableState, table: GameTable | undefined): void {
  if (!state.handId || !state.board || state.board.length < 3) return;
  if (!table) return;

  // Capture positions from the engine while hand state is still live
  const positions: Record<number, string> = {};
  for (const p of state.players) {
    positions[p.seat] = table.getPosition(p.seat) ?? "BTN";
  }

  const playerSeats = state.players
    .filter((p) => p.inHand || !p.folded)
    .map((p) => p.seat);

  // Queue an audit for each seated player who has revealed hole cards
  const revealedHoles = state.revealedHoles ?? {};
  for (const p of state.players) {
    if (!p.userId || p.userId.startsWith("guest-")) continue;
    const cards = revealedHoles[p.seat] as [string, string] | undefined;
    if (!cards || cards.length < 2) continue;

    getAuditService().queueHandAudit(
      {
        handId: state.handId,
        handHistoryId: state.handId,
        tableId,
        bigBlind: state.bigBlind,
        smallBlind: state.smallBlind,
        buttonSeat: state.buttonSeat,
        playerSeats,
        actions: [...state.actions],
        positions,
        heroUserId: p.userId,
        heroSeat: p.seat,
        heroCards: [cards[0], cards[1]],
        board: [...state.board],
        totalPot: state.pot,
      },
      undefined
    );
  }
}

io.on("connection", (socket) => {
  const identity = socketIdentity.get(socket.id);
  if (!identity) {
    socket.disconnect(true);
    return;
  }

  const requireClubAuth = (): boolean => {
    if (isClubAuthenticatedIdentity(identity)) return true;
    const reason = identity.userId.startsWith("guest-") ? "Guest accounts cannot access club features. Please log in." : "Authentication required.";
    emitClubUnauthorized(socket, reason);
    return false;
  };

  socket.emit("connected", {
    socketId: socket.id,
    userId: identity.userId,
    displayName: identity.displayName,
    supabaseEnabled: supabase.enabled()
  });
  void emitLobbySnapshot(socket.id);

  // ── Auto-restore seat on reconnect ──
  const graceSeat = roomManager.getDisconnectedSeatByUserId(identity.userId);
  if (graceSeat) {
    const { tableId: graceTableId, seat: graceSeatNo } = graceSeat;
    // Skip auto-restore if the player explicitly requested to leave (pending stand-up)
    const hasPendingStandUp = pendingStandUps.get(graceTableId)?.has(graceSeatNo);
    if (hasPendingStandUp) {
      // Player intentionally left — cancel grace, don't pull them back
      roomManager.cancelDisconnectGrace(graceTableId, graceSeatNo);
      rejoinInfo.delete(identity.userId);
      logInfo({
        event: "player.skip_auto_restore",
        userId: identity.userId,
        tableId: graceTableId,
        message: `Seat ${graceSeatNo} has pending leave — skipping auto-restore`,
      });
    } else {
      const graceRoom = roomsByTableId.get(graceTableId);
      if (graceRoom) {
        // Re-bind socket to room and seat
        socket.join(graceTableId);
        socketSeat.set(socket.id, {
          tableId: graceTableId,
          seat: graceSeatNo,
          userId: identity.userId,
          name: identity.displayName,
        });
        roomManager.cancelDisconnectGrace(graceTableId, graceSeatNo);
        rejoinInfo.delete(identity.userId);

        // Notify the reconnected player
        socket.emit("room_joined", {
          tableId: graceTableId,
          roomCode: graceRoom.roomCode,
          roomName: graceRoom.roomName,
        });
        emitHydratedSnapshot(socket.id, graceTableId);
        const fullState = roomManager.getFullState(graceTableId);
        if (fullState) socket.emit("room_state_update", withClubRoomStateMetadata(fullState, graceTableId, identity.userId));

        // Update Supabase
        supabase.upsertSeat({
          table_id: graceTableId,
          seat_no: graceSeatNo,
          user_id: identity.userId,
          display_name: identity.displayName,
          stack: tables.get(graceTableId)?.getPublicState().players.find((p) => p.seat === graceSeatNo)?.stack ?? 0,
          is_connected: true,
        }).catch((e) => console.warn("reconnect: upsertSeat failed:", (e as Error).message));

        logInfo({
          event: "player.auto_reconnected",
          userId: identity.userId,
          tableId: graceTableId,
          message: `Seat ${graceSeatNo} auto-restored`,
        });
      }
    }
  }

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

        // Auto-close any stale room the user already owns
        const ownedRoom = roomManager.getActiveRoomOwnedBy(identity.userId);
        if (ownedRoom) {
          const staleTableId = ownedRoom.tableId;
          logInfo({
            event: "room.auto_close.stale",
            tableId: staleTableId,
            userId: identity.userId,
            message: `Auto-closing stale room ${ownedRoom.roomCode} before creating new room`,
          });

          clearAutoDealSchedule(staleTableId);
          clearShowdownDecisionTimeout(staleTableId);
          clearPendingRunCountDecision(staleTableId);
          clearHandIdleWatchdog(staleTableId);
          removeAllBots(staleTableId);
          roomManager.endGame(staleTableId, identity.userId, identity.displayName);

          io.to(staleTableId).emit("room_closed", { tableId: staleTableId, reason: "Host created a new room" });

          const staleTable = tables.get(staleTableId);
          if (staleTable) {
            const state = staleTable.getPublicState();
            for (const player of state.players) {
              staleTable.removePlayer(player.seat);
            }
          }

          for (const [sid, binding] of socketSeat.entries()) {
            if (binding.tableId === staleTableId) {
              socketSeat.delete(sid);
              const sock = io.sockets.sockets.get(sid);
              if (sock) sock.leave(staleTableId);
            }
          }

          const staleRoomInfo = roomsByTableId.get(staleTableId);
          if (staleRoomInfo) {
            roomCodeToTableId.delete(staleRoomInfo.roomCode);
            sessionStatsByRoomCode.delete(staleRoomInfo.roomCode);
            roomsByTableId.delete(staleTableId);
          }
          pendingStandUps.delete(staleTableId);
          pendingTableLeaves.delete(staleTableId);
          pendingPause.delete(staleTableId);
          for (const [orderId, request] of pendingSeatRequests.entries()) {
            if (request.tableId === staleTableId) pendingSeatRequests.delete(orderId);
          }
          for (const [orderId, deposit] of pendingRebuys.entries()) {
            if (deposit.tableId === staleTableId) pendingRebuys.delete(orderId);
          }
          tables.delete(staleTableId);
          tableSnapshotVersions.delete(staleTableId);
          roomManager.deleteRoom(staleTableId);

          closeRoomSessionIfOpen(staleTableId, "auto_close_stale").catch(() => {});
          supabase.touchRoom(staleTableId, "CLOSED").catch(() => {});
          supabase.logEvent({
            tableId: staleTableId,
            eventType: "ROOM_CLOSED",
            actorUserId: identity.userId,
            payload: { reason: "auto_closed_stale_before_create" },
          }).catch(() => {});

          void emitLobbySnapshot();
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
        if (IDENTITY_DEBUG) {
          logInfo({
            event: "room.create.ownership",
            userId: identity.userId,
            message: JSON.stringify({ tableId: room.tableId, roomCode: room.roomCode, ownerId: identity.userId }),
          });
        }

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
        emitHydratedSnapshot(socket.id, room.tableId);
        const fullState = roomManager.getFullState(room.tableId);
        if (fullState) socket.emit("room_state_update", withClubRoomStateMetadata(fullState, room.tableId, identity.userId));
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

  socket.on("request_room_hands", async (payload: { roomId: string; limit?: number }) => {
    try {
      if (!payload?.roomId) throw new Error("roomId is required");
      // Verify user is in the room
      const room = roomManager.getRoom(payload.roomId);
      if (!room) throw new Error("Room not found");
      const hands = await supabase.listHandsByRoom(payload.roomId, payload.limit ?? 100);
      socket.emit("room_hands", { roomId: payload.roomId, hands });
    } catch (error) {
      socket.emit("room_hands", { roomId: payload?.roomId ?? "", hands: [] });
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

  socket.on("history_gto_analyze", async (payload: { handId: string; handRecord: unknown; precision: "fast" | "deep" }) => {
    try {
      if (!payload?.handId || !payload?.handRecord) {
        throw new Error("handId and handRecord are required");
      }
      const analyzeHandGTO = await getAnalyzeHandGTO();
      if (!analyzeHandGTO) {
        throw new Error("GTO analysis is temporarily unavailable on this server");
      }
      const precision = payload.precision === "deep" ? "deep" : "fast";
      const gtoAnalysis = await analyzeHandGTO(payload.handRecord as Parameters<typeof analyzeHandGTO>[0], precision);
      socket.emit("history_gto_result", { handId: payload.handId, gtoAnalysis });
    } catch (error) {
      logWarn({ event: "history_gto_analyze.failed", message: (error as Error).message });
      socket.emit("history_gto_result", { handId: payload?.handId ?? "", gtoAnalysis: null, error: (error as Error).message });
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

      const clubInfo = clubManager.getClubForTableById(room.tableId);
      if (clubInfo && !requireClubAuth()) {
        return;
      }

      if (room.status === "CLOSED") {
        if (clubInfo) {
          if (!clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
            throw new Error("Club members only: this table is restricted to active club members.");
          }
        } else if (room.createdBy && room.createdBy !== identity.userId) {
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
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("Club members only: this table is restricted to active club members.");
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
      maybeCheckRoomEmpty(room.tableId, currentPlayerCount(room.tableId) + 1);

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
      emitHydratedSnapshot(socket.id, room.tableId);
      const fullState = roomManager.getFullState(room.tableId);
      if (fullState) socket.emit("room_state_update", withClubRoomStateMetadata(fullState, room.tableId, identity.userId));
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
    const clubInfo = clubManager.getClubForTableById(payload.tableId);
    if (clubInfo) {
      if (!requireClubAuth()) return;
      if (!clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        socket.emit("error_event", { message: "Club members only: this table is restricted to active club members." });
        return;
      }
    }

    const table = createTableIfNeeded(room);
    socket.join(payload.tableId);

    // Cancel empty timer if someone joins the room
    maybeCheckRoomEmpty(payload.tableId, currentPlayerCount(payload.tableId) + 1);

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
    emitHydratedSnapshot(socket.id, room.tableId);
    const fullState = roomManager.getFullState(room.tableId);
    if (fullState) socket.emit("room_state_update", withClubRoomStateMetadata(fullState, room.tableId, identity.userId));
    emitPresence(payload.tableId);
    void emitLobbySnapshot();
  });

  const seatPlayerDirect = async (params: {
    tableId: string;
    seat: number;
    buyIn: number;
    userId: string;
    userName: string;
    socketId: string;
    isRestore: boolean;
    approvedByUserId: string;
  }): Promise<void> => {
    const room = await ensureRoomByTableId(params.tableId);
    ensureManagedRoom(room, identity);
    const table = createTableIfNeeded(room);
    const managed = roomManager.getRoom(params.tableId);
    if (!managed) throw new Error("Room not found");

    if (params.seat < 1 || params.seat > managed.settings.maxPlayers) {
      throw new Error(`Seat must be between 1 and ${managed.settings.maxPlayers}`);
    }

    const existing = bindingByUser(params.tableId, params.userId);
    if (existing && existing.seat !== params.seat) {
      throw new Error("You are already seated at this table. Stand up first to switch seats.");
    }

    if (table.getPublicState().players.some((p) => p.seat === params.seat)) {
      throw new Error("Seat already occupied");
    }

    const clubInfo = clubManager.getClubForTableById(params.tableId);
    if (clubInfo) {
      if (!clubManager.isActiveMember(clubInfo.clubId, params.userId)) {
        throw new Error("Only active club members can sit at this table");
      }
      const walletBalance = await clubDataRepo.getWalletBalance(clubInfo.clubId, params.userId, "chips");
      if (walletBalance < params.buyIn) {
        throw new Error(`Club has insufficient funds (${walletBalance}) for buy-in ${params.buyIn}`);
      }
    }

    table.addPlayer({
      seat: params.seat,
      userId: params.userId,
      name: params.userName,
      stack: params.buyIn,
    });

    if (clubInfo) {
      try {
        const tx = await appendWalletTx({
          clubId: clubInfo.clubId,
          userId: params.userId,
          type: "buy_in",
          amount: -Math.trunc(params.buyIn),
          currency: "chips",
          refType: "table_seat",
          refId: `${params.tableId}:${params.seat}`,
          createdBy: params.approvedByUserId,
          note: `Buy-in for seat ${params.seat} at ${room.roomName}`,
          metaJson: {
            tableId: params.tableId,
            seat: params.seat,
            roomCode: room.roomCode,
            approvedBy: params.approvedByUserId,
          },
        });
        await emitWalletBalanceToUser(clubInfo.clubId, params.userId, tx.newBalance, "chips");
      } catch (error) {
        table.removePlayer(params.seat);
        throw error;
      }
    }

    if (!params.isRestore) {
      recordSessionBuyIn(params.tableId, params.userId, params.userName, params.buyIn);
    }
    setSessionLastStack(params.tableId, params.userId, params.userName, params.buyIn);

    socketSeat.set(params.socketId, {
      tableId: params.tableId,
      seat: params.seat,
      userId: params.userId,
      name: params.userName,
    });

    // Cancel disconnect grace if this seat was in grace period (reconnect scenario)
    roomManager.cancelDisconnectGrace(params.tableId, params.seat);
    // Clear rejoin info since player is now seated
    rejoinInfo.delete(params.userId);

    supabase.upsertSeat({
      table_id: params.tableId,
      seat_no: params.seat,
      user_id: params.userId,
      display_name: params.userName,
      stack: params.buyIn,
      is_connected: true,
    }).catch((e) => console.warn("seatPlayerDirect: upsertSeat failed:", (e as Error).message));

    supabase.touchRoom(params.tableId, "OPEN").catch((e) => console.warn("seatPlayerDirect: touchRoom failed:", (e as Error).message));
    supabase.logEvent({
      tableId: params.tableId,
      eventType: "SIT_DOWN",
      actorUserId: params.userId,
      payload: { seat: params.seat, buyIn: params.buyIn, restored: params.isRestore },
    }).catch((e) => console.warn("seatPlayerDirect: logEvent failed:", (e as Error).message));

    if (params.isRestore) {
      io.to(params.socketId).emit("system_message", {
        message: `Room funds tracking restored your previous stack (${params.buyIn}).`,
      });
    }

    touchLocalRoom(params.tableId);
    broadcastSnapshot(params.tableId);
    broadcastSessionStats(params.tableId);
    scheduleAutoDealIfNeeded(params.tableId);
    void emitLobbySnapshot();
  };

  socket.on("sit_down", async (payload: { tableId: string; seat: number; buyIn: number; name?: string }) => {
    try {
      console.log("[SIT_DOWN] Request from", identity.userId, "payload:", payload);
      const room = await ensureRoomByTableId(payload.tableId);
      ensureManagedRoom(room, identity);
      const clubInfo = clubManager.getClubForTableById(payload.tableId);
      if (clubInfo && !requireClubAuth()) {
        return;
      }
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("Only active club members can sit at this table");
      }
      const managed = roomManager.getRoom(payload.tableId);
      if (!managed) throw new Error("Room not found");
      if (IDENTITY_DEBUG) {
        console.log("[SIT_DOWN] Identity/ownership check", {
          requesterUserId: identity.userId,
          ownerId: managed.ownership.ownerId,
          isHostOrCoHost: roomManager.isHostOrCoHost(payload.tableId, identity.userId),
        });
      }

      if (payload.seat < 1 || payload.seat > managed.settings.maxPlayers) {
        throw new Error(`Seat must be between 1 and ${managed.settings.maxPlayers}`);
      }

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

      await seatPlayerDirect({
        tableId: payload.tableId,
        seat: payload.seat,
        buyIn: payload.buyIn,
        userId: identity.userId,
        userName: payload.name?.slice(0, 32) || identity.displayName,
        socketId: socket.id,
        isRestore,
        approvedByUserId: identity.userId,
      });
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ SEAT REQUEST / APPROVE / REJECT ═══════════ */

  socket.on("seat_request", async (payload: { tableId: string; seat: number; buyIn: number; name?: string }) => {
    try {
      console.log("[SEAT_REQUEST] Received from", identity.userId, identity.displayName, "payload:", payload);
      
      const managed = roomManager.getRoom(payload.tableId);
      if (!managed) throw new Error("Room not found");

      if (payload.seat < 1 || payload.seat > managed.settings.maxPlayers) {
        throw new Error(`Seat must be between 1 and ${managed.settings.maxPlayers}`);
      }

      // Club membership gate
      const clubInfo = clubManager.getClubForTableById(payload.tableId);
      if (clubInfo && !requireClubAuth()) {
        return;
      }
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("Only active club members can request seats at this table");
      }

      if (IDENTITY_DEBUG) {
        console.log("[SEAT_REQUEST] Identity/ownership check", {
          requesterUserId: identity.userId,
          ownerId: managed.ownership.ownerId,
          isHostOrCoHost: roomManager.isHostOrCoHost(payload.tableId, identity.userId),
        });
      }

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

      // Hosts/co-hosts should never need approval, even if client emitted seat_request.
      if (roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        await seatPlayerDirect({
          tableId: payload.tableId,
          seat: payload.seat,
          buyIn: requestedStack,
          userId: identity.userId,
          userName: payload.name?.slice(0, 32) || identity.displayName,
          socketId: socket.id,
          isRestore,
          approvedByUserId: identity.userId,
        });
        socket.emit("seat_approved", { seat: payload.seat, buyIn: requestedStack });
        return;
      }

      if (clubInfo) {
        await seatPlayerDirect({
          tableId: payload.tableId,
          seat: payload.seat,
          buyIn: requestedStack,
          userId: identity.userId,
          userName: payload.name?.slice(0, 32) || identity.displayName,
          socketId: socket.id,
          isRestore,
          approvedByUserId: identity.userId,
        });
        socket.emit("seat_approved", { seat: payload.seat, buyIn: requestedStack });
        return;
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

  socket.on("approve_seat", async (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host/co-host can approve seat requests");
      }

      const request = pendingSeatRequests.get(payload.orderId);
      if (!request || request.tableId !== payload.tableId) {
        throw new Error("Seat request not found or expired");
      }
      pendingSeatRequests.delete(payload.orderId);

      await seatPlayerDirect({
        tableId: request.tableId,
        seat: request.seat,
        buyIn: request.buyIn,
        userId: request.userId,
        userName: request.userName,
        socketId: request.socketId,
        isRestore: request.isRestore,
        approvedByUserId: identity.userId,
      });

      // Notify the requester
      io.to(request.socketId).emit("seat_approved", { seat: request.seat, buyIn: request.buyIn });
      if (request.isRestore) {
        io.to(request.socketId).emit("system_message", { message: `Your previous room stack was restored (${request.buyIn}).` });
      }
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

  socket.on("deposit_request", async (payload: { tableId: string; amount: number }) => {
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
      const pendingForSeat = [...pendingRebuys.values()]
        .filter((deposit) => deposit.tableId === payload.tableId && deposit.seat === binding.seat)
        .reduce((sum, deposit) => sum + deposit.amount, 0);
      if (player.stack + pendingForSeat + payload.amount > buyInMax) {
        throw new Error(`Rebuy would exceed max buy-in (${buyInMax})`);
      }

      const clubInfo = clubManager.getClubForTableById(payload.tableId);
      if (clubInfo && !requireClubAuth()) {
        return;
      }
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("Only active club members can rebuy at this table");
      }
      if (clubInfo) {
        const walletBalance = await clubDataRepo.getWalletBalance(clubInfo.clubId, identity.userId, "chips");
        const pendingForUser = [...pendingRebuys.values()]
          .filter((deposit) => deposit.tableId === payload.tableId && deposit.userId === identity.userId)
          .reduce((sum, deposit) => sum + deposit.amount, 0);
        if (walletBalance < payload.amount + pendingForUser) {
          throw new Error(`Club has insufficient funds (${walletBalance}) for rebuy ${payload.amount}`);
        }
      }

      const orderId = randomUUID();
      const deposit: RebuyRequest = {
        orderId, tableId: payload.tableId, seat: binding.seat,
        userId: identity.userId, userName: identity.displayName,
        amount: payload.amount, approved: false, createdAt: Date.now(),
      };
      pendingRebuys.set(orderId, deposit);

      // Club table rebuys are hostless: auto-approved for active members.
      const autoApprove = !!clubInfo || roomManager.isHostOrCoHost(payload.tableId, identity.userId);
      if (autoApprove) {
        deposit.approved = true;
        socket.emit("system_message", { message: `Rebuy of ${payload.amount} approved — credited at next hand start.` });
        io.to(payload.tableId).emit("system_message", {
          message: `${identity.displayName} (Seat ${binding.seat}) rebuy approved: ${payload.amount} (auto)`,
        });
      } else {
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
        socket.emit("system_message", { message: `Rebuy request of ${payload.amount} sent to host for approval` });
      }
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("approve_deposit", (payload: { tableId: string; orderId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) throw new Error("Only host/co-host can approve deposits");
      const deposit = pendingRebuys.get(payload.orderId);
      if (!deposit || deposit.tableId !== payload.tableId) throw new Error("Rebuy request not found");

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
      const deposit = pendingRebuys.get(payload.orderId);
      if (!deposit || deposit.tableId !== payload.tableId) throw new Error("Rebuy request not found");
      pendingRebuys.delete(payload.orderId);

      const sid = socketIdBySeat(payload.tableId, deposit.seat);
      if (sid) io.to(sid).emit("system_message", { message: "Your rebuy request was declined by the host" });
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  // Host adds chips to a bot player
  socket.on("bot_add_chips", (payload: { tableId: string; seat: number; amount: number }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only host/co-host can add chips to bots");
      }
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("Table not found");

      const state = table.getPublicState();
      const player = state.players.find((p) => p.seat === payload.seat);
      if (!player) throw new Error("No player at that seat");

      const botIds = getBotUserIds(payload.tableId);
      if (!botIds.has(player.userId)) {
        throw new Error("Target player is not a bot");
      }
      if (payload.amount <= 0) throw new Error("Amount must be positive");

      const managed = roomManager.getRoom(payload.tableId);
      if (managed) {
        const { buyInMax } = managed.settings;
        if (player.stack + payload.amount > buyInMax) {
          throw new Error(`Adding chips would exceed max buy-in (${buyInMax})`);
        }
      }

      table.addStack(payload.seat, payload.amount);

      io.to(payload.tableId).emit("system_message", {
        message: `Host added ${payload.amount} chips to ${player.name} (Seat ${payload.seat})`,
      });
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("stand_up", async (payload: { tableId: string; seat?: number }) => {
    const table = tables.get(payload.tableId);
    if (!table) return;

    const binding = socketSeat.get(socket.id);
    if (!binding || binding.tableId !== payload.tableId) {
      socket.emit("error_event", { message: "You can only stand up from your own seat" });
      return;
    }

    const seatNum = binding.seat;

    // Defer if hand is active — mark as pending and process after hand ends
    if (table.isHandActive()) {
      let pending = pendingStandUps.get(payload.tableId);
      if (!pending) { pending = new Set(); pendingStandUps.set(payload.tableId, pending); }
      pending.add(seatNum);
      socket.emit("system_message", { message: "Leaving after this hand." });
      broadcastSnapshot(payload.tableId);
      return;
    }

    await standUpPlayer(payload.tableId, seatNum, "Stood up");
  });

  /* ═══════════ SIT OUT / SIT IN ═══════════ */

  socket.on("sit_out", (payload: { tableId: string }) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("Table not found");
      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId) throw new Error("Not seated at this table");

      const state = table.getPublicState();
      const player = state.players.find((p) => p.seat === binding.seat);
      if (!player) throw new Error("Player not found");
      if (player.status === "sitting_out") throw new Error("Already sitting out");

      // If hand is active and player is in the hand, defer until hand ends
      if (table.isHandActive() && player.inHand) {
        // Mark as pending sit-out via player status change at hand boundary
        table.setPlayerStatus(binding.seat, "sitting_out");
        socket.emit("system_message", { message: "You will sit out after this hand." });
      } else {
        table.setPlayerStatus(binding.seat, "sitting_out");
        socket.emit("system_message", { message: "You are now sitting out." });
        io.to(payload.tableId).emit("system_message", { message: `${identity.displayName} is sitting out.` });
      }

      const room = roomManager.getRoom(payload.tableId);
      if (room) {
        roomManager.addLog(room, "PLAYER_SAT_OUT", {
          actorId: identity.userId,
          actorName: identity.displayName,
          message: `${identity.displayName} sat out`,
        });
      }
      broadcastSnapshot(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("sit_in", (payload: { tableId: string }) => {
    try {
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("Table not found");
      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId) throw new Error("Not seated at this table");

      const state = table.getPublicState();
      const player = state.players.find((p) => p.seat === binding.seat);
      if (!player) throw new Error("Player not found");
      if (player.status === "active") throw new Error("Already active");

      table.setPlayerStatus(binding.seat, "active");
      table.resetConsecutiveTimeouts(binding.seat);
      // Also reset room-manager timeout count
      const room = roomManager.getRoom(payload.tableId);
      if (room) {
        room.timeoutCounts.set(identity.userId, 0);
        roomManager.addLog(room, "SYSTEM_MESSAGE", {
          actorId: identity.userId,
          actorName: identity.displayName,
          message: `${identity.displayName} is back`,
        });
      }
      socket.emit("system_message", { message: "You are back in the game." });
      io.to(payload.tableId).emit("system_message", { message: `${identity.displayName} is back.` });
      broadcastSnapshot(payload.tableId);
      scheduleAutoDealIfNeeded(payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("start_hand", async (payload: { tableId: string }) => {
    try {
      await ensureRoomByTableId(payload.tableId);
      const binding = socketSeat.get(socket.id);
      const isSeatedAtTable = Boolean(binding && binding.tableId === payload.tableId);
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId) && !isSeatedAtTable) {
        throw new Error("Only seated players or hosts can start a hand");
      }

      clearAutoDealSchedule(payload.tableId);
      await startHandFlow(payload.tableId, identity.userId, "manual");
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
        // Explicitly trigger advice on street change so turn/river is never missed
        if (newState.actorSeat != null) {
          setImmediate(() => {
            void emitAdviceIfNeeded(payload.tableId, newState, "street_changed").catch((err: unknown) => {
              console.warn("[advice] street_changed push error:", (err as Error).message);
            });
          });
        }
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

  // ── Post-hand show cards (after hand ended) ──
  socket.on("show_hand_post", (payload: { tableId: string; seat: number }) => {
    try {
      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
        throw new Error("You can only show your own hand");
      }

      const savedCards = lastHandHoleCards.get(payload.tableId);
      const cards = savedCards?.get(payload.seat);
      if (!cards) throw new Error("No saved cards to show");

      // Broadcast the reveal to everyone
      io.to(payload.tableId).emit("post_hand_reveal", {
        tableId: payload.tableId,
        seat: payload.seat,
        cards,
      });

      // Check if this seat has a pending 7-2 bounty claim
      const claim = pendingBountyClaim.get(payload.tableId);
      if (claim && claim.winnerSeat === payload.seat) {
        applySevenTwoBounty(payload.tableId, claim);
      }
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  // ── Explicit 7-2 bounty claim (dedicated button) ──
  socket.on("claim_seven_two_bounty", (payload: { tableId: string; seat: number }) => {
    try {
      const binding = socketSeat.get(socket.id);
      if (!binding || binding.tableId !== payload.tableId || binding.seat !== payload.seat) {
        throw new Error("You can only claim your own bounty");
      }

      const claim = pendingBountyClaim.get(payload.tableId);
      if (!claim || claim.winnerSeat !== payload.seat) {
        throw new Error("No pending bounty claim for this seat");
      }

      applySevenTwoBounty(payload.tableId, claim);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  const handleRunPreferenceSubmit = (payload: { tableId: string; handId: string; runCount: 1 | 2 | 3 }): void => {
    const table = tables.get(payload.tableId);
    if (!table) throw new Error("table not found");
    const liveState = table.getPublicState();
    if (!liveState.handId || liveState.handId !== payload.handId) {
      throw new Error("stale or invalid handId");
    }

    const pending = pendingRunCountDecisions.get(payload.tableId);
    if (!pending || pending.handId !== payload.handId) {
      throw new Error("no pending run count decision");
    }

    const binding = socketSeat.get(socket.id);
    if (!binding || binding.tableId !== payload.tableId) {
      throw new Error("player seat not found");
    }

    if (!pending.eligiblePlayers.some((player) => player.seat === binding.seat)) {
      throw new Error("seat is not eligible for run count decision");
    }

    if (pending.preferencesBySeat[binding.seat] != null) {
      throw new Error("run count choice already submitted");
    }

    const vote: RunCountPreference = payload.runCount === 3 ? 3 : payload.runCount === 2 ? 2 : 1;

    if (binding.seat === pending.underdogSeat) {
      pending.preferencesBySeat[binding.seat] = vote;
      pending.targetRunCount = vote;
      for (const player of pending.eligiblePlayers) {
        if (player.seat !== pending.underdogSeat) {
          pending.preferencesBySeat[player.seat] = null;
        }
      }
      pendingRunCountDecisions.set(payload.tableId, pending);
      emitAllInLocked(payload.tableId, pending);

      if (vote === 1 || pending.eligiblePlayers.length <= 1) {
        finalizeRunCountDecision(payload.tableId, table, pending, binding.seat, false, 1);
      }
      return;
    }

    if (pending.targetRunCount == null) {
      throw new Error("Waiting for underdog run-count choice");
    }

    if (pending.targetRunCount === 1) {
      throw new Error("Run count already resolved to once");
    }

    pending.preferencesBySeat[binding.seat] = vote;
    pendingRunCountDecisions.set(payload.tableId, pending);
    emitAllInLocked(payload.tableId, pending);

    if (vote !== pending.targetRunCount) {
      finalizeRunCountDecision(payload.tableId, table, pending, binding.seat, false, 1);
      return;
    }

    const allOpponentsSubmitted = pending.eligiblePlayers
      .filter((player) => player.seat !== pending.underdogSeat)
      .every((player) => pending.preferencesBySeat[player.seat] != null);
    if (!allOpponentsSubmitted) return;

    finalizeRunCountDecision(payload.tableId, table, pending, binding.seat, false, pending.targetRunCount);
  };

  socket.on("submit_run_preference", (payload: { tableId: string; handId: string; runCount: 1 | 2 | 3 }) => {
    try {
      handleRunPreferenceSubmit(payload);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  // Backward-compatible alias for older clients.
  socket.on("run_count_submit", (payload: { tableId: string; handId: string; runCount: 1 | 2 | 3 }) => {
    try {
      handleRunPreferenceSubmit(payload);
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
      const room = roomManager.getRoom(payload.tableId);
      if (!room) throw new Error("Room not found");
      const table = tables.get(payload.tableId);
      const currentPlayers = table ? table.getPublicState().players : [];
      const roomStats = getRoomSessionStats(payload.tableId, false);
      const entries: Array<{ seat: number | null; userId: string; name: string; totalBuyIn: number; totalCashOut: number; currentStack: number; net: number; handsPlayed: number; status: string }> = [];

      if (roomStats) {
        for (const [uid, entry] of roomStats.entries()) {
          const seated = currentPlayers.find((p) => p.userId === uid);
          const currentStack = seated ? seated.stack : 0;
          entries.push({
            seat: seated?.seat ?? null,
            userId: entry.userId,
            name: entry.name,
            totalBuyIn: entry.totalBuyIn,
            totalCashOut: entry.totalCashOut,
            currentStack,
            net: currentStack + entry.totalCashOut - entry.totalBuyIn,
            handsPlayed: entry.handsPlayed,
            status: seated ? "seated" : "away",
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
      // Prevent auto-restore on reconnect — player explicitly chose to leave
      rejoinInfo.delete(identity.userId);
      socket.emit("system_message", { message: "Leaving after this hand." });
      touchLocalRoom(payload.tableId);
      broadcastSnapshot(payload.tableId);
      return;
    }

    if (binding && binding.tableId === payload.tableId) {
      await standUpPlayer(payload.tableId, binding.seat, "Left table");
    }

    // Prevent auto-restore on reconnect — player explicitly chose to leave
    rejoinInfo.delete(identity.userId);
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

  socket.on("request_table_snapshot", async (payload: { tableId: string }) => {
    try {
      if (!payload?.tableId) {
        throw new Error("tableId is required");
      }
      const room = await ensureRoomByTableId(payload.tableId);
      ensureManagedRoom(room, identity);
      const clubInfo = clubManager.getClubForTableById(payload.tableId);
      if (clubInfo && !requireClubAuth()) {
        return;
      }
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("Club members only: this table is restricted to active club members.");
      }
      emitHydratedSnapshot(socket.id, payload.tableId);
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  socket.on("request_room_state", async (payload: { tableId: string }) => {
    try {
      if (!payload?.tableId) {
        throw new Error("tableId is required");
      }
      const clubInfo = clubManager.getClubForTableById(payload.tableId);
      if (clubInfo && !requireClubAuth()) {
        return;
      }
      if (clubInfo && !clubManager.isActiveMember(clubInfo.clubId, identity.userId)) {
        throw new Error("Club members only: this table is restricted to active club members.");
      }
      const state = roomManager.getFullState(payload.tableId);
      if (state) socket.emit("room_state_update", withClubRoomStateMetadata(state, payload.tableId, identity.userId));
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
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

      // Sync bot seats if botSeats or botBuyIn changed
      if ((payload.settings.botSeats !== undefined || payload.settings.botBuyIn !== undefined) && managed) {
        const room = roomsByTableId.get(payload.tableId);
        if (room) {
          syncBots(
            payload.tableId,
            room.roomCode,
            managed.settings.bigBlind,
            managed.settings.botSeats,
            runtimeConfig.port,
            managed.settings.buyInMin,
            managed.settings.buyInMax,
            managed.settings.botBuyIn,
          );
        }
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

  // Bomb Pot manual trigger: host queues next hand as bomb pot
  socket.on("queue_bomb_pot", (payload: { tableId: string }) => {
    try {
      if (!roomManager.isHostOrCoHost(payload.tableId, identity.userId)) {
        throw new Error("Only the host or co-host can trigger bomb pots");
      }
      const table = tables.get(payload.tableId);
      if (!table) throw new Error("Table not found");
      table.queueBombPotNextHand();
      io.to(payload.tableId).emit("bomb_pot_queued", { queuedBy: identity.displayName });
      broadcastSnapshot(payload.tableId);
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
          clearPendingRunCountDecision(payload.tableId);
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
          clearPendingRunCountDecision(payload.tableId);
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
      const clubInfo = getClubInfoForTableId(payload.tableId);
      if (clubInfo) {
        if (!requireClubAuth()) {
          return;
        }
        // Club tables: allow club owner/admin OR room owner
        if (!isClubOwnerOrAdmin(clubInfo.clubId, identity.userId) && !roomManager.isOwner(payload.tableId, identity.userId)) {
          throw new Error("Only club owner/admin or room host can close this table");
        }
      } else {
        // Regular rooms: only room owner
        if (!roomManager.isOwner(payload.tableId, identity.userId)) {
          throw new Error("Only the host can close the room");
        }
      }

      logInfo({
        event: "room.close.requested",
        tableId: payload.tableId,
        userId: identity.userId,
        message: identity.displayName,
      });

      // For club tables, also update club manager state
      if (clubInfo) {
        clubManager.closeTable(clubInfo.clubId, identity.userId, clubInfo.clubTableId);
      }

      // Stop auto-deal and timers
      clearAutoDealSchedule(payload.tableId);
      clearShowdownDecisionTimeout(payload.tableId);
      removeAllBots(payload.tableId);
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
      clearPendingRunCountDecision(payload.tableId);
      for (const [orderId, request] of pendingSeatRequests.entries()) {
        if (request.tableId === payload.tableId) pendingSeatRequests.delete(orderId);
      }
      for (const [orderId, deposit] of pendingRebuys.entries()) {
        if (deposit.tableId === payload.tableId) pendingRebuys.delete(orderId);
      }
      tables.delete(payload.tableId);
      tableSnapshotVersions.delete(payload.tableId);
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

      // Refresh club detail for members so the table list updates
      if (clubInfo) {
        void emitClubDetail(socket.id, clubInfo.clubId, identity.userId);
      }
    } catch (error) {
      socket.emit("error_event", { message: (error as Error).message });
    }
  });

  /* ═══════════ CLUBS ═══════════ */

  socket.on("club_create", async (payload: ClubCreatePayload) => {
    try {
      if (!requireClubAuth()) return;
      logInfo({ event: "club_create.start", userId: identity.userId, name: payload.name });
      const club = await clubManager.createClub({
        ownerUserId: identity.userId,
        ownerDisplayName: identity.displayName,
        name: payload.name,
        description: payload.description,
        visibility: payload.visibility,
        requireApprovalToJoin: payload.requireApprovalToJoin,
        badgeColor: payload.badgeColor,
      });
      logInfo({ event: "club_create.success", clubId: club.id, code: club.code, userId: identity.userId });
      socket.emit("club_created", { club });
      // Refresh club list for the user
      socket.emit("club_list", { clubs: clubManager.listMyClubs(identity.userId) });
    } catch (error) {
      logError({ event: "club_create.failed", userId: identity.userId, message: (error as Error).message });
      socket.emit("club_error", { code: "CREATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_update", (payload: ClubUpdatePayload) => {
    try {
      if (!requireClubAuth()) return;
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
      if (!requireClubAuth()) {
        console.log("[clubs] club_list_my_clubs denied for", identity.userId, "(not club-authenticated)");
        return;
      }
      const clubs = clubManager.listMyClubs(identity.userId);
      console.log("[clubs] club_list_my_clubs →", identity.userId, "clubs:", clubs.length);
      socket.emit("club_list", { clubs });
    } catch (error) {
      console.warn("[clubs] club_list_my_clubs error for", identity.userId, (error as Error).message);
      socket.emit("club_error", { code: "LIST_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_get_detail", async (payload: { clubId: string }) => {
    try {
      if (!requireClubAuth()) return;
      const result = await buildClubDetailPayload(payload.clubId, identity.userId);
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
      if (!requireClubAuth()) return;
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
      if (!requireClubAuth()) return;
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
      if (!requireClubAuth()) return;
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
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "REJECT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_invite_create", (payload: ClubInviteCreatePayload) => {
    try {
      if (!requireClubAuth()) return;
      const invite = clubManager.createInvite(payload.clubId, identity.userId, payload.maxUses, payload.expiresInHours);
      if (!invite) {
        socket.emit("club_error", { code: "INVITE_DENIED", message: "Cannot create invite — insufficient permissions" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "INVITE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_invite_revoke", (payload: ClubInviteRevokePayload) => {
    try {
      if (!requireClubAuth()) return;
      const ok = clubManager.revokeInvite(payload.clubId, identity.userId, payload.inviteId);
      if (!ok) {
        socket.emit("club_error", { code: "REVOKE_DENIED", message: "Cannot revoke invite" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "REVOKE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_update_role", (payload: ClubMemberUpdateRolePayload) => {
    try {
      if (!requireClubAuth()) return;
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
      if (!requireClubAuth()) return;
      const ok = clubManager.kickMember(payload.clubId, identity.userId, payload.userId);
      if (!ok) {
        socket.emit("club_error", { code: "KICK_DENIED", message: "Cannot kick member" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "KICK_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_ban", (payload: ClubMemberBanPayload) => {
    try {
      if (!requireClubAuth()) return;
      const ok = clubManager.banMember(payload.clubId, identity.userId, payload.userId, payload.reason, payload.expiresInHours);
      if (!ok) {
        socket.emit("club_error", { code: "BAN_DENIED", message: "Cannot ban member" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "BAN_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_member_unban", (payload: ClubMemberUnbanPayload) => {
    try {
      if (!requireClubAuth()) return;
      const ok = clubManager.unbanMember(payload.clubId, identity.userId, payload.userId);
      if (!ok) {
        socket.emit("club_error", { code: "UNBAN_DENIED", message: "Cannot unban member" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "UNBAN_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_ruleset_create", (payload: ClubRulesetCreatePayload) => {
    try {
      if (!requireClubAuth()) return;
      const ruleset = clubManager.createRuleset(payload.clubId, identity.userId, payload.name, payload.rules, payload.isDefault);
      if (!ruleset) {
        socket.emit("club_error", { code: "RULESET_DENIED", message: "Cannot create ruleset — insufficient permissions" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "RULESET_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_ruleset_update", (payload: ClubRulesetUpdatePayload) => {
    try {
      if (!requireClubAuth()) return;
      const ruleset = clubManager.updateRuleset(payload.clubId, identity.userId, payload.rulesetId, {
        name: payload.name,
        rules: payload.rules,
      });
      if (!ruleset) {
        socket.emit("club_error", { code: "RULESET_UPDATE_DENIED", message: "Cannot update ruleset" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "RULESET_UPDATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_ruleset_set_default", (payload: ClubRulesetSetDefaultPayload) => {
    try {
      if (!requireClubAuth()) return;
      const ok = clubManager.setDefaultRuleset(payload.clubId, identity.userId, payload.rulesetId);
      if (!ok) {
        socket.emit("club_error", { code: "RULESET_DEFAULT_DENIED", message: "Cannot set default ruleset" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "RULESET_DEFAULT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_create", async (payload: ClubTableCreatePayload) => {
    try {
      if (!requireClubAuth()) return;
      const result = clubManager.createTable(payload.clubId, identity.userId, payload.name, payload.config, payload.templateRulesetId);
      if (!result) {
        socket.emit("club_error", { code: "TABLE_DENIED", message: "Cannot create table — insufficient permissions" });
        return;
      }

      const { clubTable, rules } = result;

      // Create runtime room using clubTable.id as the room's tableId (1:1 mapping)
      ensureClubTableRoom(payload.clubId, clubTable.id);

      socket.emit("club_table_created", {
        clubId: payload.clubId,
        table: clubTable,
      });

      // Refresh club detail
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_CREATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_list", async (payload: { clubId: string }) => {
    try {
      if (!requireClubAuth()) return;
      const detail = await buildClubDetailPayload(payload.clubId, identity.userId);
      if (!detail) {
        socket.emit("club_error", { code: "TABLE_LIST_DENIED", message: "Not a member" });
        return;
      }
      socket.emit("club_detail", detail);
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_LIST_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_update", async (payload: ClubTableUpdatePayload) => {
    try {
      if (!requireClubAuth()) return;
      if (!isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "TABLE_UPDATE_DENIED", message: "Only owner/admin can update tables" });
        return;
      }

      const currentTable = clubManager.getClubTable(payload.clubId, payload.tableId);
      if (!currentTable || currentTable.status === "closed") {
        socket.emit("club_error", { code: "TABLE_UPDATE_DENIED", message: "Table not found" });
        return;
      }

      const detailForRules = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (!detailForRules) {
        socket.emit("club_error", { code: "TABLE_UPDATE_DENIED", message: "Not a club member" });
        return;
      }

      // Pre-check: prevent update while hand is active or reducing seats below occupancy
      const serverTableId = payload.tableId; // clubTable.id = room tableId
      const liveTable = tables.get(serverTableId);
      if (liveTable?.isHandActive()) {
        socket.emit("club_error", { code: "TABLE_UPDATE_DENIED", message: "Cannot update table while a hand is active" });
        return;
      }
      const currentRules = clubManager.getRulesForTable(payload.clubId, payload.tableId);
      if (currentRules && payload.config?.maxSeats != null) {
        const occupiedSeats = liveTable?.getPublicState().players.length ?? 0;
        if (payload.config.maxSeats < occupiedSeats) {
          socket.emit("club_error", {
            code: "TABLE_UPDATE_DENIED",
            message: `Cannot reduce seats below occupied count (${occupiedSeats})`,
          });
          return;
        }
      }

      const result = clubManager.updateTable(payload.clubId, identity.userId, payload.tableId, {
        name: payload.name,
        config: payload.config,
      });
      if (!result) {
        socket.emit("club_error", { code: "TABLE_UPDATE_DENIED", message: "Cannot update table" });
        return;
      }

      // Sync runtime room with updated rules
      const managed = roomManager.getRoom(serverTableId);
      const roomInfo = roomsByTableId.get(serverTableId);
      const club = clubManager.getClub(payload.clubId);

      if (managed) {
        roomManager.updateSettings(serverTableId, {
          gameType: result.rules.extras.gameType,
          maxPlayers: result.rules.maxSeats,
          smallBlind: result.rules.stakes.smallBlind,
          bigBlind: result.rules.stakes.bigBlind,
          buyInMin: result.rules.buyIn.minBuyIn,
          buyInMax: result.rules.buyIn.maxBuyIn,
          actionTimerSeconds: result.rules.time.actionTimeSec,
          timeBankSeconds: result.rules.time.timeBankSec,
          disconnectGracePeriod: result.rules.time.disconnectGraceSec,
          autoStartNextHand: result.rules.dealing.autoStartNextHand && result.rules.dealing.autoDealEnabled,
          minPlayersToStart: Math.max(2, Math.min(result.rules.maxSeats, result.rules.dealing.minPlayersToStart ?? 2)),
          spectatorAllowed: result.rules.moderation.allowSpectators,
          runItTwice: result.rules.runit.allowRunItTwice,
          runItTwiceMode: result.rules.runit.allowRunItTwice ? "ask_players" : "off",
          straddleAllowed: result.rules.extras.straddleAllowed,
          bombPotEnabled: result.rules.extras.bombPotEnabled,
          rabbitHunting: result.rules.extras.rabbitHuntEnabled,
          sevenTwoBounty: result.rules.extras.sevenTwoBounty,
          visibility: "private",
        }, identity.userId, identity.displayName);
      }

      if (roomInfo) {
        roomInfo.roomName = `${club?.name ?? "Club"} — ${result.table.name}`;
        roomInfo.smallBlind = result.rules.stakes.smallBlind;
        roomInfo.bigBlind = result.rules.stakes.bigBlind;
        roomInfo.maxPlayers = result.rules.maxSeats;
        roomInfo.isPublic = false;
        roomInfo.updatedAt = new Date().toISOString();
        if (managed) {
          managed.roomName = roomInfo.roomName;
        }
        supabase.upsertRoom(roomInfo).catch((e) => logWarn({
          event: "club_table.update.persist_failed",
          tableId: serverTableId,
          message: (e as Error).message,
        }));
      }

      if (liveTable) {
        liveTable.updateBlindStructure(result.rules.stakes.smallBlind, result.rules.stakes.bigBlind, managed?.settings.ante ?? 0);
        applyRoomVariantSettings(serverTableId, liveTable);
        broadcastSnapshot(serverTableId);
      }

      for (const [sid, ident] of socketIdentity.entries()) {
        if (!clubManager.isActiveMember(payload.clubId, ident.userId)) continue;
        io.to(sid).emit("club_table_updated", { clubId: payload.clubId, table: result.table });
      }

      await emitClubDetail(socket.id, payload.clubId, identity.userId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_UPDATE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_close", async (payload: ClubTableClosePayload) => {
    try {
      if (!requireClubAuth()) return;
      const tableBeforeClose = clubManager.getClubTable(payload.clubId, payload.tableId);
      const ok = clubManager.closeTable(payload.clubId, identity.userId, payload.tableId);
      if (!ok) {
        socket.emit("club_error", { code: "TABLE_CLOSE_DENIED", message: "Cannot close table" });
        return;
      }

      // Closing a persistent club table also closes its runtime room.
      // clubTable.id = room tableId (direct 1:1 mapping)
      const serverTableId = payload.tableId;
      if (roomsByTableId.has(serverTableId)) {
        clearAutoDealSchedule(serverTableId);
        clearShowdownDecisionTimeout(serverTableId);
        roomManager.endGame(serverTableId, identity.userId, identity.displayName);
        io.to(serverTableId).emit("room_closed", { tableId: serverTableId, reason: "Club table closed" });

        const roomSockets = io.sockets.adapter.rooms.get(serverTableId);
        if (roomSockets) {
          for (const sid of roomSockets) {
            const sock = io.sockets.sockets.get(sid);
            if (sock) sock.leave(serverTableId);
          }
        }

        for (const [sid, binding] of socketSeat.entries()) {
          if (binding.tableId !== serverTableId) continue;
          socketSeat.delete(sid);
          const sock = io.sockets.sockets.get(sid);
          if (sock) sock.leave(serverTableId);
          io.to(sid).emit("left_table", { tableId: serverTableId });
        }

        const room = roomsByTableId.get(serverTableId);
        if (room) {
          roomCodeToTableId.delete(room.roomCode);
          sessionStatsByRoomCode.delete(room.roomCode);
          roomsByTableId.delete(serverTableId);
        }
        pendingStandUps.delete(serverTableId);
        pendingTableLeaves.delete(serverTableId);
        pendingPause.delete(serverTableId);
        clearPendingRunCountDecision(serverTableId);
        for (const [orderId, request] of pendingSeatRequests.entries()) {
          if (request.tableId === serverTableId) pendingSeatRequests.delete(orderId);
        }
        for (const [orderId, deposit] of pendingRebuys.entries()) {
          if (deposit.tableId === serverTableId) pendingRebuys.delete(orderId);
        }
        tables.delete(serverTableId);
        tableSnapshotVersions.delete(serverTableId);
        roomManager.deleteRoom(serverTableId);

        closeRoomSessionIfOpen(serverTableId, "club_table_close").catch(() => {});
        supabase.touchRoom(serverTableId, "CLOSED").catch(() => {});
      }

      await emitClubDetail(socket.id, payload.clubId, identity.userId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_CLOSE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_table_pause", (payload: ClubTablePausePayload) => {
    try {
      if (!requireClubAuth()) return;
      // Pause is deferred until hand end (enforced by rules)
      const ok = clubManager.pauseTable(payload.clubId, identity.userId, payload.tableId);
      if (!ok) {
        socket.emit("club_error", { code: "TABLE_PAUSE_DENIED", message: "Cannot pause table" });
        return;
      }
      void emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_PAUSE_FAILED", message: (error as Error).message });
    }
  });

  /* ═══════════ CLUB TABLE JOIN ═══════════ */

  socket.on("club_table_join", async (payload: ClubTableJoinPayload) => {
    try {
      if (!requireClubAuth()) return;
      if (!clubManager.isActiveMember(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "TABLE_JOIN_DENIED", message: "Only active club members can join tables" });
        return;
      }

      const tableId = ensureClubTableRoom(payload.clubId, payload.tableId);
      if (!tableId) {
        socket.emit("club_error", { code: "TABLE_JOIN_DENIED", message: "Table not found or closed" });
        return;
      }

      const room = roomsByTableId.get(tableId);
      if (!room) {
        socket.emit("club_error", { code: "TABLE_JOIN_DENIED", message: "Room not available" });
        return;
      }

      if (roomManager.isBanned(tableId, identity.userId)) {
        socket.emit("error_event", { message: "You are banned from this table" });
        return;
      }

      socket.join(tableId);
      createTableIfNeeded(room);
      maybeCheckRoomEmpty(tableId, currentPlayerCount(tableId) + 1);

      supabase.touchRoom(tableId, "OPEN").catch(() => {});
      openRoomSessionIfNeeded(tableId, "club_table_join").catch(() => {});

      const club = clubManager.getClub(payload.clubId);
      socket.emit("room_joined", {
        tableId,
        roomCode: tableId,
        roomName: room.roomName,
      });
      socket.emit("club_table_joined", {
        tableId,
        clubId: payload.clubId,
        roomName: room.roomName,
      });

      emitHydratedSnapshot(socket.id, tableId);
      const fullState = roomManager.getFullState(tableId);
      if (fullState) socket.emit("room_state_update", withClubRoomStateMetadata(fullState, tableId, identity.userId));
      emitPresence(tableId);
      void emitLobbySnapshot();
    } catch (error) {
      socket.emit("club_error", { code: "TABLE_JOIN_FAILED", message: (error as Error).message });
    }
  });

  /* ═══════════ CLUB CREDITS ═══════════ */

  socket.on("club_wallet_balance_get", async (payload: { clubId: string; userId?: string; currency?: string }) => {
    try {
      if (!requireClubAuth()) return;
      if (!clubManager.isActiveMember(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "WALLET_DENIED", message: "Not a club member" });
        return;
      }

      const targetUserId = payload.userId ?? identity.userId;
      if (targetUserId !== identity.userId && !isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "WALLET_DENIED", message: "Only admins can view other members' credits" });
        return;
      }
      if (!clubManager.getMember(payload.clubId, targetUserId)) {
        socket.emit("club_error", { code: "WALLET_DENIED", message: "Target member not found" });
        return;
      }

      const currency = payload.currency ?? "chips";
      const balance = await clubDataRepo.getWalletBalance(payload.clubId, targetUserId, currency);
      clubManager.setMemberBalance(payload.clubId, targetUserId, balance);
      socket.emit("club_wallet_balance", { balance: { clubId: payload.clubId, userId: targetUserId, currency, balance } });
    } catch (error) {
      socket.emit("club_error", { code: "WALLET_BALANCE_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_wallet_transactions_list", async (payload: { clubId: string; userId?: string; currency?: string; limit?: number; offset?: number }) => {
    try {
      if (!requireClubAuth()) return;
      if (!clubManager.isActiveMember(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "WALLET_DENIED", message: "Not a club member" });
        return;
      }
      const targetUserId = payload.userId ?? identity.userId;
      if (targetUserId !== identity.userId && !isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "WALLET_DENIED", message: "Only admins can view other members' ledger" });
        return;
      }
      const currency = payload.currency ?? "chips";
      const limit = Math.max(1, Math.min(payload.limit ?? 50, 200));
      const offset = Math.max(0, payload.offset ?? 0);
      const transactions: ClubWalletTransaction[] = await clubDataRepo.listWalletTxs(
        payload.clubId,
        targetUserId,
        currency,
        limit,
        offset,
      );
      socket.emit("club_wallet_transactions", {
        clubId: payload.clubId,
        userId: targetUserId,
        currency,
        limit,
        offset,
        transactions,
      });
    } catch (error) {
      socket.emit("club_error", { code: "WALLET_TX_LIST_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_wallet_admin_deposit", async (payload: { clubId: string; userId: string; amount: number; currency?: string; note?: string; idempotencyKey?: string }) => {
    try {
      if (!requireClubAuth()) return;
      if (!isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Only owner/admin can deposit" });
        return;
      }
      if (!clubManager.isActiveMember(payload.clubId, payload.userId)) {
        socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Target is not an active member" });
        return;
      }
      const amount = Math.trunc(payload.amount);
      if (amount <= 0) {
        socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Amount must be positive" });
        return;
      }

      const tx = await appendWalletTx({
        clubId: payload.clubId,
        userId: payload.userId,
        type: "admin_grant",
        amount,
        currency: payload.currency ?? "chips",
        createdBy: identity.userId,
        note: payload.note ?? "Admin deposit",
        metaJson: { adminUserId: identity.userId },
        idempotencyKey: payload.idempotencyKey ?? null,
      });

      await clubDataRepo.appendAudit({
        clubId: payload.clubId,
        actorUserId: identity.userId,
        actionType: "wallet_admin_deposit",
        payloadJson: {
          targetUserId: payload.userId,
          amount,
          currency: payload.currency ?? "chips",
          note: payload.note ?? "",
          txId: tx.tx.id,
        },
        createdAt: new Date().toISOString(),
      });

      await emitWalletBalanceToUser(payload.clubId, payload.userId, tx.newBalance, payload.currency ?? "chips");
      socket.emit("system_message", { message: `Granted ${amount} credits to member` });
      await emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "WALLET_ADMIN_DEPOSIT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_wallet_admin_adjust", async (payload: { clubId: string; userId: string; amount: number; currency?: string; note?: string; idempotencyKey?: string }) => {
    try {
      if (!requireClubAuth()) return;
      if (!isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Only owner/admin can adjust balances" });
        return;
      }
      if (!clubManager.isActiveMember(payload.clubId, payload.userId)) {
        socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Target is not an active member" });
        return;
      }

      const amount = Math.trunc(payload.amount);
      if (amount === 0) {
        socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Adjustment amount cannot be zero" });
        return;
      }

      const currency = payload.currency ?? "chips";
      if (amount < 0) {
        const currentBalance = await clubDataRepo.getWalletBalance(payload.clubId, payload.userId, currency);
        if (currentBalance + amount < 0) {
          socket.emit("club_error", { code: "WALLET_ADMIN_DENIED", message: "Insufficient credits for adjustment" });
          return;
        }
      }

      const tx = await appendWalletTx({
        clubId: payload.clubId,
        userId: payload.userId,
        type: "adjustment",
        amount,
        currency,
        createdBy: identity.userId,
        note: payload.note ?? "Admin adjustment",
        metaJson: { adminUserId: identity.userId },
        idempotencyKey: payload.idempotencyKey ?? null,
      });

      await clubDataRepo.appendAudit({
        clubId: payload.clubId,
        actorUserId: identity.userId,
        actionType: "wallet_admin_adjust",
        payloadJson: {
          targetUserId: payload.userId,
          amount,
          currency,
          note: payload.note ?? "",
          txId: tx.tx.id,
        },
        createdAt: new Date().toISOString(),
      });

      await emitWalletBalanceToUser(payload.clubId, payload.userId, tx.newBalance, currency);
      socket.emit("system_message", { message: `Adjusted member credits by ${amount}` });
      await emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "WALLET_ADMIN_ADJUST_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_leaderboard_get", async (payload: { clubId: string; timeRange?: ClubLeaderboardRange; metric?: ClubLeaderboardMetric; limit?: number }) => {
    try {
      if (!requireClubAuth()) return;
      if (!clubManager.isActiveMember(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "LEADERBOARD_DENIED", message: "Not a club member" });
        return;
      }

      const timeRange: ClubLeaderboardRange =
        payload.timeRange === "day" ||
        payload.timeRange === "week" ||
        payload.timeRange === "month" ||
        payload.timeRange === "all"
          ? payload.timeRange
          : "week";
      const metric: ClubLeaderboardMetric = payload.metric === "hands" || payload.metric === "buyin" || payload.metric === "deposits"
        ? payload.metric
        : "net";
      const limit = Math.max(1, Math.min(payload.limit ?? 50, 200));

      const entries = await clubDataRepo.getClubLeaderboard(payload.clubId, timeRange, metric, limit);
      const myRow = entries.find((entry) => entry.userId === identity.userId);
      socket.emit("club_leaderboard", {
        clubId: payload.clubId,
        timeRange,
        metric,
        entries,
        myRank: myRow?.rank ?? null,
      });
    } catch (error) {
      socket.emit("club_error", { code: "LEADERBOARD_FAILED", message: (error as Error).message });
    }
  });

  // Backward compatibility aliases.
  socket.on("club_grant_credits", async (payload: { clubId: string; userId: string; amount: number; reason?: string }) => {
    try {
      if (!requireClubAuth()) return;
      if (!isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "GRANT_DENIED", message: "Only owner/admin can grant credits" });
        return;
      }
      if (!clubManager.isActiveMember(payload.clubId, payload.userId)) {
        socket.emit("club_error", { code: "GRANT_DENIED", message: "Target is not an active member" });
        return;
      }
      const amount = Math.trunc(payload.amount);
      if (amount <= 0) {
        socket.emit("club_error", { code: "GRANT_DENIED", message: "Amount must be positive" });
        return;
      }
      const tx = await appendWalletTx({
        clubId: payload.clubId,
        userId: payload.userId,
        type: "admin_grant",
        amount,
        currency: "chips",
        createdBy: identity.userId,
        note: payload.reason ?? "Legacy grant credits",
        metaJson: { legacyEvent: "club_grant_credits" },
      });
      await emitWalletBalanceToUser(payload.clubId, payload.userId, tx.newBalance, "chips");
      await emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "GRANT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_deduct_credits", async (payload: { clubId: string; userId: string; amount: number; reason?: string }) => {
    try {
      if (!requireClubAuth()) return;
      if (!isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "DEDUCT_DENIED", message: "Only owner/admin can deduct credits" });
        return;
      }
      if (!clubManager.isActiveMember(payload.clubId, payload.userId)) {
        socket.emit("club_error", { code: "DEDUCT_DENIED", message: "Target is not an active member" });
        return;
      }
      const amount = Math.abs(Math.trunc(payload.amount));
      if (amount <= 0) {
        socket.emit("club_error", { code: "DEDUCT_DENIED", message: "Amount must be positive" });
        return;
      }
      const currentBalance = await clubDataRepo.getWalletBalance(payload.clubId, payload.userId, "chips");
      if (currentBalance < amount) {
        socket.emit("club_error", { code: "DEDUCT_DENIED", message: "Insufficient balance" });
        return;
      }
      const tx = await appendWalletTx({
        clubId: payload.clubId,
        userId: payload.userId,
        type: "admin_deduct",
        amount: -amount,
        currency: "chips",
        createdBy: identity.userId,
        note: payload.reason ?? "Legacy deduct credits",
        metaJson: { legacyEvent: "club_deduct_credits" },
      });
      await emitWalletBalanceToUser(payload.clubId, payload.userId, tx.newBalance, "chips");
      await emitClubDetail(socket.id, payload.clubId, identity.userId);
    } catch (error) {
      socket.emit("club_error", { code: "DEDUCT_FAILED", message: (error as Error).message });
    }
  });

  socket.on("club_request_addon", async (payload: { clubId: string; amount: number }) => {
    try {
      if (!requireClubAuth()) return;
      if (!clubManager.isActiveMember(payload.clubId, identity.userId)) {
        socket.emit("club_error", { code: "ADDON_DENIED", message: "Not a club member" });
        return;
      }

      if (isClubOwnerOrAdmin(payload.clubId, identity.userId)) {
        const tx = await appendWalletTx({
          clubId: payload.clubId,
          userId: identity.userId,
          type: "admin_grant",
          amount: Math.max(1, Math.trunc(payload.amount)),
          currency: "chips",
          createdBy: identity.userId,
          note: "Self add-on",
          metaJson: { addon: true },
        });
        await emitWalletBalanceToUser(payload.clubId, identity.userId, tx.newBalance, "chips");
        socket.emit("system_message", { message: `Add-on of ${payload.amount} credits auto-approved` });
        await emitClubDetail(socket.id, payload.clubId, identity.userId);
        return;
      }

      const clubDetail = clubManager.getClubDetail(payload.clubId, identity.userId);
      if (!clubDetail) return;
      for (const [sid, ident] of socketIdentity.entries()) {
        const memberRole = clubManager.getMemberRole(payload.clubId, ident.userId);
        if (memberRole === "owner" || memberRole === "admin") {
          io.to(sid).emit("club_addon_request", {
            clubId: payload.clubId,
            userId: identity.userId,
            userName: identity.displayName,
            amount: payload.amount,
          });
        }
      }
      socket.emit("system_message", { message: `Add-on request of ${payload.amount} sent to club admins for approval` });
    } catch (error) {
      socket.emit("club_error", { code: "ADDON_FAILED", message: (error as Error).message });
    }
  });

  /* ═══════════ DISCONNECT ═══════════ */

  socket.on("disconnect", async () => {
    const binding = socketSeat.get(socket.id);
    if (binding) {
      const managed = roomManager.getRoom(binding.tableId);
      const table = tables.get(binding.tableId);

      // Cache rejoin info for auto-restore on reconnect —
      // but NOT if the player explicitly requested to leave (pending stand-up / table leave)
      const hasPendingLeave = pendingTableLeaves.get(binding.tableId)?.has(socket.id) ||
                              pendingStandUps.get(binding.tableId)?.has(binding.seat);
      const roomCode = roomCodeForTable(binding.tableId);
      if (roomCode && !hasPendingLeave) {
        rejoinInfo.set(identity.userId, {
          tableId: binding.tableId,
          seat: binding.seat,
          roomCode,
        });
      }

      // If hand is active, use disconnect grace period instead of immediate removal
      if (managed && table && table.isHandActive()) {
        roomManager.startDisconnectGrace(
          binding.tableId,
          binding.seat,
          identity.userId,
          () => {
            // Grace expired — auto-check/fold and remove player
            const tbl = tables.get(binding.tableId);
            if (tbl && tbl.isHandActive()) {
              const state = tbl.getPublicState();
              if (state.actorSeat === binding.seat) {
                try {
                  const { state: newState, action: timeoutAction } = tbl.handleTimeout(binding.seat);
                  io.to(binding.tableId).emit("action_applied", {
                    seat: binding.seat, action: timeoutAction, amount: 0,
                    pot: newState.pot, auto: true,
                  });
                  handlePostAction(binding.tableId, tbl, newState);
                } catch { /* already folded or hand ended */ }
              }
            }
            // Now remove the player (with club-wallet cash-out if applicable).
            void standUpPlayer(binding.tableId, binding.seat, "Disconnected (grace expired)");
            // Check room empty
            maybeCheckRoomEmpty(binding.tableId, currentPlayerCount(binding.tableId));
            void emitLobbySnapshot();
          }
        );
        // Mark disconnected in Supabase but keep seat for grace period
        supabase.setDisconnected(binding.tableId, binding.seat).catch((e) => console.warn("disconnect: setDisconnected failed:", (e as Error).message));
        // Arm idle watchdog in case all players disconnect
        resetHandIdleWatchdog(binding.tableId);
      } else {
        // No active hand — remove player immediately
        await standUpPlayer(binding.tableId, binding.seat, "Disconnected");
        supabase.setDisconnected(binding.tableId, binding.seat).catch((e) => console.warn("disconnect: setDisconnected failed:", (e as Error).message));
      }

      // Ownership transfer if disconnected player is the owner (exclude bots)
      if (roomManager.isOwner(binding.tableId, identity.userId)) {
        const disconnectBotIds = getBotUserIds(binding.tableId);
        const onlinePlayers = bindingsByTable(binding.tableId)
          .filter(({ socketId: sid }) => sid !== socket.id)
          .filter(({ binding: b }) => !disconnectBotIds.has(b.userId))
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
      maybeCheckRoomEmpty(binding.tableId, currentPlayerCount(binding.tableId));

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
    pendingRunCountDecisions.clear();
    pendingStandUps.clear();
    pendingTableLeaves.clear();
    pendingPause.clear();
    pendingSeatRequests.clear();
    pendingRebuys.clear();
    shutdownAllBots();
    tableSnapshotVersions.clear();
    for (const handle of clubLeaderboardRefreshTimers.values()) {
      clearTimeout(handle);
    }
    clubLeaderboardRefreshTimers.clear();

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
