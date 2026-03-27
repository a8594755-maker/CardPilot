#!/usr/bin/env node
import { io, type Socket } from 'socket.io-client';
import { appendFile, existsSync, mkdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { getProfile } from './profiles.js';
import { decide, quickHandStrength } from './decision.js';
import {
  createSessionStats,
  loadSessionStats,
  saveSessionStats,
  recordAction,
  recordHandResult,
  computeAdaptiveAdjustments,
  type SessionStats,
} from './session-stats.js';
import { encodeFeatures, loadModel, type MLP } from '@cardpilot/fast-model';
import type { TrainingSample } from '@cardpilot/fast-model';
import type { TableState, AdvicePayload, StrategyMix } from './types.js';

// New module imports
import { generatePersona, type BotPersona } from './persona.js';
import { createMoodState, updateMood, type MoodState } from './mood.js';
import { OpponentTracker } from './opponent-model.js';
import { computeThinkingTime } from './thinking-time.js';
import { analyzeRaiseContext } from './raise-context.js';
import { getBoardTexture } from './board-integration.js';
import { TraceLogger } from './trace-logger.js';
import { ResolverPool } from './realtime-resolver.js';

// ===== CLI argument parsing =====
export interface BotArgs {
  server: string;
  room: string;
  seat: number;
  buyin: number;
  profile: string;
  name?: string;
  userId?: string;
  delay?: number; // ms to wait before acting (humanize)
  mode?: 'train' | 'play'; // V2: train=clean labels, play=full personality
  version?: 'v3'; // model version (v3 = cfr-combined + resolver)
  // In-process bot support (used by self-play orchestrator)
  sharedModel?: MLP | null; // shared model instance (avoids loading per-bot)
  dataDir?: string; // override data directory
  skipPersistStats?: boolean; // skip saving session stats to disk
  quiet?: boolean; // suppress routine bot logs (for high-throughput self-play)
}

function parseArgs(argv: string[]): BotArgs {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const key = argv[i].slice(2);
      const val = argv[i + 1] ?? '';
      args[key] = val;
      i++;
    }
  }

  const server = args['server'] ?? 'http://127.0.0.1:3001';
  const room = args['room'];
  const seat = parseInt(args['seat'] ?? '0', 10);
  const buyin = parseInt(args['buyin'] ?? '200', 10);
  const profile = args['profile'] ?? 'gto_balanced';
  const name = args['name'];
  const userId = args['userId'];
  const delay = parseInt(args['delay'] ?? '800', 10);
  const mode = (args['mode'] ?? 'play') as 'train' | 'play';
  const version = 'v3' as const;

  if (!room) {
    console.error(
      'Usage: --room <ROOM_CODE> [--server url] [--seat N] [--buyin N] [--profile id] [--name str] [--userId str] [--delay ms] [--mode train|play]',
    );
    process.exit(1);
  }

  return { server, room, seat, buyin, profile, name, userId, delay, mode, version };
}

// ===== Bot class =====
export class PokerBot {
  private socket: Socket;
  private tableId: string | null = null;
  private mySeat: number;
  private myName: string;
  private latestState: TableState | null = null;
  private pendingAdvice: StrategyMix | null = null;
  private myCards: [string, string] | null = null;
  private profile;
  private actDelay: number;
  private seated = false;
  private handActedMap = new Set<string>();
  private sessionStats: SessionStats;
  private lastHandStack: number | null = null;
  private lastHandId: string | null = null;
  private fastModel: MLP | null = null;
  private dataDir: string;
  private sampleCount = 0;
  private readonly MAX_SAMPLES_PER_FILE = 100_000;
  private writeBuffer: string[] = [];
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private readonly FLUSH_INTERVAL_MS = 2000; // flush writes every 2s
  private readonly FLUSH_BATCH_SIZE = 50; // or when buffer hits 50 samples

  // New enhancement state
  private persona: BotPersona;
  private moodState: MoodState;
  private opponentTracker: OpponentTracker;
  private traceLogger: TraceLogger;
  private handNumber = 0;
  private lastProcessedActionCount = 0; // track observed actions for opponent model
  private lastHandStrength: number | null = null; // for bad beat detection
  private preflopSampleCount = 0; // track ALL preflop samples for downsampling
  private readonly preflopKeepEvery: number;
  private _pendingRebuy = false; // debounce rebuy requests

