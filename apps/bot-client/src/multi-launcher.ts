#!/usr/bin/env node
/**
 * Multi-bot launcher: spawns multiple bot processes from a JSON config or CLI args.
 *
 * Usage:
 *   pnpm --filter bot-client multi -- --config bots.json
 *   pnpm --filter bot-client multi -- --server http://127.0.0.1:3001 --room ABCD --buyin 200 \
 *     --bots "2:lag,3:nit,4:gto_balanced,5:limp_fish,6:tag"
 */
import { spawn, type ChildProcess } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

interface BotEntry {
  seat: number;
  profile: string;
  buyin?: number;
  name?: string;
  userId?: string;
  delay?: number;
}

interface MultiConfig {
  server: string;
  room: string;
  buyin?: number;
  delay?: number;
  bots: BotEntry[];
}

function parseMultiArgs(argv: string[]): MultiConfig {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const key = argv[i].slice(2);
      const val = argv[i + 1] ?? '';
      args[key] = val;
      i++;
    }
  }

  // If --config is given, load from JSON file
  if (args['config']) {
    const raw = readFileSync(resolve(process.cwd(), args['config']), 'utf-8');
    return JSON.parse(raw) as MultiConfig;
  }

  const server = args['server'] ?? 'http://127.0.0.1:3001';
  const room = args['room'];
  const buyin = parseInt(args['buyin'] ?? '200', 10);
  const delay = parseInt(args['delay'] ?? '800', 10);

  if (!room) {
    console.error('Usage: --room ROOM_CODE --bots "seat:profile,..." [--server url] [--buyin N] [--delay ms]');
    console.error('   or: --config bots.json');
    process.exit(1);
  }

  // Parse --bots "2:lag,3:nit,4:gto_balanced"
  const botsStr = args['bots'] ?? '';
  if (!botsStr) {
    console.error('Provide --bots "seat:profile,..." or --config file.json');
    process.exit(1);
  }

  const bots: BotEntry[] = botsStr.split(',').map(entry => {
    const [seatStr, profile] = entry.trim().split(':');
    return { seat: parseInt(seatStr, 10), profile: profile ?? 'gto_balanced' };
  });

  return { server, room, buyin, delay, bots };
}

function launchBot(config: MultiConfig, bot: BotEntry): ChildProcess {
  const mainScript = resolve(__dirname, 'main.ts');
  const args = [
    mainScript,
    '--server', config.server,
    '--room', config.room,
    '--seat', String(bot.seat),
    '--buyin', String(bot.buyin ?? config.buyin ?? 200),
    '--profile', bot.profile,
    '--delay', String(bot.delay ?? config.delay ?? 800),
  ];
  if (bot.name) args.push('--name', bot.name);
  if (bot.userId) args.push('--userId', bot.userId);

  const child = spawn('npx', ['tsx', ...args], {
    stdio: 'inherit',
    cwd: resolve(__dirname, '..'),
  });

  child.on('exit', (code) => {
    console.log(`[launcher] Bot seat=${bot.seat} profile=${bot.profile} exited with code=${code}`);
  });

  return child;
}

// ===== Main =====
const config = parseMultiArgs(process.argv.slice(2));
console.log(`[launcher] Starting ${config.bots.length} bots for room=${config.room} server=${config.server}`);

const children: ChildProcess[] = [];

// Stagger launches by 500ms to avoid race conditions
for (let i = 0; i < config.bots.length; i++) {
  const bot = config.bots[i];
  setTimeout(() => {
    console.log(`[launcher] Launching bot seat=${bot.seat} profile=${bot.profile}`);
    children.push(launchBot(config, bot));
  }, i * 500);
}

// Graceful shutdown
function shutdown(): void {
  console.log('\n[launcher] Shutting down all bots...');
  for (const child of children) {
    child.kill('SIGTERM');
  }
  setTimeout(() => process.exit(0), 2000);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
