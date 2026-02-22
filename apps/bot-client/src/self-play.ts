#!/usr/bin/env tsx
/**
 * Self-Play Orchestrator — Automated multi-room bot training pipeline.
 *
 * Creates rooms on the game server, spawns bots to play against each other,
 * monitors training sample collection, and triggers model training at milestones.
 * Dynamically scales rooms up/down based on available RAM.
 *
 * Usage:
 *   pnpm --filter bot-client self-play
 *   pnpm --filter bot-client self-play -- --rooms auto --server http://127.0.0.1:4000
 *
 * Prerequisites: game server must be running (pnpm --filter game-server dev)
 */

import { spawn } from 'node:child_process';
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { freemem, totalmem } from 'node:os';
import { fileURLToPath } from 'node:url';
import { io, type Socket } from 'socket.io-client';
import { PokerBot } from './main.js';
import { loadModel, type MLP } from '@cardpilot/fast-model';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..', '..');
const DATA_DIR = join(ROOT, 'data');

// ── Constants ──

const PER_BOT_GB = 0.005;          // ~5 MB per in-process bot (shared model, no process overhead)
const RAM_TARGET_USAGE = 0.85;     // use up to 85% of total RAM (safe with watchdog)
const SCALE_CHECK_MS = 30_000;     // check every 30s for faster scaling response
const RAM_CRITICAL_PCT = 0.92;     // emergency scale-down threshold

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
  version: 'v1' | 'v2';
}

function parseArgs(): SelfPlayConfig {
  const argv = process.argv.slice(2).filter(a => a !== '--');
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--') && argv[i].length > 2) {
      args[argv[i].slice(2)] = argv[i + 1] ?? '';
      i++;
    }
  }

  // Support multiple servers: --servers "4000,4001,4002" or --servers "http://...,http://..."
  const rawServers = args['servers'] ?? args['server'] ?? '4000,4001,4002';
  const servers = rawServers.split(',').map(s => {
    s = s.trim();
    if (/^\d+$/.test(s)) return `http://127.0.0.1:${s}`;
    return s;
  });

  return {
    servers,
    botsPerRoom: parseInt(args['bots-per-room'] ?? '6', 10),
    trainEvery: parseInt(args['train-every'] ?? '100000', 10),
    target: parseInt(args['target'] ?? '1000000', 10),
    bigBlind: parseInt(args['big-blind'] ?? '100', 10),
    buyIn: parseInt(args['buy-in'] ?? '10000', 10),
    dashboardPort: parseInt(args['dashboard-port'] ?? '3456', 10),
    mode: (args['mode'] ?? 'play') as 'train' | 'play',
    version: (args['version'] ?? 'v1') as 'v1' | 'v2',
  };
}

function calcIdealRooms(botsPerRoom: number, currentRooms: number = 0): number {
  const totalGB = totalmem() / (1024 ** 3);
  const usedGB = totalGB - freemem() / (1024 ** 3);
  const budgetGB = totalGB * RAM_TARGET_USAGE;       // 80% of total
  const ourUsageGB = currentRooms * botsPerRoom * PER_BOT_GB;
  const availableGB = budgetGB - (usedGB - ourUsageGB); // budget minus other processes
  const perRoomGB = botsPerRoom * PER_BOT_GB;
  const rooms = Math.floor(availableGB / perRoomGB);
  return Math.max(1, rooms);
}

// ── Profiles to rotate across seats ──

const PLAY_PROFILES = [
  'gto_balanced', 'lag', 'tag', 'nit', 'limp_fish',
  'gto_balanced', 'lag', 'tag', 'nit',
];

// TRAIN mode: mix GTO + postflop_trainer for balanced data collection
// postflop_trainers call loosely preflop → more multiway flops → more postflop samples
const TRAIN_PROFILES = [
  'gto_balanced', 'postflop_trainer', 'gto_balanced',
  'postflop_trainer', 'gto_balanced', 'postflop_trainer',
  'gto_balanced', 'postflop_trainer', 'gto_balanced',
];

// Active profile list (set in main based on config.mode)
let BOT_PROFILES = PLAY_PROFILES;

// ── Logging ──

function log(msg: string): void {
  const ts = new Date().toISOString().slice(11, 23);
  console.log(`[${ts}] [self-play] ${msg}`);
}

// ── Count samples in data directory ──

interface StreetCounts {
  total: number;
  PREFLOP: number;
  FLOP: number;
  TURN: number;
  RIVER: number;
}

