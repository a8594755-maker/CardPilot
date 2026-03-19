/**
 * Fast Battle Pool Manager
 *
 * Orchestrates the "Infinite Fast Battle" training mode:
 * - Maintains a pool of private rooms with AI bots
 * - Manages player sessions across table hops
 * - Records per-hand data for analytics
 * - Triggers table switching on fold / hand-end
 *
 * Designed as a standalone module — server.ts calls into it via thin hooks.
 */

import { randomUUID } from 'node:crypto';
import type { Server as SocketServer } from 'socket.io';
import type {
  TableState,
  SettlementResult,
  PlayerActionType,
  Street,
  BotSeatConfig,
} from '@cardpilot/shared-types';
import type {
  FastBattleHandRecord,
  FastBattleHeroAction,
  FastBattleReport,
} from '@cardpilot/shared-types';
import type { HandAuditSummary } from '@cardpilot/shared-types';
import { generateFastBattleReport } from './fast-battle-analytics.js';
import { logInfo, logWarn } from '../logger.js';

// ── Types for server.ts bridge functions ──

export interface FastBattleBridge {
  io: SocketServer;
  registerRoom: (room: {
    tableId: string;
    roomCode: string;
    roomName: string;
    maxPlayers: number;
    smallBlind: number;
    bigBlind: number;
    status: 'OPEN';
    isPublic: boolean;
    createdAt: string;
    updatedAt: string;
    createdBy: string | null;
  }) => void;
  createTableIfNeeded: (tableId: string) => void;
  createManagedRoom: (params: {
    tableId: string;
    roomCode: string;
    roomName: string;
    ownerId: string;
    ownerName: string;
    settings: Record<string, unknown>;
  }) => void;
  syncBots: (
    tableId: string,
    roomCode: string,
    bigBlind: number,
    botSeats: BotSeatConfig[],
    serverPort: number,
    buyInMin?: number,
    buyInMax?: number,
    botBuyIn?: number,
  ) => void;
  removeAllBots: (tableId: string) => void;
  standUpPlayer: (tableId: string, seat: number, reason: string) => Promise<boolean>;
  sitDownInternal: (
    tableId: string,
    seat: number,
    buyIn: number,
    userId: string,
    name: string,
    socketId?: string,
  ) => boolean;
  rebindSocket: (
    socketId: string,
    tableId: string,
    seat: number,
    userId: string,
    name: string,
  ) => void;
  destroyTable: (tableId: string) => void;
  getTable: (tableId: string) =>
    | {
        getPublicState(): TableState;
        getSettlementResult(): SettlementResult | null;
        getHoleCards(seat: number): string[] | null;
      }
    | undefined;
  setButtonSeat: (tableId: string, seat: number) => void;
  getAuditService: () => {
    queueHandAudit(input: unknown, sessionId?: string): void;
    getSessionLeakSummary(sessionId: string, userId: string): unknown;
  };
  randomRoomCode: () => string;
  serverPort: number;
  markTableStarted: (tableId: string) => void;
  scheduleAutoDeal: (tableId: string) => void;
}

// ── Internal Types ──

interface PoolRoom {
  tableId: string;
  roomCode: string;
  status: 'idle' | 'assigned' | 'playing';
  humanUserId: string | null;
  createdAt: number;
}

interface FastBattleSession {
  sessionId: string;
  userId: string;
  socketId: string;
  displayName: string;
  targetHandCount: number;
  bigBlind: number;
  smallBlind: number;
  botModelVersion: string;
  handsPlayed: number;
  cumulativeResult: number;
  currentTableId: string | null;
  currentHandId: string | null;
  currentHandStartedAt: number;
  handRecords: FastBattleHandRecord[];
  pendingHeroActions: FastBattleHeroAction[];
  handAuditSummaries: HandAuditSummary[];
  earlyFoldPending: boolean;
  startedAt: number;
  endedAt: number | null;
  state: 'active' | 'switching' | 'report' | 'ended';
}

// ── Constants ──

