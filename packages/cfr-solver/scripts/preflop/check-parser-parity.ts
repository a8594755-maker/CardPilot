#!/usr/bin/env tsx
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const FIXED_GENERATED_AT = '2026-01-01T00:00:00.000Z';

function getArg(name: string, fallback: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx >= 0 && process.argv[idx + 1]) return process.argv[idx + 1];
  return fallback;
}

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    const out: Record<string, unknown> = {};
    for (const key of keys) {
      out[key] = stable(obj[key]);
    }
    return out;
  }
  return value;
}

function hashJson(path: string): string {
  const parsed = JSON.parse(readFileSync(path, 'utf-8')) as unknown;
  const normalized = JSON.stringify(stable(parsed));
  return createHash('sha256').update(normalized).digest('hex');
}

function runCommand(cmd: string, args: string[], cwd: string): void {
  const result = spawnSync(cmd, args, {
    cwd,
    stdio: 'pipe',
    encoding: 'utf-8',
  });
  if (result.status !== 0) {
    throw new Error(
      [
        `Command failed: ${cmd} ${args.join(' ')}`,
        result.stdout?.trim() ?? '',
        result.stderr?.trim() ?? '',
      ]
        .filter(Boolean)
        .join('\n'),
    );
  }
}

function detectPython(): string {
  if (process.env.PYTHON) return process.env.PYTHON;
  for (const candidate of ['python', 'py']) {
    const test = spawnSync(candidate, ['--version'], { stdio: 'ignore' });
    if (test.status === 0) return candidate;
  }
  throw new Error('python interpreter not found (set PYTHON env var)');
}

function main(): void {
  const repoRoot = resolve(process.cwd());
  const chartPath = resolve(
    getArg('chart', join(repoRoot, 'GTO + sample', 'Preflop Strategy Chart.md')),
  );

  if (!existsSync(chartPath)) {
    throw new Error(`chart not found: ${chartPath}`);
  }

  const tempDir = mkdtempSync(join(tmpdir(), 'preflop-parity-'));
  const tsOut = join(tempDir, 'ts.preflop_library.v1.json');
  const tsLegacyOut = join(tempDir, 'ts.preflop_charts.json');
  const pyOut = join(tempDir, 'py.preflop_library.v1.json');
  const pyLegacyOut = join(tempDir, 'py.preflop_charts.json');

  try {
    runCommand(
      process.execPath,
      [
        '--import',
        'tsx',
        'packages/cfr-solver/scripts/preflop/parse-chart.ts',
        '--chart',
        chartPath,
        '--out',
        tsOut,
        '--legacy-out',
        tsLegacyOut,
        '--generated-at',
        FIXED_GENERATED_AT,
        '--quiet',
      ],
      repoRoot,
    );

    const python = detectPython();
    const pyArgs =
      python === 'py'
        ? [
            '-3',
            'tools/preflop/parse_chart.py',
            '--chart',
            chartPath,
            '--out',
            pyOut,
            '--legacy-out',
            pyLegacyOut,
            '--generated-at',
            FIXED_GENERATED_AT,
            '--quiet',
          ]
        : [
            'tools/preflop/parse_chart.py',
            '--chart',
            chartPath,
            '--out',
            pyOut,
            '--legacy-out',
            pyLegacyOut,
            '--generated-at',
            FIXED_GENERATED_AT,
            '--quiet',
          ];

    runCommand(python, pyArgs, repoRoot);

    const tsCanonicalHash = hashJson(tsOut);
    const pyCanonicalHash = hashJson(pyOut);
    const tsLegacyHash = hashJson(tsLegacyOut);
    const pyLegacyHash = hashJson(pyLegacyOut);

    console.log(`TS canonical hash: ${tsCanonicalHash}`);
    console.log(`PY canonical hash: ${pyCanonicalHash}`);
    console.log(`TS legacy hash:    ${tsLegacyHash}`);
    console.log(`PY legacy hash:    ${pyLegacyHash}`);

    if (tsCanonicalHash !== pyCanonicalHash || tsLegacyHash !== pyLegacyHash) {
      throw new Error('parser parity check failed: hashes differ');
    }

    console.log('Parser parity check passed.');
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}

main();
