#!/usr/bin/env tsx
/**
 * Self-Play Orchestrator — Automated multi-room bot training pipeline.
 *
 * Creates rooms on the game server, spawns bots to play against each other,
 * monitors training sample collection, and triggers model training at milestones.
 * Dynamically scales rooms up/down based on available RAM and server count.
 *
 * Usage:
 *   pnpm --filter bot-client self-play
 *   pnpm --filter bot-client self-play -- --rooms auto --servers "4000,4001,4002"
 *   pnpm --filter bot-client self-play -- --rooms 12 --max-rooms-per-server 4 --servers "4000,4001,4002,4003,4004,4005"
 *   pnpm --filter bot-client self-play -- --ram-target 0.90 --per-bot-mb 120
 *
 * Prerequisites: game server must be running (pnpm --filter game-server dev)
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readdirSync, readFileSync, existsSync, statSync, openSync, readSync, closeSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { freemem, totalmem } from 'node:os';
import { fileURLToPath } from 'node:url';
import { io, type Socket } from 'socket.io-client';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..', '..');
const DATA_DIR = join(ROOT, 'data');
const BOT_MAIN = join(__dirname, 'main.ts');

// ── Constants ──

const DEFAULT_PER_BOT_GB = 0.08;           // ~80 MB per bot process (tsx shared runtime)
const DEFAULT_RAM_TARGET = 0.95;           // use up to 95% of total RAM
const DEFAULT_MAX_ROOMS_PER_SERVER = 10;   // Node.js event-loop safety cap per server
const SCALE_CHECK_MS = 30_000;             // check every 30 seconds

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
  rooms: number | 'auto';
  maxRoomsPerServer: number;
  ramTarget: number;
  perBotMb: number;
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

  const rawRooms = args['rooms'] ?? 'auto';
  const rooms: number | 'auto' = rawRooms === 'auto'
    ? 'auto'
    : Math.max(1, parseInt(rawRooms, 10));

  return {
    servers,
    botsPerRoom: parseInt(args['bots-per-room'] ?? '6', 10),
    trainEvery: parseInt(args['train-every'] ?? '50000', 10),
    target: parseInt(args['target'] ?? '1000000', 10),
    bigBlind: parseInt(args['big-blind'] ?? '100', 10),
    buyIn: parseInt(args['buy-in'] ?? '10000', 10),
    dashboardPort: parseInt(args['dashboard-port'] ?? '3456', 10),
    mode: (args['mode'] ?? 'play') as 'train' | 'play',
    version: (args['version'] ?? 'v1') as 'v1' | 'v2',
    rooms,
    maxRoomsPerServer: parseInt(args['max-rooms-per-server'] ?? String(DEFAULT_MAX_ROOMS_PER_SERVER), 10),
    ramTarget: parseFloat(args['ram-target'] ?? String(DEFAULT_RAM_TARGET)),
    perBotMb: parseFloat(args['per-bot-mb'] ?? String(DEFAULT_PER_BOT_GB * 1024)),
  };
}

function calcIdealRooms(botsPerRoom: number, currentRooms: number, config: SelfPlayConfig): number {
  const perBotGB = config.perBotMb / 1024;
  const perRoomGB = botsPerRoom * perBotGB;

  // RAM-based limit
  const totalGB = totalmem() / (1024 ** 3);
  const usedGB = totalGB - freemem() / (1024 ** 3);
  const budgetGB = totalGB * config.ramTarget;
  const ourUsageGB = currentRooms * perRoomGB;
  const availableGB = budgetGB - (usedGB - ourUsageGB);
  const ramLimit = Math.floor(availableGB / perRoomGB);

  // Server-capacity limit
  const serverLimit = config.servers.length * config.maxRoomsPerServer;

  return Math.min(Math.max(1, ramLimit), serverLimit);
}

// ── Profiles to rotate across seats ──

const PLAY_PROFILES = [
  'gto_balanced', 'lag', 'tag', 'nit', 'limp_fish',
  'gto_balanced', 'lag', 'tag', 'nit',
];

// TRAIN mode: all GTO-balanced for clean, representative game states
const TRAIN_PROFILES = [
  'gto_balanced', 'gto_balanced', 'gto_balanced',
  'gto_balanced', 'gto_balanced', 'gto_balanced',
  'gto_balanced', 'gto_balanced', 'gto_balanced',
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
    const files = readdirSync(dataDir).filter(f => f.endsWith('.jsonl'));
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
          if (buf[i] === 0x0A) { // '\n'
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

/** Count samples grouped by street using fast string matching (no JSON.parse). */
function countSamplesByStreet(dataDir: string = DATA_DIR): Record<string, number> {
  const counts: Record<string, number> = { PREFLOP: 0, FLOP: 0, TURN: 0, RIVER: 0 };
  try {
    if (!existsSync(dataDir)) return counts;
    const files = readdirSync(dataDir).filter(f => f.endsWith('.jsonl'));
    for (const file of files) {
      const content = readFileSync(join(dataDir, file), 'utf-8');
      const lines = content.split('\n');
      for (const line of lines) {
        if (!line) continue;
        if (line.includes('"s":"PREFLOP"')) counts.PREFLOP++;
        else if (line.includes('"s":"FLOP"')) counts.FLOP++;
        else if (line.includes('"s":"TURN"')) counts.TURN++;
        else if (line.includes('"s":"RIVER"')) counts.RIVER++;
      }
    }
  } catch { /* ignore */ }
  return counts;
}