const TARGET_POOL_SIZE = 25;
const MIN_IDLE_ROOMS = 5;
const SHOWDOWN_SWITCH_DELAY_MS = 2000;
const HUMAN_SEAT = 1;
const REQUIRED_BOTS = 5; // wait for all 5 bots before assigning table
const BOT_PROFILES: BotSeatConfig[] = [
  { seat: 2, profile: 'gto_balanced' },
  { seat: 3, profile: 'tag' },
  { seat: 4, profile: 'lag' },
  { seat: 5, profile: 'nit' },
  { seat: 6, profile: 'gto_balanced' },
];
const SYSTEM_USER_ID = 'fast-battle-system';

// ══════════════════════════════════════════════════════════════
// FastBattlePoolManager
// ══════════════════════════════════════════════════════════════

export class FastBattlePoolManager {
  private pool = new Map<string, PoolRoom>(); // tableId → room
  private sessions = new Map<string, FastBattleSession>(); // userId → session
  private bridge: FastBattleBridge;
  private poolMaintenanceTimer: ReturnType<typeof setInterval> | null = null;

  constructor(bridge: FastBattleBridge) {
    this.bridge = bridge;
    // Pre-warm pool after a short delay (let server finish init)
    setTimeout(() => this.ensurePoolSize(), 2_000);
    // Periodic pool maintenance every 30s
    this.poolMaintenanceTimer = setInterval(() => this.ensurePoolSize(), 30_000);
    logInfo({ event: 'fast_battle.pool.init', message: 'FastBattlePoolManager initialized' });
  }

  // ── Session Lifecycle ──

  startSession(params: {
    userId: string;
    socketId: string;
    displayName: string;
    targetHandCount: number;
    bigBlind?: number;
    botModelVersion?: string;
  }): FastBattleSession | null {
    // Clean up stale session from previous page load / reconnect
    if (this.sessions.has(params.userId)) {
      logInfo({
        event: 'fast_battle.session.stale_cleanup',
        message: `Cleaning up stale session for ${params.userId} before starting new one`,
      });
      this.endSession(params.userId, params.socketId);
    }

    const bigBlind = params.bigBlind ?? 3;
    const smallBlind = params.bigBlind ? Math.floor(params.bigBlind / 2) : 1;
    const session: FastBattleSession = {
      sessionId: `fb_${randomUUID().replace(/-/g, '').slice(0, 12)}`,
      userId: params.userId,
      socketId: params.socketId,
      displayName: params.displayName,
      targetHandCount: params.targetHandCount,
      bigBlind,
      smallBlind,
      botModelVersion: params.botModelVersion ?? 'v4',
      handsPlayed: 0,
      cumulativeResult: 0,
      currentTableId: null,
      currentHandId: null,
      currentHandStartedAt: 0,
      handRecords: [],
      pendingHeroActions: [],
      handAuditSummaries: [],
      earlyFoldPending: false,
      startedAt: Date.now(),
      endedAt: null,
      state: 'active',
    };

    this.sessions.set(params.userId, session);

    logInfo({
      event: 'fast_battle.session.start',
      message: `User ${params.userId} started fast battle: ${params.targetHandCount} hands, ${bigBlind}bb`,
    });

    // Emit session started
    this.bridge.io.to(params.socketId).emit('fast_battle_session_started', {
      sessionId: session.sessionId,
      targetHandCount: session.targetHandCount,
      bigBlind: session.bigBlind,
    });

    // Ensure pool is warm, then assign first table
    this.ensurePoolSize();
    this.assignNextTable(params.userId);

    return session;
  }

