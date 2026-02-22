import { spawn } from "node:child_process";
import net from "node:net";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = resolve(__dirname, "..");
const WEB_DIR = resolve(ROOT_DIR, "apps/web");
const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
const BACKEND_HEALTH_URL = "http://127.0.0.1:4000/healthz";

function isPortListening(port, host = "127.0.0.1", timeoutMs = 500) {
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
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
    socket.connect(port, host);
  });
}

function delay(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

async function isCardPilotBackendHealthy({ attempts = 3, timeoutMs = 800 } = {}) {
  for (let i = 0; i < attempts; i += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(BACKEND_HEALTH_URL, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });

      if (response.ok) {
        const payload = await response.json().catch(() => null);
        if (payload?.ok === true && payload?.service === "cardpilot-game-server") {
          return true;
        }
      }
    } catch {
      // ignore and retry
    } finally {
      clearTimeout(timeout);
    }

    if (i < attempts - 1) {
      await delay(200);
    }
  }

  return false;
}

function run(cmd, args, cwd) {
  return spawn(cmd, args, {
    cwd,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
}

function terminate(child) {
  if (!child || child.killed) return;
  try {
    child.kill("SIGTERM");
  } catch {
    // no-op
  }
}

async function main() {
  const backendPortListening = await isPortListening(4000);
  const backendRunning = backendPortListening
    ? await isCardPilotBackendHealthy()
    : false;
  const webRunning = await isPortListening(5173);

  if (backendPortListening && !backendRunning) {
    console.error(
      `[dev] Port :4000 is occupied, but ${BACKEND_HEALTH_URL} is not a healthy CardPilot backend.`,
    );
    console.error("[dev] Stop the process on :4000 or set VITE_DEV_SERVER_TARGET to the correct backend.");
    process.exit(1);
  }

  if (backendRunning && webRunning) {
    console.log("[dev] Existing stack detected on :4000 and :5173. Nothing to start.");
    return;
  }

  if (!backendRunning && webRunning) {
    console.log("[dev] Web is running on :5173, starting game-server only.");
    const gameServer = run(npmCmd, ["run", "dev", "-w", "@cardpilot/game-server"], ROOT_DIR);
    gameServer.on("exit", (code) => process.exit(code ?? 0));
    return;
  }

  if (backendRunning) {
    console.log("[dev] Detected server on :4000. Starting Vite only.");
    const vite = run(npmCmd, ["exec", "vite"], WEB_DIR);
    vite.on("exit", (code) => process.exit(code ?? 0));
    return;
  }

  console.log("[dev] No server on :4000. Starting game-server + Vite.");
  const gameServer = run(npmCmd, ["run", "dev", "-w", "@cardpilot/game-server"], ROOT_DIR);
  const vite = run(npmCmd, ["exec", "vite"], WEB_DIR);

  let exiting = false;
  const shutdown = (exitCode = 0) => {
    if (exiting) return;
    exiting = true;
    terminate(gameServer);
    terminate(vite);
    process.exit(exitCode);
  };

  gameServer.on("exit", (code) => {
    const exitCode = code ?? 0;
    shutdown(exitCode);
  });
  vite.on("exit", (code) => {
    const exitCode = code ?? 0;
    shutdown(exitCode);
  });

  process.on("SIGINT", () => shutdown(0));
  process.on("SIGTERM", () => shutdown(0));
}

await main();
