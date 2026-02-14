import { randomUUID } from "node:crypto";
import type {
  RoomSettings,
  RoomOwnership,
  RoomLogEntry,
  RoomLogEventType,
  RoomFullState,
  RoomStatus,
  TimerState,
  DEFAULT_ROOM_SETTINGS,
} from "@cardpilot/shared-types";

// Re-define default here to avoid runtime import issues with const exports
const DEFAULTS: RoomSettings = {
  gameType: "texas",
  maxPlayers: 6,
  spectatorAllowed: true,
  smallBlind: 50,
  bigBlind: 100,
  ante: 0,
  blindStructure: null,
  buyInMin: 2000,
  buyInMax: 20000,
  rebuyAllowed: true,
  addOnAllowed: false,
  straddleAllowed: false,
  runItTwice: false,
  visibility: "public",
  password: null,
  hostStartRequired: false,
  actionTimerSeconds: 15,
  timeBankSeconds: 60,
  timeBankRefillPerHand: 5,
  disconnectGracePeriod: 30,
  maxConsecutiveTimeouts: 3,
};

const MAX_LOG_ENTRIES = 200;
const ROOM_EMPTY_TTL_MS = 90_000; // 90 seconds before auto-destroy

export interface ManagedRoom {
  tableId: string;
  roomCode: string;
  roomName: string;
  settings: RoomSettings;
  ownership: RoomOwnership;
  status: RoomStatus;
  banList: string[];
  log: RoomLogEntry[];
  emptySince: number | null;
  // Timer state
  timer: TimerState | null;
  actionTimerHandle: ReturnType<typeof setTimeout> | null;
  // Per-player time banks: userId -> remaining seconds
  timeBanks: Map<string, number>;
  // Per-player consecutive timeout count: userId -> count
  timeoutCounts: Map<string, number>;
  // Disconnect grace: seatNumber -> { userId, handle, disconnectedAt }
  disconnectGrace: Map<number, { userId: string; handle: ReturnType<typeof setTimeout>; disconnectedAt: number }>;
  // Room empty timer
  emptyTimerHandle: ReturnType<typeof setTimeout> | null;
  // Hand active?
  handActive: boolean;
  // Paused?
  paused: boolean;
  // Created at
  createdAt: string;
  updatedAt: string;
}

export type RoomEventCallback = (tableId: string, event: string, data: unknown) => void;

export class RoomManager {
  private rooms = new Map<string, ManagedRoom>();
  private onEvent: RoomEventCallback;

  constructor(onEvent: RoomEventCallback) {
    this.onEvent = onEvent;
  }

  /* ═══════════ CREATION ═══════════ */

  createRoom(params: {
    tableId: string;
    roomCode: string;
    roomName: string;
    ownerId: string;
    ownerName: string;
    settings?: Partial<RoomSettings>;
  }): ManagedRoom {
    const settings: RoomSettings = { ...DEFAULTS, ...params.settings };
    // Validate blinds
    if (settings.bigBlind <= settings.smallBlind) {
      settings.bigBlind = settings.smallBlind * 2;
    }
    settings.maxPlayers = Math.min(9, Math.max(2, settings.maxPlayers));

    const room: ManagedRoom = {
      tableId: params.tableId,
      roomCode: params.roomCode,
      roomName: params.roomName,
      settings,
      ownership: {
        ownerId: params.ownerId,
        ownerName: params.ownerName,
        coHostIds: [],
      },
      status: "WAITING",
      banList: [],
      log: [],
      emptySince: null,
      timer: null,
      actionTimerHandle: null,
      timeBanks: new Map(),
      timeoutCounts: new Map(),
      disconnectGrace: new Map(),
      emptyTimerHandle: null,
      handActive: false,
      paused: false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    this.rooms.set(params.tableId, room);
    this.addLog(room, "SYSTEM_MESSAGE", {
      message: `Room created by ${params.ownerName}`,
      actorId: params.ownerId,
      actorName: params.ownerName,
    });

    return room;
  }

  getRoom(tableId: string): ManagedRoom | undefined {
    return this.rooms.get(tableId);
  }

  deleteRoom(tableId: string): void {
    const room = this.rooms.get(tableId);
    if (!room) return;
    // Cleanup timers
    if (room.actionTimerHandle) clearTimeout(room.actionTimerHandle);
    if (room.emptyTimerHandle) clearTimeout(room.emptyTimerHandle);
    for (const grace of room.disconnectGrace.values()) {
      clearTimeout(grace.handle);
    }
    this.rooms.delete(tableId);
  }

  /* ═══════════ OWNERSHIP ═══════════ */

  isOwner(tableId: string, userId: string): boolean {
    const room = this.rooms.get(tableId);
    return room?.ownership.ownerId === userId;
  }

  isCoHost(tableId: string, userId: string): boolean {
    const room = this.rooms.get(tableId);
    return room?.ownership.coHostIds.includes(userId) ?? false;
  }

  isHostOrCoHost(tableId: string, userId: string): boolean {
    return this.isOwner(tableId, userId) || this.isCoHost(tableId, userId);
  }

  transferOwnership(tableId: string, newOwnerId: string, newOwnerName: string, actorId: string, actorName: string): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;

    const oldOwner = room.ownership.ownerName;
    room.ownership.ownerId = newOwnerId;
    room.ownership.ownerName = newOwnerName;
    // Remove from co-host if they were one
    room.ownership.coHostIds = room.ownership.coHostIds.filter((id) => id !== newOwnerId);

    this.addLog(room, "OWNER_CHANGED", {
      actorId, actorName,
      targetId: newOwnerId, targetName: newOwnerName,
      message: `Owner changed: ${oldOwner} → ${newOwnerName}`,
    });

    this.emitRoomUpdate(room);
    return true;
  }

