#!/usr/bin/env tsx
/**
 * Self-Play Orchestrator — Automated multi-room bot training pipeline.
 *
 * Uses IN-PROCESS bots (all bots share one Node.js process and model).
 * This is ~16x more RAM efficient than child-process bots.
 *
 * Usage:
 *   npx tsx apps/bot-client/src/self-play.ts --mode train --version v2 --servers 4000,4001,4002
 *
 * Prerequisites: game server must be running
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import {
  readdirSync,
  readFileSync,
  existsSync,
  statSync,
  openSync,
  readSync,
  closeSync,
} from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { freemem, totalmem } from 'node:os';
import { monitorEventLoopDelay } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import { io, type Socket } from 'socket.io-client';
import { PokerBot } from './main.js';
import { loadModel, type MLP } from '@cardpilot/fast-model';
import {
  getEvTeacherQualityState,
  setEvTeacherQualityProfile,
  type EvTeacherQualityProfile,
} from './ev-teacher.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..', '..');
const DATA_DIR = join(ROOT, 'data');

// ── Constants ──

const PER_BOT_GB = 0.005; // ~5 MB per in-process bot (shared model)
const RAM_TARGET_USAGE = 0.85; // use up to 85% of total RAM
const RAM_CRITICAL_PCT = 0.92; // emergency scale-down threshold
const DEFAULT_MAX_ROOMS_PER_SERVER = 30; // single server event-loop cap
const SCALE_CHECK_MS = 30_000; // check every 30 seconds
const MONITOR_INTERVAL_MS = 30_000;
const SCALE_STEP_LIMIT = 1;
const EVENT_LOOP_CRITICAL_P99_MS = 350;

// ── CLI args ──

interface SelfPlayConfig {
  servers: string[];
  botsPerRoom: number;
  trainEvery: number;
  target: number;
  bigBlind: number;
  buyIn: number;
  dashboardPort: number;
  mode: 'train' | 'play';
  version: 'v1' | 'v2' | 'v3';
  minRate: number; // samples/hour threshold (0 = disabled)
  minRateGraceMinutes: number; // how long low-rate must persist before recovery
  recoverRooms: number; // rooms to recycle per recovery action
  recoverCooldownMinutes: number; // min minutes between recovery actions
  maxRoomsPerServer: number;
  shards: number;
  shardIndex: number;
  qualityCooldownMinutes: number;
  shardWorker: boolean;
}

function parseArgs(): SelfPlayConfig {
  const argv = process.argv.slice(2).filter((a) => a !== '--');
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--') && argv[i].length > 2) {
      args[argv[i].slice(2)] = argv[i + 1] ?? '';
      i++;
    }
  }

  // Support multiple servers: --servers "4000,4001,4002" or --servers "http://...,http://..."
  const rawServers = args['servers'] ?? args['server'] ?? '4000,4001,4002';
  const servers = rawServers.split(',').map((s) => {
    s = s.trim();
    if (/^\d+$/.test(s)) return `http://127.0.0.1:${s}`;
    return s;
  });

  return {
    servers,
    botsPerRoom: parseInt(args['bots-per-room'] ?? '6', 10),
    trainEvery: parseInt(args['train-every'] ?? '50000', 10),
    target: parseInt(args['target'] ?? '1000000', 10),
    bigBlind: parseInt(args['big-blind'] ?? '100', 10),
    buyIn: parseInt(args['buy-in'] ?? '10000', 10),
    dashboardPort: parseInt(args['dashboard-port'] ?? '3456', 10),
    mode: (args['mode'] ?? 'play') as 'train' | 'play',
    version: (args['version'] ?? 'v1') as 'v1' | 'v2' | 'v3',
    minRate: parseFloat(args['min-rate'] ?? '0'),
    minRateGraceMinutes: parseInt(args['min-rate-grace-min'] ?? '4', 10),
    recoverRooms: parseInt(args['recover-rooms'] ?? '1', 10),
    recoverCooldownMinutes: parseInt(args['recover-cooldown-min'] ?? '5', 10),
    maxRoomsPerServer: parseInt(
      args['max-rooms-per-server'] ?? String(DEFAULT_MAX_ROOMS_PER_SERVER),
      10,
    ),
    shards: Math.max(1, parseInt(args['shards'] ?? '1', 10)),
    shardIndex: Math.max(0, parseInt(args['shard-index'] ?? '0', 10)),
    qualityCooldownMinutes: Math.max(1, parseInt(args['quality-cooldown-min'] ?? '2', 10)),
    shardWorker: args['shard-worker'] === '1',
  };
}

function calcIdealRooms(
  botsPerRoom: number,
  currentRooms: number,
  numServers: number,
  maxRoomsPerServer: number,
): number {
  const totalGB = totalmem() / 1024 ** 3;
  const usedGB = totalGB - freemem() / 1024 ** 3;
  const budgetGB = totalGB * RAM_TARGET_USAGE;
  const ourUsageGB = currentRooms * botsPerRoom * PER_BOT_GB;
  const availableGB = budgetGB - (usedGB - ourUsageGB);
  const perRoomGB = botsPerRoom * PER_BOT_GB;
  const ramRooms = Math.floor(availableGB / perRoomGB);
  const serverCap = maxRoomsPerServer * numServers;
  return Math.max(1, Math.min(ramRooms, serverCap));
}

// ── Profiles to rotate across seats ──

const PLAY_PROFILES = [
  'gto_balanced',
  'lag',
  'tag',
  'nit',
  'limp_fish',
  'gto_balanced',
  'lag',
  'tag',
  'nit',
];

// TRAIN mode: all GTO-balanced for clean, representative game states
const TRAIN_PROFILES = [
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
  'gto_balanced',
];

// Active profile list (set in main based on config.mode)
let BOT_PROFILES = PLAY_PROFILES;

// ── Logging ──

function log(msg: string): void {
  const ts = new Date().toISOString().slice(11, 23);
  console.log(`[${ts}] [self-play] ${msg}`);
}

// ── Count samples in data directory ──

/**
 * Count lines in JSONL files by scanning for newline bytes.
 * Much faster than readFileSync + split — avoids UTF-8 decoding and string allocation.
 */
