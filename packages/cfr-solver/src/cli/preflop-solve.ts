#!/usr/bin/env tsx
// CLI entry point for the preflop GTO solver.
//
// Commands:
//   equity   — Precompute 169×169 hand class equity table
//   solve    — Run CFR+ solver on a preflop config
//   export   — Export solved strategies to JSON (web) + JSONL (AI training)
//   verify   — Compare solutions against GTO Wizard charts
//   tree     — Print tree stats + scenario breakdown
//   batch    — Solve multiple configs (groups: hu, 3bet, 6max, all)
//
// Examples:
//   npx tsx preflop-solve.ts equity
//   npx tsx preflop-solve.ts solve --config cash_6max_100bb --iterations 1000000
//   npx tsx preflop-solve.ts solve --config cash_6max_100bb --iterations 1000000 --seed 42
//   npx tsx preflop-solve.ts export --config cash_6max_100bb
//   npx tsx preflop-solve.ts export --all-configs
//   npx tsx preflop-solve.ts verify --config cash_6max_100bb
//   npx tsx preflop-solve.ts tree --config cash_6max_100bb

import { resolve, join } from 'node:path';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { getPreflopConfig, PREFLOP_CONFIGS } from '../preflop/preflop-config.js';
import {
  buildPreflopTree,
  countPreflopNodes,
  collectInfoSetKeys,
  printTree,
} from '../preflop/preflop-tree.js';
import { solvePreflopCFR } from '../preflop/preflop-cfr.js';
import { EquityTable, computeFullEquityTable } from '../preflop/equity-table.js';
import { exportForWeb, exportForTraining, exportRawInfoSets } from '../preflop/preflop-export.js';
import { InfoSetStore } from '../engine/info-set-store.js';
import { NUM_HAND_CLASSES } from '../preflop/preflop-types.js';

// ── Path helpers ──

function findProjectRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 10; i++) {
    if (existsSync(join(dir, 'packages', 'cfr-solver'))) return dir;
    if (existsSync(join(dir, 'data'))) return dir;
    dir = resolve(dir, '..');
  }
  return process.cwd();
}

const ROOT = findProjectRoot();
const DATA_DIR = join(ROOT, 'data', 'preflop');
const EQUITY_PATH = join(DATA_DIR, 'equity_169x169.bin');
const SOLUTIONS_DIR = join(DATA_DIR, 'solutions');

// ── CLI parsing ──

function parseArgs(): { command: string; flags: Record<string, string> } {
  const args = process.argv.slice(2);
  const command = args[0] || 'help';
  const flags: Record<string, string> = {};

  for (let i = 1; i < args.length; i++) {
    if (args[i].startsWith('--')) {
      const key = args[i].slice(2);
      const value = args[i + 1] && !args[i + 1].startsWith('--') ? args[i + 1] : 'true';
      flags[key] = value;
      if (value !== 'true') i++;
    }
  }

  return { command, flags };
}

// ── Commands ──

async function cmdEquity(flags: Record<string, string>): Promise<void> {
  console.log('=== Preflop Equity Table Precomputation ===\n');

  mkdirSync(DATA_DIR, { recursive: true });

  const samples = parseInt(flags['samples'] || '10000');
  const startPair = parseInt(flags['start'] || '0');
  const endPair = flags['end'] ? parseInt(flags['end']) : undefined;

  const totalPairs = (NUM_HAND_CLASSES * (NUM_HAND_CLASSES - 1)) / 2;
  console.log(`Total unique pairs: ${totalPairs}`);
  console.log(`Range: ${startPair} to ${endPair ?? totalPairs}`);
  console.log(`Samples per combo matchup: ${samples}`);
  console.log('');

  const startTime = Date.now();

  const data = computeFullEquityTable(startPair, endPair, samples, (done, total) => {
    const pct = ((done / total) * 100).toFixed(1);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
    const rate = (done / ((Date.now() - startTime) / 1000)).toFixed(0);
    process.stdout.write(
      `\r  Progress: ${done}/${total} (${pct}%) — ${elapsed}s — ${rate} pairs/s`,
    );
  });

  console.log('\n');

  // If this is a partial computation, save as a shard
  if (startPair > 0 || endPair !== undefined) {
    const shardPath = join(DATA_DIR, `equity_shard_${startPair}_${endPair ?? totalPairs}.bin`);
    const table = EquityTable.fromData(data);
    table.save(shardPath);
    console.log(`Shard saved: ${shardPath}`);
    return;
  }

  // Full computation — save directly
  const table = EquityTable.fromData(data);
  table.save(EQUITY_PATH);
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`Equity table saved: ${EQUITY_PATH}`);
  console.log(`Time: ${elapsed}s`);
}