  // Mode/version
  private mode: 'train' | 'play';
  private version: 'v3';

  private skipPersistStats: boolean;
  private quiet: boolean;
  private modelReloadTimer: ReturnType<typeof setInterval> | null = null;
  private resolverPool: ResolverPool | null = null;

  constructor(private args: BotArgs) {
    this.mySeat = args.seat;
    this.profile = getProfile(args.profile);
    this.myName = args.name ?? `Bot-${this.profile.displayName}`;
    this.actDelay = args.delay ?? 800;
    this.mode = args.mode ?? 'play';
    this.version = 'v3';
    this.skipPersistStats = args.skipPersistStats ?? false;
    this.quiet = args.quiet ?? false;
    this.preflopKeepEvery = Math.max(
      1,
      parseInt(process.env['PREFLOP_KEEP_EVERY'] ?? '10', 10) || 10,
    );

    // ── Load persistent session stats ──
    this.sessionStats = this.skipPersistStats
      ? createSessionStats()
      : loadSessionStats(this.profile.id);
    if (this.sessionStats.handsPlayed > 0) {
      this.log(
        `Loaded stats: hands=${this.sessionStats.handsPlayed} net=${this.sessionStats.netChips}`,
      );
    }

    // ── Initialize persona (fixed for entire session) ──
    this.persona = generatePersona(this.profile.id);

    // ── Initialize mood state ──
    this.moodState = createMoodState();

    // ── Initialize opponent tracker ──
    this.opponentTracker = new OpponentTracker();

    // ── Initialize trace logger ──
    this.traceLogger = new TraceLogger();

    // ── Fast model: use shared model if provided, otherwise load from disk ──
    if (args.sharedModel !== undefined) {
      this.fastModel = args.sharedModel;
    } else {
      const __dirname = dirname(fileURLToPath(import.meta.url));
      const modelPath = join(__dirname, '..', '..', '..', 'models', 'vnet-v91-balanced.json');
      this.fastModel = loadModel(modelPath);
      if (this.fastModel) {
        this.log(`Fast model loaded (${this.version})`);
      } else {
        this.log('No fast model found, will use heuristic fallback');
      }

      // ── Hot-reload model every 5 minutes (only for standalone bots) ──
      let lastModelMtime = 0;
      try {
        lastModelMtime = statSync(modelPath).mtimeMs;
      } catch {}
      this.modelReloadTimer = setInterval(
        () => {
          try {
            const currentMtime = statSync(modelPath).mtimeMs;
            if (currentMtime > lastModelMtime) {
              const newModel = loadModel(modelPath);
              if (newModel) {
                this.fastModel = newModel;
                lastModelMtime = currentMtime;
                this.log('Model hot-reloaded!');
              }
            }
          } catch {}
        },
        5 * 60 * 1000,
      );
    }

    // ── Real-time CFR resolver pool (always enabled, disable with BOT_USE_RESOLVER=0) ──
    if (process.env['BOT_USE_RESOLVER'] !== '0') {
      const projectRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
      this.resolverPool = new ResolverPool({
        projectRoot,
        verbose: !this.quiet,
        flopIterations: parseInt(process.env['RESOLVER_FLOP_ITERS'] ?? '2000', 10),
        turnIterations: parseInt(process.env['RESOLVER_TURN_ITERS'] ?? '1000', 10),
        riverIterations: parseInt(process.env['RESOLVER_RIVER_ITERS'] ?? '500', 10),
      });
      const loaded = this.resolverPool.initialize();
      if (loaded > 0) {
        this.log(`ResolverPool: ${loaded}/4 scenarios ready`);
      } else {
        this.log('ResolverPool: no scenarios loaded — disabled');
        this.resolverPool = null;
      }
    }

    // ── Data collection directories ──
    if (args.dataDir) {
      this.dataDir = args.dataDir;
    } else {
      const __dirname2 = dirname(fileURLToPath(import.meta.url));
      this.dataDir = join(__dirname2, '..', '..', '..', 'data');
      if (!existsSync(this.dataDir)) {
        mkdirSync(this.dataDir, { recursive: true });
      }
    }

    // ── Batched write timer (flush accumulated samples periodically) ──
    this.flushTimer = setInterval(() => this.flushWriteBuffer(), this.FLUSH_INTERVAL_MS);

    const botUserId = args.userId ?? `bot-${this.profile.id}-${this.mySeat}-${Date.now()}`;

    this.log(
      `Connecting to ${args.server} as "${this.myName}" (profile=${this.profile.id}, seat=${this.mySeat}, mode=${this.mode}, version=${this.version})`,
    );

    this.socket = io(args.server, {
      auth: {
        displayName: this.myName,
        userId: botUserId,
      },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 2000,
      reconnectionAttempts: 20,
    });

    this.wireEvents();
  }