  endSession(userId: string, callerSocketId?: string): FastBattleReport | null {
    const session = this.sessions.get(userId);
    if (!session) {
      logWarn({
        event: 'fast_battle.session.end.not_found',
        message: `No active fast-battle session for ${userId}`,
      });
      return null;
    }

    session.state = 'ended';
    session.endedAt = Date.now();

    // Stand up from current table
    if (session.currentTableId) {
      this.releaseRoom(session.currentTableId);
    }

    // Generate report (never let this throw)
    let report: FastBattleReport;
    try {
      report = generateFastBattleReport(session.handRecords, session.handAuditSummaries, session);
    } catch (err) {
      logWarn({
        event: 'fast_battle.report.error',
        message: `Report generation failed: ${(err as Error).message}`,
      });
      // Return a minimal report so the client still transitions
      report = {
        sessionId: session.sessionId,
        stats: {
          handsPlayed: session.handsPlayed,
          handsWon: 0,
          vpip: 0,
          pfr: 0,
          threeBet: 0,
          foldTo3Bet: 0,
          cbetFlop: 0,
          cbetTurn: 0,
          aggressionFactor: 0,
          wtsd: 0,
          wsd: 0,
          netChips: session.cumulativeResult,
          netBb:
            session.bigBlind > 0
              ? Math.round((session.cumulativeResult / session.bigBlind) * 100) / 100
              : 0,
          decisionsPerHour: 0,
        },
        sessionLeak: null,
        problemHands: [],
        recommendations: [],
        handRecords: session.handRecords,
        handCount: session.handsPlayed,
        durationMs: (session.endedAt ?? Date.now()) - session.startedAt,
      };
    }

    // Emit to client — prefer callerSocketId (current socket) over stored one
    const targetSocketId = callerSocketId ?? session.socketId;
    this.bridge.io.to(targetSocketId).emit('fast_battle_session_ended', {
      sessionId: session.sessionId,
      report,
    });

    logInfo({
      event: 'fast_battle.session.end',
      message: `User ${userId} ended fast battle: ${session.handsPlayed}/${session.targetHandCount} hands, net=${session.cumulativeResult}`,
    });

    this.sessions.delete(userId);
    return report;
  }

  // ── Table Assignment ──

  assignNextTable(userId: string): boolean {
    const session = this.sessions.get(userId);
    if (!session || session.state === 'ended' || session.state === 'report') return false;

    // Check if target reached
    if (session.handsPlayed >= session.targetHandCount) {
      this.endSession(userId);
      return false;
    }

    session.state = 'switching';

    // Find an idle room with bots ready
    const room = this.findIdleRoom();
    if (!room) {
      // No room with bots ready — ensure pool is warm and poll until one is ready
      this.ensurePoolSize();
      this.waitForReadyRoom(session);
      return true;
    }

    return this.doAssignment(session, room);
  }

  /**
   * Poll every 500ms until an idle room with bots becomes available.
   * This handles the case where pool rooms exist but bots haven't connected yet.
   */
  private waitForReadyRoom(session: FastBattleSession, startTime: number = Date.now()): void {
    const MAX_WAIT_MS = 15000;

    if (session.state === 'ended') return;

    const room = this.findIdleRoom();
    if (room) {
      const elapsed = Date.now() - startTime;
      if (elapsed > 500) {
        logInfo({
          event: 'fast_battle.wait_ready_room.found',
          message: `Found ready room ${room.tableId} after ${Math.round(elapsed)}ms`,
        });
      }
      this.doAssignment(session, room);
      return;
    }

    if (Date.now() - startTime >= MAX_WAIT_MS) {
      logWarn({
        event: 'fast_battle.wait_ready_room.timeout',
        message: `No ready room after ${MAX_WAIT_MS}ms, pool size=${this.pool.size}`,
      });
      this.bridge.io.to(session.socketId).emit('fast_battle_error', {
        message: 'No room with bots available after 15s, please try again',
        code: 'NO_ROOM_AVAILABLE' as const,
      });
      return;
    }

    setTimeout(() => {
      this.waitForReadyRoom(session, startTime);
    }, 500);
  }

  private doAssignment(session: FastBattleSession, room: PoolRoom): boolean {
    // Release old room if any
    if (session.currentTableId && session.currentTableId !== room.tableId) {
      this.releaseRoom(session.currentTableId);
    }

    // Mark room as assigned
    room.status = 'assigned';
    room.humanUserId = session.userId;
    session.currentTableId = room.tableId;
    session.currentHandId = null;
    session.pendingHeroActions = [];
    session.state = 'active';

    // Wait for bots to be seated, then notify client (human is seated in seatHumanOnJoin)
    this.waitForBotsAndNotify(session, room);

    return true;
  }

