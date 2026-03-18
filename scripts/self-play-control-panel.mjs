import { execFile, spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { URL } from 'node:url';
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = resolve(__dirname, '..');

const PANEL_PORT = parseInt(process.env.SELF_PLAY_PANEL_PORT ?? '3460', 10);
const PANEL_HOST = '127.0.0.1';

const CONFIG_PATH = join(ROOT_DIR, 'data', 'self-play-panel-config.json');
const LOG_PATH = join(ROOT_DIR, 'logs', 'self-play-panel.log');
const HTML_PATH = join(__dirname, 'self-play-control-panel.html');
const MAX_LOG_LINES = 1200;
const MAX_LOG_LINE_CHARS = 800;

const DEFAULT_CONFIG = Object.freeze({
  serverCount: 32,
  startPort: 4000,
  rooms: 360,
  maxRoomsPerServer: 120,
  mode: 'train',
  version: 'v2',
  target: 5000000,
  trainEvery: 5000000,
  dashboardPort: 3456,
  disableSupabase: true,
  logLevel: 'warn',
  showdownTimeoutSec: 1,
  runCountTimeoutSec: 1,
});

/** @type {string[]} */
const logRing = [];
/** @type {import("node:child_process").ChildProcess | null} */
let managedChild = null;
/** @type {number | null} */
let managedPid = null;
let startedAtMs = 0;
let activeConfig = loadConfig();
let cpuSample = null;
let latestCpuUsagePct = null;
let cpuSamplerBusy = false;

const CPU_SAMPLE_INTERVAL_MS = 2000;
const CPU_EMA_ALPHA = 0.8;

function ensureParentDir(filePath) {
  mkdirSync(dirname(filePath), { recursive: true });
}

function pushLog(message) {
  const raw = String(message ?? '');
  const compact =
    raw.length > MAX_LOG_LINE_CHARS ? `${raw.slice(0, MAX_LOG_LINE_CHARS)} ...[truncated]` : raw;
  const line = `[${new Date().toISOString()}] ${compact}`;
  logRing.push(line);
  if (logRing.length > MAX_LOG_LINES) logRing.splice(0, logRing.length - MAX_LOG_LINES);
  ensureParentDir(LOG_PATH);
  appendFileSync(LOG_PATH, `${line}\n`, 'utf8');
}

function toInt(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function normalizeConfig(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  return {
    serverCount: toInt(source.serverCount, DEFAULT_CONFIG.serverCount, 1, 128),
    startPort: toInt(source.startPort, DEFAULT_CONFIG.startPort, 1024, 65500),
    rooms: toInt(source.rooms, DEFAULT_CONFIG.rooms, 1, 2000),
    maxRoomsPerServer: toInt(source.maxRoomsPerServer, DEFAULT_CONFIG.maxRoomsPerServer, 1, 500),
    mode: source.mode === 'play' ? 'play' : 'train',
    version: source.version === 'v1' ? 'v1' : 'v2',
    target: toInt(source.target, DEFAULT_CONFIG.target, 1000, 2000000000),
    trainEvery: toInt(source.trainEvery, DEFAULT_CONFIG.trainEvery, 1000, 2000000000),
    dashboardPort: toInt(source.dashboardPort, DEFAULT_CONFIG.dashboardPort, 1024, 65500),
    disableSupabase: source.disableSupabase !== false,
    logLevel: source.logLevel === 'error' ? 'error' : source.logLevel === 'info' ? 'info' : 'warn',
    showdownTimeoutSec: toInt(source.showdownTimeoutSec, DEFAULT_CONFIG.showdownTimeoutSec, 1, 30),
    runCountTimeoutSec: toInt(source.runCountTimeoutSec, DEFAULT_CONFIG.runCountTimeoutSec, 1, 30),
  };
}

function loadConfig() {
  if (!existsSync(CONFIG_PATH)) return { ...DEFAULT_CONFIG };
  try {
    const parsed = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
    return normalizeConfig({ ...DEFAULT_CONFIG, ...parsed });
  } catch (error) {
    pushLog(`config load failed: ${error.message}`);
    return { ...DEFAULT_CONFIG };
  }
}

function saveConfig(config) {
  const normalized = normalizeConfig(config);
  ensureParentDir(CONFIG_PATH);
  writeFileSync(CONFIG_PATH, `${JSON.stringify(normalized, null, 2)}\n`, 'utf8');
  return normalized;
}

function isRunning() {
  return Boolean(managedChild && managedChild.exitCode == null && !managedChild.killed);
}

function chunkedStream(stream, onLine) {
  let buffer = '';
  stream.on('data', (data) => {
    buffer += data.toString('utf8');
    const parts = buffer.split(/\r?\n/);
    buffer = parts.pop() ?? '';
    for (const line of parts) {
      if (line.trim().length > 0) onLine(line);
    }
  });
  stream.on('end', () => {
    if (buffer.trim().length > 0) onLine(buffer);
  });
}

function buildClusterArgs(config) {
  return [
    'run',
    'self-play:cluster',
    '--',
    '--server-count',
    String(config.serverCount),
    '--start-port',
    String(config.startPort),
    '--rooms',
    String(config.rooms),
    '--max-rooms-per-server',
    String(config.maxRoomsPerServer),
    '--mode',
    config.mode,
    '--version',
    config.version,
    '--target',
    String(config.target),
    '--train-every',
    String(config.trainEvery),
    '--dashboard-port',
    String(config.dashboardPort),
  ];
}

function buildEnv(config) {
  const env = { ...process.env };
  env.CARDPILOT_LOG_LEVEL = config.logLevel;
  env.SHOWDOWN_DECISION_TIMEOUT_SECONDS = String(config.showdownTimeoutSec);
  env.RUN_COUNT_DECISION_TIMEOUT_SECONDS = String(config.runCountTimeoutSec);
  if (config.disableSupabase) env.DISABLE_SUPABASE = '1';
  else delete env.DISABLE_SUPABASE;
  return env;
}

function startManagedProcess(config) {
  if (isRunning()) throw new Error('Self-play is already running.');
  const normalized = saveConfig(config);
  activeConfig = normalized;

  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const args = buildClusterArgs(normalized);
  const env = buildEnv(normalized);
  let child;
  if (process.platform === 'win32') {
    const cmdline = [npmCmd, ...args].join(' ');
    child = spawn('cmd.exe', ['/d', '/s', '/c', cmdline], {
      cwd: ROOT_DIR,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
  } else {
    child = spawn(npmCmd, args, {
      cwd: ROOT_DIR,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
  }

  managedChild = child;
  managedPid = child.pid ?? null;
  startedAtMs = Date.now();
  pushLog(`start pid=${managedPid ?? 'n/a'} args=${args.join(' ')}`);

  if (child.stdout) chunkedStream(child.stdout, (line) => pushLog(`[cluster] ${line}`));
  if (child.stderr) chunkedStream(child.stderr, (line) => pushLog(`[cluster:err] ${line}`));

  child.on('exit', (code, signal) => {
    pushLog(`exit pid=${managedPid ?? 'n/a'} code=${code ?? 'null'} signal=${signal ?? 'null'}`);
    managedChild = null;
    managedPid = null;
    startedAtMs = 0;
  });

  child.on('error', (error) => {
    pushLog(`spawn error: ${error.message}`);
  });

  return { pid: managedPid, config: normalized };
}

function stopManagedProcess() {
  const pid = managedPid ?? managedChild?.pid ?? null;
  if (pid == null) return false;

  pushLog(`stop requested pid=${pid}`);
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true });
  } else {
    try {
      process.kill(-pid, 'SIGTERM');
    } catch {
      try {
        process.kill(pid, 'SIGTERM');
      } catch {
        // ignore
      }
    }
  }

  managedChild = null;
  managedPid = null;
  startedAtMs = 0;
  return true;
}

function readCpuTimes() {
  const cpus = os.cpus();
  let idle = 0;
  let total = 0;
  for (const cpu of cpus) {
    idle += cpu.times.idle;
    total += cpu.times.idle + cpu.times.user + cpu.times.nice + cpu.times.sys + cpu.times.irq;
  }
  return { idle, total };
}

function sampleCpuUsageFallback() {
  const now = readCpuTimes();
  if (!cpuSample) {
    cpuSample = now;
    return null;
  }
  const totalDiff = now.total - cpuSample.total;
  const idleDiff = now.idle - cpuSample.idle;
  cpuSample = now;
  if (totalDiff <= 0) return null;
  const usage = (1 - idleDiff / totalDiff) * 100;
  return Number(usage.toFixed(1));
}

function smoothCpuUsage(nextSample) {
  if (!Number.isFinite(nextSample)) return;
  const clipped = Math.max(0, Math.min(100, nextSample));
  if (latestCpuUsagePct == null) {
    latestCpuUsagePct = Number(clipped.toFixed(1));
    return;
  }
  const blended = latestCpuUsagePct * (1 - CPU_EMA_ALPHA) + clipped * CPU_EMA_ALPHA;
  latestCpuUsagePct = Number(blended.toFixed(1));
}

function readWindowsCpuPct() {
  return new Promise((resolve) => {
    execFile(
      'powershell',
      [
        '-NoProfile',
        '-Command',
        "$s=(Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples; $s[$s.Count-1].CookedValue",
      ],
      {
        windowsHide: true,
        timeout: 2500,
      },
      (error, stdout) => {
        if (error) {
          resolve(null);
          return;
        }
        const text = String(stdout ?? '').trim();
        const parsed = Number.parseFloat(text);
        resolve(Number.isFinite(parsed) ? parsed : null);
      },
    );
  });
}

async function refreshCpuUsage() {
  if (cpuSamplerBusy) return;
  cpuSamplerBusy = true;
  try {
    let sampled = null;
    if (process.platform === 'win32') {
      sampled = await readWindowsCpuPct();
    }
    if (sampled == null) {
      sampled = sampleCpuUsageFallback();
    }
    if (sampled != null) {
      smoothCpuUsage(sampled);
    }
  } finally {
    cpuSamplerBusy = false;
  }
}

function getSystemSummary() {
  const totalMem = os.totalmem();
  const freeMem = os.freemem();
  const usedMem = totalMem - freeMem;
  return {
    cpuUsagePct: latestCpuUsagePct ?? sampleCpuUsageFallback(),
    totalMemGb: Number((totalMem / 1024 ** 3).toFixed(1)),
    usedMemGb: Number((usedMem / 1024 ** 3).toFixed(1)),
    freeMemGb: Number((freeMem / 1024 ** 3).toFixed(1)),
  };
}

async function fetchDashboardSummary(port) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/api/stats`, {
      signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) {
      return { reachable: false, error: `HTTP ${response.status}` };
    }
    const stats = await response.json();
    return {
      reachable: true,
      rooms: Array.isArray(stats.rooms) ? stats.rooms.length : 0,
      servers: Array.isArray(stats.rooms)
        ? new Set(stats.rooms.map((room) => room.server).filter(Boolean)).size
        : 0,
      rate: Number(Math.round(stats.rate ?? 0)),
      samples: Number(stats.currentSamples ?? 0),
      newThisSession: Number(stats.newThisSession ?? 0),
      watch: Array.isArray(stats.rooms) ? stats.rooms.filter((room) => room.watchdog).length : 0,
      warn: Array.isArray(stats.rooms) ? stats.rooms.filter((room) => room.warning).length : 0,
      freeRAM: Number(
        (stats.freeRAM ?? 0).toFixed ? stats.freeRAM.toFixed(1) : (stats.freeRAM ?? 0),
      ),
      elapsedHours: Number(stats.elapsedHours ?? 0),
      etaHours: Number(stats.etaHours ?? 0),
      dashboardUrl: `http://localhost:${port}`,
    };
  } catch (error) {
    return { reachable: false, error: error.message };
  }
}