  private log(msg: string): void {
    if (this.quiet) return;
    const ts = new Date().toISOString().slice(11, 23);
    console.log(`[${ts}] [seat${this.mySeat}/${this.profile.id}] ${msg}`);
  }

  private wireEvents(): void {
    this.socket.on('connect', () => {
      this.log('Connected, joining room...');
      this.socket.emit('join_room_code', { roomCode: this.args.room });
    });

    this.socket.on('connect_error', (err) => {
      this.log(`Connection error: ${err.message}`);
    });

    this.socket.on('disconnect', (reason) => {
      this.log(`Disconnected: ${reason}`);
      this.seated = false;
    });

    this.socket.on(
      'connected',
      (data: { socketId: string; userId: string; displayName: string }) => {
        this.log(`Server acknowledged: userId=${data.userId}, name=${data.displayName}`);
      },
    );

    this.socket.on(
      'room_joined',
      (data: { tableId: string; roomCode: string; roomName: string }) => {
        this.tableId = data.tableId;
        this.log(`Joined room "${data.roomName}" (tableId=${data.tableId})`);
        if (!this.seated) {
          this.trySitDown();
        }
      },
    );

    this.socket.on('error_event', (data: { message: string }) => {
      this.log(`Server error: ${data.message}`);
      if ((!this.seated && data.message.includes('seat')) || data.message.includes('Seat')) {
        this.log('Will retry sit_down in 3s...');
        setTimeout(() => this.trySitDown(), 3000);
      }
    });

    // ── Hole cards: know our own hand ──
    this.socket.on('hole_cards', (data: { handId: string; cards: string[]; seat: number }) => {
      if (data.seat === this.mySeat && data.cards && data.cards.length >= 2) {
        this.myCards = [data.cards[0], data.cards[1]];
        this.log(`Hole cards: ${this.myCards[0]} ${this.myCards[1]}`);
      }
    });

    // ── Hand started: reset per-hand state ──
    this.socket.on('hand_started', (data: { handId: string }) => {
      this.myCards = null;
      this.pendingAdvice = null;
      this.lastHandId = data.handId;
      this.handNumber++;
      this.lastProcessedActionCount = 0;
      this.lastHandStrength = null;
      this.resolverPool?.resetHand();

      // Snapshot stack at hand start for P&L tracking
      const me = this.latestState?.players.find((p) => p.seat === this.mySeat);
      this.lastHandStack = me?.stack ?? null;

      // Notify opponent tracker of new hand
      if (this.latestState) {
        this.opponentTracker.observeHandStart(this.latestState);
      }
    });

    this.socket.on('table_snapshot', (state: TableState) => {
      this.latestState = state;

      if (!this.tableId && state.tableId) {
        this.tableId = state.tableId;
      }

      // Try to sit down if not seated yet
      if (!this.seated) {
        const alreadySeated = state.players.some((p) => p.seat === this.mySeat);
        if (alreadySeated) {
          this.seated = true;
          this.log('Already seated (detected from snapshot)');
        } else {
          this.trySitDown();
          return;
        }
      }

      // Feed new actions to opponent tracker
      this.observeNewActions(state);

      // Detect hand ending for session stats + mood update
      if (!state.handId && this.lastHandStack !== null && this.lastHandId) {
        const me = state.players.find((p) => p.seat === this.mySeat);
        if (me) {
          const net = me.stack - this.lastHandStack;
          const won = net > 0;
          recordHandResult(this.sessionStats, net, won);
          if (!this.skipPersistStats) saveSessionStats(this.sessionStats, this.profile.id);

          // Update mood with hand result
          const wasBadBeat = !won && this.lastHandStrength != null && this.lastHandStrength >= 0.65;
          this.moodState = updateMood(
            this.moodState,
            { net, wasShowdown: this.lastHandStrength != null, wasBadBeat },
            this.handNumber,
            state.bigBlind || 1,
            this.persona,
          );

          if (this.sessionStats.handsPlayed % 10 === 0) {
            const ftr =
              this.sessionStats.facingRaiseCount > 0
                ? (
                    (this.sessionStats.foldToRaiseCount / this.sessionStats.facingRaiseCount) *
                    100
                  ).toFixed(0)
                : '0';
            this.log(
              `Stats: hands=${this.sessionStats.handsPlayed} wins=${this.sessionStats.handsWon} ` +
                `net=${this.sessionStats.netChips} foldToRaise=${ftr}% mood=${this.moodState.value.toFixed(2)}`,
            );
          }

          // Auto-rebuy when stack is low (self-play training mode)
          const bb = state.bigBlind || 1;
          if (me.stack < bb * 5 && this.tableId) {
            const rebuyAmount = this.args.buyin - me.stack;
            if (rebuyAmount > 0) {
              this.log(`Stack low (${me.stack}), requesting rebuy of ${rebuyAmount}`);
              this.socket.emit('deposit_request', {
                tableId: this.tableId,
                amount: rebuyAmount,
              });
            }
          }
        }
        this.lastHandStack = null;
        this.lastHandId = null;
      }

      // Auto-rebuy between hands when stack is low (catch busted bots that missed hand_ended)
      if (this.mode === 'train' && !state.handId && this.tableId) {
        const me2 = state.players.find((p) => p.seat === this.mySeat);
        const bb2 = state.bigBlind || 1;
        if (me2 && me2.stack < bb2 * 10 && !this._pendingRebuy) {
          const rebuyAmount = this.args.buyin - me2.stack;
          if (rebuyAmount > 0) {
            this._pendingRebuy = true;
            this.socket.emit('deposit_request', {
              tableId: this.tableId,
              amount: rebuyAmount,
            });
          }
        } else if (me2 && me2.stack >= bb2 * 10) {
          this._pendingRebuy = false;
        }
      }

      // Check if it's our turn to act
      this.maybeAct();
    });

    this.socket.on('advice_payload', (advice: AdvicePayload) => {
      if (advice.seat === this.mySeat && advice.mix) {
        this.log(
          `Received advice: R=${advice.mix.raise.toFixed(2)} C=${advice.mix.call.toFixed(2)} F=${advice.mix.fold.toFixed(2)}`,
        );
        this.pendingAdvice = advice.mix;

        // Collect training sample
        this.collectSample(advice);

        this.maybeAct();
      }
    });

    this.socket.on('action_applied', (data: { seat: number; action: string; amount: number }) => {
      if (data.seat === this.mySeat) {
        this.log(`Action confirmed: ${data.action}${data.amount ? ` ${data.amount}` : ''}`);
      }
    });

    this.socket.io.on('reconnect', () => {
      this.log('Reconnected, re-joining room...');
      this.socket.emit('join_room_code', { roomCode: this.args.room });
    });
  }