function countSamples(dataDir: string = DATA_DIR): number {
  try {
    if (!existsSync(dataDir)) return 0;
    const files = readdirSync(dataDir).filter((f) => f.endsWith('.jsonl'));
    let total = 0;
    const chunkSize = 65536; // 64 KB read chunks
    const buf = Buffer.alloc(chunkSize);

    for (const file of files) {
      const filePath = join(dataDir, file);
      const size = statSync(filePath).size;
      if (size === 0) continue;

      const fd = openSync(filePath, 'r');
      let pos = 0;
      let lastCharWasNewline = true; // track whether we ended on a newline

      while (pos < size) {
        const bytesRead = readSync(fd, buf, 0, chunkSize, pos);
        for (let i = 0; i < bytesRead; i++) {
          if (buf[i] === 0x0a) {
            // '\n'
            total++;
            lastCharWasNewline = true;
          } else {
            lastCharWasNewline = false;
          }
        }
        pos += bytesRead;
      }

      // Count last line if file doesn't end with newline
      if (!lastCharWasNewline) total++;
      closeSync(fd);
    }
    return total;
  } catch {
    return 0;
  }
}

interface SampleCounterState {
  total: number;
  offsets: Map<string, number>;
}

function initializeSampleCounter(dataDir: string = DATA_DIR): SampleCounterState {
  const total = countSamples(dataDir);
  const offsets = new Map<string, number>();
  try {
    if (existsSync(dataDir)) {
      const files = readdirSync(dataDir).filter((f) => f.endsWith('.jsonl'));
      for (const file of files) {
        const filePath = join(dataDir, file);
        offsets.set(filePath, statSync(filePath).size);
      }
    }
  } catch {
    /* ignore */
  }
  return { total, offsets };
}

/** Incremental sample counter: reads only appended bytes since last poll. */
function updateSampleCounter(counter: SampleCounterState, dataDir: string = DATA_DIR): number {
  try {
    if (!existsSync(dataDir)) return counter.total;
    const files = readdirSync(dataDir).filter((f) => f.endsWith('.jsonl'));
    for (const file of files) {
      const filePath = join(dataDir, file);
      const size = statSync(filePath).size;
      const prev = counter.offsets.get(filePath) ?? 0;
      if (size <= prev) {
        counter.offsets.set(filePath, size);
        continue;
      }

      const bytesToRead = size - prev;
      const buf = Buffer.alloc(bytesToRead);
      const fd = openSync(filePath, 'r');
      readSync(fd, buf, 0, bytesToRead, prev);
      closeSync(fd);

      for (let i = 0; i < bytesToRead; i++) {
        if (buf[i] === 0x0a) counter.total++;
      }
      counter.offsets.set(filePath, size);
    }
  } catch {
    /* ignore */
  }
  return counter.total;
}

/**
 * Incremental street counter — only reads bytes added since last call.
 * Avoids re-reading the entire dataset every monitor tick.
 */
const _streetOffsets = new Map<string, number>(); // filePath → last read offset
const _streetCounts = { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 };
const _streetCountsInitialized = false;

function countSamplesByStreet(dataDir: string = DATA_DIR): Record<string, number> {
  try {
    if (!existsSync(dataDir)) return { ..._streetCounts };
    const files = readdirSync(dataDir).filter((f) => f.endsWith('.jsonl'));

    for (const file of files) {
      const filePath = join(dataDir, file);
      const size = statSync(filePath).size;
      const lastOffset = _streetOffsets.get(filePath) ?? 0;
      if (size <= lastOffset) continue; // no new data

      // Read only new bytes
      const bytesToRead = size - lastOffset;
      const buf = Buffer.alloc(bytesToRead);
      const fd = openSync(filePath, 'r');
      readSync(fd, buf, 0, bytesToRead, lastOffset);
      closeSync(fd);

      const chunk = buf.toString('utf-8');
      // Count street markers in new data
      let pos = 0;
      while ((pos = chunk.indexOf('"s":"PREFLOP"', pos)) !== -1) {
        _streetCounts.PREFLOP++;
        pos++;
      }
      pos = 0;
      while ((pos = chunk.indexOf('"s":"FLOP"', pos)) !== -1) {
        _streetCounts.FLOP++;
        pos++;
      }
      pos = 0;
      while ((pos = chunk.indexOf('"s":"TURN"', pos)) !== -1) {
        _streetCounts.TURN++;
        pos++;
      }
      pos = 0;
      while ((pos = chunk.indexOf('"s":"RIVER"', pos)) !== -1) {
        _streetCounts.RIVER++;
        pos++;
      }

      _streetOffsets.set(filePath, size);
    }
  } catch {
    /* ignore */
  }
  return { ..._streetCounts };
}

// ── LiveRoom: bundles all resources for one room ──

interface LiveRoom {
  index: number;
  serverUrl: string;
  roomCode: string;
  tableId: string;
  socket: Socket;
  bots: PokerBot[];
  healthCheckTimer?: ReturnType<typeof setInterval>;
}

let roomCounter = 0; // monotonically increasing room index
let sharedModel: MLP | null = null; // shared model loaded once, used by all in-process bots
let activeDataDir: string = DATA_DIR; // set in main()