function getLogTail(lines = 200) {
  const count = Math.max(10, Math.min(1000, Number.parseInt(String(lines), 10) || 200));
  return logRing.slice(-count);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk.toString('utf8');
      if (raw.length > 1_000_000) reject(new Error('Payload too large.'));
    });
    req.on('end', () => resolve(raw));
    req.on('error', reject);
  });
}

function sendJson(res, statusCode, payload) {
  const json = JSON.stringify(payload);
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate',
    Pragma: 'no-cache',
  });
  res.end(json);
}

async function parseRequestJson(req) {
  const raw = await readBody(req);
  if (!raw.trim()) return {};
  return JSON.parse(raw);
}

async function buildStatusPayload({ includeLogs = false } = {}) {
  const running = isRunning();
  const payload = {
    running,
    pid: managedPid,
    startedAt: startedAtMs || null,
    uptimeSec: running ? Math.floor((Date.now() - startedAtMs) / 1000) : 0,
    config: activeConfig,
    system: getSystemSummary(),
    dashboard: await fetchDashboardSummary(activeConfig.dashboardPort),
  };
  if (includeLogs) payload.logs = getLogTail(120);
  return payload;
}

const html = readFileSync(HTML_PATH, 'utf8');

setInterval(() => {
  refreshCpuUsage().catch(() => {});
}, CPU_SAMPLE_INTERVAL_MS);
refreshCpuUsage().catch(() => {});