function countSamples(dataDir: string = DATA_DIR): number {
  return countSamplesDetailed(dataDir).total;
}

// Incremental counter: cache file sizes to only re-read changed/new files
const _fileCache = new Map<string, { size: number; counts: StreetCounts }>();

function countSamplesDetailed(dataDir: string = DATA_DIR): StreetCounts {
  const counts: StreetCounts = { total: 0, PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 };
  try {
    if (!existsSync(dataDir)) return counts;
    const files = readdirSync(dataDir).filter(f => f.endsWith('.jsonl'));
    for (const file of files) {
      const fullPath = join(dataDir, file);
      const stat = statSync(fullPath);
      const cached = _fileCache.get(fullPath);

      // If file size unchanged, use cached counts
      if (cached && cached.size === stat.size) {
        counts.total += cached.counts.total;
        counts.PREFLOP += cached.counts.PREFLOP;
        counts.FLOP += cached.counts.FLOP;
        counts.TURN += cached.counts.TURN;
        counts.RIVER += cached.counts.RIVER;
        continue;
      }

      // Re-read changed file
      const fileCounts: StreetCounts = { total: 0, PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 };
      const content = readFileSync(fullPath, 'utf-8');
      const lines = content.split('\n');
      for (const line of lines) {
        if (!line.trim()) continue;
        fileCounts.total++;
        const sMatch = line.match(/"s":"(PREFLOP|FLOP|TURN|RIVER)"/);
        if (sMatch) {
          fileCounts[sMatch[1] as keyof Omit<StreetCounts, 'total'>]++;
        }
      }
      _fileCache.set(fullPath, { size: stat.size, counts: fileCounts });
      counts.total += fileCounts.total;
      counts.PREFLOP += fileCounts.PREFLOP;
      counts.FLOP += fileCounts.FLOP;
      counts.TURN += fileCounts.TURN;
      counts.RIVER += fileCounts.RIVER;
    }
  } catch {}
  return counts;
}

// ── LiveRoom: bundles all resources for one room ──

interface LiveRoom {
  index: number;
  serverUrl: string;
  roomCode: string;
  tableId: string;
  socket: Socket;
  bots: PokerBot[];
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
    const timer = setTimeout(() => { s.disconnect(); rej(new Error('Connection timeout')); }, 10_000);
    s.on('connect', () => { clearTimeout(timer); res(s); });
    s.on('connect_error', (err) => log(`Connection error (room ${idx}): ${err.message}`));
  });

  const { tableId, roomCode } = await new Promise<{ tableId: string; roomCode: string }>((res, rej) => {
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
  });

  // Configure for maximum speed (selfPlayTurbo = zero delays)
  socket.emit('update_settings', {
    tableId,
    settings: {
      autoStartNextHand: true,
      showdownSpeed: 'turbo',
      actionTimerSeconds: 1,          // selfPlayTurbo allows <5s; bots act in <50ms
      maxConsecutiveTimeouts: 100,
      selfPlayTurbo: true,            // zero showdown/runout delays
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
      version: config.version,
      name: `SP-${profile}-s${seat}`,
      userId: `sp-${profile}-${seat}-${Date.now()}`,
      sharedModel,
      dataDir: activeDataDir,
      skipPersistStats: true,
    });

    bots.push(bot);
  }

  // Start first hand after bots connect
  setTimeout(() => socket.emit('start_hand', { tableId }), 2500);

  const port = new URL(serverUrl).port;
  log(`Room ${roomCode} live on :${port}: ${config.botsPerRoom} in-process bots, autoDeal=on`);
  return { index: idx, serverUrl, roomCode, tableId, socket, bots };
}

