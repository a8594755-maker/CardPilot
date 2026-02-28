// Export preflop solver results in two formats:
//
// 1. Web Display JSON — per-spot files for the GTO Wizard-style trainer
// 2. AI Training JSONL — flat records optimized for ML training pipelines
//
// Both formats contain the same underlying data: for each decision point,
// the GTO-optimal action frequencies for all 169 hand classes.

import { mkdirSync, writeFileSync, openSync, writeSync, closeSync } from 'node:fs';
import { join } from 'node:path';
import type {
  PreflopGameNode,
  PreflopActionNode,
  PreflopSolveConfig,
  SpotSolution,
  SolutionIndex,
  ScenarioType,
  Position,
} from './preflop-types.js';
import { POSITION_6MAX, NUM_HAND_CLASSES, allHandClasses, indexToHandClass } from './preflop-types.js';
import { InfoSetStore } from '../engine/info-set-store.js';

// ── Types ──

interface SpotInfo {
  historyKey: string;
  seat: number;
  position: Position;
  actions: string[];
  pot: number;
  scenario: ScenarioType;
  description: string;
}

/** AI training record — one per (spot, handClass) pair. */
export interface TrainingRecord {
  format: string;        // 'cash_6max_100bb'
  spot: string;          // 'BB_vs_BTN_open'
  position: string;      // 'BB'
  scenario: string;      // 'facing_open'
  handClass: string;     // 'AKs'
  handClassIndex: number;// 1
  actions: string[];     // ['fold','call','3bet_8.75']
  frequencies: number[]; // [0.05, 0.55, 0.40]
  pot: number;           // 3.5
  history: string;       // 'Uo-Hf-Cf-Bf'  (raw action sequence)
}

// ── Export for Web Display ──

/**
 * Walk the solved tree and export per-spot JSON files for the web trainer.
 */
export function exportForWeb(
  root: PreflopActionNode,
  store: InfoSetStore,
  config: PreflopSolveConfig,
  outputDir: string,
  solveMetadata: { iterations: number; exploitability: number; solveDate: string },
): string[] {
  mkdirSync(outputDir, { recursive: true });

  const spots = collectSpots(root);
  const handClasses = allHandClasses();
  const exportedFiles: string[] = [];

  const indexEntries: SolutionIndex['spots'] = [];

  for (const spot of spots) {
    const grid: Record<string, Record<string, number>> = {};
    const actionTotals: Record<string, number> = {};
    let rangeSize = 0;
    let totalCombos = 0;

    for (const action of spot.actions) {
      actionTotals[action] = 0;
    }

    for (let hc = 0; hc < NUM_HAND_CLASSES; hc++) {
      const infoKey = `${hc}|${spot.historyKey}`;
      const avg = store.getAverageStrategy(infoKey, spot.actions.length);
      const handClass = handClasses[hc];

      const freqs: Record<string, number> = {};
      let hasFold = false;
      let foldFreq = 0;

      for (let a = 0; a < spot.actions.length; a++) {
        const freq = Math.round(avg[a] * 1000) / 1000; // 3 decimal places
        freqs[spot.actions[a]] = freq;
        actionTotals[spot.actions[a]] += freq;

        if (spot.actions[a] === 'fold') {
          hasFold = true;
          foldFreq = freq;
        }
      }

      grid[handClass] = freqs;
      totalCombos++;
      if (!hasFold || foldFreq < 0.99) rangeSize++;
    }

    // Normalize action totals to frequencies
    const actionFrequencies: Record<string, number> = {};
    for (const [action, total] of Object.entries(actionTotals)) {
      actionFrequencies[action] = Math.round((total / totalCombos) * 1000) / 1000;
    }

    const spotName = buildSpotName(spot);
    const solution: SpotSolution = {
      spot: spotName,
      format: config.name,
      heroPosition: spot.position,
      villainPosition: inferVillain(spot),
      scenario: spot.scenario,
      potSize: Math.round(spot.pot * 100) / 100,
      actions: spot.actions,
      grid,
      summary: {
        totalCombos,
        rangeSize,
        actionFrequencies,
      },
      metadata: {
        iterations: solveMetadata.iterations,
        exploitability: solveMetadata.exploitability,
        solveDate: solveMetadata.solveDate,
        solver: 'cardpilot-preflop-cfr-v1',
      },
    };

    const filename = `${spotName}.json`;
    writeFileSync(join(outputDir, filename), JSON.stringify(solution, null, 2));
    exportedFiles.push(filename);

    indexEntries.push({
      file: filename,
      spot: spotName,
      heroPosition: spot.position,
      scenario: spot.scenario,
    });
  }

  // Write index.json
  const index: SolutionIndex = {
    format: config.name,
    configs: [config.name],
    spots: indexEntries,
    solveDate: solveMetadata.solveDate,
  };
  writeFileSync(join(outputDir, 'index.json'), JSON.stringify(index, null, 2));
  exportedFiles.push('index.json');

  // Write metadata.json
  writeFileSync(join(outputDir, 'metadata.json'), JSON.stringify({
    config: config.name,
    ...solveMetadata,
    solver: 'cardpilot-preflop-cfr-v1',
    totalSpots: spots.length,
    totalInfoSets: store.size,
  }, null, 2));
  exportedFiles.push('metadata.json');

  return exportedFiles;
}

