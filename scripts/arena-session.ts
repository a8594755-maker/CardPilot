#!/usr/bin/env tsx
/**
 * arena-session.ts — Single session worker (called by arena.ts parallel mode)
 * Outputs JSON array of per-hand chip-net for seat A to stdout.
 */
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { GameTable } from '../packages/game-engine/src/index.js';
import { loadModel } from '../packages/fast-model/src/index.js';
import { decide } from '../apps/bot-client/src/decision.js';
import { getProfile } from '../apps/bot-client/src/profiles.js';
import { ResolverPool } from '../apps/bot-client/src/realtime-resolver.js';
import type { MLP } from '../packages/fast-model/src/types.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

const SB = 25;
const BB = 50;
const BUY_IN = BB * 100;
const REBUY_THRESHOLD = BB * 20;
const SEAT_A = 1;
const SEAT_B = 2;

const FILE_MAP: Record<string, string> = {
  v3: 'cfr-combined-v3.json',
  'v3.2': 'cfr-combined-v3-preflop.json',
  v4: 'cfr-combined-v4.json',
  v6: 'vnet-v6-unified.json',
  v7: 'vnet-v7-gpu.json',
  v91: 'vnet-v91-balanced.json',
};

function loadBotModel(name: string): MLP {
  const file = FILE_MAP[name] ?? `cfr-combined-${name}.json`;
  const path = resolve(__dirname, `../models/${file}`);
  const model = loadModel(path);
  if (!model) throw new Error(`Cannot load: ${path}`);
  return model;
}

function runSession(
  numHands: number,
  nameA: string,
  nameB: string,
  resolverSeat: number | null,
): number[] {
  const modelA = loadBotModel(nameA);
  const modelB = loadBotModel(nameB);
  const models: Record<number, MLP> = { [SEAT_A]: modelA, [SEAT_B]: modelB };
  const profile = getProfile('gto_balanced');

  // Optionally initialize resolver for one bot
  let resolverPool: ResolverPool | null = null;
  if (resolverSeat != null) {
    const projectRoot = resolve(__dirname, '..');
    resolverPool = new ResolverPool({ projectRoot });
    const loaded = resolverPool.initialize();
    process.stderr.write(`Resolver loaded ${loaded} scenarios\n`);
  }

  let table = new GameTable({ tableId: 'arena', smallBlind: SB, bigBlind: BB });
  table.addPlayer({ seat: SEAT_A, userId: 'botA', name: nameA, stack: BUY_IN });
  table.addPlayer({ seat: SEAT_B, userId: 'botB', name: nameB, stack: BUY_IN });

  const results: number[] = [];
  let stuckCount = 0;

  while (results.length < numHands) {
    const stateNow = table.getPublicState();
    for (const seat of [SEAT_A, SEAT_B]) {
      const player = stateNow.players.find((p) => p.seat === seat);
      if (!player || player.stack < REBUY_THRESHOLD) {
        table.removePlayer(seat);
        table.addPlayer({
          seat,
          userId: seat === SEAT_A ? 'botA' : 'botB',
          name: seat === SEAT_A ? nameA : nameB,
          stack: BUY_IN,
        });
      }
    }

    const before = table.getPublicState();
    const stackBefore = before.players.find((p) => p.seat === SEAT_A)?.stack ?? BUY_IN;
    table.startHand();
    resolverPool?.resetHand();

    let handStuck = false;
    for (let step = 0; step < 500; step++) {
      const state = table.getPublicState();
      if (state.showdownPhase === 'decision') {
        table.finalizeShowdownReveals({ autoMuckLosingHands: true });
        continue;
      }
      if (table.isRunoutPending()) {
        table.performRunout();
        continue;
      }
      if (!table.isHandActive()) break;
      const actorSeat = state.actorSeat;
      if (actorSeat == null) {
        handStuck = true;
        break;
      }

      const result = decide({
        state,
        profile,
        advice: null,
        holeCards: table.getHoleCards(actorSeat),
        mySeat: actorSeat,
        fastModel: models[actorSeat] ?? null,
        resolverPool: actorSeat === resolverSeat ? resolverPool : null,
      });

      const la = state.legalActions;
      if (!la) break;
      let action = result.action,
        amount = result.amount;
      if (action === 'raise') {
        if (!la.canRaise) {
          action = la.canCall ? 'call' : 'fold';
          amount = undefined;
        } else if (amount != null)
          amount = Math.max(la.minRaise, Math.min(la.maxRaise ?? amount, amount));
      } else if (action === 'call' && !la.canCall) {
        action = la.canCheck ? 'check' : 'fold';
      } else if (action === 'check' && !la.canCheck) {
        action = la.canCall ? 'call' : 'fold';
      }
      table.applyAction(actorSeat, action, amount);
    }

    if (table.getPublicState().showdownPhase === 'decision')
      table.finalizeShowdownReveals({ autoMuckLosingHands: true });

    // If hand is stuck (e.g. all-in edge case), recreate the table to recover
    if (handStuck || table.isHandActive()) {
      stuckCount++;
      table = new GameTable({ tableId: 'arena', smallBlind: SB, bigBlind: BB });
      table.addPlayer({ seat: SEAT_A, userId: 'botA', name: nameA, stack: BUY_IN });
      table.addPlayer({ seat: SEAT_B, userId: 'botB', name: nameB, stack: BUY_IN });
      continue;
    }

    const stackAfter =
      table.getPublicState().players.find((p) => p.seat === SEAT_A)?.stack ?? stackBefore;
    results.push(stackAfter - stackBefore);
  }
  if (stuckCount > 0) {
    process.stderr.write(`${stuckCount} stuck hands skipped\n`);
  }
  return results;
}

const args = process.argv.slice(2);
let numHands = 1000,
  nameA = 'v4',
  nameB = 'v3',
  resolverFor: string | null = null;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--hands' && args[i + 1]) numHands = parseInt(args[++i], 10);
  if (args[i] === '--a' && args[i + 1]) nameA = args[++i];
  if (args[i] === '--b' && args[i + 1]) nameB = args[++i];
  if (args[i] === '--resolver' && args[i + 1]) resolverFor = args[++i];
}

const resolverSeat = resolverFor === 'a' ? SEAT_A : resolverFor === 'b' ? SEAT_B : null;
const results = runSession(numHands, nameA, nameB, resolverSeat);
process.stdout.write(JSON.stringify(results) + '\n');