function teardownRoom(room: LiveRoom): void {
  log(`Tearing down room ${room.roomCode}...`);
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

    const child = spawn('pnpm', ['--filter', 'fast-model', 'train'], {
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
    log('  V2 TRAINING TRIGGERED');
    log('========================================');

    const v2DataDir = join(ROOT, 'data', 'v2');
    const v2OutPath = join(ROOT, 'packages', 'fast-model', 'models', 'model-v2-latest.json');

    const child = spawn('pnpm', [
      '--filter', 'fast-model', 'train', '--',
      '--v2', '--data', v2DataDir, '--out', v2OutPath,
    ], {
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
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDuration(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 24) return `${hours.toFixed(1)} hrs`;
  return `${(hours / 24).toFixed(1)} days`;
}

// ── Dashboard state ──

interface DashboardEvent { time: string; badge: string; badgeClass: string; message: string; }
interface RoomStats { roomCode: string; tableId: string; server: string; bots: { name: string; profile: string }[]; }
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
  pipelineVersion: 'v1' | 'v2';
  pipelineMode: 'train' | 'play';
  v1Metrics?: Record<string, unknown>;
  v2Metrics?: Record<string, unknown>;
  streetCounts: { PREFLOP: number; FLOP: number; TURN: number; RIVER: number };
}

const dashboardState: DashboardState = {
  currentSamples: 0, initialSamples: 0, newThisSession: 0, target: 1_000_000,
  rate: 0, etaHours: Infinity, elapsedHours: 0,
  isTraining: false, trainingSessions: 0, trainEvery: 50_000, nextTrainThreshold: 0,
  freeRAM: 0,
  rooms: [], history: [], events: [],
  pipelineVersion: 'v1', pipelineMode: 'play',
  streetCounts: { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 },
};

function addEvent(badge: string, badgeClass: string, message: string): void {
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  dashboardState.events.unshift({ time, badge, badgeClass, message });
  if (dashboardState.events.length > 100) dashboardState.events.length = 100;
}

function syncDashboardRooms(liveRooms: LiveRoom[], botsPerRoom: number): void {
  dashboardState.rooms = liveRooms.map(r => ({
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

  let currentPort = port;
  const maxRetries = 5;

  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    if (req.url === '/api/stats') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      res.end(JSON.stringify(dashboardState));
    } else {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(dashboardHtml);
    }
  });

  server.listen(currentPort, () => log(`Dashboard running at http://localhost:${currentPort}`));
  server.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE' && currentPort < port + maxRetries) {
      currentPort++;
      log(`Dashboard port ${currentPort - 1} in use, trying ${currentPort}...`);
      server.listen(currentPort);
    } else if (err.code === 'EADDRINUSE') {
      log(`Dashboard: all ports ${port}-${currentPort} in use, giving up`);
    }
  });
}

// ── Main ──