async function cmdSolve(flags: Record<string, string>): Promise<void> {
  const configName = flags['config'] || 'cash_6max_100bb';
  const iterations = parseInt(flags['iterations'] || flags['iter'] || '1000000');
  const seed = flags['seed'] ? parseInt(flags['seed']) : undefined;

  console.log('=== Preflop CFR+ Solver ===\n');
  console.log(`Config:     ${configName}`);
  console.log(`Iterations: ${iterations.toLocaleString()}`);
  if (seed !== undefined) console.log(`Seed:       ${seed}`);
  console.log('');

  // Load config
  const config = getPreflopConfig(configName);
  config.iterations = iterations;

  // Load equity table
  console.log('Loading equity table...');
  if (!existsSync(EQUITY_PATH)) {
    console.error(`ERROR: Equity table not found at ${EQUITY_PATH}`);
    console.error('Run "npx tsx preflop-solve.ts equity" first.');
    process.exit(1);
  }
  const equityTable = EquityTable.load(EQUITY_PATH);
  console.log('  Equity table loaded.\n');

  // Build game tree
  console.log('Building preflop game tree...');
  const root = buildPreflopTree(config);
  const nodeCount = countPreflopNodes(root);
  const infoKeys = collectInfoSetKeys(root);
  console.log(`  Action nodes:  ${nodeCount.action.toLocaleString()}`);
  console.log(`  Terminal nodes: ${nodeCount.terminal.toLocaleString()}`);
  console.log(`  Unique decision points: ${infoKeys.size.toLocaleString()}`);
  console.log(`  Info sets (× 169 hands): ~${(infoKeys.size * 169).toLocaleString()}`);
  console.log('');

  // Solve
  console.log('Running CFR+ solver...');
  const store = new InfoSetStore();
  const result = solvePreflopCFR({
    root,
    store,
    equityTable,
    config,
    iterations,
    seed,
    onProgress: (iter, elapsed) => {
      const pct = ((iter / iterations) * 100).toFixed(1);
      const ips = Math.round(iter / (elapsed / 1000));
      const memMB = Math.round(store.estimateMemoryBytes() / 1024 / 1024);
      process.stdout.write(
        `\r  ${iter.toLocaleString()} / ${iterations.toLocaleString()} (${pct}%) — ${ips.toLocaleString()} iter/s — ${memMB} MB`,
      );
    },
  });

  console.log('\n');
  console.log(`Done!`);
  console.log(`  Time:      ${(result.elapsed / 1000).toFixed(1)}s`);
  console.log(`  Info sets: ${result.infoSets.toLocaleString()}`);
  console.log(`  Peak RAM:  ${result.peakMemoryMB} MB`);
  console.log(
    `  Speed:     ${Math.round(iterations / (result.elapsed / 1000)).toLocaleString()} iter/s`,
  );

  // Save raw store for later export
  const storePath = join(DATA_DIR, `store_${configName}${seed ? `_seed${seed}` : ''}.jsonl`);
  mkdirSync(DATA_DIR, { recursive: true });
  const rawCount = exportRawInfoSets(store, storePath);
  console.log(`\n  Raw info-sets saved: ${storePath} (${rawCount.toLocaleString()} entries)`);

  // Auto-export if not a partial seed run
  if (!seed) {
    console.log('\nAuto-exporting solutions...');
    await doExport(configName, root, store, config, iterations);
  }
}

async function cmdExport(flags: Record<string, string>): Promise<void> {
  const allConfigs = flags['all-configs'] === 'true';
  const configNames = allConfigs
    ? Object.keys(PREFLOP_CONFIGS)
    : [flags['config'] || 'cash_6max_100bb'];

  for (const configName of configNames) {
    console.log(`\n=== Exporting: ${configName} ===\n`);

    const config = getPreflopConfig(configName);

    // Rebuild tree (lightweight)
    const root = buildPreflopTree(config);

    // Load store from saved raw data
    const storePath = join(DATA_DIR, `store_${configName}.jsonl`);
    if (!existsSync(storePath)) {
      console.error(`  ERROR: No solved data found at ${storePath}`);
      console.error(`  Run "npx tsx preflop-solve.ts solve --config ${configName}" first.`);
      continue;
    }

    const store = loadInfoSetStore(storePath);
    await doExport(configName, root, store, config, config.iterations);
  }
}

