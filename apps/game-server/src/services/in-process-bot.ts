/**
 * In-process bot: a lightweight socket.io-client that runs inside the
 * game-server process instead of spawning a child process.
 *
 * Memory: ~1-2 MB per bot vs ~80 MB per child process (npx tsx overhead).
 *
 * The bot connects to the game-server via localhost socket.io, so the
 * server-side event handling is completely unchanged — the server sees
 * each in-process bot as a normal socket connection.
 */
import { io, type Socket } from 'socket.io-client';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { appendFile, existsSync, mkdirSync } from 'node:fs';

// ── Bot logic imports (from bot-client, used directly in-process) ──
import { getProfile } from '../../../bot-client/src/profiles.js';
import { decide, quickHandStrength } from '../../../bot-client/src/decision.js';
import {
  createSessionStats,
  recordAction,
  recordHandResult,
  computeAdaptiveAdjustments,
  type SessionStats,
} from '../../../bot-client/src/session-stats.js';
import { generatePersona, type BotPersona } from '../../../bot-client/src/persona.js';
import { createMoodState, updateMood, type MoodState } from '../../../bot-client/src/mood.js';
import { OpponentTracker } from '../../../bot-client/src/opponent-model.js';
import { computeThinkingTime } from '../../../bot-client/src/thinking-time.js';
import { analyzeRaiseContext } from '../../../bot-client/src/raise-context.js';
import { getBoardTexture } from '../../../bot-client/src/board-integration.js';
import { TraceLogger } from '../../../bot-client/src/trace-logger.js';
import { ResolverPool } from '../../../bot-client/src/realtime-resolver.js';
import { encodeFeatures, loadModel, type MLP } from '@cardpilot/fast-model';
import type { TrainingSample } from '@cardpilot/fast-model';
import type { TableState, AdvicePayload, StrategyMix } from '../../../bot-client/src/types.js';

import { logInfo, logWarn } from '../logger.js';

// ══════════════════════════════════════════════════════════════
// Config
// ══════════════════════════════════════════════════════════════

export interface InProcessBotConfig {
  serverUrl: string;
  roomCode: string;
  seat: number;
  buyIn: number;
  profile: string;
  botName: string;
  userId: string;
  delay?: number; // action delay in ms (default 800)
}

// ══════════════════════════════════════════════════════════════
// Shared fast-model + ResolverPool singletons (loaded once, shared across all bots)
// ══════════════════════════════════════════════════════════════

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dirname, '../../../..');

// Shared fast model (cfr-combined-v3 — trained on all 4 pipeline datasets)
let sharedFastModel: MLP | null | undefined; // undefined = not yet loaded

function getSharedFastModel(): MLP | null {
  if (sharedFastModel !== undefined) return sharedFastModel;
  const modelPath = resolve(PROJECT_ROOT, 'models/vnet-v91-balanced.json');
  sharedFastModel = loadModel(modelPath);
  if (sharedFastModel) {
    logInfo({ event: 'bot.model', message: `Shared fast model loaded: vnet-v91-balanced.json` });
  } else {
    logWarn({ event: 'bot.model', message: `Fast model not found at ${modelPath}` });
  }
  return sharedFastModel;
}

// NOTE: ResolverPool is intentionally NOT loaded for in-process bots.
// solveStreet() is synchronous and blocks the game server's event loop
// for 500-2000ms per decision. The fast model (vnet-v7-gpu) is used instead.

// ══════════════════════════════════════════════════════════════
// Data collection directory (shared)
// ══════════════════════════════════════════════════════════════

const dataDir = resolve(__dirname, '../../../../data');
let dataDirEnsured = false;

function ensureDataDir(): void {
  if (dataDirEnsured) return;
  if (!existsSync(dataDir)) {
    mkdirSync(dataDir, { recursive: true });
  }
  dataDirEnsured = true;
}

// ══════════════════════════════════════════════════════════════
// InProcessBot
// ══════════════════════════════════════════════════════════════

export class InProcessBot {
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
  private sessionStats: SessionStats = createSessionStats();
  private lastHandStack: number | null = null;
  private lastHandId: string | null = null;
  private fastModel: MLP | null = null;
  private resolverPool: ResolverPool | null = null;
  private sampleCount = 0;
  private readonly MAX_SAMPLES_PER_FILE = 100_000;

  // Enhancement state
  private persona: BotPersona;
  private moodState: MoodState;
  private opponentTracker: OpponentTracker;
  private traceLogger: TraceLogger;
  private handNumber = 0;
  private lastProcessedActionCount = 0;
  private lastHandStrength: number | null = null;