  /**
   * Wait until enough bots are seated, then notify the client.
   * The human is NOT seated here — that happens in seatHumanOnJoin()
   * when the client confirms readiness via join_room_code.
   */
  private waitForBotsAndNotify(
    session: FastBattleSession,
    room: PoolRoom,
    startTime: number = Date.now(),
  ): void {
    const MAX_WAIT_MS = 5000;

    // Check how many bots are seated
    const table = this.bridge.getTable(room.tableId);
    const botCount = table
      ? table.getPublicState().players.filter((p) => p.seat !== HUMAN_SEAT).length
      : 0;

    if (botCount >= REQUIRED_BOTS) {
      this.seatHumanDirect(session, room);
    } else if (Date.now() - startTime >= MAX_WAIT_MS) {
      // Bots not ready after safety timeout — release room and try a different one
      logWarn({
        event: 'fast_battle.wait_bots.timeout',
        message: `Only ${botCount} bots after ${MAX_WAIT_MS}ms on ${room.tableId}, trying another room`,
      });
      room.status = 'idle';
      room.humanUserId = null;
      session.currentTableId = null;
      if (session.state !== 'ended') {
        this.assignNextTable(session.userId);
      }
    } else {
      // Retry after 500ms
      setTimeout(() => {
        if (session.state !== 'ended' && session.currentTableId === room.tableId) {
          this.waitForBotsAndNotify(session, room, startTime);
        }
      }, 500);
    }
  }

  /**
   * Directly seat the human on the assigned table — bypasses join_room_code
   * to eliminate the room-lookup round-trip that caused "Room not found" errors.
   */
  private seatHumanDirect(session: FastBattleSession, room: PoolRoom): void {
    const buyIn = session.bigBlind * 100;

    // 1. Join the human's socket to the table's socket.io room
    const sock = this.bridge.io.sockets.sockets.get(session.socketId);
    if (!sock) {
      logWarn({
        event: 'fast_battle.seat.no_socket',
        message: `Socket ${session.socketId} not found for ${session.userId} — cannot seat`,
      });
      return;
    }

    // Leave any previous table room
    for (const r of sock.rooms) {
      if (r.startsWith('fb_') && r !== room.tableId) {
        sock.leave(r);
      }
    }
    sock.join(room.tableId);

    // 2. Seat the human via sitDownInternal
    const alreadySeated = this.bridge
      .getTable(room.tableId)
      ?.getPublicState()
      .players.some((p) => p.seat === HUMAN_SEAT);

    if (!alreadySeated) {
      const seated = this.bridge.sitDownInternal(
        room.tableId,
        HUMAN_SEAT,
        buyIn,
        session.userId,
        session.displayName,
        session.socketId,
      );
      if (!seated) {
        logWarn({
          event: 'fast_battle.seat.failed',
          message: `Failed to seat ${session.userId} at ${room.tableId}:${HUMAN_SEAT}`,
        });
        room.status = 'idle';
        room.humanUserId = null;
        session.currentTableId = null;
        // Try a different room
        if (session.state !== 'ended') {
          this.assignNextTable(session.userId);
        }
        return;
      }
    }

    // 3. Randomize button position so hero gets a different position each hand
    const randomButton = [1, 2, 3, 4, 5, 6][Math.floor(Math.random() * 6)];
    this.bridge.setButtonSeat(room.tableId, randomButton);

    room.status = 'playing';
    this.bridge.markTableStarted(room.tableId);
    this.bridge.scheduleAutoDeal(room.tableId);

    // 5. Notify client — table is already set up, just need to switch UI
    //    NO room_joined here — Fast Battle uses its own event flow,
    //    not the regular poker table join logic.
    this.bridge.io.to(session.socketId).emit('fast_battle_table_assigned', {
      tableId: room.tableId,
      roomCode: room.roomCode,
      seat: HUMAN_SEAT,
      buyIn,
      handNumber: session.handsPlayed + 1,
      totalHands: session.targetHandCount,
    });

    logInfo({
      event: 'fast_battle.table.assigned',
      message: `Seated ${session.userId} at ${room.tableId}:${HUMAN_SEAT} (hand ${session.handsPlayed + 1}/${session.targetHandCount}), deal scheduled`,
    });

    // Ensure pool stays warm
    this.ensurePoolSize();
  }