async function doExport(
  configName: string,
  root: ReturnType<typeof buildPreflopTree>,
  store: InfoSetStore,
  config: ReturnType<typeof getPreflopConfig>,
  iterations: number,
): Promise<void> {
  const outputDir = join(SOLUTIONS_DIR, configName);
  mkdirSync(outputDir, { recursive: true });

  // Web display JSON
  const webFiles = exportForWeb(root, store, config, outputDir, {
    iterations,
    exploitability: 0, // TODO: compute actual exploitability
    solveDate: new Date().toISOString().slice(0, 10),
  });
  console.log(`  Web JSON: ${webFiles.length} files → ${outputDir}`);

  // AI training JSONL
  const trainingPath = join(DATA_DIR, `training_${configName}.jsonl`);
  const trainingCount = exportForTraining(root, store, config, trainingPath);
  console.log(`  AI Training: ${trainingCount.toLocaleString()} records → ${trainingPath}`);
}

function loadInfoSetStore(path: string): InfoSetStore {
  const store = new InfoSetStore();
  const content = readFileSync(path, 'utf-8');
  const lines = content.trim().split('\n');

  for (const line of lines) {
    if (!line) continue;
    const entry = JSON.parse(line) as { key: string; numActions: number; strategy: number[] };
    // Reconstruct strategy sums from average strategy
    // (Approximate: use strategy as-is since we saved average)
    for (let a = 0; a < entry.numActions; a++) {
      store.addStrategyWeight(entry.key, a, entry.strategy[a] * 1000, entry.numActions);
    }
  }

  return store;
}

async function cmdVerify(flags: Record<string, string>): Promise<void> {
  const configName = flags['config'] || 'cash_6max_100bb';
  console.log(`=== Verify: ${configName} vs GTO Wizard ===\n`);

  const chartsPath = join(ROOT, 'data', 'preflop_charts.json');
  if (!existsSync(chartsPath)) {
    console.error(`GTO Wizard charts not found: ${chartsPath}`);
    process.exit(1);
  }

  const solutionDir = join(SOLUTIONS_DIR, configName);
  const indexPath = join(solutionDir, 'index.json');
  if (!existsSync(indexPath)) {
    console.error(`Solutions not found: ${indexPath}. Run export first.`);
    process.exit(1);
  }

  // Load GTO Wizard data
  const gtoData = JSON.parse(readFileSync(chartsPath, 'utf-8')) as Array<{
    format: string;
    spot: string;
    hand: string;
    mix: Record<string, number>;
  }>;

  // Map GTO Wizard spots to our spot names
  const spotMapping: Record<string, string> = {
    'UTG_unopened_open2.5x': 'UTG_RFI',
    'HJ_unopened_open2.5x': 'HJ_RFI',
    'CO_unopened_open2.5x': 'CO_RFI',
    'BTN_unopened_open2.5x': 'BTN_RFI',
    'SB_unopened_open2.5x': 'SB_RFI',
    'BB_vs_BTN_facing_open2.5x': 'BB_vs_BTN_open',
    'BB_vs_CO_facing_open2.5x': 'BB_vs_CO_open',
    'BB_vs_UTG_facing_open2.5x': 'BB_vs_UTG_open',
  };

  let totalDeviation = 0;
  let totalComparisons = 0;

  for (const [gtoSpot, ourSpot] of Object.entries(spotMapping)) {
    const ourFile = join(solutionDir, `${ourSpot}.json`);
    if (!existsSync(ourFile)) {
      console.log(`  SKIP: ${ourSpot} (not solved)`);
      continue;
    }

    const ourSolution = JSON.parse(readFileSync(ourFile, 'utf-8'));
    const gtoEntries = gtoData.filter((e) => e.spot === gtoSpot);

    let spotDeviation = 0;
    let spotCount = 0;

    for (const gtoEntry of gtoEntries) {
      const hand = gtoEntry.hand;
      const ourGrid = ourSolution.grid[hand];
      if (!ourGrid) continue;

      // Compare raise/call/fold frequencies
      const gtoRaise = gtoEntry.mix.raise || 0;
      const gtoCall = gtoEntry.mix.call || 0;
      const gtoFold = gtoEntry.mix.fold || 0;

      // Map our actions to raise/call/fold
      let ourRaise = 0,
        ourCall = 0,
        ourFold = 0;
      for (const [action, freq] of Object.entries(ourGrid)) {
        if (action === 'fold') ourFold += freq as number;
        else if (action === 'call' || action === 'check') ourCall += freq as number;
        else ourRaise += freq as number; // open, 3bet, etc.
      }

      const dev =
        Math.abs(gtoRaise - ourRaise) + Math.abs(gtoCall - ourCall) + Math.abs(gtoFold - ourFold);
      spotDeviation += dev;
      spotCount++;
    }

    if (spotCount > 0) {
      const avgDev = spotDeviation / spotCount;
      const status = avgDev < 0.1 ? 'PASS' : avgDev < 0.2 ? 'WARN' : 'FAIL';
      console.log(
        `  ${status}: ${ourSpot} — avg deviation ${(avgDev * 100).toFixed(1)}% (${spotCount} hands)`,
      );
      totalDeviation += spotDeviation;
      totalComparisons += spotCount;
    }
  }

  if (totalComparisons > 0) {
    const overallAvg = totalDeviation / totalComparisons;
    console.log(
      `\n  Overall: ${(overallAvg * 100).toFixed(1)}% avg deviation across ${totalComparisons} comparisons`,
    );
    console.log(`  Target: <5%`);
  }
}

