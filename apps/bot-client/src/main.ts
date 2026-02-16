#!/usr/bin/env node
import { io, type Socket } from 'socket.io-client';
import { getProfile } from './profiles.js';
import { decide } from './decision.js';
import type { TableState, AdvicePayload, StrategyMix } from './types.js';

// ===== CLI argument parsing =====
interface BotArgs {
  server: string;
  room: string;
  seat: number;
  buyin: number;
  profile: string;
  name?: string;
  userId?: string;
  delay?: number; // ms to wait before acting (humanize)
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

  if (!room) {
    console.error('Usage: --room <ROOM_CODE> [--server url] [--seat N] [--buyin N] [--profile id] [--name str] [--userId str] [--delay ms]');
    process.exit(1);
  }

  return { server, room, seat, buyin, profile, name, userId, delay };
}

// ===== Bot class =====
class PokerBot {
  private socket: Socket;
  private tableId: string | null = null;
  private mySeat: number;
  private myName: string;
  private latestState: TableState | null = null;
  private pendingAdvice: StrategyMix | null = null;
  private profile;
  private actDelay: number;
  private seated = false;
  private handActedMap = new Set<string>(); // handId:street to avoid double-acting

  constructor(private args: BotArgs) {
    this.mySeat = args.seat;
    this.profile = getProfile(args.profile);
    this.myName = args.name ?? `Bot-${this.profile.displayName}`;
    this.actDelay = args.delay ?? 800;

    const botUserId = args.userId ?? `bot-${this.profile.id}-${this.mySeat}-${Date.now()}`;

    this.log(`Connecting to ${args.server} as "${this.myName}" (profile=${this.profile.id}, seat=${this.mySeat})`);

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

    this.socket.on('connected', (data: { socketId: string; userId: string; displayName: string }) => {
      this.log(`Server acknowledged: userId=${data.userId}, name=${data.displayName}`);
    });

    this.socket.on('room_joined', (data: { tableId: string; roomCode: string; roomName: string }) => {
      this.tableId = data.tableId;
      this.log(`Joined room "${data.roomName}" (tableId=${data.tableId})`);
      if (!this.seated) {
        this.trySitDown();
      }
    });

    this.socket.on('error_event', (data: { message: string }) => {
      this.log(`Server error: ${data.message}`);
      // Retry sit_down if seat-related error and we're not seated
      if (!this.seated && data.message.includes('seat') || data.message.includes('Seat')) {
        this.log('Will retry sit_down in 3s...');
        setTimeout(() => this.trySitDown(), 3000);
      }
    });

    this.socket.on('table_snapshot', (state: TableState) => {
      this.latestState = state;

      // If tableId wasn't set from room_joined, grab it from snapshot
      if (!this.tableId && state.tableId) {
        this.tableId = state.tableId;
      }

      // Try to sit down if not seated yet
      if (!this.seated) {
        const alreadySeated = state.players.some(p => p.seat === this.mySeat);
        if (alreadySeated) {
          this.seated = true;
          this.log('Already seated (detected from snapshot)');
        } else {
          this.trySitDown();
          return;
        }
      }

      // Check if it's our turn to act
      this.maybeAct();
    });

    this.socket.on('advice_payload', (advice: AdvicePayload) => {
      if (advice.seat === this.mySeat && advice.mix) {
        this.log(`Received advice: R=${advice.mix.raise.toFixed(2)} C=${advice.mix.call.toFixed(2)} F=${advice.mix.fold.toFixed(2)}`);
        this.pendingAdvice = advice.mix;
        // Re-check if we should act (advice may arrive after snapshot)
        this.maybeAct();
      }
    });

    this.socket.on('action_applied', (data: { seat: number; action: string; amount: number }) => {
      if (data.seat === this.mySeat) {
        this.log(`Action confirmed: ${data.action}${data.amount ? ` ${data.amount}` : ''}`);
      }
    });

    // Handle reconnection: re-join room
    this.socket.io.on('reconnect', () => {
      this.log('Reconnected, re-joining room...');
      this.socket.emit('join_room_code', { roomCode: this.args.room });
    });
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
    // Optimistically mark as seated; error_event will reset
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
      entries.slice(0, 100).forEach(k => this.handActedMap.delete(k));
    }

    // Delay to appear more human
    const delay = this.actDelay + Math.floor(Math.random() * 500);
    setTimeout(() => this.act(state), delay);
  }

  private act(state: TableState): void {
    if (!this.tableId || !state.handId || !state.legalActions) return;

    // Use pending advice if available, then clear
    const advice = this.pendingAdvice;
    this.pendingAdvice = null;

    const result = decide(state, this.profile, advice);

    this.log(
      `Hand ${state.handId.slice(0, 8)} ${state.street} pot=${state.pot} → ${result.action}` +
      `${result.amount != null ? ` ${result.amount}` : ''} (${result.reasoning})`
    );

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
}

// ===== Entry point =====
const botArgs = parseArgs(process.argv.slice(2));
new PokerBot(botArgs);