  /**
   * Fallback: called from server.ts join_room_code handler if client
   * still emits join_room_code (e.g. old client code or retry).
   * In the new flow, seatHumanDirect handles seating before the event.
   */
  seatHumanOnJoin(userId: string, tableId: string, socketId?: string): boolean {
    const session = this.sessions.get(userId);
    if (!session || session.currentTableId !== tableId) return false;

    // Keep session socketId fresh (handles reconnects)
    if (socketId) {
      session.socketId = socketId;
    }

    const room = this.pool.get(tableId);
    if (!room) return false;

    // Already seated? (e.g. duplicate join_room_code)
    const table = this.bridge.getTable(tableId);
    if (table && table.getPublicState().players.some((p) => p.seat === HUMAN_SEAT)) {
      return true; // already seated, just broadcast updated snapshot
    }

    const buyIn = session.bigBlind * 100;
    const seated = this.bridge.sitDownInternal(
      tableId,
      HUMAN_SEAT,
      buyIn,
      session.userId,
      session.displayName,
      socketId,
    );

    if (!seated) {
      logWarn({
        event: 'fast_battle.seat.failed',
        message: `Failed to seat ${session.userId} at ${tableId}:${HUMAN_SEAT} (socketId=${socketId ?? 'unknown'})`,
      });
      room.status = 'idle';
      room.humanUserId = null;
      session.currentTableId = null;
      // Try a different room
      if (session.state !== 'ended') {
        this.assignNextTable(session.userId);
      }
      return false;
    }

    room.status = 'playing';

    // Now that human is seated and client is connected, start dealing
    this.bridge.markTableStarted(tableId);
    this.bridge.scheduleAutoDeal(tableId);

    logInfo({
      event: 'fast_battle.seat.success',
      message: `Seated ${session.userId} at ${tableId}:${HUMAN_SEAT} (socketId=${socketId ?? 'unknown'}), scheduling deal`,
    });

    return true;
  }

  // ── Hand Lifecycle Hooks (called from server.ts) ──

  onHandStarted(tableId: string, handId: string): void {
    const room = this.pool.get(tableId);
    if (!room || !room.humanUserId) return;

    const session = this.sessions.get(room.humanUserId);
    if (!session) return;

    session.currentHandId = handId;
    session.currentHandStartedAt = Date.now();
    session.pendingHeroActions = [];
    session.earlyFoldPending = false;
  }

  onHeroAction(
    tableId: string,
    userId: string,
    action: PlayerActionType,
    amount: number,
    state: TableState,
  ): void {
    const session = this.sessions.get(userId);
    if (!session || session.currentTableId !== tableId) return;

    session.pendingHeroActions.push({
      street: state.street as Street,
      action,
      amount: amount ?? 0,
      pot: state.pot,
      toCall: state.legalActions?.callAmount ?? 0,
    });
  }

  onHeroFolded(tableId: string, userId: string, state: TableState): void {
    const session = this.sessions.get(userId);
    if (!session || session.currentTableId !== tableId) return;

    // Record the fold action
    this.onHeroAction(tableId, userId, 'fold', 0, state);

    // Record hand result (folded, lost whatever was committed)
    this.recordHandResult(session, tableId, state, null, false);

    // Immediately switch to next table
    this.assignNextTable(userId);
  }

  /**
   * Request early fold — user wants to fold before their turn.
   * Returns { tableId, seat } if it's already the hero's turn (caller should fold immediately).
   * Returns null if the flag was set and fold will happen when hero's turn comes.
   */
  requestEarlyFold(userId: string): { tableId: string; seat: number } | null {
    const session = this.sessions.get(userId);
    if (!session || session.state !== 'active' || !session.currentTableId) return null;

    const table = this.bridge.getTable(session.currentTableId);
    if (!table) return null;
    const state = table.getPublicState();

    if (state.actorSeat === HUMAN_SEAT) {
      // Already hero's turn — caller should fold immediately via game engine
      return { tableId: session.currentTableId, seat: HUMAN_SEAT };
    }

    // Not hero's turn yet — set flag for auto-fold when turn comes
    session.earlyFoldPending = true;
    logInfo({ event: 'fast_battle.early_fold.queued', userId, tableId: session.currentTableId });
    return null;
  }