  setCoHost(tableId: string, userId: string, userName: string, add: boolean, actorId: string, actorName: string): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;

    if (add) {
      if (!room.ownership.coHostIds.includes(userId)) {
        room.ownership.coHostIds.push(userId);
        this.addLog(room, "SYSTEM_MESSAGE", {
          actorId, actorName,
          message: `${actorName} promoted ${userName} to co-host`,
        });
      }
    } else {
      room.ownership.coHostIds = room.ownership.coHostIds.filter((id) => id !== userId);
      this.addLog(room, "SYSTEM_MESSAGE", {
        actorId, actorName,
        message: `${actorName} removed ${userName} from co-host`,
      });
    }

    this.emitRoomUpdate(room);
    return true;
  }

  /** Auto-transfer ownership when owner disconnects. Returns new owner userId or null. */
  autoTransferOwnership(
    tableId: string,
    seatedOnlinePlayers: Array<{ userId: string; name: string }>
  ): { newOwnerId: string; newOwnerName: string } | null {
    const room = this.rooms.get(tableId);
    if (!room) return null;

    // Try co-hosts first
    for (const coHostId of room.ownership.coHostIds) {
      const p = seatedOnlinePlayers.find((pp) => pp.userId === coHostId);
      if (p) {
        this.transferOwnership(tableId, p.userId, p.name, p.userId, p.name);
        return { newOwnerId: p.userId, newOwnerName: p.name };
      }
    }

    // Fallback: next seated + online player
    for (const p of seatedOnlinePlayers) {
      if (p.userId !== room.ownership.ownerId) {
        this.transferOwnership(tableId, p.userId, p.name, p.userId, p.name);
        return { newOwnerId: p.userId, newOwnerName: p.name };
      }
    }

    return null;
  }

  /* ═══════════ SETTINGS ═══════════ */

  updateSettings(tableId: string, partial: Partial<RoomSettings>, actorId: string, actorName: string): { applied: Partial<RoomSettings>; deferred: Partial<RoomSettings> } | null {
    const room = this.rooms.get(tableId);
    if (!room) return null;

    const applied: Partial<RoomSettings> = {};
    const deferred: Partial<RoomSettings> = {};

    // Fields that can ALWAYS be changed
    const alwaysEditable: Array<keyof RoomSettings> = [
      "spectatorAllowed", "visibility", "password", "hostStartRequired",
      "actionTimerSeconds", "timeBankSeconds", "timeBankRefillPerHand",
      "disconnectGracePeriod", "maxConsecutiveTimeouts",
    ];

    // Fields that can only change pre-game or apply next hand
    const preGameOnly: Array<keyof RoomSettings> = [
      "gameType", "maxPlayers", "smallBlind", "bigBlind", "ante",
      "blindStructure", "buyInMin", "buyInMax", "rebuyAllowed", "addOnAllowed",
      "straddleAllowed", "runItTwice",
    ];

    for (const key of alwaysEditable) {
      if (key in partial) {
        (room.settings as any)[key] = (partial as any)[key];
        (applied as any)[key] = (partial as any)[key];
      }
    }

    for (const key of preGameOnly) {
      if (key in partial) {
        if (!room.handActive) {
          (room.settings as any)[key] = (partial as any)[key];
          (applied as any)[key] = (partial as any)[key];
        } else {
          (deferred as any)[key] = (partial as any)[key];
        }
      }
    }

    // Re-validate blinds
    if (room.settings.bigBlind <= room.settings.smallBlind) {
      room.settings.bigBlind = room.settings.smallBlind * 2;
    }

    const changedKeys = [...Object.keys(applied), ...Object.keys(deferred)];
    if (changedKeys.length > 0) {
      this.addLog(room, "SETTINGS_CHANGED", {
        actorId, actorName,
        message: `${actorName} changed settings: ${changedKeys.join(", ")}`,
        payload: { applied, deferred },
      });
      this.emitRoomUpdate(room);
    }

    return { applied, deferred };
  }

  /* ═══════════ KICK / BAN ═══════════ */

  kickPlayer(tableId: string, targetUserId: string, targetName: string, reason: string, ban: boolean, actorId: string, actorName: string): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;

    if (ban && !room.banList.includes(targetUserId)) {
      room.banList.push(targetUserId);
      this.addLog(room, "PLAYER_BANNED", {
        actorId, actorName, targetId: targetUserId, targetName,
        message: `${actorName} banned ${targetName}${reason ? `: ${reason}` : ""}`,
      });
    } else {
      this.addLog(room, "PLAYER_KICKED", {
        actorId, actorName, targetId: targetUserId, targetName,
        message: `${actorName} kicked ${targetName}${reason ? `: ${reason}` : ""}`,
      });
    }

    this.emitRoomUpdate(room);
    return true;
  }

  isBanned(tableId: string, userId: string): boolean {
    const room = this.rooms.get(tableId);
    return room?.banList.includes(userId) ?? false;
  }

  /* ═══════════ GAME FLOW CONTROL ═══════════ */

  setHandActive(tableId: string, active: boolean): void {
    const room = this.rooms.get(tableId);
    if (!room) return;
    room.handActive = active;
    if (active) {
      room.status = "PLAYING";
    } else if (room.paused) {
      room.status = "PAUSED";
    } else {
      room.status = "WAITING";
    }
    room.updatedAt = new Date().toISOString();
  }

  pauseGame(tableId: string, actorId: string, actorName: string): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;
    room.paused = true;
    room.status = "PAUSED";
    // Stop action timer while paused
    this.clearActionTimer(tableId);
    this.addLog(room, "GAME_PAUSED", {
      actorId, actorName,
      message: `${actorName} paused the game`,
    });
    this.emitRoomUpdate(room);
    return true;
  }

  resumeGame(tableId: string, actorId: string, actorName: string): boolean {
    const room = this.rooms.get(tableId);
    if (!room || !room.paused) return false;
    room.paused = false;
    room.status = room.handActive ? "PLAYING" : "WAITING";
    this.addLog(room, "GAME_RESUMED", {
      actorId, actorName,
      message: `${actorName} resumed the game`,
    });
    this.emitRoomUpdate(room);
    return true;
  }

  endGame(tableId: string, actorId: string, actorName: string): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;
    room.handActive = false;
    room.paused = false;
    room.status = "WAITING";
    this.clearActionTimer(tableId);
    this.addLog(room, "GAME_ENDED", {
      actorId, actorName,
      message: `${actorName} ended the game`,
    });
    this.emitRoomUpdate(room);
    return true;
  }

  isPaused(tableId: string): boolean {
    return this.rooms.get(tableId)?.paused ?? false;
  }

  /* ═══════════ ACTION TIMER ═══════════ */

  startActionTimer(
    tableId: string,
    seat: number,
    userId: string,
    onTimeout: () => void
  ): TimerState | null {
    const room = this.rooms.get(tableId);
    if (!room || room.paused) return null;

    this.clearActionTimer(tableId);

    const timerSeconds = room.settings.actionTimerSeconds;
    const timeBankLeft = room.timeBanks.get(userId) ?? room.settings.timeBankSeconds;

    const timerState: TimerState = {
      seat,
      remaining: timerSeconds,
      timeBankRemaining: timeBankLeft,
      usingTimeBank: false,
      startedAt: Date.now(),
    };
    room.timer = timerState;

    // Set main timer
    room.actionTimerHandle = setTimeout(() => {
      // Main timer expired, start time bank
      if (timeBankLeft > 0) {
        timerState.usingTimeBank = true;
        timerState.remaining = 0;
        this.emitTimerUpdate(room);

        // Time bank timer
        room.actionTimerHandle = setTimeout(() => {
          // Time bank expired → timeout
          room.timeBanks.set(userId, 0);
          this.handleTimeout(room, seat, userId, onTimeout);
        }, timeBankLeft * 1000);

        // Deduct time bank in real-time (update every second)
        const bankInterval = setInterval(() => {
          if (!room.timer || !room.timer.usingTimeBank) {
            clearInterval(bankInterval);
            return;
          }
          room.timer.timeBankRemaining = Math.max(0, room.timer.timeBankRemaining - 1);
          room.timeBanks.set(userId, room.timer.timeBankRemaining);
          this.emitTimerUpdate(room);
          if (room.timer.timeBankRemaining <= 0) {
            clearInterval(bankInterval);
          }
        }, 1000);
      } else {
        // No time bank left → immediate timeout
        this.handleTimeout(room, seat, userId, onTimeout);
      }
    }, timerSeconds * 1000);

    this.emitTimerUpdate(room);
    return timerState;
  }

  clearActionTimer(tableId: string): void {
    const room = this.rooms.get(tableId);
    if (!room) return;
    if (room.actionTimerHandle) {
      clearTimeout(room.actionTimerHandle);
      room.actionTimerHandle = null;
    }
    room.timer = null;
  }

  /** Called when player acts in time — stop timer and save remaining time bank */
  playerActedInTime(tableId: string, userId: string): void {
    const room = this.rooms.get(tableId);
    if (!room || !room.timer) return;

    // If they were using time bank, save remaining
    if (room.timer.usingTimeBank) {
      const elapsed = (Date.now() - room.timer.startedAt) / 1000 - room.settings.actionTimerSeconds;
      const used = Math.max(0, elapsed);
      const bankBefore = room.timeBanks.get(userId) ?? room.settings.timeBankSeconds;
      room.timeBanks.set(userId, Math.max(0, bankBefore - used));
    }

    // Reset consecutive timeout counter
    room.timeoutCounts.set(userId, 0);
    this.clearActionTimer(tableId);
  }

  /** Refill time banks at hand start */
  refillTimeBanks(tableId: string, playerUserIds: string[]): void {
    const room = this.rooms.get(tableId);
    if (!room) return;
    const refill = room.settings.timeBankRefillPerHand;
    const max = room.settings.timeBankSeconds;
    for (const uid of playerUserIds) {
      const current = room.timeBanks.get(uid) ?? max;
      room.timeBanks.set(uid, Math.min(max, current + refill));
    }
  }

  private handleTimeout(room: ManagedRoom, seat: number, userId: string, onTimeout: () => void): void {
    const count = (room.timeoutCounts.get(userId) ?? 0) + 1;
    room.timeoutCounts.set(userId, count);

    this.addLog(room, "PLAYER_TIMED_OUT", {
      targetId: userId,
      message: `Seat ${seat} timed out (auto-fold)`,
    });

    // Check consecutive timeout threshold
    if (count >= room.settings.maxConsecutiveTimeouts) {
      this.addLog(room, "PLAYER_SAT_OUT", {
        targetId: userId,
        message: `Seat ${seat} auto sat-out after ${count} consecutive timeouts`,
      });
      this.onEvent(room.tableId, "player_auto_sitout", { seat, userId, reason: "consecutive_timeouts" });
    }

    room.timer = null;
    room.actionTimerHandle = null;
    onTimeout();
    this.emitRoomUpdate(room);
  }

  /* ═══════════ DISCONNECT PROTECTION ═══════════ */

  startDisconnectGrace(
    tableId: string,
    seat: number,
    userId: string,
    onGraceExpired: () => void
  ): void {
    const room = this.rooms.get(tableId);
    if (!room) return;

    // Clear existing grace for this seat
    const existing = room.disconnectGrace.get(seat);
    if (existing) clearTimeout(existing.handle);

    const handle = setTimeout(() => {
      room.disconnectGrace.delete(seat);
      this.addLog(room, "SYSTEM_MESSAGE", {
        targetId: userId,
        message: `Seat ${seat} reconnect window expired — auto-fold`,
      });
      onGraceExpired();
    }, room.settings.disconnectGracePeriod * 1000);

    room.disconnectGrace.set(seat, {
      userId,
      handle,
      disconnectedAt: Date.now(),
    });

    this.onEvent(tableId, "player_disconnected", { seat, userId, graceSeconds: room.settings.disconnectGracePeriod });
  }

  cancelDisconnectGrace(tableId: string, seat: number): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;
    const grace = room.disconnectGrace.get(seat);
    if (!grace) return false;
    clearTimeout(grace.handle);
    room.disconnectGrace.delete(seat);
    this.onEvent(tableId, "player_reconnected", { seat, userId: grace.userId });
    return true;
  }

  /* ═══════════ ROOM EMPTY AUTO-CLOSE ═══════════ */

  checkRoomEmpty(tableId: string, currentPlayerCount: number, onDestroy: () => void): void {
    const room = this.rooms.get(tableId);
    if (!room) return;

    if (currentPlayerCount === 0) {
      if (!room.emptySince) {
        room.emptySince = Date.now();
        room.emptyTimerHandle = setTimeout(() => {
          // Check again in case someone joined
          this.onEvent(tableId, "room_auto_close_check", {});
          // The server should call finalizeAutoClose after verifying
        }, ROOM_EMPTY_TTL_MS);
        this.onEvent(tableId, "room_empty_countdown", { ttlMs: ROOM_EMPTY_TTL_MS });
      }
    } else {
      // Cancel empty timer
      if (room.emptySince) {
        room.emptySince = null;
        if (room.emptyTimerHandle) {
          clearTimeout(room.emptyTimerHandle);
          room.emptyTimerHandle = null;
        }
      }
    }
  }

  finalizeAutoClose(tableId: string, currentPlayerCount: number): boolean {
    const room = this.rooms.get(tableId);
    if (!room) return false;

    if (currentPlayerCount > 0) {
      // Someone rejoined, cancel
      room.emptySince = null;
      return false;
    }

    // For safety: if hand is active, be more conservative
    if (room.handActive) {
      // Extend TTL
      room.emptyTimerHandle = setTimeout(() => {
        this.onEvent(tableId, "room_auto_close_check", {});
      }, ROOM_EMPTY_TTL_MS);
      return false;
    }

    this.addLog(room, "SYSTEM_MESSAGE", { message: "Room auto-closed (empty)" });
    room.status = "CLOSED";
    this.onEvent(tableId, "room_destroyed", {});
    this.deleteRoom(tableId);
    return true;
  }

  /* ═══════════ ROOM LOG ═══════════ */

  addLog(room: ManagedRoom, type: RoomLogEventType, data: {
    actorId?: string; actorName?: string;
    targetId?: string; targetName?: string;
    message: string; payload?: Record<string, unknown>;
  }): RoomLogEntry {
    const entry: RoomLogEntry = {
      id: randomUUID().slice(0, 8),
      timestamp: Date.now(),
      type,
      ...data,
    };
    room.log.push(entry);
    // Trim log
    if (room.log.length > MAX_LOG_ENTRIES) {
      room.log = room.log.slice(-MAX_LOG_ENTRIES);
    }
    this.onEvent(room.tableId, "room_log", entry);
    return entry;
  }

  /* ═══════════ STATE EXPORT ═══════════ */

  getFullState(tableId: string): RoomFullState | null {
    const room = this.rooms.get(tableId);
    if (!room) return null;

    return {
      tableId: room.tableId,
      roomCode: room.roomCode,
      roomName: room.roomName,
      settings: { ...room.settings },
      ownership: { ...room.ownership },
      status: room.status,
      banList: [...room.banList],
      timer: room.timer ? { ...room.timer } : null,
      log: room.log.slice(-50), // Send last 50 entries to client
      emptySince: room.emptySince,
    };
  }

  /* ═══════════ HELPERS ═══════════ */

  private emitRoomUpdate(room: ManagedRoom): void {
    room.updatedAt = new Date().toISOString();
    this.onEvent(room.tableId, "room_state_update", this.getFullState(room.tableId));
  }

  private emitTimerUpdate(room: ManagedRoom): void {
    if (room.timer) {
      this.onEvent(room.tableId, "timer_update", { ...room.timer });
    }
  }
}