async function spawnRoom(config: SelfPlayConfig, serverUrl: string): Promise<LiveRoom> {
  const idx = roomCounter++;

  const socket = await new Promise<Socket>((res, rej) => {
    const s = io(serverUrl, {
      auth: {
        displayName: `SelfPlay-Host-${idx}`,
        userId: `self-play-host-${idx}-${Date.now()}`,
      },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 2000,
      reconnectionAttempts: 10,
    });
    const timer = setTimeout(() => {
      s.disconnect();
      rej(new Error('Connection timeout'));
    }, 10_000);
    s.on('connect', () => {
      clearTimeout(timer);
      res(s);
    });
    s.on('connect_error', (err) => log(`Connection error (room ${idx}): ${err.message}`));
  });

  const { tableId, roomCode } = await new Promise<{ tableId: string; roomCode: string }>(
    (res, rej) => {
      const timer = setTimeout(() => rej(new Error('Room creation timeout')), 15_000);
      socket.once('room_created', (data: { tableId: string; roomCode: string }) => {
        clearTimeout(timer);
        res(data);
      });
      socket.once('error_event', (data: { message: string }) => {
        clearTimeout(timer);
        rej(new Error(data.message));
      });
      socket.emit('create_room', {
        roomName: `Self-Play Room ${idx}`,
        maxPlayers: 6,
        smallBlind: Math.floor(config.bigBlind / 2),
        bigBlind: config.bigBlind,
        isPublic: false,
        buyInMin: config.bigBlind * 20,
        buyInMax: config.bigBlind * 200,
      });
    },
  );

  // Configure for maximum speed (selfPlayTurbo = zero delays)
  socket.emit('update_settings', {
    tableId,
    settings: {
      autoStartNextHand: true,
      showdownSpeed: 'turbo',
      selfPlayTurbo: true,
      actionTimerSeconds: 1,
      maxConsecutiveTimeouts: 100,
    },
  });

  // Spawn in-process bots (no child processes — all bots run in this event loop)
  const bots: PokerBot[] = [];
  for (let i = 0; i < config.botsPerRoom; i++) {
    const seat = i + 1;
    const profile = BOT_PROFILES[(idx * config.botsPerRoom + i) % BOT_PROFILES.length];

    const bot = new PokerBot({
      server: serverUrl,
      room: roomCode,
      seat,
      buyin: config.buyIn,
      profile,
      delay: 0,
      mode: config.mode,
      version: 'v3',
      name: `SP-${profile}-s${seat}`,
      userId: `sp-${profile}-${seat}-${Date.now()}`,
      sharedModel,
      dataDir: activeDataDir,
      skipPersistStats: true,
      quiet: true,
    });

    bots.push(bot);
  }

  // Start first hand after bots connect
  setTimeout(() => socket.emit('start_hand', { tableId }), 2500);

  // Health check: periodically restart stalled rooms (all bots busted → no hands dealing)
  // The host socket emits start_hand every 15s. If a hand is already running, server ignores it.
  // If room is stuck (busted bots got approved rebuys), this kicks off applyApprovedRebuys → new hand.
  const healthCheckTimer = setInterval(() => {
    socket.emit('start_hand', { tableId });
  }, 15_000);

  const port = new URL(serverUrl).port;
  log(`Room ${roomCode} live on :${port}: ${config.botsPerRoom} in-process bots, autoDeal=on`);
  return { index: idx, serverUrl, roomCode, tableId, socket, bots, healthCheckTimer };
}

function teardownRoom(room: LiveRoom): void {
  log(`Tearing down room ${room.roomCode}...`);
  if (room.healthCheckTimer) clearInterval(room.healthCheckTimer);
  for (const bot of room.bots) {
    bot.destroy();
  }
  try {
    room.socket.emit('close_room', { tableId: room.tableId });
    room.socket.disconnect();
  } catch {}
}

// ── Run the trainer ──

function runTrainer(): Promise<void> {
  return new Promise((res, rej) => {
    log('========================================');
    log('  TRAINING TRIGGERED');
    log('========================================');

    const child = spawn('npx', ['tsx', join(ROOT, 'packages', 'fast-model', 'src', 'trainer.ts')], {
      stdio: 'inherit',
      cwd: ROOT,
      shell: true,
    });

    child.on('exit', (code) => {
      if (code === 0) {
        log('  TRAINING COMPLETE — model updated');
        log('========================================');
        res();
      } else {
        rej(new Error(`Trainer exited with code ${code}`));
      }
    });
    child.on('error', rej);
  });
}

// ── Run V2 trainer ──

function runTrainerV2(): Promise<void> {
  return new Promise((res, rej) => {
    log('========================================');
    log('  V2 TRAINING TRIGGERED (warm-start enabled)');
    log('========================================');

    const v2DataDir = join(ROOT, 'data', 'v2');
    const v2OutPath = join(ROOT, 'packages', 'fast-model', 'models', 'model-v2-latest.json');
    const v1ModelPath = join(ROOT, 'packages', 'fast-model', 'models', 'model-latest.json');

    // Auto warm-start from V1 if V2 model doesn't exist yet
    const v2ModelExists = existsSync(v2OutPath);
    const trainerScript = join(ROOT, 'packages', 'fast-model', 'src', 'trainer.ts');
    const trainerArgs = ['tsx', trainerScript, '--v2', '--data', v2DataDir, '--out', v2OutPath];
    if (!v2ModelExists && existsSync(v1ModelPath)) {
      trainerArgs.push('--warm-start', v1ModelPath);
      log('  Using V1 model for warm-start transfer learning');
    }

    const child = spawn('npx', trainerArgs, {
      stdio: 'inherit',
      cwd: ROOT,
      shell: true,
    });

    child.on('exit', (code) => {
      if (code === 0) {
        log('  V2 TRAINING COMPLETE — model updated');
        log('========================================');
        res();
      } else {
        rej(new Error(`V2 trainer exited with code ${code}`));
      }
    });
    child.on('error', rej);
  });
}

// ── Load metrics from JSON file ──

function loadMetrics(modelName: string): Record<string, unknown> | undefined {
  try {
    const metricsPath = join(ROOT, 'packages', 'fast-model', 'models', `${modelName}-metrics.json`);
    if (!existsSync(metricsPath)) return undefined;
    return JSON.parse(readFileSync(metricsPath, 'utf-8'));
  } catch {
    return undefined;
  }
}

// ── Format helpers ──

function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

function formatDuration(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 24) return `${hours.toFixed(1)} hrs`;
  return `${(hours / 24).toFixed(1)} days`;
}

// ── Dashboard state ──