async function main(): Promise<void> {
  const config = parseArgs();

  // Set profile list based on mode
  BOT_PROFILES = config.mode === 'train' ? TRAIN_PROFILES : PLAY_PROFILES;

  // Data directory depends on version (set module-level var for spawnRoom access)
  activeDataDir = config.version === 'v2' ? join(DATA_DIR, 'v2') : DATA_DIR;

  console.log('');
  log('╔══════════════════════════════════════════════════╗');
  log('║       CardPilot Self-Play Training Pipeline      ║');
  log('╚══════════════════════════════════════════════════╝');
  const freeGB = freemem() / (1024 ** 3);
  const initialRooms = calcIdealRooms(config.botsPerRoom);
  log(`Servers:      ${config.servers.join(', ')}`);
  log(`Mode:         ${config.mode} | Version: ${config.version}`);
  log(`Profiles:     ${config.mode === 'train' ? 'all gto_balanced (TRAIN)' : 'mixed (PLAY)'}`);
  log(`Free RAM:     ${freeGB.toFixed(1)} GB`);
  log(`Initial rooms: ${initialRooms} (${initialRooms * config.botsPerRoom} bots)`);
  log(`Auto-scale:   ON (every ${SCALE_CHECK_MS / 60000} min, RAM ≤ ${RAM_TARGET_USAGE * 100}%)`);
  log(`Train every:  ${formatNumber(config.trainEvery)} samples`);
  log(`Target:       ${formatNumber(config.target)} samples`);
  console.log('');

  // ── Load shared model once for all in-process bots ──
  const modelFileName = config.version === 'v2' ? 'model-v2-latest.json' : 'model-latest.json';
  const modelPath = join(ROOT, 'packages', 'fast-model', 'models', modelFileName);
  sharedModel = loadModel(modelPath);
  log(`Shared model: ${sharedModel ? 'loaded' : 'not found (heuristic fallback)'}`);

  const initialSamples = countSamples(activeDataDir);
  log(`Existing samples: ${formatNumber(initialSamples)}`);

  // Dashboard
  dashboardState.initialSamples = initialSamples;
  dashboardState.currentSamples = initialSamples;
  dashboardState.target = config.target;
  dashboardState.trainEvery = config.trainEvery;
  dashboardState.pipelineVersion = config.version;
  dashboardState.pipelineMode = config.mode;
  dashboardState.history.push({ t: Date.now(), samples: initialSamples });
  addEvent('START', 'milestone', `Pipeline started (${config.version}/${config.mode}) — ${formatNumber(initialSamples)} existing, ${config.servers.length} servers`);
  startDashboardServer(config.dashboardPort);

  // State
  const liveRooms: LiveRoom[] = [];
  let isTraining = false;
  let nextTrainThreshold = Math.ceil((initialSamples + 1) / config.trainEvery) * config.trainEvery;
  let isShuttingDown = false;
  let isScaling = false;

  // ── Centralized model hot-reload (every 5 min, updates all bots at once) ──
  let lastModelMtime = 0;
  try { lastModelMtime = statSync(modelPath).mtimeMs; } catch {}
  const modelReloadInterval = setInterval(() => {
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
  }, 5 * 60 * 1000);

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
        else await new Promise(r => setTimeout(r, 2000));
      }
    }
  }

  // ── Spawn initial rooms in parallel (round-robin across servers) ──
  const roomPromises = Array.from({ length: initialRooms }, (_, r) => {
    const serverUrl = config.servers[r % config.servers.length];
    return spawnRoom(config, serverUrl)
      .then(room => {
        liveRooms.push(room);
        syncDashboardRooms(liveRooms, config.botsPerRoom);
        const port = new URL(serverUrl).port;
        addEvent('ROOM', 'success', `Room ${room.roomCode} on :${port} (${config.botsPerRoom} in-process bots)`);
      })
      .catch(err => {
        log(`Failed to create room on ${serverUrl}: ${(err as Error).message}`);
      });
  });
  await Promise.allSettled(roomPromises);

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
      const totalGB = totalmem() / (1024 ** 3);
      const currentFreeGB = freemem() / (1024 ** 3);
      const usagePct = ((totalGB - currentFreeGB) / totalGB) * 100;
      dashboardState.freeRAM = currentFreeGB;

      // Emergency scale-down if RAM critically high (prevent OOM/crash)
      if (usagePct / 100 >= RAM_CRITICAL_PCT && liveRooms.length > 1) {
        const room = liveRooms.pop()!;
        teardownRoom(room);
        syncDashboardRooms(liveRooms, config.botsPerRoom);
        log(`[auto-scale] EMERGENCY scale-down (RAM ${usagePct.toFixed(0)}%) → ${liveRooms.length} rooms`);
        addEvent('WARN', 'error', `Emergency scale-down: RAM ${usagePct.toFixed(0)}% → ${liveRooms.length} rooms`);
        isScaling = false;
        return;
      }

      const ideal = calcIdealRooms(config.botsPerRoom, liveRooms.length);
      log(`[auto-scale] RAM: ${currentFreeGB.toFixed(1)} GB free (${usagePct.toFixed(0)}% used) | rooms: ${liveRooms.length} → ideal: ${ideal}`);

      // Scale UP in parallel (round-robin across servers)
      if (ideal > liveRooms.length) {
        const toAdd = ideal - liveRooms.length;
        const scalePromises = Array.from({ length: toAdd }, (_, i) => {
          const serverUrl = config.servers[(liveRooms.length + i) % config.servers.length];
          return spawnRoom(config, serverUrl)
            .then(room => {
              liveRooms.push(room);
              syncDashboardRooms(liveRooms, config.botsPerRoom);
              const port = new URL(serverUrl).port;
              addEvent('SCALE', 'success', `Scaled UP → ${liveRooms.length} rooms on :${port} (${currentFreeGB.toFixed(1)} GB free)`);
              log(`[auto-scale] +1 room on :${port} → ${liveRooms.length} total`);
            })
            .catch(err => {
              log(`[auto-scale] Failed to add room: ${(err as Error).message}`);
            });
        });
        await Promise.allSettled(scalePromises);
      }

      // Scale DOWN
      if (ideal < liveRooms.length && liveRooms.length > 1) {
        const toRemove = liveRooms.length - ideal;
        for (let i = 0; i < toRemove && liveRooms.length > 1; i++) {
          const room = liveRooms.pop()!;
          teardownRoom(room);
          syncDashboardRooms(liveRooms, config.botsPerRoom);
          log(`[auto-scale] -1 room (${room.roomCode}) → ${liveRooms.length} total`);
          addEvent('SCALE', 'error', `Scaled DOWN → ${liveRooms.length} rooms (RAM ${usagePct.toFixed(0)}%)`);
        }
      }
    } catch (err) {
      log(`[auto-scale] Error: ${(err as Error).message}`);
    }

    isScaling = false;
  }, SCALE_CHECK_MS);

  // ── Monitor loop (every 30s) ──
  const startTime = Date.now();
  let lastSampleCount = initialSamples;

  const monitorInterval = setInterval(async () => {
    if (isShuttingDown) return;

    const detailed = countSamplesDetailed(activeDataDir);
    const currentSamples = detailed.total;
    const newSamples = currentSamples - initialSamples;
    const elapsedHours = (Date.now() - startTime) / 3_600_000;
    const rate = elapsedHours > 0.001 ? newSamples / elapsedHours : 0;
    const remaining = config.target - currentSamples;
    const etaHours = rate > 0 ? remaining / rate : Infinity;
    const deltaSinceLast = currentSamples - lastSampleCount;

    const progress = Math.min(100, (currentSamples / config.target) * 100);
    const bar = '█'.repeat(Math.floor(progress / 5)) + '░'.repeat(20 - Math.floor(progress / 5));
    const ramGB = (freemem() / (1024 ** 3)).toFixed(1);

    const postflopTotal = detailed.FLOP + detailed.TURN + detailed.RIVER;
    const postflopPct = currentSamples > 0 ? (postflopTotal / currentSamples * 100).toFixed(1) : '0.0';

    log(
      `[${bar}] ${progress.toFixed(1)}% | ` +
      `${formatNumber(currentSamples)} (+${deltaSinceLast}) | ` +
      `${formatNumber(Math.round(rate))}/hr | ` +
      `ETA: ${remaining > 0 ? formatDuration(etaHours) : 'DONE!'} | ` +
      `${liveRooms.length} rooms | RAM: ${ramGB} GB`
    );
    log(
      `  Streets: PRE=${formatNumber(detailed.PREFLOP)} ` +
      `F=${formatNumber(detailed.FLOP)} T=${formatNumber(detailed.TURN)} R=${formatNumber(detailed.RIVER)} ` +
      `(postflop ${postflopPct}%)`
    );

    // Update dashboard
    dashboardState.currentSamples = currentSamples;
    dashboardState.newThisSession = newSamples;
    dashboardState.rate = rate;
    dashboardState.etaHours = etaHours;
    dashboardState.elapsedHours = elapsedHours;
    dashboardState.nextTrainThreshold = nextTrainThreshold;
    dashboardState.freeRAM = parseFloat(ramGB);
    dashboardState.streetCounts = {
      PREFLOP: detailed.PREFLOP,
      FLOP: detailed.FLOP,
      TURN: detailed.TURN,
      RIVER: detailed.RIVER,
    };
    dashboardState.history.push({ t: Date.now(), samples: currentSamples });
    if (dashboardState.history.length > 500) dashboardState.history.shift();

    lastSampleCount = currentSamples;

    // Target reached
    if (currentSamples >= config.target) {
      log(`Target of ${formatNumber(config.target)} samples reached!`);
      addEvent('TARGET', 'milestone', `Target of ${formatNumber(config.target)} reached!`);
      if (!isTraining) {
        isTraining = true;
        dashboardState.isTraining = true;
        addEvent('TRAIN', 'train', `Final ${config.version} training triggered`);
        try {
          if (config.version === 'v2') await runTrainerV2(); else await runTrainer();
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

    // Milestone training
    if (currentSamples >= nextTrainThreshold && !isTraining) {
      isTraining = true;
      dashboardState.isTraining = true;
      nextTrainThreshold += config.trainEvery;
      dashboardState.nextTrainThreshold = nextTrainThreshold;
      addEvent('TRAIN', 'train', `${config.version.toUpperCase()} training at ${formatNumber(currentSamples)} samples`);
      try {
        if (config.version === 'v2') await runTrainerV2(); else await runTrainer();
        dashboardState.trainingSessions++;
        // Load metrics after training
        dashboardState.v1Metrics = loadMetrics('model-latest');
        dashboardState.v2Metrics = loadMetrics('model-v2-latest');
        addEvent('DONE', 'success', `${config.version.toUpperCase()} training complete — model updated`);
      } catch (err) {
        log(`Training error (non-fatal): ${(err as Error).message}`);
        addEvent('ERROR', 'error', `Training failed: ${(err as Error).message}`);
      }
      isTraining = false;
      dashboardState.isTraining = false;
    }
  }, 30_000);

  // ── Graceful shutdown ──
  function shutdown(): void {
    if (isShuttingDown) return;
    isShuttingDown = true;

    log('Shutting down...');
    clearInterval(monitorInterval);
    clearInterval(scaleInterval);
    clearInterval(modelReloadInterval);

    for (const room of liveRooms) teardownRoom(room);

    const finalSamples = countSamples(activeDataDir);
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