  // ── Feed new actions to opponent tracker ──
  private observeNewActions(state: TableState): void {
    if (!state.handId) return;
    const actions = state.actions;
    // Only process new actions since last check
    for (let i = this.lastProcessedActionCount; i < actions.length; i++) {
      this.opponentTracker.observeAction(actions[i], state, this.mySeat);
    }
    this.lastProcessedActionCount = actions.length;
  }

  private trySitDown(): void {
    if (this.seated || !this.tableId) return;
    this.log(`Sitting down at seat ${this.mySeat} with buyIn=${this.args.buyin}`);
    this.socket.emit('sit_down', {
      tableId: this.tableId,
      seat: this.mySeat,
      buyIn: this.args.buyin,
      name: this.myName,
    });
    this.seated = true;
  }

  private maybeAct(): void {
    const state = this.latestState;
    if (!state || !state.handId || state.actorSeat !== this.mySeat) return;
    if (!state.legalActions) return;

    // Dedup: don't act twice for the same hand+street
    const dedupKey = `${state.handId}:${state.street}:${state.currentBet}:${state.pot}`;
    if (this.handActedMap.has(dedupKey)) return;
    this.handActedMap.add(dedupKey);

    // Prune old dedup entries
    if (this.handActedMap.size > 200) {
      const entries = [...this.handActedMap];
      entries.slice(0, 100).forEach((k) => this.handActedMap.delete(k));
    }

    // ── Context-dependent thinking time (Enhancement #5) ──
    const raiseContext = analyzeRaiseContext(state, this.mySeat);
    const boardTexture = getBoardTexture(state.board);
    const handStrength = this.myCards
      ? quickHandStrength(this.myCards, state.board, state.street)
      : null;

    const myPlayer = state.players.find((p) => p.seat === this.mySeat);
    const myStack = myPlayer?.stack ?? 0;
    const isAllInDecision = (state.legalActions.callAmount ?? 0) >= myStack * 0.9;

    const thinkingTime = computeThinkingTime({
      street: state.street,
      pot: state.pot,
      bigBlind: state.bigBlind || 1,
      toCall: state.legalActions.callAmount ?? 0,
      handStrength,
      boardTexture,
      raiseContext,
      numPlayersInHand: state.players.filter((p) => p.inHand && !p.folded).length,
      isAllInDecision,
      baseDelay: this.actDelay,
    });

    // Wait for advice with polling, then act
    const adviceDeadline = Date.now() + 3500;

    const checkAndAct = () => {
      if (this.pendingAdvice) {
        this.act(state);
        return;
      }
      if (Date.now() < adviceDeadline) {
        setTimeout(checkAndAct, 200);
        return;
      }
      this.log('Advice timeout, using fallback');
      this.act(state);
    };

    // Two-stage thinking time
    if (thinkingTime.twoStage) {
      setTimeout(() => {
        // First stage pause, then second stage before polling
        setTimeout(checkAndAct, thinkingTime.secondStageMs);
      }, thinkingTime.firstStageMs);
    } else {
      setTimeout(checkAndAct, thinkingTime.delayMs);
    }
  }