interface DashboardEvent {
  time: string;
  badge: string;
  badgeClass: string;
  message: string;
}
interface RoomStats {
  roomCode: string;
  tableId: string;
  server: string;
  bots: { name: string; profile: string }[];
}
interface DashboardState {
  currentSamples: number;
  initialSamples: number;
  newThisSession: number;
  target: number;
  rate: number;
  etaHours: number;
  elapsedHours: number;
  isTraining: boolean;
  trainingSessions: number;
  trainEvery: number;
  nextTrainThreshold: number;
  freeRAM: number;
  rooms: RoomStats[];
  history: { t: number; samples: number }[];
  events: DashboardEvent[];
  pipelineVersion: 'v1' | 'v2' | 'v3';
  pipelineMode: 'train' | 'play';
  v1Metrics?: Record<string, unknown>;
  v2Metrics?: Record<string, unknown>;
  streetCounts: Record<string, number>;
}

const dashboardState: DashboardState = {
  currentSamples: 0,
  initialSamples: 0,
  newThisSession: 0,
  target: 1_000_000,
  rate: 0,
  etaHours: Infinity,
  elapsedHours: 0,
  isTraining: false,
  trainingSessions: 0,
  trainEvery: 50_000,
  nextTrainThreshold: 0,
  freeRAM: 0,
  rooms: [],
  history: [],
  events: [],
  pipelineVersion: 'v1',
  pipelineMode: 'play',
  streetCounts: { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 },
};

function addEvent(badge: string, badgeClass: string, message: string): void {
  const time = new Date().toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  dashboardState.events.unshift({ time, badge, badgeClass, message });
  if (dashboardState.events.length > 100) dashboardState.events.length = 100;
}

function syncDashboardRooms(liveRooms: LiveRoom[], botsPerRoom: number): void {
  dashboardState.rooms = liveRooms.map((r) => ({
    roomCode: r.roomCode,
    tableId: r.tableId,
    server: `:${new URL(r.serverUrl).port}`,
    bots: Array.from({ length: botsPerRoom }, (_, i) => {
      const profile = BOT_PROFILES[(r.index * botsPerRoom + i) % BOT_PROFILES.length];
      return { name: `SP-${profile}-s${i + 1}`, profile };
    }),
  }));
}

function startDashboardServer(port: number): void {
  const dashboardHtml = readFileSync(join(__dirname, 'dashboard.html'), 'utf-8');

  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    if (req.url === '/api/stats') {
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(JSON.stringify(dashboardState));
    } else {
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        Pragma: 'no-cache',
      });
      res.end(dashboardHtml);
    }
  });

  let dashPort = port;
  server.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE' && dashPort < port + 10) {
      dashPort++;
      log(`Dashboard port ${dashPort - 1} in use, trying ${dashPort}...`);
      server.listen(dashPort);
    }
  });
  server.listen(dashPort, () => log(`Dashboard running at http://localhost:${dashPort}`));
}

async function fetchShardStats(port: number): Promise<DashboardState | null> {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/stats`);
    if (!res.ok) return null;
    return (await res.json()) as DashboardState;
  } catch {
    return null;
  }
}

function mergeHistory(
  histories: Array<{ t: number; samples: number }[]>,
): Array<{ t: number; samples: number }> {
  const nonEmpty = histories.filter((h) => h.length > 0);
  if (nonEmpty.length === 0) return [];
  const minLen = Math.min(...nonEmpty.map((h) => h.length));
  const merged: Array<{ t: number; samples: number }> = [];
  for (let i = 0; i < minLen; i++) {
    let samples = 0;
    let t = 0;
    for (const h of nonEmpty) {
      const entry = h[h.length - minLen + i];
      samples += entry.samples;
      if (entry.t > t) t = entry.t;
    }
    merged.push({ t, samples });
  }
  return merged;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function aggregateShardStates(states: DashboardState[]): DashboardState {
  const active =
    states.length > 0
      ? states
      : [
          {
            ...dashboardState,
            currentSamples: 0,
            initialSamples: 0,
            newThisSession: 0,
            target: 0,
            rate: 0,
            etaHours: Infinity,
            elapsedHours: 0,
            isTraining: false,
            trainingSessions: 0,
            trainEvery: 0,
            nextTrainThreshold: 0,
            freeRAM: 0,
            rooms: [],
            history: [],
            events: [],
            streetCounts: { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 },
          },
        ];

  // Shards currently share the same dataset path, so progress metrics are global and duplicated.
  // Use one representative shard for dataset-global fields; sum only truly per-shard capacity fields.
  const primary = active.reduce(
    (best, s) => (s.currentSamples >= best.currentSamples ? s : best),
    active[0],
  );
  const totalCurrent = primary.currentSamples;
  const totalTarget = Math.max(...active.map((x) => x.target));
  const rateCandidates = active.map((x) => x.rate).filter((v) => Number.isFinite(v) && v > 0);
  const totalRate =
    rateCandidates.length > 0
      ? median(rateCandidates)
      : Math.max(...active.map((x) => (Number.isFinite(x.rate) ? x.rate : 0)));
  const totalInitial = primary.initialSamples;
  const totalNew = primary.newThisSession;
  const freeRamCandidates = active.map((x) => x.freeRAM).filter((v) => Number.isFinite(v) && v > 0);
  const remaining = Math.max(0, totalTarget - totalCurrent);
  const eta = totalRate > 0 ? remaining / totalRate : Infinity;

  return {
    ...primary,
    currentSamples: totalCurrent,
    initialSamples: totalInitial,
    newThisSession: totalNew,
    target: totalTarget,
    rate: totalRate,
    etaHours: eta,
    elapsedHours: Math.max(...active.map((x) => x.elapsedHours)),
    isTraining: active.some((x) => x.isTraining),
    trainingSessions: Math.max(...active.map((x) => x.trainingSessions)),
    trainEvery: Math.max(...active.map((x) => x.trainEvery)),
    nextTrainThreshold: Math.max(...active.map((x) => x.nextTrainThreshold)),
    freeRAM: freeRamCandidates.length > 0 ? Math.min(...freeRamCandidates) : 0,
    rooms: active.flatMap((x) => x.rooms ?? []),
    history: primary.history ?? mergeHistory(active.map((x) => x.history ?? [])),
    events: active.flatMap((x) => x.events ?? []).slice(0, 100),
    streetCounts: primary.streetCounts ?? { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 },
  };
}

function startAggregateDashboardServer(port: number, shardPorts: number[]): void {
  const dashboardHtml = readFileSync(join(__dirname, 'dashboard.html'), 'utf-8');
  const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
    if (req.url === '/api/stats') {
      const shardStates = await Promise.all(shardPorts.map((p) => fetchShardStats(p)));
      const activeStates = shardStates.filter((s): s is DashboardState => s != null);
      const merged = aggregateShardStates(activeStates);
      res.writeHead(200, {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      });
      res.end(JSON.stringify(merged));
      return;
    }
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      Pragma: 'no-cache',
    });
    res.end(dashboardHtml);
  });
  server.listen(port, () =>
    log(
      `Aggregate dashboard running at http://localhost:${port} (shards: ${shardPorts.join(',')})`,
    ),
  );
}