// ── LiveRoom: bundles all resources for one room ──

interface LiveRoom {
  index: number;
  serverUrl: string;
  roomCode: string;
  tableId: string;
  socket: Socket;
  children: ChildProcess[];
}

let roomCounter = 0; // monotonically increasing room index

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

  // Configure for maximum speed
  socket.emit('update_settings', {
    tableId,
    settings: {
      autoStartNextHand: true,
      showdownSpeed: 'turbo',
      actionTimerSeconds: 2,
      maxConsecutiveTimeouts: 9999,
      rebuyAllowed: true,
    },
  });

  // Spawn bots
  const children: ChildProcess[] = [];
  for (let i = 0; i < config.botsPerRoom; i++) {
    const seat = i + 1;
    const profile = BOT_PROFILES[(idx * config.botsPerRoom + i) % BOT_PROFILES.length];

    await new Promise(r => setTimeout(r, i === 0 ? 0 : 150));

    const args = [
      'tsx', BOT_MAIN,
      '--server', serverUrl,
      '--room', roomCode,
      '--seat', String(seat),
      '--buyin', String(config.buyIn),
      '--profile', profile,
      '--delay', '0',
      '--mode', config.mode,
      '--version', config.version,
      '--name', `SP-${profile}-s${seat}`,
      '--userId', `sp-${profile}-${seat}-${Date.now()}`,
    ];

    const child = spawn('npx', args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: resolve(__dirname, '..'),
      shell: true,
    });

    const prefix = `[r${idx}/s${seat}]`;
    child.stdout?.on('data', (data: Buffer) => {
      for (const line of data.toString().split('\n').filter(l => l.trim())) {
        if (line.includes('Connected') || line.includes('Joined') || line.includes('Sitting') ||
            line.includes('Stats:') || line.includes('Model') ||
            line.includes('error') || line.includes('Error')) {
          console.log(`  ${prefix} ${line.trim()}`);
        }
      }
    });

    child.stderr?.on('data', (data: Buffer) => {
      const text = data.toString().trim();
      if (text && !text.includes('ExperimentalWarning') && !text.includes('--experimental')
          && !text.includes('npm warn')) {
        console.error(`  ${prefix} ERR: ${text}`);
      }
    });

    // Auto-restart crashed bots
    child.on('exit', (code) => {
      if (code !== 0 && code !== null) {
        log(`Bot crashed r${idx}/s${seat}/${profile}, restarting...`);
        const replacement = spawn('npx', args, {
          stdio: ['ignore', 'pipe', 'pipe'],
          cwd: resolve(__dirname, '..'),
          shell: true,
        });
        const ci = children.indexOf(child);
        if (ci !== -1) children[ci] = replacement;
        addEvent('RESTART', 'train', `Bot restarted: s${seat}/${profile} in ${roomCode}`);
      }
    });

    children.push(child);
  }

  // Auto-approve all rebuy (deposit) requests from bots
  socket.on('deposit_request_pending', (data: { orderId: string; seat: number; amount: number }) => {
    log(`Auto-approving rebuy: room ${roomCode} seat ${data.seat} amount ${data.amount}`);
    socket.emit('approve_deposit', { tableId, orderId: data.orderId });
  });

  // Start first hand after bots connect
  setTimeout(() => socket.emit('start_hand', { tableId }), 1500);

  const port = new URL(serverUrl).port;
  log(`Room ${roomCode} live on :${port}: ${config.botsPerRoom} bots, autoDeal=on`);
  return { index: idx, serverUrl, roomCode, tableId, socket, children };
}