  private collectSample(advice: AdvicePayload): void {
    try {
      const state = this.latestState;
      if (!state || !this.myCards || !state.handId) return;
      if (state.actorSeat !== this.mySeat && !this.pendingAdvice) return;
      if (state.street === 'SHOWDOWN' || state.street === 'RUN_IT_TWICE_PROMPT') return;

      const me = state.players.find((p) => p.seat === this.mySeat);
      if (!me) return;

      const heroPosition = state.positions?.[this.mySeat] ?? 'BTN';
      const villains = state.players.filter((p) => p.inHand && !p.folded && p.seat !== this.mySeat);
      const numVillains = villains.length || 1;
      const heroInPosition = heroPosition === 'BTN' || heroPosition === 'CO';
      const heroRaisedPreflop = state.actions.some(
        (a) => a.seat === this.mySeat && a.street === 'PREFLOP' && a.type === 'raise',
      );
      const effectiveStack = Math.min(me.stack, ...villains.map((v) => v.stack));
      const bb = state.bigBlind || 1;
      const callAmount = state.legalActions?.callAmount ?? 0;

      const features = encodeFeatures(
        this.myCards,
        state.board,
        state.street,
        state.pot,
        bb,
        callAmount,
        effectiveStack,
        heroPosition,
        heroInPosition,
        numVillains,
        heroRaisedPreflop,
      );

      const sample: TrainingSample = {
        f: features.map((v) => Math.round(v * 10000) / 10000),
        l: [advice.mix.raise, advice.mix.call, advice.mix.fold],
        h: state.handId.slice(0, 8),
        s: state.street,
      };

      this.bufferSample(JSON.stringify(sample) + '\n', this.dataDir);
    } catch {
      // Never let data collection crash the bot
    }
  }