// ── Main ──

async function main(): Promise<void> {
  const config = parseArgs();

  // Parent mode: fan out multiple shard processes to use multi-core CPU.
  if (config.shards > 1 && config.shardIndex === 0 && !config.shardWorker) {
    log(`Launching ${config.shards} self-play shards...`);
    const shardPorts = Array.from(
      { length: config.shards },
      (_, i) => config.dashboardPort + i + 1,
    );
    startAggregateDashboardServer(config.dashboardPort, shardPorts);
    const children: ChildProcess[] = [];
    for (let i = 0; i < config.shards; i++) {
      const childArgs = [
        'tsx',
        join(__dirname, 'self-play.ts'),
        '--servers',
        config.servers.join(','),
        '--bots-per-room',
        String(config.botsPerRoom),
        '--train-every',
        String(config.trainEvery),
        '--target',
        String(config.target),
        '--big-blind',
        String(config.bigBlind),
        '--buy-in',
        String(config.buyIn),
        '--dashboard-port',
        String(shardPorts[i]),
        '--mode',
        config.mode,
        '--version',
        config.version,
        '--min-rate',
        String(config.minRate),
        '--min-rate-grace-min',
        String(config.minRateGraceMinutes),
        '--recover-rooms',
        String(config.recoverRooms),
        '--recover-cooldown-min',
        String(config.recoverCooldownMinutes),
        '--max-rooms-per-server',
        String(config.maxRoomsPerServer),
        '--quality-cooldown-min',
        String(config.qualityCooldownMinutes),
        '--shards',
        String(config.shards),
        '--shard-index',
        String(i),
        '--shard-worker',
        '1',
      ];
      const child = spawn('npx', childArgs, {
        stdio: 'inherit',
        cwd: ROOT,
        shell: true,
      });
      children.push(child);
    }

    const stopChildren = () => {
      for (const child of children) {
        try {
          child.kill('SIGTERM');
        } catch {}
      }
    };
    process.on('SIGINT', stopChildren);
    process.on('SIGTERM', stopChildren);
    await new Promise<void>(() => {});
    return;
  }

  // Worker mode: split work by shard index when possible.
  if (config.shards > 1) {
    const shardServers = config.servers.filter(
      (_, idx) => idx % config.shards === config.shardIndex,
    );
    if (shardServers.length > 0) config.servers = shardServers;
  }
  const isCoordinatorShard = config.shards <= 1 || config.shardIndex === 0;

  // Set profile list based on mode
  BOT_PROFILES = config.mode === 'train' ? TRAIN_PROFILES : PLAY_PROFILES;

  // Data directory depends on version (set module-level var for spawnRoom access)
  activeDataDir = config.version === 'v2' ? join(DATA_DIR, 'v2') : DATA_DIR;

  console.log('');

  // ── Supabase egress safeguard ──
  // Training generates thousands of hands/min. If game-server connects to
  // production Supabase, each hand triggers ~10 DB queries via emitLobbySnapshot()
  // which can burn through 130-390 GB/day of egress.
  if (process.env.DISABLE_SUPABASE !== '1') {
    log('');
    log('╔══════════════════════════════════════════════════════════════╗');
    log('║  ⚠  WARNING: DISABLE_SUPABASE is not set!                  ║');
    log('║                                                             ║');
    log('║  Training generates massive Supabase egress if game-server  ║');
    log('║  is connected to production. Start your game-server with:   ║');
    log('║                                                             ║');
    log('║    DISABLE_SUPABASE=1 npm run dev -w @cardpilot/game-server ║');
    log('║                                                             ║');
    log('║  Or set DISABLE_SUPABASE=1 in your shell environment.       ║');
    log('╚══════════════════════════════════════════════════════════════╝');
    log('');
  }

  log('╔══════════════════════════════════════════════════╗');
  log('║       CardPilot Self-Play Training Pipeline      ║');
  log('╚══════════════════════════════════════════════════╝');
  const freeGB = freemem() / 1024 ** 3;
  const initialRooms = calcIdealRooms(
    config.botsPerRoom,
    0,
    config.servers.length,
    config.maxRoomsPerServer,
  );
  log(`Servers:      ${config.servers.join(', ')}`);
  log(`Mode:         ${config.mode} | Version: ${config.version}`);
  log(`Profiles:     ${config.mode === 'train' ? 'all gto_balanced (TRAIN)' : 'mixed (PLAY)'}`);
  log(`Free RAM:     ${freeGB.toFixed(1)} GB`);
  log(`Initial rooms: ${initialRooms} (${initialRooms * config.botsPerRoom} in-process bots)`);
  log(
    `Room cap:     ${config.servers.length} servers × ${config.maxRoomsPerServer}/server = ${config.servers.length * config.maxRoomsPerServer} max`,
  );
  log(`Auto-scale:   ON (every ${SCALE_CHECK_MS / 60000} min, RAM ≤ ${RAM_TARGET_USAGE * 100}%)`);
  log(`Train every:  ${formatNumber(config.trainEvery)} samples`);
  log(`Target:       ${formatNumber(config.target)} samples`);
  console.log('');

  // ── Load shared model once for all in-process bots ──
  const modelPath = join(ROOT, 'models', 'cfr-combined-v3.json');
  sharedModel = loadModel(modelPath);
  log(`Shared model: ${sharedModel ? 'loaded' : 'not found (heuristic fallback)'}`);

  const sampleCounter = initializeSampleCounter(activeDataDir);
  const initialSamples = sampleCounter.total;
  log(`Existing samples: ${formatNumber(initialSamples)}`);
  if (config.minRate > 0) {
    log(
      `Min rate guard: ${formatNumber(Math.round(config.minRate))}/hr, grace=${config.minRateGraceMinutes}m, recover=${config.recoverRooms} room(s), cooldown=${config.recoverCooldownMinutes}m`,
    );
  } else {
    log('Min rate guard: disabled');
  }

  // Dashboard
  dashboardState.initialSamples = initialSamples;
  dashboardState.currentSamples = initialSamples;
  dashboardState.target = config.target;
  dashboardState.trainEvery = config.trainEvery;
  dashboardState.pipelineVersion = config.version;
  dashboardState.pipelineMode = config.mode;
  dashboardState.history.push({ t: Date.now(), samples: initialSamples });
  addEvent(
    'START',
    'milestone',
    `Pipeline started (${config.version}/${config.mode}) — ${formatNumber(initialSamples)} existing, ${config.servers.length} servers, cap ${config.servers.length * config.maxRoomsPerServer} rooms`,
  );
  startDashboardServer(config.dashboardPort);

  // State
  const liveRooms: LiveRoom[] = [];
  let isTraining = false;
  let nextTrainThreshold = Math.ceil((initialSamples + 1) / config.trainEvery) * config.trainEvery;
  let isShuttingDown = false;
  let isScaling = false;
  let lowRateSinceMs: number | null = null;
  let lastRecoveryAtMs = 0;
  const rollingHistory: { t: number; samples: number }[] = [
    { t: Date.now(), samples: initialSamples },
  ];
  let lastLoopP99Ms = 0;
  const eventLoopHist = monitorEventLoopDelay({ resolution: 20 });
  eventLoopHist.enable();
  let quality: EvTeacherQualityProfile = 'normal';
  let lastQualityChangeMs = 0;

  const dynamicQualityEnabled =
    config.mode === 'train' && config.version === 'v2' && config.minRate > 0;
  if (dynamicQualityEnabled) {
    setEvTeacherQualityProfile('normal');
    const q = getEvTeacherQualityState();
    log(`EV quality: ${q.profile} (${q.iterations} iters / ${q.timeLimitMs}ms)`);
  }

  // ── Centralized model hot-reload (every 5 min, updates all bots at once) ──
  let lastModelMtime = 0;
  try {
    lastModelMtime = statSync(modelPath).mtimeMs;
  } catch {}
  const modelReloadInterval = setInterval(
    () => {
      try {
        const mtime = statSync(modelPath).mtimeMs;
        if (mtime > lastModelMtime) {
          const newModel = loadModel(modelPath);
          if (newModel) {
            sharedModel = newModel;
            lastModelMtime = mtime;
            log('Shared model hot-reloaded — updating all bots');
            for (const room of liveRooms) {
              for (const bot of room.bots) bot.setModel(sharedModel);
            }
          }
        }
      } catch {}
    },
    5 * 60 * 1000,
  );

  // ── Wait for all game servers to be ready ──
  log('Waiting for game servers...');
  for (const serverUrl of config.servers) {
    for (let attempt = 1; attempt <= 20; attempt++) {
      try {
        await fetch(serverUrl);
        log(`  ${serverUrl} — ready`);
        break;
      } catch {
        if (attempt === 20) log(`  ${serverUrl} — FAILED (continuing without it)`);
        else await new Promise((r) => setTimeout(r, 2000));
      }
    }
  }

  // ── Spawn initial rooms (round-robin across servers) ──
  for (let r = 0; r < initialRooms; r++) {
    const serverUrl = config.servers[r % config.servers.length];
    try {
      const room = await spawnRoom(config, serverUrl);
      liveRooms.push(room);
      syncDashboardRooms(liveRooms, config.botsPerRoom);
      const port = new URL(serverUrl).port;
      addEvent(
        'ROOM',
        'success',
        `Room ${room.roomCode} on :${port} (${config.botsPerRoom} in-process bots)`,
      );
    } catch (err) {
      log(`Failed to create room on ${serverUrl}: ${(err as Error).message}`);
    }
  }

  if (liveRooms.length === 0) {
    log('No rooms created. Exiting.');
    process.exit(1);
  }

  log('');
  log(`${liveRooms.length} rooms live. Auto-scaling enabled.`);
  log('');

  // ── Auto-scaler (every 10 min) ──
  const scaleInterval = setInterval(async () => {
    if (isShuttingDown || isScaling || isTraining) return;
    isScaling = true;

    try {
      const totalGB = totalmem() / 1024 ** 3;
      const currentFreeGB = freemem() / 1024 ** 3;
      const usagePct = ((totalGB - currentFreeGB) / totalGB) * 100;
      dashboardState.freeRAM = currentFreeGB;
      const loopCritical = lastLoopP99Ms >= EVENT_LOOP_CRITICAL_P99_MS;

      // Emergency scale-down if RAM critically high (prevent OOM/crash)
      if (usagePct / 100 >= RAM_CRITICAL_PCT && liveRooms.length > 1) {
        const room = liveRooms.pop()!;
        teardownRoom(room);
        syncDashboardRooms(liveRooms, config.botsPerRoom);
        log(
          `[auto-scale] EMERGENCY scale-down (RAM ${usagePct.toFixed(0)}%) → ${liveRooms.length} rooms`,
        );
        addEvent(
          'WARN',
          'error',
          `Emergency scale-down: RAM ${usagePct.toFixed(0)}% → ${liveRooms.length} rooms`,
        );
        isScaling = false;
        return;
      }

      const ideal = calcIdealRooms(
        config.botsPerRoom,
        liveRooms.length,
        config.servers.length,
        config.maxRoomsPerServer,
      );
      log(
        `[auto-scale] RAM: ${currentFreeGB.toFixed(1)} GB free (${usagePct.toFixed(0)}% used), loop p99=${lastLoopP99Ms.toFixed(1)}ms | rooms: ${liveRooms.length} → ideal: ${ideal}`,
      );

      // Scale UP (round-robin across servers)
      if (ideal > liveRooms.length && !loopCritical) {
        const toAdd = Math.min(SCALE_STEP_LIMIT, ideal - liveRooms.length);
        for (let i = 0; i < toAdd; i++) {
          const serverUrl = config.servers[(liveRooms.length + i) % config.servers.length];
          try {
            const room = await spawnRoom(config, serverUrl);
            liveRooms.push(room);
            syncDashboardRooms(liveRooms, config.botsPerRoom);
            const port = new URL(serverUrl).port;
            addEvent(
              'SCALE',
              'success',
              `Scaled UP → ${liveRooms.length} rooms on :${port} (${currentFreeGB.toFixed(1)} GB free)`,
            );
            log(`[auto-scale] +1 room on :${port} → ${liveRooms.length} total`);
            await new Promise((r) => setTimeout(r, 1000));
          } catch (err) {
            log(`[auto-scale] Failed to add room: ${(err as Error).message}`);
            break;
          }
        }
      }

      // Scale DOWN
      if ((ideal < liveRooms.length || loopCritical) && liveRooms.length > 1) {
        const toRemove = Math.min(
          SCALE_STEP_LIMIT,
          Math.max(liveRooms.length - ideal, loopCritical ? 1 : 0),
        );
        for (let i = 0; i < toRemove && liveRooms.length > 1; i++) {
          const room = liveRooms.pop()!;
          teardownRoom(room);
          syncDashboardRooms(liveRooms, config.botsPerRoom);
          log(`[auto-scale] -1 room (${room.roomCode}) → ${liveRooms.length} total`);
          addEvent(
            'SCALE',
            'error',
            `Scaled DOWN → ${liveRooms.length} rooms (RAM ${usagePct.toFixed(0)}%)`,
          );
        }
      }
    } catch (err) {
      log(`[auto-scale] Error: ${(err as Error).message}`);
    }

    isScaling = false;
  }, SCALE_CHECK_MS);

  // ── Monitor loop (every 30s) ──
  async function recoverLowRate(currentRollingRate: number): Promise<void> {
    if (isShuttingDown || isTraining || isScaling || liveRooms.length === 0) return;
    isScaling = true;
    try {
      const recycleCount = Math.max(1, Math.min(config.recoverRooms, liveRooms.length));
      addEvent(
        'RECOVER',
        'error',
        `Low rate ${formatNumber(Math.round(currentRollingRate))}/hr < ${formatNumber(Math.round(config.minRate))}/hr, recycling ${recycleCount} room(s)`,
      );
      log(
        `[watchdog] Low rate detected (${Math.round(currentRollingRate)}/hr). Recycling ${recycleCount} room(s)...`,
      );

      for (let i = 0; i < recycleCount; i++) {
        const oldRoom = liveRooms.pop();
        if (!oldRoom) break;
        const serverUrl = config.servers[(oldRoom.index + i) % config.servers.length];
        teardownRoom(oldRoom);
        try {
          const newRoom = await spawnRoom(config, serverUrl);
          liveRooms.push(newRoom);
        } catch (err) {
          log(`[watchdog] Failed to respawn room on ${serverUrl}: ${(err as Error).message}`);
        }
      }
      syncDashboardRooms(liveRooms, config.botsPerRoom);
      lastRecoveryAtMs = Date.now();
    } finally {
      isScaling = false;
    }
  }

  const startTime = Date.now();
  let lastSampleCount = initialSamples;

  const monitorInterval = setInterval(async () => {
    if (isShuttingDown) return;

    const now = Date.now();
    const currentSamples = updateSampleCounter(sampleCounter, activeDataDir);
    const newSamples = currentSamples - initialSamples;
    const elapsedHours = (now - startTime) / 3_600_000;
    const rate = elapsedHours > 0.001 ? newSamples / elapsedHours : 0;
    const remaining = config.target - currentSamples;
    const etaHours = rate > 0 ? remaining / rate : Infinity;
    const deltaSinceLast = currentSamples - lastSampleCount;
    const deltaRate = deltaSinceLast * (3_600_000 / MONITOR_INTERVAL_MS);

    rollingHistory.push({ t: now, samples: currentSamples });
    const rollingWindowMs = Math.max(config.minRateGraceMinutes * 60_000, 180_000);
    while (rollingHistory.length > 2 && rollingHistory[0].t < now - rollingWindowMs)
      rollingHistory.shift();
    const oldest = rollingHistory[0];
    const rollingElapsedHrs = Math.max((now - oldest.t) / 3_600_000, 1 / 3600);
    const rollingRate = (currentSamples - oldest.samples) / rollingElapsedHrs;
    lastLoopP99Ms = eventLoopHist.percentile(99) / 1e6;
    eventLoopHist.reset();

    const progress = Math.min(100, (currentSamples / config.target) * 100);
    const bar = '█'.repeat(Math.floor(progress / 5)) + '░'.repeat(20 - Math.floor(progress / 5));
    const ramGB = (freemem() / 1024 ** 3).toFixed(1);

    log(
      `[${bar}] ${progress.toFixed(1)}% | ` +
        `${formatNumber(currentSamples)} / ${formatNumber(config.target)} (+${formatNumber(deltaSinceLast)}) | ` +
        `${formatNumber(Math.round(rate))}/hr avg | ` +
        `${formatNumber(Math.round(deltaRate))}/hr now | ` +
        `ETA: ${remaining > 0 ? formatDuration(etaHours) : 'DONE!'} | ` +
        `${liveRooms.length} rooms | RAM: ${ramGB} GB | loop p99=${lastLoopP99Ms.toFixed(1)}ms`,
    );

    // Update dashboard
    dashboardState.currentSamples = currentSamples;
    dashboardState.newThisSession = newSamples;
    // Dashboard should show near-real-time throughput, not startup-skewed cumulative average.
    dashboardState.rate = Number.isFinite(rollingRate) ? rollingRate : rate;
    dashboardState.etaHours = etaHours;
    dashboardState.elapsedHours = elapsedHours;
    dashboardState.nextTrainThreshold = nextTrainThreshold;
    dashboardState.freeRAM = parseFloat(ramGB);
    dashboardState.history.push({ t: Date.now(), samples: currentSamples });
    if (dashboardState.history.length > 500) dashboardState.history.shift();
    dashboardState.streetCounts = countSamplesByStreet(activeDataDir);

    lastSampleCount = currentSamples;

    if (dynamicQualityEnabled) {
      let targetQuality = quality;
      if (rollingRate < config.minRate * 0.8) targetQuality = 'low';
      else if (rollingRate > config.minRate * 1.25) targetQuality = 'high';
      else if (rollingRate >= config.minRate * 0.95 && quality === 'low') targetQuality = 'normal';
      else if (rollingRate <= config.minRate * 1.1 && quality === 'high') targetQuality = 'normal';

      const qualityCooldownMs = config.qualityCooldownMinutes * 60_000;
      if (targetQuality !== quality && now - lastQualityChangeMs >= qualityCooldownMs) {
        setEvTeacherQualityProfile(targetQuality);
        quality = targetQuality;
        lastQualityChangeMs = now;
        const q = getEvTeacherQualityState();
        addEvent(
          'QUALITY',
          'train',
          `EV quality → ${q.profile} (${q.iterations} iters / ${q.timeLimitMs}ms)`,
        );
        log(
          `[quality] EV teacher set to ${q.profile} (${q.iterations} iters / ${q.timeLimitMs}ms)`,
        );
      }
    }

    if (config.minRate > 0 && !isTraining && !isShuttingDown) {
      const below = rollingRate < config.minRate;
      if (below) {
        if (lowRateSinceMs == null) lowRateSinceMs = now;
      } else {
        lowRateSinceMs = null;
      }

      const graceMs = config.minRateGraceMinutes * 60_000;
      const cooldownMs = config.recoverCooldownMinutes * 60_000;
      const coolingDown = now - lastRecoveryAtMs < cooldownMs;
      const canRecoverRooms = !dynamicQualityEnabled || quality === 'low';
      if (
        lowRateSinceMs != null &&
        now - lowRateSinceMs >= graceMs &&
        !coolingDown &&
        canRecoverRooms
      ) {
        await recoverLowRate(rollingRate);
        lowRateSinceMs = null;
      }
    }

    // Target reached (coordinator shard only)
    if (isCoordinatorShard && currentSamples >= config.target) {
      log(`Target of ${formatNumber(config.target)} samples reached!`);
      addEvent('TARGET', 'milestone', `Target of ${formatNumber(config.target)} reached!`);
      if (!isTraining) {
        isTraining = true;
        dashboardState.isTraining = true;
        addEvent('TRAIN', 'train', `Final ${config.version} training triggered`);
        try {
          if (config.version === 'v2') await runTrainerV2();
          else await runTrainer();
          dashboardState.trainingSessions++;
          // Load metrics after training
          dashboardState.v1Metrics = loadMetrics('model-latest');
          dashboardState.v2Metrics = loadMetrics('model-v2-latest');
          addEvent('DONE', 'success', `Final ${config.version} training complete`);
        } catch {}
        isTraining = false;
        dashboardState.isTraining = false;
      }
      shutdown();
      return;
    }

    // Milestone training (coordinator shard only)
    if (isCoordinatorShard && currentSamples >= nextTrainThreshold && !isTraining) {
      isTraining = true;
      dashboardState.isTraining = true;
      nextTrainThreshold += config.trainEvery;
      dashboardState.nextTrainThreshold = nextTrainThreshold;
      addEvent(
        'TRAIN',
        'train',
        `${config.version.toUpperCase()} training at ${formatNumber(currentSamples)} samples`,
      );
      try {
        if (config.version === 'v2') await runTrainerV2();
        else await runTrainer();
        dashboardState.trainingSessions++;
        // Load metrics after training
        dashboardState.v1Metrics = loadMetrics('model-latest');
        dashboardState.v2Metrics = loadMetrics('model-v2-latest');
        addEvent(
          'DONE',
          'success',
          `${config.version.toUpperCase()} training complete — model updated`,
        );
      } catch (err) {
        log(`Training error (non-fatal): ${(err as Error).message}`);
        addEvent('ERROR', 'error', `Training failed: ${(err as Error).message}`);
      }
      isTraining = false;
      dashboardState.isTraining = false;
    }
  }, MONITOR_INTERVAL_MS);

  // ── Graceful shutdown ──
  function shutdown(): void {
    if (isShuttingDown) return;
    isShuttingDown = true;

    log('Shutting down...');
    clearInterval(monitorInterval);
    clearInterval(scaleInterval);
    clearInterval(modelReloadInterval);
    eventLoopHist.disable();

    for (const room of liveRooms) teardownRoom(room);

    const finalSamples = updateSampleCounter(sampleCounter, activeDataDir);
    const totalNew = finalSamples - initialSamples;
    const elapsed = (Date.now() - startTime) / 3_600_000;

    log('');
    log('╔══════════════════════════════════════════════════╗');
    log('║              Session Summary                     ║');
    log('╚══════════════════════════════════════════════════╝');
    log(`  Total samples:    ${formatNumber(finalSamples)}`);
    log(`  New this session: ${formatNumber(totalNew)}`);
    log(`  Duration:         ${formatDuration(elapsed)}`);
    log(`  Avg rate:         ${formatNumber(Math.round(totalNew / Math.max(elapsed, 0.01)))}/hr`);
    log('');

    setTimeout(() => process.exit(0), 2000);
  }

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