  /**
   * Check if the given actor on the given table has an early fold pending.
   * Returns the userId if so (and clears the flag), or null.
   */
  consumeEarlyFold(tableId: string, actorSeat: number): string | null {
    if (actorSeat !== HUMAN_SEAT) return null;
    const room = this.pool.get(tableId);
    if (!room || !room.humanUserId) return null;
    const session = this.sessions.get(room.humanUserId);
    if (!session || session.currentTableId !== tableId) return null;
    if (!session.earlyFoldPending) return null;
    session.earlyFoldPending = false;
    return session.userId;
  }

  onHandEnded(tableId: string, state: TableState, settlement: SettlementResult | null): void {
    const room = this.pool.get(tableId);
    if (!room || !room.humanUserId) return;

    const session = this.sessions.get(room.humanUserId);
    if (!session || session.currentTableId !== tableId) return;

    // If we already recorded this hand (e.g. hero folded), skip
    if (
      session.handRecords.length > 0 &&
      session.handRecords[session.handRecords.length - 1].handId === state.handId
    ) {
      return;
    }

    // Record hand result
    const wentToShowdown = state.players.some(
      (p) => p.seat === HUMAN_SEAT && p.inHand && !p.folded,
    );
    this.recordHandResult(session, tableId, state, settlement, wentToShowdown);

    // Queue audit for this hand
    this.queueAudit(session, tableId, state);

    // Auto-rebuy if busted
    this.autoRebuyIfNeeded(session, tableId);

    // Delay switch for showdown hands so player sees the result
    if (wentToShowdown) {
      setTimeout(() => {
        if (session.state !== 'ended') {
          this.assignNextTable(session.userId);
        }
      }, SHOWDOWN_SWITCH_DELAY_MS);
    } else {
      // Non-showdown hand end (e.g. all opponents folded) — switch immediately
      this.assignNextTable(session.userId);
    }
  }

  // ── Hand Audit Integration ──

  onAuditComplete(userId: string, summary: HandAuditSummary): void {
    const session = this.sessions.get(userId);
    if (!session) return;

    // Only collect audits for hands in this session
    const isSessionHand = session.handRecords.some((h) => h.handId === summary.handId);
    if (isSessionHand) {
      session.handAuditSummaries.push(summary);
    }
  }

  // ── Queries ──

  isInFastBattle(userId: string): boolean {
    return this.sessions.has(userId);
  }

  isFastBattleTable(tableId: string): boolean {
    return this.pool.has(tableId);
  }

  getSession(userId: string): FastBattleSession | null {
    return this.sessions.get(userId) ?? null;
  }

  /**
   * Handle socket reconnect for a user with an active fast battle session.
   * Re-joins the socket to the current table room and sends updated state.
   * Returns true if the user was successfully reconnected.
   */
  handleReconnect(userId: string, socketId: string): boolean {
    const session = this.sessions.get(userId);
    if (!session || session.state === 'ended') return false;

    // Update socketId (new socket after reconnect)
    session.socketId = socketId;

    const tableId = session.currentTableId;
    if (!tableId) return false;

    const room = this.pool.get(tableId);
    if (!room) return false;

    // Rejoin the socket to the table room and rebind seat mapping
    const sock = this.bridge.io.sockets.sockets.get(socketId);
    if (!sock) return false;
    sock.join(tableId);
    this.bridge.rebindSocket(socketId, tableId, HUMAN_SEAT, userId, session.displayName);

    // Re-emit table assignment so client state is restored
    this.bridge.io.to(socketId).emit('fast_battle_table_assigned', {
      tableId: room.tableId,
      roomCode: room.roomCode,
      seat: HUMAN_SEAT,
      buyIn: session.bigBlind * 100,
      handNumber: session.handsPlayed + 1,
      totalHands: session.targetHandCount,
    });

    logInfo({
      event: 'fast_battle.reconnect',
      message: `Reconnected ${userId} to fast battle table ${tableId} (socket=${socketId})`,
    });

    return true;
  }

  // ── Pool Management ──

  ensurePoolSize(): void {
    let idleCount = 0;
    for (const room of this.pool.values()) {
      if (room.status === 'idle') idleCount++;
    }

    const needed = Math.max(0, MIN_IDLE_ROOMS - idleCount);
    const totalNeeded = Math.max(0, TARGET_POOL_SIZE - this.pool.size);
    const toCreate = Math.max(needed, Math.min(totalNeeded, 5)); // Create up to 5 at a time

    for (let i = 0; i < toCreate; i++) {
      this.createPoolRoom(3, 1); // default 1/3 stakes
    }
  }