  private act(state: TableState): void {
    if (!this.tableId || !state.handId || !state.legalActions) return;

    // Use pending advice if available, then clear
    const advice = this.pendingAdvice;
    this.pendingAdvice = null;

    // Track hand strength for bad beat detection
    if (this.myCards) {
      this.lastHandStrength = quickHandStrength(this.myCards, state.board, state.street);
    }

    let result;
    if (this.mode === 'train') {
      // TRAIN mode: clean decision without personality layers
      result = decide({
        state,
        profile: this.profile,
        advice,
        holeCards: this.myCards,
        mySeat: this.mySeat,
        fastModel: this.fastModel,
        resolverPool: this.resolverPool,
        // Omit: adaptiveAdj, persona, moodState, opponentAdj, handNumber
        // This skips persona/mood/opponent/adaptive/mistake layers
      });
    } else {
      // PLAY mode: full personality pipeline
      const adaptiveAdj = computeAdaptiveAdjustments(this.sessionStats);
      const raiseContext = analyzeRaiseContext(state, this.mySeat);
      let opponentAdj;
      if (raiseContext.raiserSeat != null) {
        const situation =
          state.street === 'FLOP' && raiseContext.facingType === 'facing_open'
            ? ('facing_cbet' as const)
            : raiseContext.facingType !== 'unopened'
              ? ('facing_raise' as const)
              : ('general' as const);
        opponentAdj = this.opponentTracker.computeAdjustment(raiseContext.raiserSeat, situation);
      }

      result = decide({
        state,
        profile: this.profile,
        advice,
        holeCards: this.myCards,
        mySeat: this.mySeat,
        adaptiveAdj,
        persona: this.persona,
        moodState: this.moodState,
        opponentAdj,
        handNumber: this.handNumber,
        fastModel: this.fastModel,
        resolverPool: this.resolverPool,
      });
    }

    this.log(
      `Hand ${state.handId.slice(0, 8)} ${state.street} pot=${state.pot} → ${result.action}` +
        `${result.amount != null ? ` ${result.amount}` : ''} (${result.reasoning})`,
    );

    // Log structured trace
    if (result.trace) {
      this.traceLogger.log(result.trace);
    }

    // Track action in session stats
    const facingRaise = (state.legalActions.callAmount ?? 0) > (state.bigBlind || 1);
    recordAction(this.sessionStats, result.action, facingRaise);

    const payload: { tableId: string; handId: string; action: string; amount?: number } = {
      tableId: this.tableId,
      handId: state.handId,
      action: result.action,
    };
    if (result.amount != null) {
      payload.amount = result.amount;
    }

    this.socket.emit('action_submit', payload);
  }

  /** Flush buffered sample lines to disk (async, non-blocking) */
  private flushWriteBuffer(): void {
    if (this.writeBuffer.length === 0) return;
    const lines = this.writeBuffer.join('');
    this.writeBuffer.length = 0;
    const targetDir = this.dataDir;
    const fileIdx = Math.floor(this.sampleCount / this.MAX_SAMPLES_PER_FILE);
    const filePath = join(targetDir, `training-samples${fileIdx > 0 ? `-${fileIdx}` : ''}.jsonl`);
    appendFile(filePath, lines, () => {}); // fire-and-forget async write
  }

  /** Buffer a sample line (batched write for perf) */
  private bufferSample(line: string, _dir: string): void {
    this.writeBuffer.push(line);
    this.sampleCount++;
    if (this.writeBuffer.length >= this.FLUSH_BATCH_SIZE) {
      this.flushWriteBuffer();
    }
  }

  /** Update the model reference (used by orchestrator for hot-reload) */
  setModel(model: MLP): void {
    this.fastModel = model;
  }

  /** Clean up socket and timers, flush remaining data */
  destroy(): void {
    if (this.modelReloadTimer) clearInterval(this.modelReloadTimer);
    if (this.flushTimer) clearInterval(this.flushTimer);
    this.flushWriteBuffer(); // flush any remaining samples
    try {
      this.socket.disconnect();
    } catch {}
  }
}

// ===== Entry point (only when run as standalone script) =====
const isMainModule =
  process.argv[1] && (process.argv[1].endsWith('main.ts') || process.argv[1].endsWith('main.js'));
if (!isMainModule) {
  // Imported as a module — don't auto-create bot
} else {
  const botArgs = parseArgs(process.argv.slice(2));
  new PokerBot(botArgs);
}
