/**
 * Bot Orchestrator: spawns and manages bot child processes per table.
 *
 * When the host updates `botSeats` in room settings, `syncBots()` is called
 * to reconcile the desired bot configuration with running bot processes.
 * Each bot runs as an isolated child process executing `bot-client/src/main.ts`.
 */
import { spawn, type ChildProcess } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { BotSeatConfig } from "@cardpilot/shared-types";
import { logInfo, logWarn, logError } from "../logger.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Resolve path to bot-client main script (relative from services/ → ../../bot-client/src/main.ts)
const BOT_MAIN_SCRIPT = resolve(__dirname, "../../../bot-client/src/main.ts");

const BOT_BUY_IN_BB = 100; // default: bot buys in for 100 big blinds

const BOT_NAMES = [
  "Atsuki", "Take", "Ryo", "Ryu", "Seam", "Joshua",
  "Louis", "Issac", "Jack", "Emily", "Claire", "Mandy",
];

interface ActiveBot {
  seat: number;
  profile: string;
  process: ChildProcess;
  userId: string;
  name: string;
}

// Map<tableId, Map<seat, ActiveBot>>
const tableBots = new Map<string, Map<number, ActiveBot>>();

/**
 * Pick a random bot name not already in use on this table.
 */
function pickBotName(tableId: string): string {
  const existing = tableBots.get(tableId);
  const usedNames = new Set<string>();
  if (existing) {
    for (const bot of existing.values()) {
      usedNames.add(bot.name);
    }
  }
  const available = BOT_NAMES.filter((n) => !usedNames.has(n));
  if (available.length === 0) {
    return `${BOT_NAMES[Math.floor(Math.random() * BOT_NAMES.length)]}-${Date.now() % 1000}`;
  }
  return available[Math.floor(Math.random() * available.length)];
}

/**
 * Get the server URL that bots should connect to.
 * Uses the same port the game server is running on.
 */
function getServerUrl(port: number): string {
  return process.env.BOT_SERVER_URL ?? `http://127.0.0.1:${port}`;
}

/**
 * Spawn a single bot process.
 */
function spawnBot(
  serverUrl: string,
  roomCode: string,
  seat: number,
  profile: string,
  buyIn: number,
  botName: string,
): { process: ChildProcess; userId: string } {
  const userId = `bot-${profile}-seat${seat}-${Date.now()}`;

  const args = [
    BOT_MAIN_SCRIPT,
    "--server", serverUrl,
    "--room", roomCode,
    "--seat", String(seat),
    "--buyin", String(buyIn),
    "--profile", profile,
    "--name", botName,
    "--userId", userId,
    "--delay", "800",
  ];

  const child = spawn("npx", ["tsx", ...args], {
    stdio: "pipe",
    cwd: resolve(__dirname, "../../../bot-client"),
    shell: true,
  });

  // Pipe bot stdout/stderr with prefix
  const prefix = `[bot:seat${seat}/${profile}]`;

  child.stdout?.on("data", (data: Buffer) => {
    const lines = data.toString().trim().split("\n");
    for (const line of lines) {
      logInfo({ event: "bot.stdout", message: `${prefix} ${line}` });
    }
  });

  child.stderr?.on("data", (data: Buffer) => {
    const lines = data.toString().trim().split("\n");
    for (const line of lines) {
      logWarn({ event: "bot.stderr", message: `${prefix} ${line}` });
    }
  });

  child.on("error", (err) => {
    logError({
      event: "bot.spawn_error",
      message: `${prefix} spawn error: ${err.message}`,
      seat,
      profile,
    });
  });

  child.on("exit", (code) => {
    logInfo({
      event: "bot.exit",
      message: `${prefix} exited with code=${code}`,
      seat,
      profile,
    });
  });

  return { process: child, userId };
}

/**
 * Synchronize bot seats for a table:
 *  - Remove bots that are no longer in the desired config (or whose profile changed)
 *  - Spawn new bots for seats that don't have one yet
 */
export function syncBots(
  tableId: string,
  roomCode: string,
  bigBlind: number,
  botSeats: BotSeatConfig[],
  serverPort: number,
  buyInMin?: number,
  buyInMax?: number,
  botBuyIn?: number,
): void {
  if (!tableBots.has(tableId)) {
    tableBots.set(tableId, new Map());
  }
  const current = tableBots.get(tableId)!;
  const serverUrl = getServerUrl(serverPort);
  // Use configured botBuyIn if set, else default to 100BB
  const desiredBuyIn = botBuyIn ?? bigBlind * BOT_BUY_IN_BB;
  const buyIn = Math.min(
    buyInMax ?? desiredBuyIn,
    Math.max(buyInMin ?? desiredBuyIn, desiredBuyIn),
  );

  // Remove bots that are no longer desired or whose profile changed
  for (const [seat, bot] of current.entries()) {
    const desired = botSeats.find((b) => b.seat === seat && b.profile === bot.profile);
    if (!desired) {
      logInfo({
        event: "bot.removing",
        message: `Removing bot seat=${seat} profile=${bot.profile} from table=${tableId}`,
      });
      bot.process.kill("SIGTERM");
      current.delete(seat);
    }
  }

  // Spawn new bots (staggered by 500ms to avoid race conditions)
  let staggerIndex = 0;
  for (const cfg of botSeats) {
    if (current.has(cfg.seat)) continue; // already running

    const delay = staggerIndex * 500;
    staggerIndex++;

    setTimeout(() => {
      const botName = pickBotName(tableId);
      logInfo({
        event: "bot.spawning",
        message: `Spawning bot seat=${cfg.seat} profile=${cfg.profile} name=${botName} for table=${tableId}`,
      });
      const { process: child, userId } = spawnBot(
        serverUrl,
        roomCode,
        cfg.seat,
        cfg.profile,
        buyIn,
        botName,
      );

      const activeBot: ActiveBot = {
        seat: cfg.seat,
        profile: cfg.profile,
        process: child,
        userId,
        name: botName,
      };
      current.set(cfg.seat, activeBot);

      // Auto-clean on unexpected exit
      child.on("exit", () => {
        const bots = tableBots.get(tableId);
        if (bots?.get(cfg.seat)?.userId === userId) {
          bots.delete(cfg.seat);
        }
      });
    }, delay);
  }
}

/**
 * Remove all bots for a table (called when room is closed).
 */
export function removeAllBots(tableId: string): void {
  const bots = tableBots.get(tableId);
  if (!bots) return;

  logInfo({
    event: "bot.removeAll",
    message: `Removing all ${bots.size} bots from table=${tableId}`,
  });

  for (const bot of bots.values()) {
    bot.process.kill("SIGTERM");
  }
  tableBots.delete(tableId);
}

/**
 * Get currently active bot seats for a table (for status display).
 */
export function getActiveBots(tableId: string): Array<{ seat: number; profile: string; userId: string }> {
  const bots = tableBots.get(tableId);
  if (!bots) return [];
  return [...bots.values()].map((b) => ({ seat: b.seat, profile: b.profile, userId: b.userId }));
}

/**
 * Returns the set of bot userIds for a given table.
 */
export function getBotUserIds(tableId: string): Set<string> {
  const bots = tableBots.get(tableId);
  if (!bots) return new Set();
  return new Set([...bots.values()].map((b) => b.userId));
}

/**
 * Shutdown all bots across all tables (for graceful server shutdown).
 */
export function shutdownAllBots(): void {
  for (const [tableId, bots] of tableBots.entries()) {
    for (const bot of bots.values()) {
      bot.process.kill("SIGTERM");
    }
    bots.clear();
  }
  tableBots.clear();
}