const server = createServer(async (req, res) => {
  try {
    if (!req.url) {
      sendJson(res, 400, { ok: false, error: 'Invalid request.' });
      return;
    }

    const url = new URL(req.url, `http://${PANEL_HOST}:${PANEL_PORT}`);

    if (req.method === 'GET' && url.pathname === '/') {
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        Pragma: 'no-cache',
      });
      res.end(html);
      return;
    }

    if (req.method === 'GET' && url.pathname === '/api/config') {
      sendJson(res, 200, { ok: true, config: activeConfig });
      return;
    }

    if (req.method === 'POST' && url.pathname === '/api/config') {
      const payload = await parseRequestJson(req);
      activeConfig = saveConfig({ ...activeConfig, ...(payload.config ?? payload) });
      pushLog('config saved');
      sendJson(res, 200, { ok: true, config: activeConfig });
      return;
    }

    if (req.method === 'GET' && url.pathname === '/api/status') {
      const includeLogs = url.searchParams.get('logs') === '1';
      sendJson(res, 200, { ok: true, ...(await buildStatusPayload({ includeLogs })) });
      return;
    }

    if (req.method === 'GET' && url.pathname === '/api/logs') {
      const lines = url.searchParams.get('lines');
      sendJson(res, 200, { ok: true, logs: getLogTail(lines ?? 120) });
      return;
    }

    if (req.method === 'POST' && url.pathname === '/api/start') {
      const payload = await parseRequestJson(req);
      const requested = normalizeConfig({ ...activeConfig, ...(payload.config ?? payload) });
      const started = startManagedProcess(requested);
      sendJson(res, 200, { ok: true, started });
      return;
    }

    if (req.method === 'POST' && url.pathname === '/api/stop') {
      const stopped = stopManagedProcess();
      sendJson(res, 200, { ok: true, stopped });
      return;
    }

    if (req.method === 'POST' && url.pathname === '/api/restart') {
      const payload = await parseRequestJson(req);
      const requested = normalizeConfig({ ...activeConfig, ...(payload.config ?? payload) });
      stopManagedProcess();
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const started = startManagedProcess(requested);
      sendJson(res, 200, { ok: true, started });
      return;
    }

    sendJson(res, 404, { ok: false, error: 'Not found.' });
  } catch (error) {
    sendJson(res, 500, { ok: false, error: error.message });
  }
});

server.listen(PANEL_PORT, PANEL_HOST, () => {
  pushLog(`panel started on http://${PANEL_HOST}:${PANEL_PORT}`);
  console.log(`Self-play control panel: http://${PANEL_HOST}:${PANEL_PORT}`);
});
