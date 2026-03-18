#!/usr/bin/env tsx
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { loadPreflopLibrary } from '../../src/preflop/preflop-library.js';
import { allHandClasses } from '../../src/preflop/preflop-types.js';

interface SpotSolution {
  spot: string;
  actions: string[];
  grid: Record<string, Record<string, number>>;
}

interface SpotReport {
  spot: string;
  position: string;
  scenario: string;
  handAccuracy: number;
  actionErrors: Record<string, number>;
  maxActionError: number;
}

interface ValidationReport {
  timestamp: string;
  config: string;
  overallAccuracy: number;
  minSpotAccuracy: number;
  passed: boolean;
  thresholds: {
    overallAccuracy: number;
    actionError: number;
  };
  spots: SpotReport[];
}

const HAND_CLASSES = allHandClasses();

function getArg(name: string, fallback: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function handCombos(handClass: string): number {
  if (handClass.length === 2) return 6;
  return handClass.endsWith('s') ? 4 : 12;
}

function loadSolution(solutionDir: string, spotId: string): SpotSolution | null {
  const path = join(solutionDir, `${spotId}.json`);
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as SpotSolution;
  } catch {
    return null;
  }
}

function rowAccuracy(
  truth: Record<string, number>,
  pred: Record<string, number>,
  actions: string[],
): number {
  let l1 = 0;
  for (const action of actions) {
    l1 += Math.abs((truth[action] ?? 0) - (pred[action] ?? 0));
  }
  const score = 1 - l1 / 2;
  return Math.max(0, Math.min(1, score));
}

function weightedActionError(
  truthGrid: Record<string, Record<string, number>>,
  predGrid: Record<string, Record<string, number>>,
  actions: string[],
): Record<string, number> {
  const combosByAction: Record<string, number> = {};
  const predByAction: Record<string, number> = {};
  for (const action of actions) {
    combosByAction[action] = 0;
    predByAction[action] = 0;
  }

  let total = 0;
  for (const hand of HAND_CLASSES) {
    const combos = handCombos(hand);
    total += combos;
    const truth = truthGrid[hand] ?? {};
    const pred = predGrid[hand] ?? {};
    for (const action of actions) {
      combosByAction[action] += combos * (truth[action] ?? 0);
      predByAction[action] += combos * (pred[action] ?? 0);
    }
  }

  const out: Record<string, number> = {};
  for (const action of actions) {
    out[action] = total > 0 ? Math.abs(combosByAction[action] - predByAction[action]) / total : 0;
  }
  return out;
}

function main(): void {
  const config = getArg('config', 'chart_solver_v1');
  const solutionDir = resolve(
    getArg('solutions', join(process.cwd(), 'data', 'preflop', 'solutions', config)),
  );
  const reportPath = resolve(
    getArg('out', join(process.cwd(), 'data', 'preflop', `validation_${config}.json`)),
  );
  const overallThreshold = parseFloat(getArg('overall-threshold', '0.95'));
  const actionErrorThreshold = parseFloat(getArg('action-error-threshold', '0.01'));

  const library = loadPreflopLibrary();
  if (!library) {
    throw new Error('preflop library not found');
  }

  const spotReports: SpotReport[] = [];
  for (const spot of library.spots) {
    const solved = loadSolution(solutionDir, spot.id);
    if (!solved) {
      throw new Error(`missing solution for spot ${spot.id} at ${solutionDir}`);
    }

    let weightedSum = 0;
    let totalCombos = 0;
    for (const hand of HAND_CLASSES) {
      const combos = handCombos(hand);
      const truth = spot.grid[hand] ?? {};
      const pred = solved.grid[hand] ?? {};
      weightedSum += combos * rowAccuracy(truth, pred, spot.actions);
      totalCombos += combos;
    }

    const handAccuracy = totalCombos > 0 ? weightedSum / totalCombos : 0;
    const actionErrors = weightedActionError(spot.grid, solved.grid, spot.actions);
    const maxActionError = Math.max(...Object.values(actionErrors));

    spotReports.push({
      spot: spot.id,
      position: spot.heroPosition,
      scenario: spot.scenario,
      handAccuracy,
      actionErrors,
      maxActionError,
    });
  }

  const overallAccuracy =
    spotReports.reduce((acc, row) => acc + row.handAccuracy, 0) / Math.max(1, spotReports.length);
  const minSpotAccuracy = Math.min(...spotReports.map((row) => row.handAccuracy));
  const maxActionError = Math.max(...spotReports.map((row) => row.maxActionError));

  const passed = overallAccuracy >= overallThreshold && maxActionError <= actionErrorThreshold;

  const report: ValidationReport = {
    timestamp: new Date().toISOString(),
    config,
    overallAccuracy,
    minSpotAccuracy,
    passed,
    thresholds: {
      overallAccuracy: overallThreshold,
      actionError: actionErrorThreshold,
    },
    spots: spotReports,
  };

  mkdirSync(dirname(reportPath), { recursive: true });
  writeFileSync(reportPath, JSON.stringify(report, null, 2));

  console.log(`Validation report written: ${reportPath}`);
  console.log(`Overall accuracy: ${(overallAccuracy * 100).toFixed(2)}%`);
  console.log(`Min spot accuracy: ${(minSpotAccuracy * 100).toFixed(2)}%`);
  console.log(`Max action error: ${(maxActionError * 100).toFixed(2)}%`);

  if (!passed) {
    process.exit(1);
  }
}

main();