  private createPoolRoom(bigBlind: number, smallBlindOverride?: number): PoolRoom {
    const smallBlind = smallBlindOverride ?? Math.floor(bigBlind / 2);
    const roomCode = this.bridge.randomRoomCode();
    const tableId = `fb_${randomUUID().replace(/-/g, '').slice(0, 10)}`;
    const buyIn = bigBlind * 100;

    // Register room in server.ts maps
    this.bridge.registerRoom({
      tableId,
      roomCode,
      roomName: `Fast Battle #${this.pool.size + 1}`,
      maxPlayers: 6,
      smallBlind,
      bigBlind,
      status: 'OPEN',
      isPublic: false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      createdBy: SYSTEM_USER_ID,
    });

    // Create managed room BEFORE GameTable so settings are available
    this.bridge.createManagedRoom({
      tableId,
      roomCode,
      roomName: `Fast Battle #${this.pool.size + 1}`,
      ownerId: SYSTEM_USER_ID,
      ownerName: 'Fast Battle',
      settings: {
        maxPlayers: 6,
        smallBlind,
        bigBlind,
        buyInMin: buyIn,
        buyInMax: buyIn,
        visibility: 'private',
        autoStartNextHand: true,
        hostStartRequired: false,
        dealToAwayPlayers: true,
        revealAllAtShowdown: true,
        actionTimerSeconds: 15,
        timeBankSeconds: 0,
        disconnectGracePeriod: 5,
        showdownSpeed: 'turbo',
      },
    });

    // Create GameTable (after managed room so settings like showdownSpeed are available)
    this.bridge.createTableIfNeeded(tableId);

    // NOTE: markTableStarted is called in seatHumanDirect (after human sits)
    // to prevent bots from auto-dealing among themselves before human arrives.

    // Spawn bots on seats 2-6
    this.bridge.syncBots(
      tableId,
      roomCode,
      bigBlind,
      BOT_PROFILES,
      this.bridge.serverPort,
      buyIn,
      buyIn,
      buyIn,
    );

    const poolRoom: PoolRoom = {
      tableId,
      roomCode,
      status: 'idle',
      humanUserId: null,
      createdAt: Date.now(),
    };

    this.pool.set(tableId, poolRoom);

    logInfo({
      event: 'fast_battle.pool.room_created',
      message: `Created pool room ${tableId} (${roomCode}), pool size=${this.pool.size}`,
    });

    return poolRoom;
  }

  private findIdleRoom(): PoolRoom | null {
    for (const room of this.pool.values()) {
      if (room.status !== 'idle') continue;
      // Only return rooms where bots are actually seated
      const table = this.bridge.getTable(room.tableId);
      const botCount = table
        ? table.getPublicState().players.filter((p) => p.seat !== HUMAN_SEAT).length
        : 0;
      if (botCount >= REQUIRED_BOTS) return room;
    }
    return null;
  }

  private releaseRoom(tableId: string): void {
    const room = this.pool.get(tableId);
    if (!room) return;

    // Stand up the human
    this.bridge.standUpPlayer(tableId, HUMAN_SEAT, 'Fast Battle: switching tables').catch(() => {});

    // Remove all bots, destroy the table from server maps to prevent zombie snapshots
    this.bridge.removeAllBots(tableId);
    this.bridge.destroyTable(tableId);
    this.pool.delete(tableId);

    logInfo({
      event: 'fast_battle.pool.room_released',
      message: `Released and destroyed room ${tableId}, pool size=${this.pool.size}`,
    });
  }

  // ── Internal Helpers ──

