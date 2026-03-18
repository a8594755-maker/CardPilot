import { spawn } from 'node:child_process';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = resolve(__dirname, '..');
const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const npxCmd = process.platform === 'win32' ? 'npx.cmd' : 'npx';

function parseArgs(argv) {
  const result = {
    serverCount: 6,
    startPort: 4000,
    forwardedArgs: [],
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--server-count') {
      const next = argv[i + 1];
      if (!next) throw new Error('--server-count requires a value');
      const parsed = Number.parseInt(next, 10);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new Error(`--server-count must be a positive integer (received "${next}")`);
      }
      result.serverCount = parsed;
      i += 1;
      continue;
    }

    if (token === '--start-port') {
      const next = argv[i + 1];
      if (!next) throw new Error('--start-port requires a value');
      const parsed = Number.parseInt(next, 10);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new Error(`--start-port must be a positive integer (received "${next}")`);
      }
      result.startPort = parsed;
      i += 1;
      continue;
    }

    result.forwardedArgs.push(token);
  }

  return result;
}

function delay(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

function isPortListening(port, host = '127.0.0.1', timeoutMs = 500) {
  return new Promise((resolvePromise) => {
    const socket = new net.Socket();
    let settled = false;

    const done = (value) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolvePromise(value);
    };

    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(true));
    socket.once('timeout', () => done(false));
    socket.once('error', () => done(false));
    socket.connect(port, host);
  });
}

async function isServerHealthy(port, attempts = 2) {
  const url = `http://127.0.0.1:${port}/healthz`;
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url, {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) {
        await delay(200);
        continue;
      }
      const payload = await response.json().catch(() => null);
      if (payload?.ok === true && payload?.service === 'cardpilot-game-server') {
        return true;
      }
    } catch {
      // ignore and retry
    }
    await delay(200);
  }
  return false;
}

async function waitHealthy(port, attempts = 60, delayMs = 1000) {
  for (let i = 1; i <= attempts; i += 1) {
    if (await isServerHealthy(port, 1)) return true;
    if (i < attempts) await delay(delayMs);
  }
  return false;
}

function run(cmd, args, envOverride) {
  return spawn(cmd, args, {
    cwd: ROOT_DIR,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: {
      ...process.env,
      ...envOverride,
    },
  });
}

function terminate(child) {
  if (!child || child.killed) return;
  try {
    child.kill('SIGTERM');
  } catch {
    // no-op
  }
}

async function main() {
  const { serverCount, startPort, forwardedArgs } = parseArgs(process.argv.slice(2));
  const ports = Array.from({ length: serverCount }, (_, i) => startPort + i);
  const managedChildren = [];
  const serversCsv = ports.join(',');

  console.log(`[cluster] target: ${serverCount} servers on ports ${serversCsv}`);

  for (const port of ports) {
    const listening = await isPortListening(port);
    if (!listening) {
      console.log(`[cluster] starting game-server on :${port}`);
      const child = run(npmCmd, ['run', 'dev', '-w', '@cardpilot/game-server'], {
        PORT: String(port),
      });
      managedChildren.push({ port, child });
      continue;
    }

    if (await isServerHealthy(port, 2)) {
      console.log(`[cluster] reusing existing healthy game-server on :${port}`);
      continue;
    }

    throw new Error(`Port :${port} is occupied by a non-CardPilot process; cannot continue.`);
  }

  console.log('[cluster] waiting for servers to become healthy...');
  for (const port of ports) {
    const ok = await waitHealthy(port);
    if (!ok) {
      throw new Error(`Server on :${port} failed health checks`);
    }
    console.log(`[cluster] :${port} healthy`);
  }

  const selfPlayArgs = [
    'tsx',
    'apps/bot-client/src/self-play.ts',
    '--servers',
    serversCsv,
    ...forwardedArgs,
  ];

  console.log(`[cluster] launching self-play with --servers ${serversCsv}`);
  const selfPlay = run(npxCmd, selfPlayArgs);

  let shuttingDown = false;
  const shutdown = (exitCode = 0) => {
    if (shuttingDown) return;
    shuttingDown = true;
    terminate(selfPlay);
    for (const { child } of managedChildren) terminate(child);
    process.exit(exitCode);
  };

  selfPlay.on('exit', (code) => shutdown(code ?? 0));

  for (const { port, child } of managedChildren) {
    child.on('exit', (code) => {
      if (!shuttingDown) {
        console.error(`[cluster] game-server :${port} exited unexpectedly (code=${code ?? 0})`);
        shutdown(1);
      }
    });
  }

  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));
}

await main();