  // Lifecycle
  private destroyed = false;
  private destroyCallback: (() => void) | null = null;
  private pendingTimers = new Set<ReturnType<typeof setTimeout>>();
  private readonly logPrefix: string;

  constructor(private config: InProcessBotConfig) {
    this.mySeat = config.seat;
    this.profile = getProfile(config.profile);
    this.myName = config.botName;
    this.actDelay = config.delay ?? 800;
    this.logPrefix = `[bot:seat${this.mySeat}/${this.profile.id}]`;

    // ── Initialize persona (fixed for entire session) ──
    this.persona = generatePersona(this.profile.id);
    this.log(
      `Persona: L/T=${this.persona.looseTightBias.toFixed(2)} ` +
        `P/A=${this.persona.passiveAggressiveBias.toFixed(2)} ` +
        `bluff=${this.persona.bluffFrequency.toFixed(2)} ` +
        `hero=${this.persona.heroCallTendency.toFixed(2)}`,
    );

    // ── Initialize mood & opponent tracker & trace logger ──
    this.moodState = createMoodState();
    this.opponentTracker = new OpponentTracker();
    this.traceLogger = new TraceLogger();

    // ── Load shared fast model (cfr-combined-v3) ──
    // NOTE: ResolverPool is intentionally disabled for in-process bots.
    // solveStreet() is synchronous and blocks the game server's event loop
    // for 500-2000ms per decision. The fast model produces good results in <1ms.
    this.fastModel = getSharedFastModel();
    if (this.fastModel) {
      this.log('Fast model loaded (cfr-combined-v3)');
    }

    // ── Ensure data directory exists ──
    ensureDataDir();

    this.log(
      `Connecting to ${config.serverUrl} as "${this.myName}" ` +
        `(profile=${this.profile.id}, seat=${this.mySeat})`,
    );

    this.socket = io(config.serverUrl, {
      auth: {
        displayName: this.myName,
        userId: config.userId,
      },
      transports: ['websocket'],
      reconnection: false, // in-process — no network partition
      forceNew: true, // each bot gets its own connection
    });

    this.wireEvents();
  }

  // ── Public API ──

  /** Register a callback to run when this bot is destroyed / disconnects. */
  onDestroy(cb: () => void): void {
    this.destroyCallback = cb;
  }

  /** Cleanly disconnect and tear down all listeners + timers. */
  destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;

    // Clear all pending timers
    for (const h of this.pendingTimers) clearTimeout(h);
    this.pendingTimers.clear();

    // Disconnect socket
    this.socket.removeAllListeners();
    this.socket.disconnect();

    this.log('Destroyed');