  private recordHandResult(
    session: FastBattleSession,
    tableId: string,
    state: TableState,
    settlement: SettlementResult | null,
    wentToShowdown: boolean,
  ): void {
    // Calculate hero result from settlement or state
    let result = 0;
    if (settlement) {
      const heroEntry = settlement.ledger.find((e) => e.seat === HUMAN_SEAT);
      result = heroEntry?.net ?? 0;
    }

    // Get hero position
    const heroPosition = state.positions?.[HUMAN_SEAT] ?? '?';

    // Get all players' hole cards
    const table = this.bridge.getTable(tableId);
    const rawCards = table?.getHoleCards(HUMAN_SEAT);
    const holeCards: [string, string] =
      rawCards && rawCards.length >= 2 ? [rawCards[0], rawCards[1]] : ['??', '??'];

    const allHoleCards: Record<number, [string, string]> = {};
    if (table) {
      for (const p of state.players) {
        const cards = table.getHoleCards(p.seat);
        if (cards && cards.length >= 2) {
          allHoleCards[p.seat] = [cards[0], cards[1]];
        }
      }
    }

    const record: FastBattleHandRecord = {
      handId: state.handId ?? session.currentHandId ?? `unknown-${Date.now()}`,
      tableId,
      heroSeat: HUMAN_SEAT,
      heroPosition,
      holeCards,
      allHoleCards,
      board: [...state.board],
      heroActions: [...session.pendingHeroActions],
      result,
      totalPot: state.pot,
      wentToShowdown,
      startedAt: session.currentHandStartedAt || Date.now(),
      endedAt: Date.now(),
    };

    session.handRecords.push(record);
    session.handsPlayed++;
    session.cumulativeResult += result;

    // Emit hand result
    this.bridge.io.to(session.socketId).emit('fast_battle_hand_result', {
      handId: record.handId,
      handNumber: session.handsPlayed,
      result,
      heroPosition: record.heroPosition,
      holeCards: record.holeCards,
      board: record.board,
      wentToShowdown,
      cumulativeResult: session.cumulativeResult,
    });

    // Emit progress
    const elapsed = Date.now() - session.startedAt;
    const decisionsPerHour =
      elapsed > 0 ? Math.round((session.handsPlayed / elapsed) * 3_600_000) : 0;

    this.bridge.io.to(session.socketId).emit('fast_battle_progress', {
      handsPlayed: session.handsPlayed,
      targetHandCount: session.targetHandCount,
      cumulativeResult: session.cumulativeResult,
      decisionsPerHour,
    });
  }

  private queueAudit(session: FastBattleSession, tableId: string, state: TableState): void {
    const table = this.bridge.getTable(tableId);
    if (!table) return;

    const cards = table.getHoleCards(HUMAN_SEAT);
    if (!cards || cards.length < 2) return;

    const playerSeats = state.players.filter((p) => p.inHand || !p.folded).map((p) => p.seat);

    this.bridge.getAuditService().queueHandAudit(
      {
        handId: state.handId,
        handHistoryId: state.handId,
        tableId,
        bigBlind: state.bigBlind,
        smallBlind: state.smallBlind,
        buttonSeat: state.buttonSeat,
        playerSeats,
        actions: [...state.actions],
        positions: state.positions,
        heroUserId: session.userId,
        heroSeat: HUMAN_SEAT,
        heroCards: [cards[0], cards[1]],
        board: [...state.board],
        totalPot: state.pot,
      },
      session.sessionId,
    );
  }

  private autoRebuyIfNeeded(session: FastBattleSession, tableId: string): void {
    const table = this.bridge.getTable(tableId);
    if (!table) return;

    const state = table.getPublicState();
    const hero = state.players.find((p) => p.seat === HUMAN_SEAT);
    if (hero && hero.stack <= 0) {
      // Will get a fresh buy-in at the next table assignment
      logInfo({
        event: 'fast_battle.rebuy',
        message: `Hero busted on ${tableId}, will rebuy on next table`,
      });
    }
  }

  // ── Cleanup ──

  shutdown(): void {
    if (this.poolMaintenanceTimer) {
      clearInterval(this.poolMaintenanceTimer);
      this.poolMaintenanceTimer = null;
    }

    // End all sessions
    for (const userId of [...this.sessions.keys()]) {
      this.endSession(userId);
    }

    // Tear down all pool rooms
    for (const room of this.pool.values()) {
      this.bridge.removeAllBots(room.tableId);
    }
    this.pool.clear();

    logInfo({ event: 'fast_battle.pool.shutdown', message: 'FastBattlePoolManager shut down' });
  }
}