function teardownRoom(room: LiveRoom): void {
  log(`Tearing down room ${room.roomCode}...`);
  for (const child of room.children) {
    try { child.kill('SIGTERM'); } catch {}
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
    const trainerArgs = [
      'tsx', trainerScript,
      '--v2', '--data', v2DataDir, '--out', v2OutPath,
    ];
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
  streetCounts: Record<string, number>;
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

  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    if (req.url === '/api/stats') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
      res.end(JSON.stringify(dashboardState));
    } else {
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'Pragma': 'no-cache',
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

// ── Main ──

async function main(): Promise<void> {
  const config = parseArgs();

  // Set profile list based on mode
  BOT_PROFILES = config.mode === 'train' ? TRAIN_PROFILES : PLAY_PROFILES;

  // Data directory depends on version
  const activeDataDir = config.version === 'v2' ? join(DATA_DIR, 'v2') : DATA_DIR;

  console.log('');
  log('╔══════════════════════════════════════════════════╗');
  log('║       CardPilot Self-Play Training Pipeline      ║');
  log('╚══════════════════════════════════════════════════╝');
  const freeGB = freemem() / (1024 ** 3);
  const initialRooms = config.rooms === 'auto'
    ? calcIdealRooms(config.botsPerRoom, 0, config)
    : config.rooms;
  if (config.rooms !== 'auto') {
    const ramEstimate = calcIdealRooms(config.botsPerRoom, 0, config);
    if (config.rooms > ramEstimate) {
      log(`⚠ WARNING: --rooms ${config.rooms} exceeds RAM estimate (${ramEstimate}). Proceeding anyway.`);
    }
  }
  log(`Servers:      ${config.servers.join(', ')}`);
  log(`Mode:         ${config.mode} | Version: ${config.version}`);
  log(`Profiles:     ${config.mode === 'train' ? 'all gto_balanced (TRAIN)' : 'mixed (PLAY)'}`);
  log(`Free RAM:     ${freeGB.toFixed(1)} GB`);
  log(`Initial rooms: ${initialRooms} (${initialRooms * config.botsPerRoom} bots)`);
  log(`Room cap:     ${config.servers.length} servers × ${config.maxRoomsPerServer}/server = ${config.servers.length * config.maxRoomsPerServer} max`);
  log(`Rooms mode:   ${config.rooms === 'auto' ? 'auto (RAM + server-count bounded)' : `fixed (${config.rooms})`}`);
  log(`Auto-scale:   ON (every ${SCALE_CHECK_MS / 60000} min, RAM ≤ ${config.ramTarget * 100}%)`);
  log(`Train every:  ${formatNumber(config.trainEvery)} samples`);
  log(`Target:       ${formatNumber(config.target)} samples`);
  console.log('');

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
  addEvent('START', 'milestone', `Pipeline started (${config.version}/${config.mode}) — ${formatNumber(initialSamples)} existing, ${config.servers.length} servers, cap ${config.servers.length * config.maxRoomsPerServer} rooms`);
  startDashboardServer(config.dashboardPort);

  // State
  const liveRooms: LiveRoom[] = [];
  let isTraining = false;
  let nextTrainThreshold = Math.ceil((initialSamples + 1) / config.trainEvery) * config.trainEvery;
  let isShuttingDown = false;
  let isScaling = false;

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

  // ── Spawn initial rooms (round-robin across servers) ──
  for (let r = 0; r < initialRooms; r++) {
    const serverUrl = config.servers[r % config.servers.length];
    try {
      const room = await spawnRoom(config, serverUrl);
      liveRooms.push(room);
      syncDashboardRooms(liveRooms, config.botsPerRoom);
      const port = new URL(serverUrl).port;
      addEvent('ROOM', 'success', `Room ${room.roomCode} on :${port} (${config.botsPerRoom} bots)`);
      if (r < initialRooms - 1) await new Promise(r => setTimeout(r, 1000));
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
      const totalGB = totalmem() / (1024 ** 3);
      const currentFreeGB = freemem() / (1024 ** 3);
      const usagePct = ((totalGB - currentFreeGB) / totalGB) * 100;
      dashboardState.freeRAM = currentFreeGB;

      const ideal = config.rooms === 'auto'
        ? calcIdealRooms(config.botsPerRoom, liveRooms.length, config)
        : config.rooms;
      log(`[auto-scale] RAM: ${currentFreeGB.toFixed(1)} GB free (${usagePct.toFixed(0)}% used) | rooms: ${liveRooms.length} → ideal: ${ideal}`);

      // Scale UP (round-robin across servers)
      if (ideal > liveRooms.length) {
        const toAdd = ideal - liveRooms.length;
        for (let i = 0; i < toAdd; i++) {
          const serverUrl = config.servers[(liveRooms.length + i) % config.servers.length];
          try {
            const room = await spawnRoom(config, serverUrl);
            liveRooms.push(room);
            syncDashboardRooms(liveRooms, config.botsPerRoom);
            const port = new URL(serverUrl).port;
            addEvent('SCALE', 'success', `Scaled UP → ${liveRooms.length} rooms on :${port} (${currentFreeGB.toFixed(1)} GB free)`);
            log(`[auto-scale] +1 room on :${port} → ${liveRooms.length} total`);
            await new Promise(r => setTimeout(r, 1000));
          } catch (err) {
            log(`[auto-scale] Failed to add room: ${(err as Error).message}`);
            break;
          }
        }
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

    const currentSamples = countSamples(activeDataDir);
    const newSamples = currentSamples - initialSamples;
    const elapsedHours = (Date.now() - startTime) / 3_600_000;
    const rate = elapsedHours > 0.001 ? newSamples / elapsedHours : 0;
    const remaining = config.target - currentSamples;
    const etaHours = rate > 0 ? remaining / rate : Infinity;
    const deltaSinceLast = currentSamples - lastSampleCount;

    const progress = Math.min(100, (currentSamples / config.target) * 100);
    const bar = '█'.repeat(Math.floor(progress / 5)) + '░'.repeat(20 - Math.floor(progress / 5));
    const ramGB = (freemem() / (1024 ** 3)).toFixed(1);

    log(
      `[${bar}] ${progress.toFixed(1)}% | ` +
      `${formatNumber(currentSamples)} / ${formatNumber(config.target)} (+${formatNumber(deltaSinceLast)}) | ` +
      `${formatNumber(Math.round(rate))}/hr | ` +
      `ETA: ${remaining > 0 ? formatDuration(etaHours) : 'DONE!'} | ` +
      `${liveRooms.length} rooms | RAM: ${ramGB} GB`
    );

    // Update dashboard
    dashboardState.currentSamples = currentSamples;
    dashboardState.newThisSession = newSamples;
    dashboardState.rate = rate;
    dashboardState.etaHours = etaHours;
    dashboardState.elapsedHours = elapsedHours;
    dashboardState.nextTrainThreshold = nextTrainThreshold;
    dashboardState.freeRAM = parseFloat(ramGB);
    dashboardState.history.push({ t: Date.now(), samples: currentSamples });
    if (dashboardState.history.length > 500) dashboardState.history.shift();
    dashboardState.streetCounts = countSamplesByStreet(activeDataDir);

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
  }, 10_000);

  // ── Graceful shutdown ──
  function shutdown(): void {
    if (isShuttingDown) return;
    isShuttingDown = true;

    log('Shutting down...');
    clearInterval(monitorInterval);
    clearInterval(scaleInterval);

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