    // Notify orchestrator
    this.destroyCallback?.();
  }

  /** Whether the bot's socket is currently connected. */
  get connected(): boolean {
    return this.socket.connected;
  }

  // ── Private helpers ──

  private log(msg: string): void {
    logInfo({ event: 'bot.inprocess', message: `${this.logPrefix} ${msg}` });
  }

  private warn(msg: string): void {
    logWarn({ event: 'bot.inprocess', message: `${this.logPrefix} ${msg}` });
  }

  /** Schedule a timeout that is automatically tracked for cleanup. */
  private schedule(fn: () => void, ms: number): void {
    if (this.destroyed) return;
    const handle = setTimeout(() => {
      this.pendingTimers.delete(handle);
      if (!this.destroyed) fn();
    }, ms);
    this.pendingTimers.add(handle);
  }

  // ── Socket event wiring ──

  private wireEvents(): void {
    this.socket.on('connect', () => {
      if (this.destroyed) return;
      this.log('Connected, joining room...');
      this.socket.emit('join_room_code', { roomCode: this.config.roomCode });
    });

    this.socket.on('connect_error', (err) => {
      if (this.destroyed) return;
      this.warn(`Connection error: ${err.message}`);
    });

    this.socket.on('disconnect', (reason) => {
      if (this.destroyed) return;
      this.log(`Disconnected: ${reason}`);
      this.seated = false;
    });

    this.socket.on(
      'connected',
      (data: { socketId: string; userId: string; displayName: string }) => {
        if (this.destroyed) return;
        this.log(`Server acknowledged: userId=${data.userId}, name=${data.displayName}`);
      },
    );

    this.socket.on(
      'room_joined',
      (data: { tableId: string; roomCode: string; roomName: string }) => {
        if (this.destroyed) return;
        this.tableId = data.tableId;
        this.log(`Joined room "${data.roomName}" (tableId=${data.tableId})`);
        if (!this.seated) {
          this.trySitDown();
        }
      },
    );

    this.socket.on('error_event', (data: { message: string }) => {
      if (this.destroyed) return;
      this.warn(`Server error: ${data.message}`);
      if (!this.seated && (data.message.includes('seat') || data.message.includes('Seat'))) {
        this.log('Will retry sit_down in 3s...');
        this.schedule(() => this.trySitDown(), 3000);
      }
    });

    // ── Hole cards ──
    this.socket.on('hole_cards', (data: { handId: string; cards: string[]; seat: number }) => {
      if (this.destroyed) return;
      if (data.seat === this.mySeat && data.cards && data.cards.length >= 2) {
        this.myCards = [data.cards[0], data.cards[1]];
        this.log(`Hole cards: ${this.myCards[0]} ${this.myCards[1]}`);
      }
    });

    // ── Hand started ──
    this.socket.on('hand_started', (data: { handId: string }) => {
      if (this.destroyed) return;
      this.myCards = null;
      this.pendingAdvice = null;
      this.lastHandId = data.handId;
      this.handNumber++;
      this.lastProcessedActionCount = 0;
      this.lastHandStrength = null;
      this.resolverPool?.resetHand();

      const me = this.latestState?.players.find((p) => p.seat === this.mySeat);
      this.lastHandStack = me?.stack ?? null;

      if (this.latestState) {
        this.opponentTracker.observeHandStart(this.latestState);
      }
    });

    // ── Table snapshot ──
    this.socket.on('table_snapshot', (state: TableState) => {
      if (this.destroyed) return;
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

          const wasBadBeat = !won && this.lastHandStrength != null && this.lastHandStrength >= 0.65;
          this.moodState = updateMood(
            this.moodState,
            {
              net,
              wasShowdown: this.lastHandStrength != null,
              wasBadBeat,
            },
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
        }
        this.lastHandStack = null;
        this.lastHandId = null;
      }

      this.maybeAct();
    });

    // ── Advice payload ──
    this.socket.on('advice_payload', (advice: AdvicePayload) => {
      if (this.destroyed) return;
      if (advice.seat === this.mySeat && advice.mix) {
        this.log(
          `Received advice: R=${advice.mix.raise.toFixed(2)} C=${advice.mix.call.toFixed(2)} F=${advice.mix.fold.toFixed(2)}`,
        );
        this.pendingAdvice = advice.mix;
        this.collectSample(advice);
        this.maybeAct();
      }
    });

    // ── Action applied ──
    this.socket.on('action_applied', (data: { seat: number; action: string; amount: number }) => {
      if (this.destroyed) return;
      if (data.seat === this.mySeat) {
        this.log(`Action confirmed: ${data.action}${data.amount ? ` ${data.amount}` : ''}`);
      }
    });

    // ── All-in runout: always choose run once / agree to any choice ──
    this.socket.on('all_in_prompt', (data: { actorSeat: number; allowedRunCounts: number[] }) => {
      if (this.destroyed) return;
      if (data.actorSeat !== this.mySeat) return;
      // Only submit immediately if we're the underdog (allowed > 1 option)
      if (data.allowedRunCounts.length > 1) {
        this.log('All-in prompt (underdog), choosing run once');
        this.socket.emit('run_count_submit', {
          tableId: this.tableId,
          handId: this.lastHandId,
          runCount: 1,
        });
      }
      // Non-underdog: wait for allin_locked with targetRunCount
    });

    // ── When underdog has chosen, non-underdog bots agree immediately ──
    this.socket.on(
      'allin_locked',
      (data: {
        handId: string;
        underdogSeat: number;
        targetRunCount: number | null;
        submittedPlayerIds: number[];
        eligiblePlayers: Array<{ seat: number }>;
      }) => {
        if (this.destroyed) return;
        // Only act if we're eligible but haven't submitted yet
        if (!data.eligiblePlayers.some((p) => p.seat === this.mySeat)) return;
        if (data.submittedPlayerIds.includes(this.mySeat)) return;
        if (data.targetRunCount == null) return; // underdog hasn't chosen yet
        this.log(`All-in locked (target=${data.targetRunCount}), agreeing`);
        this.socket.emit('run_count_submit', {
          tableId: this.tableId,
          handId: data.handId,
          runCount: data.targetRunCount as 1 | 2 | 3,
        });
      },
    );
  }

  // ── Opponent tracking ──

  private observeNewActions(state: TableState): void {
    if (!state.handId) return;
    const actions = state.actions;
    for (let i = this.lastProcessedActionCount; i < actions.length; i++) {
      this.opponentTracker.observeAction(actions[i], state, this.mySeat);
    }
    this.lastProcessedActionCount = actions.length;
  }

  // ── Sit down ──

  private trySitDown(): void {
    if (this.seated || !this.tableId || this.destroyed) return;
    this.log(`Sitting down at seat ${this.mySeat} with buyIn=${this.config.buyIn}`);
    this.socket.emit('sit_down', {
      tableId: this.tableId,
      seat: this.mySeat,
      buyIn: this.config.buyIn,
      name: this.myName,
    });
    this.seated = true;
  }

  // ── Decision loop ──

  private maybeAct(): void {
    if (this.destroyed) return;
    const state = this.latestState;
    if (!state || !state.handId || state.actorSeat !== this.mySeat) return;
    if (!state.legalActions) return;

    // Dedup: don't act twice for the same decision point
    const dedupKey = `${state.handId}:${state.street}:${state.currentBet}:${state.pot}`;
    if (this.handActedMap.has(dedupKey)) return;
    this.handActedMap.add(dedupKey);

    // Prune old dedup entries
    if (this.handActedMap.size > 200) {
      const entries = [...this.handActedMap];
      entries.slice(0, 100).forEach((k) => this.handActedMap.delete(k));
    }

    // Context-dependent thinking time
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

    // If bot has resolverPool or fastModel, act immediately after thinking time
    // (resolver is tier 0.5 — higher priority than server advice tier 1)
    const hasLocalSolver = !!(this.resolverPool || this.fastModel);

    const actAfterDelay = () => {
      if (this.destroyed) return;
      if (hasLocalSolver || this.pendingAdvice) {
        this.act(state);
        return;
      }
      // No local solver — poll for server advice (max 1500ms)
      const adviceDeadline = Date.now() + 1500;
      const checkAndAct = () => {
        if (this.destroyed) return;
        if (this.pendingAdvice || Date.now() >= adviceDeadline) {
          this.act(state);
          return;
        }
        this.schedule(checkAndAct, 200);
      };
      checkAndAct();
    };

    // Two-stage thinking time
    if (thinkingTime.twoStage) {
      this.schedule(() => {
        this.schedule(actAfterDelay, thinkingTime.secondStageMs);
      }, thinkingTime.firstStageMs);
    } else {
      this.schedule(actAfterDelay, thinkingTime.delayMs);
    }
  }

  // ── Training sample collection (async file I/O) ──

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

      const features = encodeFeatures(
        this.myCards,
        state.board,
        state.street,
        state.pot,
        bb,
        state.legalActions?.callAmount ?? 0,
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

      const fileIdx = Math.floor(this.sampleCount / this.MAX_SAMPLES_PER_FILE);
      const filePath = resolve(
        dataDir,
        `training-samples${fileIdx > 0 ? `-${fileIdx}` : ''}.jsonl`,
      );
      // Async write — never block the event loop
      appendFile(filePath, JSON.stringify(sample) + '\n', () => {});
      this.sampleCount++;
    } catch {
      // Never let data collection crash the bot
    }
  }

  // ── Execute action ──

  private act(state: TableState): void {
    if (this.destroyed) return;
    if (!this.tableId || !state.handId || !state.legalActions) return;

    try {
      const advice = this.pendingAdvice;
      this.pendingAdvice = null;

      const adaptiveAdj = computeAdaptiveAdjustments(this.sessionStats);

      // Compute opponent adjustment for the raiser (if facing one)
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

      // Track hand strength for bad beat detection
      if (this.myCards) {
        this.lastHandStrength = quickHandStrength(this.myCards, state.board, state.street);
      }

      const result = decide({
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

      this.log(
        `Hand ${state.handId.slice(0, 8)} ${state.street} pot=${state.pot} → ${result.action}` +
          `${result.amount != null ? ` ${result.amount}` : ''} (${result.reasoning})`,
      );

      if (result.trace) {
        this.traceLogger.log(result.trace);
      }

      const facingRaise = (state.legalActions.callAmount ?? 0) > (state.bigBlind || 1);
      recordAction(this.sessionStats, result.action, facingRaise);

      this.emitAction(state, result.action, result.amount);
    } catch (err) {
      this.warn(`decide() threw: ${(err as Error).message}`);
      // Fallback: check if possible, otherwise fold
      const fallbackAction = state.legalActions!.canCheck ? 'check' : 'fold';
      this.log(`Fallback action: ${fallbackAction}`);
      this.emitAction(state, fallbackAction);
    }
  }

  private emitAction(state: TableState, action: string, amount?: number): void {
    const payload: { tableId: string; handId: string; action: string; amount?: number } = {
      tableId: this.tableId!,
      handId: state.handId!,
      action,
    };
    if (amount != null) {
      payload.amount = amount;
    }
    this.socket.emit('action_submit', payload);
  }
}