async function cmdTree(flags: Record<string, string>): Promise<void> {
  const configName = flags['config'] || 'cash_6max_100bb';
  console.log(`=== Tree Stats: ${configName} ===\n`);

  const config = getPreflopConfig(configName);
  const root = buildPreflopTree(config);
  const counts = countPreflopNodes(root);
  const infoKeys = collectInfoSetKeys(root);

  console.log(`Players:          ${config.players} (${(config.positionLabels ?? []).join(', ')})`);
  console.log(`Stack:            ${config.stackSize}bb`);
  console.log(`Max raise level:  ${config.maxRaiseLevel ?? 4}`);
  console.log(`Action nodes:     ${counts.action.toLocaleString()}`);
  console.log(`Terminal nodes:   ${counts.terminal.toLocaleString()}`);
  console.log(`Total nodes:      ${(counts.action + counts.terminal).toLocaleString()}`);
  console.log(`Decision points:  ${infoKeys.size.toLocaleString()}`);
  console.log(`Info sets (×169): ${(infoKeys.size * 169).toLocaleString()}`);
  console.log(`Est. memory:      ${Math.round((infoKeys.size * 169 * 8 * 2) / 1024 / 1024)} MB`);

  // Scenario breakdown
  console.log('\nScenario breakdown:');
  const scenarios = new Map<string, string[]>();
  collectSpotSummary(root, scenarios);
  for (const [scenario, spots] of scenarios) {
    console.log(`  ${scenario}: ${spots.length} spots`);
    for (const spot of spots) {
      console.log(`    - ${spot}`);
    }
  }

  if (flags['print'] === 'true') {
    const depth = parseInt(flags['depth'] || '4');
    console.log(`\nTree (depth=${depth}):\n`);
    printTree(root, '', depth);
  }
}

function collectSpotSummary(
  node: PreflopGameNode,
  scenarios: Map<string, string[]>,
  seen = new Set<string>(),
): void {
  if (node.type === 'terminal') return;
  const act = node as PreflopActionNode;
  const key = `${act.seat}|${act.historyKey}`;
  if (!seen.has(key)) {
    seen.add(key);
    const scenario = classifySpotScenario(act.historyKey);
    const spotName = `${act.position} (${act.actions.join(', ')})`;
    if (!scenarios.has(scenario)) scenarios.set(scenario, []);
    scenarios.get(scenario)!.push(spotName);
  }
  for (const child of act.children.values()) {
    collectSpotSummary(child, scenarios, seen);
  }
}

