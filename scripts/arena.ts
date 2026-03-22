#!/usr/bin/env tsx
/**
 * arena.ts — Bot vs Bot (HU), with optional parallel tables via child_process
 * Usage: npx tsx scripts/arena.ts [--hands N] [--tables T] [--a v4] [--b v3] [--resolver a|b]
 *
 * Single table:  npx tsx scripts/arena.ts --hands 5000
 * 100 tables:    npx tsx scripts/arena.ts --tables 100 --hands 1000
 */
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BB = 50;

function printResults(allResults: number[], nameA: string, nameB: string, numTables: number): void {
  const N = allResults.length;
  const bbResults = allResults.map((n) => n / BB);
  const mean = bbResults.reduce((a, b) => a + b, 0) / N;
  const variance = bbResults.reduce((a, b) => a + (b - mean) ** 2, 0) / N;
  const stddev = Math.sqrt(variance);
  const ci95 = 1.96 * (stddev / Math.sqrt(N)) * 100;
  const bb100A = mean * 100;
  const sign = (v: number) => (v >= 0 ? `+${v.toFixed(1)}` : v.toFixed(1));

  console.log('\n' + '═'.repeat(58));
  console.log(
    `  Arena Results: ${nameA} vs ${nameB}  (${N.toLocaleString()} hands, ${numTables} tables)`,
  );
  console.log('═'.repeat(58));
  console.log(`  ${nameA.padEnd(6)}  ${sign(bb100A)} BB/100`);
  console.log(`  ${nameB.padEnd(6)}  ${sign(-bb100A)} BB/100`);
  console.log(`  95% CI:      ±${ci95.toFixed(1)} BB/100`);
  console.log(`  StdDev/hand: ${stddev.toFixed(2)} BB   (N=${N.toLocaleString()})`);
  console.log('─'.repeat(58));
  if (Math.abs(bb100A) > ci95) {
    console.log(`  ✓ Statistically significant: ${bb100A > 0 ? nameA : nameB} wins`);
  } else {
    console.log(`  ∼ Not statistically significant (need more hands)`);
  }
  console.log('═'.repeat(58));
}

async function runParallel(
  numTables: number,
  handsPerTable: number,
  nameA: string,
  nameB: string,
  resolverFor: string | null,
): Promise<void> {
  const totalHands = numTables * handsPerTable;
  const sessionScript = resolve(__dirname, 'arena-session.ts');
  // Use node + inherited tsx execArgv so .ts files resolve correctly on all platforms
  const nodeArgs = [...process.execArgv, sessionScript];
  const resolverArgs = resolverFor ? ['--resolver', resolverFor] : [];

  console.log(
    `Spawning ${numTables} workers × ${handsPerTable} hands = ${totalHands.toLocaleString()} total${resolverFor ? ` (resolver: ${resolverFor})` : ''}\n`,
  );

  const allResults: number[] = [];
  let completed = 0;
  let errors = 0;

  const workers = Array.from({ length: numTables }, (_, i) => {
    return new Promise<void>((resolve, reject) => {
      const child = spawn(
        process.execPath,
        [
          ...nodeArgs,
          '--hands',
          String(handsPerTable),
          '--a',
          nameA,
          '--b',
          nameB,
          ...resolverArgs,
        ],
        { stdio: ['ignore', 'pipe', 'pipe'] },
      );

      let stdout = '';
      let stderr = '';
      child.stdout.on('data', (d: Buffer) => (stdout += d.toString()));
      child.stderr.on('data', (d: Buffer) => (stderr += d.toString()));

      child.on('close', (code) => {
        if (code === 0) {
          try {
            const results = JSON.parse(stdout.trim()) as number[];
            allResults.push(...results);
            completed++;
            process.stdout.write(
              `\r  Done: ${completed}/${numTables}  Total hands: ${allResults.length.toLocaleString()}   `,
            );
            resolve();
          } catch (err) {
            errors++;
            console.error(`\n  Worker ${i} parse error: ${(err as Error).message}`);
            resolve();
          }
        } else {
          errors++;
          console.error(
            `\n  Worker ${i} exited with code ${code}${stderr ? ': ' + stderr.slice(0, 200) : ''}`,
          );
          resolve(); // don't reject — partial results are still useful
        }
      });

      child.on('error', (err) => {
        errors++;
        console.error(`\n  Worker ${i} spawn error: ${err.message}`);
        resolve();
      });
    });
  });

  await Promise.all(workers);
  if (errors > 0) console.log(`\n  WARNING: ${errors}/${numTables} workers failed`);
  printResults(allResults, nameA, nameB, numTables);
}

function runSingle(
  numHands: number,
  handsPerTable: number,
  nameA: string,
  nameB: string,
  resolverFor: string | null,
): void {
  const sessionScript = resolve(__dirname, 'arena-session.ts');
  const nodeArgs = [...process.execArgv, sessionScript];
  const resolverArgs = resolverFor ? ['--resolver', resolverFor] : [];
  const child = spawn(
    process.execPath,
    [...nodeArgs, '--hands', String(numHands), '--a', nameA, '--b', nameB, ...resolverArgs],
    { stdio: ['ignore', 'pipe', 'inherit'] },
  );
  let stdout = '';
  child.stdout.on('data', (d: Buffer) => (stdout += d.toString()));
  child.on('close', () => {
    try {
      const results = JSON.parse(stdout.trim()) as number[];
      printResults(results, nameA, nameB, 1);
    } catch {
      console.error('Failed to parse session output');
    }
  });
}

// ── Parse args ──────────────────────────────────────────────
const args = process.argv.slice(2);
let numHands = 5000;
let numTables = 1;
let nameA = 'v4';
let nameB = 'v3';
let resolverFor: string | null = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--hands' && args[i + 1]) numHands = parseInt(args[++i], 10);
  if (args[i] === '--tables' && args[i + 1]) numTables = parseInt(args[++i], 10);
  if (args[i] === '--a' && args[i + 1]) nameA = args[++i];
  if (args[i] === '--b' && args[i + 1]) nameB = args[++i];
  if (args[i] === '--resolver' && args[i + 1]) resolverFor = args[++i];
}

const handsPerTable = numTables > 1 ? Math.ceil(numHands / numTables) : numHands;
const resolverLabel = resolverFor ? `  resolver: ${resolverFor}` : '';
console.log(
  `Arena: ${nameA} vs ${nameB}  |  ${numTables} table(s) × ${handsPerTable} hands${resolverLabel}`,
);

if (numTables === 1) {
  runSingle(numHands, handsPerTable, nameA, nameB, resolverFor);
} else {
  runParallel(numTables, handsPerTable, nameA, nameB, resolverFor).catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
