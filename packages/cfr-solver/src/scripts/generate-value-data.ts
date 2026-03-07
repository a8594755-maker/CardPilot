#!/usr/bin/env tsx
/**
 * Value Network Training Data Generator (Phase 1A)
 *
 * Runs full-game CFR on isomorphic flops and records street-transition EVs
 * at flop→turn and turn→river boundaries. This data trains the value network
 * that replaces the heuristic EV estimator in depth-limited solving.
 *
 * Output: binary file with combo-level transition records
 * (board, pot, stacks, reaches, EVs, combos) that the Python training
 * pipeline aggregates to hand classes.
 *
 * Usage:
 *   npx tsx packages/cfr-solver/src/scripts/generate-value-data.ts \
 *     --start 0 --end 500 --iters 200 --output data/value-net/part0.bin
 *
 * Run multiple instances in parallel for different flop ranges:
 *   --start 0    --end 500  --output data/value-net/part0.bin
 *   --start 500  --end 1000 --output data/value-net/part1.bin
 *   --start 1000 --end 1500 --output data/value-net/part2.bin
 *   --start 1500 --end 1755 --output data/value-net/part3.bin
 */

import { writeFileSync, mkdirSync, existsSync, appendFileSync, openSync, closeSync, writeSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';

import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { indexToCard } from '../abstraction/card-index.js';
import {
  solveFullGameCFR,
  setTransitionRecorder,
  type TransitionRecord,
} from '../vectorized/full-game-cfr.js';
import {
  COACH_HU_SRP_100BB,
  PIPELINE_SRP_CONFIG,
  HU_BTN_BB_SRP_100BB_CONFIG,
  HU_BTN_BB_SRP_50BB_CONFIG,
  PIPELINE_SRP_V2_CONFIG,
  PIPELINE_3BET_V2_CONFIG,
  PIPELINE_SRP_100BB_CONFIG,
  PIPELINE_3BET_100BB_CONFIG,
} from '../tree/tree-config.js';
import type { TreeConfig } from '../types.js';
import type { WeightedCombo } from '../integration/preflop-ranges.js';

// ─── CLI Args ───

const { values: args } = parseArgs({
  options: {
    start:  { type: 'string', default: '0' },
    end:    { type: 'string', default: '100' },
    iters:  { type: 'string', default: '200' },
    output: { type: 'string', default: 'data/value-net/transitions.bin' },
    config: { type: 'string', default: 'vnet' },
    mccfr:  { type: 'boolean', default: false },
  },
});

const START = parseInt(args.start!, 10);
const END = parseInt(args.end!, 10);
const ITERATIONS = parseInt(args.iters!, 10);
const OUTPUT_PATH = resolve(process.cwd(), args.output!);
const USE_MCCFR = args.mccfr!;

// ─── Tree Config Selection ───

// Value network data gen config: 2 bet sizes, 100bb, raise cap 1
// Much lighter than coaching (6 sizes) but more realistic than pipeline (1 size, no raises)
const VNET_DATA_CONFIG: TreeConfig = {
  startingPot: 5,
  effectiveStack: 97.5,
  betSizes: {
    flop:  [0.33, 0.75],
    turn:  [0.50, 1.00],
    river: [0.75, 1.50],
  },
  raiseCapPerStreet: 1,
};

function getConfig(name: string): TreeConfig {
  const configs: Record<string, TreeConfig> = {
    vnet: VNET_DATA_CONFIG,
    pipeline_srp: PIPELINE_SRP_CONFIG,
    pipeline_srp_v2: PIPELINE_SRP_V2_CONFIG,
    pipeline_3bet_v2: PIPELINE_3BET_V2_CONFIG,
    pipeline_srp_100bb: PIPELINE_SRP_100BB_CONFIG,
    pipeline_3bet_100bb: PIPELINE_3BET_100BB_CONFIG,
    hu_srp_100bb: HU_BTN_BB_SRP_100BB_CONFIG,
    hu_srp_50bb: HU_BTN_BB_SRP_50BB_CONFIG,
    coach_hu_srp_100bb: COACH_HU_SRP_100BB,
  };
  const cfg = configs[name];
  if (!cfg) throw new Error(`Unknown config: ${name}. Available: ${Object.keys(configs).join(', ')}`);
  return cfg;
}

const treeConfig = getConfig(args.config!);

// ─── Binary Format ───
//
// File header:
//   magic: 4 bytes "VNET"
//   version: uint32 LE
//   recordCount: uint32 LE (updated at end)
//
// Each record:
//   type: uint8 (0=flop_to_turn, 1=turn_to_river)
//   boardLen: uint8 (3 or 4)
//   board: uint8[boardLen]
//   pot: float32 LE
//   stack0: float32 LE
//   stack1: float32 LE
//   traverser: uint8
//   numCombos: uint16 LE
//   combos: uint8[numCombos * 2]
//   oopReach: float32[numCombos] LE
//   ipReach: float32[numCombos] LE
//   resultEV: float32[numCombos] LE

const TYPE_FLOP_TO_TURN = 0;
const TYPE_TURN_TO_RIVER = 1;

function writeHeader(fd: number): void {
  const buf = Buffer.alloc(12);
  buf.write('VNET', 0, 4, 'ascii');
  buf.writeUInt32LE(1, 4); // version
  buf.writeUInt32LE(0, 8); // recordCount (placeholder)
  writeSync(fd, buf);
}

function updateRecordCount(fd: number, count: number): void {
  const buf = Buffer.alloc(4);
  buf.writeUInt32LE(count, 0);
  writeSync(fd, buf, 0, 4, 8); // offset 8 in file
}

function writeRecord(fd: number, rec: TransitionRecord): void {
  const nc = rec.numCombos;
  // Header: 1 + 1 + boardLen + 4 + 4 + 4 + 1 + 2 = 17 + boardLen
  // Data: nc*2 + nc*4*3 = nc*14
  const boardLen = rec.board.length;
  const totalSize = 17 + boardLen + nc * 14;
  const buf = Buffer.alloc(totalSize);
  let offset = 0;

  // type
  buf.writeUInt8(rec.type === 'flop_to_turn' ? TYPE_FLOP_TO_TURN : TYPE_TURN_TO_RIVER, offset);
  offset += 1;

  // boardLen
  buf.writeUInt8(boardLen, offset);
  offset += 1;

  // board cards
  for (let i = 0; i < boardLen; i++) {
    buf.writeUInt8(rec.board[i], offset);
    offset += 1;
  }

  // pot, stacks
  buf.writeFloatLE(rec.pot, offset); offset += 4;
  buf.writeFloatLE(rec.stacks[0], offset); offset += 4;
  buf.writeFloatLE(rec.stacks[1], offset); offset += 4;

  // traverser
  buf.writeUInt8(rec.traverser, offset); offset += 1;

  // numCombos
  buf.writeUInt16LE(nc, offset); offset += 2;

  // combos (card pairs)
  for (let i = 0; i < nc; i++) {
    buf.writeUInt8(rec.combos[i][0], offset); offset += 1;
    buf.writeUInt8(rec.combos[i][1], offset); offset += 1;
  }

  // oopReach
  for (let i = 0; i < nc; i++) {
    buf.writeFloatLE(rec.oopReach[i], offset); offset += 4;
  }

  // ipReach
  for (let i = 0; i < nc; i++) {
    buf.writeFloatLE(rec.ipReach[i], offset); offset += 4;
  }

  // resultEV
  for (let i = 0; i < nc; i++) {
    buf.writeFloatLE(rec.resultEV[i], offset); offset += 4;
  }

  writeSync(fd, buf);
}

// ─── Uniform Range Generator ───

function uniformRange(): WeightedCombo[] {
  const combos: WeightedCombo[] = [];
  for (let c1 = 0; c1 < 52; c1++) {
    for (let c2 = c1 + 1; c2 < 52; c2++) {
      combos.push({ combo: [c1, c2], weight: 1.0 });
    }
  }
  return combos;
}

// ─── Main ───

async function main() {
  const allFlops = enumerateIsomorphicFlops();
  console.log(`Total isomorphic flops: ${allFlops.length}`);

  if (START >= allFlops.length || START < 0) {
    throw new Error(`Invalid --start ${START}. Must be 0..${allFlops.length - 1}`);
  }
  const end = Math.min(END, allFlops.length);
  const numFlops = end - START;
  console.log(`Processing flops ${START}..${end - 1} (${numFlops} flops)`);
  console.log(`Config: ${args.config}, Iterations: ${ITERATIONS}, MCCFR: ${USE_MCCFR}`);
  console.log(`Output: ${OUTPUT_PATH}`);

  // Ensure output directory exists
  const outDir = dirname(OUTPUT_PATH);
  if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });

  // Open output file
  const fd = openSync(OUTPUT_PATH, 'w');
  writeHeader(fd);

  const oopRange = uniformRange();
  const ipRange = uniformRange();

  let totalRecords = 0;
  let totalFlopToTurn = 0;
  let totalTurnToRiver = 0;
  const globalStart = Date.now();

  for (let fi = START; fi < end; fi++) {
    const flop = allFlops[fi];
    const board = flop.cards;
    const boardStr = board.map(c => indexToCard(c)).join(' ');
    const flopStart = Date.now();

    // Collect records for this flop
    let flopRecords = 0;

    setTransitionRecorder((record: TransitionRecord) => {
      writeRecord(fd, record);
      totalRecords++;
      flopRecords++;
      if (record.type === 'flop_to_turn') totalFlopToTurn++;
      else totalTurnToRiver++;
    });

    try {
      const result = solveFullGameCFR({
        board,
        treeConfig,
        oopRange,
        ipRange,
        iterations: ITERATIONS,
        mccfr: USE_MCCFR,
        onProgress: (phase, detail, pct) => {
          if (phase === 'cfr' && pct % 25 < 5) {
            // Sparse progress logging
          }
        },
      });

      // Update record count in header after each flop (crash-safe)
      updateRecordCount(fd, totalRecords);

      const elapsed = ((Date.now() - flopStart) / 1000).toFixed(1);
      const totalElapsed = ((Date.now() - globalStart) / 1000).toFixed(0);
      const remaining = numFlops - (fi - START + 1);
      const avgPerFlop = (Date.now() - globalStart) / (fi - START + 1) / 1000;
      const eta = (remaining * avgPerFlop / 60).toFixed(0);

      console.log(
        `[${fi - START + 1}/${numFlops}] ${boardStr} | ` +
        `${elapsed}s | ${flopRecords} records | ` +
        `mem ${result.memoryMB}MB | ` +
        `total: ${totalRecords} (F→T: ${totalFlopToTurn}, T→R: ${totalTurnToRiver}) | ` +
        `elapsed: ${totalElapsed}s | ETA: ${eta}min`
      );
    } catch (err) {
      console.error(`ERROR on flop ${boardStr}: ${err}`);
    }
  }

  // Clear recorder
  setTransitionRecorder(null);

  // Update record count in header
  updateRecordCount(fd, totalRecords);
  closeSync(fd);

  const totalElapsed = ((Date.now() - globalStart) / 1000).toFixed(1);
  console.log(`\nDone! ${totalRecords} records written to ${OUTPUT_PATH}`);
  console.log(`  Flop→Turn: ${totalFlopToTurn}, Turn→River: ${totalTurnToRiver}`);
  console.log(`  Total time: ${totalElapsed}s`);
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