function classifySpotScenario(history: string): string {
  if (!history) return 'RFI';
  const parts = history.split('-');
  const raises = parts.filter((p) => /[o0-9qA]/.test(p.slice(-1)));
  if (raises.length === 0) return 'RFI';
  const hasCall = parts.some((p) => p.endsWith('c'));
  const lastRaise = raises[raises.length - 1];
  if (hasCall && (lastRaise.endsWith('3') || lastRaise.endsWith('q'))) return 'squeeze';
  if (raises.length === 1) return 'facing_open';
  if (raises.length === 2) return 'facing_3bet';
  return 'facing_4bet';
}

type PreflopActionNode = import('../preflop/preflop-types.js').PreflopActionNode;
type PreflopGameNode = import('../preflop/preflop-types.js').PreflopGameNode;

async function cmdBatch(flags: Record<string, string>): Promise<void> {
  const group = flags['group'] || 'hu';
  const iterations = parseInt(flags['iterations'] || flags['iter'] || '1000000');

  const groups: Record<string, string[]> = {
    hu: Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('hu_')),
    threeway: Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('threeway_')),
    fourway: Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('fourway_')),
    '3bet': [
      ...Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('hu_')),
      ...Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('threeway_')),
      ...Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('fourway_')),
    ],
    '6max': Object.keys(PREFLOP_CONFIGS).filter((k) => k.startsWith('cash_6max_')),
    all: Object.keys(PREFLOP_CONFIGS),
  };

  const configs = groups[group];
  if (!configs || configs.length === 0) {
    console.error(`Unknown group: ${group}. Available: ${Object.keys(groups).join(', ')}`);
    process.exit(1);
  }

  console.log(`=== Batch Solve: ${group} (${configs.length} configs) ===\n`);
  console.log(`Configs: ${configs.join(', ')}`);
  console.log(`Iterations: ${iterations.toLocaleString()}\n`);

  const batchStart = Date.now();

  for (let i = 0; i < configs.length; i++) {
    const configName = configs[i];
    console.log(`\n[${i + 1}/${configs.length}] Solving: ${configName}`);
    console.log('─'.repeat(50));

    // Check if already solved
    const storePath = join(DATA_DIR, `store_${configName}.jsonl`);
    if (existsSync(storePath) && flags['force'] !== 'true') {
      console.log(`  SKIP: Already solved (${storePath}). Use --force to re-solve.`);
      continue;
    }

    try {
      await cmdSolve({ config: configName, iterations: String(iterations) });
    } catch (err) {
      console.error(`  ERROR solving ${configName}:`, err);
    }
  }

  const totalTime = ((Date.now() - batchStart) / 1000).toFixed(0);
  console.log(`\n=== Batch complete: ${configs.length} configs in ${totalTime}s ===`);
}

// ── Main ──

async function main(): Promise<void> {
  const { command, flags } = parseArgs();

  switch (command) {
    case 'equity':
      await cmdEquity(flags);
      break;
    case 'solve':
      await cmdSolve(flags);
      break;
    case 'export':
      await cmdExport(flags);
      break;
    case 'verify':
      await cmdVerify(flags);
      break;
    case 'tree':
      await cmdTree(flags);
      break;
    case 'batch':
      await cmdBatch(flags);
      break;
    default:
      console.log('Preflop GTO Solver — CardPilot\n');
      console.log('Commands:');
      console.log('  equity                          Precompute equity table');
      console.log('  solve  --config NAME --iter N   Run CFR+ solver');
      console.log('  export --config NAME            Export solutions');
      console.log('  export --all-configs            Export all configs');
      console.log('  verify --config NAME            Compare vs GTO Wizard');
      console.log('  tree   --config NAME            Print tree stats');
      console.log('  batch  --group GROUP --iter N    Solve multiple configs');
      console.log('');
      console.log('Batch groups: hu, threeway, fourway, 3bet, 6max, all');
      console.log('');
      console.log('Configs:');
      const configKeys = Object.keys(PREFLOP_CONFIGS);
      const maxLen = Math.max(...configKeys.map((k) => k.length));
      for (const key of configKeys) {
        const cfg = PREFLOP_CONFIGS[key];
        const labels = (cfg.positionLabels ?? []).join('/');
        const maxLvl = cfg.maxRaiseLevel ?? 4;
        const scenarios = maxLvl >= 3 ? 'RFI→4bet' : maxLvl >= 2 ? 'RFI→3bet' : 'RFI→open';
        console.log(
          `  ${key.padEnd(maxLen + 2)} ${cfg.players}p ${cfg.stackSize}bb  ${labels}  (${scenarios})`,
        );
      }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
