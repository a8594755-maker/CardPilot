/**
 * Bot Orchestrator: manages in-process bot instances per table.
 *
 * When the host updates `botSeats` in room settings, `syncBots()` is called
 * to reconcile the desired bot configuration with running bot instances.
 * Each bot runs as a lightweight in-process socket.io client (~1-2 MB)
 * instead of a child process (~80 MB).
 */
import type { BotSeatConfig } from '@cardpilot/shared-types';
import { InProcessBot } from './in-process-bot.js';
import { logInfo, logWarn } from '../logger.js';

const BOT_BUY_IN_BB = 100; // default: bot buys in for 100 big blinds

const BOT_NAMES = [
  'Atsuki',
  'Take',
  'Ryo',
  'Ryu',
  'Sean',
  'Joshua',
  'Louis',
  'Issac',
  'Jack',
  'Emily',
  'Claire',
  'Mandy',
];

interface ActiveBot {
  seat: number;
  profile: string;
  bot: InProcessBot;
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
 * Synchronize bot seats for a table:
 *  - Remove bots that are no longer in the desired config (or whose profile changed)
 *  - Create new in-process bots for seats that don't have one yet
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
  for (const [seat, activeBot] of current.entries()) {
    const desired = botSeats.find((b) => b.seat === seat && b.profile === activeBot.profile);
    if (!desired) {
      logInfo({
        event: 'bot.removing',
        message: `Removing bot seat=${seat} profile=${activeBot.profile} from table=${tableId}`,
      });
      activeBot.bot.destroy();
      current.delete(seat);
    }
  }

  // Create new bots (staggered by 500ms to avoid seat assignment races)
  let staggerIndex = 0;
  for (const cfg of botSeats) {
    if (current.has(cfg.seat)) continue; // already running

    const delay = staggerIndex * 500;
    staggerIndex++;

    setTimeout(() => {
      try {
        // Guard: table may have been removed while waiting
        const bots = tableBots.get(tableId);
        if (!bots) return;

        const botName = pickBotName(tableId);
        const userId = `bot-${cfg.profile}-gto-seat${cfg.seat}-${Date.now()}`;

        logInfo({
          event: 'bot.spawning',
          message: `Creating in-process bot seat=${cfg.seat} profile=${cfg.profile} name=${botName} for table=${tableId}`,
        });

        const bot = new InProcessBot({
          serverUrl,
          roomCode,
          seat: cfg.seat,
          buyIn,
          profile: cfg.profile,
          botName,
          userId,
          delay: 800,
        });

        const activeBot: ActiveBot = {
          seat: cfg.seat,
          profile: cfg.profile,
          bot,
          userId,
          name: botName,
        };
        bots.set(cfg.seat, activeBot);

        // Auto-clean on unexpected disconnect
        bot.onDestroy(() => {
          const currentBots = tableBots.get(tableId);
          if (currentBots?.get(cfg.seat)?.userId === userId) {
            currentBots.delete(cfg.seat);
          }
        });
      } catch (err) {
        logWarn({
          event: 'bot.spawn.error',
          message: `Failed to create bot seat=${cfg.seat} profile=${cfg.profile} for table=${tableId}: ${(err as Error).message}`,
        });
      }
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
    event: 'bot.removeAll',
    message: `Removing all ${bots.size} bots from table=${tableId}`,
  });

  for (const activeBot of bots.values()) {
    activeBot.bot.destroy();
  }
  tableBots.delete(tableId);
}

/**
 * Get currently active bot seats for a table (for status display).
 */
export function getActiveBots(
  tableId: string,
): Array<{ seat: number; profile: string; userId: string }> {
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
  for (const [, bots] of tableBots.entries()) {
    for (const activeBot of bots.values()) {
      activeBot.bot.destroy();
    }
    bots.clear();
  }
  tableBots.clear();
}