// ── Export for AI Training ──

/**
 * Export flat JSONL records for AI/ML training.
 * Each line is one training sample: (spot, handClass, action_frequencies).
 * This format is optimized for:
 *   - Supervised learning (predict GTO frequencies)
 *   - Feature extraction (spot context + hand features)
 *   - Batch processing with standard ML tools
 */
export function exportForTraining(
  root: PreflopActionNode,
  store: InfoSetStore,
  config: PreflopSolveConfig,
  outputPath: string,
): number {
  const spots = collectSpots(root);
  const handClasses = allHandClasses();
  let recordCount = 0;

  // Stream to file in chunks to avoid memory issues with large trees
  const fd = openSync(outputPath, 'w');

  for (const spot of spots) {
    const spotName = buildSpotName(spot);
    const chunk: string[] = [];

    for (let hc = 0; hc < NUM_HAND_CLASSES; hc++) {
      const infoKey = `${hc}|${spot.historyKey}`;
      const avg = store.getAverageStrategy(infoKey, spot.actions.length);

      const record: TrainingRecord = {
        format: config.name,
        spot: spotName,
        position: spot.position,
        scenario: spot.scenario,
        handClass: handClasses[hc],
        handClassIndex: hc,
        actions: spot.actions,
        frequencies: Array.from(avg).map(f => Math.round(f * 10000) / 10000),
        pot: Math.round(spot.pot * 100) / 100,
        history: spot.historyKey,
      };

      chunk.push(JSON.stringify(record));
      recordCount++;
    }

    writeSync(fd, chunk.join('\n') + '\n');
  }

  closeSync(fd);
  return recordCount;
}

/**
 * Export complete raw info-set data for advanced AI training.
 * Includes every info-set key and its strategy, without any interpretation.
 */
export function exportRawInfoSets(
  store: InfoSetStore,
  outputPath: string,
): number {
  const lines: string[] = [];
  let count = 0;

  for (const entry of store.entries()) {
    lines.push(JSON.stringify({
      key: entry.key,
      numActions: entry.numActions,
      strategy: Array.from(entry.averageStrategy).map(f => Math.round(f * 10000) / 10000),
    }));
    count++;
  }

  writeFileSync(outputPath, lines.join('\n') + '\n');
  return count;
}

// ── Spot collection ──

function collectSpots(root: PreflopActionNode): SpotInfo[] {
  const spots: SpotInfo[] = [];
  const seen = new Set<string>();

  function walk(node: PreflopGameNode): void {
    if (node.type === 'terminal') return;
    const act = node as PreflopActionNode;

    // Use historyKey + seat as unique identifier
    const key = `${act.seat}|${act.historyKey}`;
    if (!seen.has(key)) {
      seen.add(key);
      spots.push({
        historyKey: act.historyKey,
        seat: act.seat,
        position: act.position,
        actions: [...act.actions],
        pot: act.pot,
        scenario: classifyScenario(act.historyKey),
        description: buildDescription(act),
      });
    }

    for (const child of act.children.values()) {
      walk(child);
    }
  }

  walk(root);
  return spots;
}

function classifyScenario(history: string): ScenarioType {
  if (!history) return 'RFI';
  const parts = history.split('-');
  const raises = parts.filter(p => /[o34A]/.test(p.slice(-1)));
  if (raises.length === 0) return 'RFI';

  if (raises.length === 1) return 'facing_open';
  if (raises.length === 2) return 'facing_3bet';
  return 'facing_4bet';
}

function buildSpotName(spot: SpotInfo): string {
  const pos = spot.position;
  if (spot.scenario === 'RFI') return `${pos}_RFI`;

  // Parse history to find villain
  const villain = inferVillain(spot);
  if (!villain) return `${pos}_${spot.scenario}`;

  if (spot.scenario === 'facing_open') return `${pos}_vs_${villain}_open`;
  if (spot.scenario === 'facing_3bet') return `${pos}_vs_${villain}_3bet`;
  if (spot.scenario === 'facing_4bet') return `${pos}_vs_${villain}_4bet`;

  return `${pos}_${spot.scenario}`;
}

function inferVillain(spot: SpotInfo): Position | undefined {
  if (!spot.historyKey) return undefined;
  const parts = spot.historyKey.split('-');
  // Find the last raiser before this spot
  const posMap: Record<string, Position> = {
    'U': 'UTG', 'H': 'HJ', 'C': 'CO', 'B': 'BTN', 'S': 'SB', 'b': 'BB',
  };

  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    if (p.length >= 2 && /[o34A]/.test(p[1])) {
      return posMap[p[0]];
    }
  }
  return undefined;
}

function buildDescription(node: PreflopActionNode): string {
  if (!node.historyKey) return `${node.position} to act (unopened)`;
  return `${node.position} to act after: ${node.historyKey}`;
}
