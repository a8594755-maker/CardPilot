#!/usr/bin/env tsx
// Pipeline CLI — start coordinator (queue server + job generator) or worker.
//
// Coordinator mode (run on Machine B):
//   npx tsx pipeline.ts coordinator [--port 3500] [--config pipeline_srp] [--iterations 200000] [--buckets 100]
//
// Worker mode (run on each machine):
//   npx tsx pipeline.ts worker --server http://192.168.1.100:3500 [--workers 4] [--id machineA]
//
// Status check (from anywhere):
//   npx tsx pipeline.ts status --server http://192.168.1.100:3500

import { resolve } from 'node:path';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { request } from 'node:http';
import type { TreeConfigName } from '../tree/tree-config.js';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

function findProjectRoot(): string {
  const fromFile = resolve(__dirname, '../../../../');
  if (existsSync(resolve(fromFile, 'data/preflop_charts.json'))) return fromFile;
  if (existsSync(resolve(process.cwd(), 'data/preflop_charts.json'))) return process.cwd();
  const parent = resolve(process.cwd(), '../..');
  if (existsSync(resolve(parent, 'data/preflop_charts.json'))) return parent;
  return process.cwd();
}

const PROJECT_ROOT = findProjectRoot();

// Parse args
const args = process.argv.slice(2);
const command = args[0];

function getArg(name: string, defaultVal: string): string {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return args[idx + 1];
  return defaultVal;
}
function getNumArg(name: string, defaultVal: number): number {
  const idx = args.indexOf(`--${name}`);
  if (idx !== -1 && args[idx + 1]) return parseInt(args[idx + 1], 10);
  return defaultVal;
}

function printUsage(): void {
  console.log(`
Usage: npx tsx pipeline.ts <command> [options]

Commands:
  coordinator   Start the queue server and generate jobs (run on Machine B)
  worker        Start a network worker (run on each machine)
  status        Check queue status

Coordinator options:
  --port N            Server port (default: 3500)
  --config NAME       Config name, comma-separated list, or "all" (default: all)
                      Examples: pipeline_srp, hu_btn_bb_srp_100bb,hu_btn_bb_3bp_100bb, all
  --iterations N      Override iterations (default: from config)
  --buckets N         Override bucket count (default: from config)
  --resume            Skip already-solved flops (checks for .meta.json files)

Worker options:
  --server URL        Queue server URL (required, e.g. http://192.168.1.100:3500)
  --workers N         Number of local solver workers (default: auto-detect)
  --id NAME           Worker identifier (default: hostname)
  --heap N            Per-worker heap size in MB (default: auto-detect)

Status options:
  --server URL        Queue server URL (required)
`);
}

// ---------- Coordinator ----------

async function runCoordinator(): Promise<void> {
  const port = getNumArg('port', 3500);
  const configArg = getArg('config', 'all');
  const iterations = getNumArg('iterations', 0) || undefined;
  const buckets = getNumArg('buckets', 0) || undefined;
  const chartsPath = resolve(PROJECT_ROOT, 'data/preflop_charts.json');
  const resume = args.includes('--resume');

  // Resolve config names
  const { getConfigOutputDir, getConfigLabel, getHUPipelineConfigNames } = await import('../tree/tree-config.js');
  let configNames: TreeConfigName[];
  if (configArg === 'all') {
    configNames = getHUPipelineConfigNames();
  } else {
    configNames = configArg.split(',').map(s => s.trim()) as TreeConfigName[];
  }

  console.log('╔═══════════════════════════════════════════════╗');
  console.log('║   CFR Pipeline — Coordinator                  ║');
  console.log('╚═══════════════════════════════════════════════╝');
  console.log();
  console.log(`Project root: ${PROJECT_ROOT}`);
  console.log(`Configs:      ${configNames.length} configs`);
  for (const cn of configNames) {
    console.log(`              - ${cn}`);
  }
  console.log(`Port:         ${port}`);
  console.log(`Resume:       ${resume}`);
  console.log();

  // Start queue server
  const { startQueueServer, addJobs, addCompletedLogPath } = await import('../pipeline/queue-server.js');
  startQueueServer(port);
  console.log(`[Coordinator] Job dedup: each job assigned to exactly one worker at a time.`);
  console.log(`[Coordinator] If coordinator restarts, running jobs re-queue after 5min stale timeout.`);
  console.log(`[Coordinator] Completed jobs persist in completed.jsonl — safe across restarts.`);

  // Configure per-config completion logs
  for (const cn of configNames) {
    const outputDir = resolve(PROJECT_ROOT, 'data/cfr', getConfigOutputDir(cn));
    mkdirSync(outputDir, { recursive: true });
    const logPath = resolve(outputDir, 'completed.jsonl');
    addCompletedLogPath(cn, logPath);
    console.log(`[${cn}] Completion log: ${logPath}`);
  }
  console.log();

  // Generate jobs for all configs (in priority order)
  const { generateJobs } = await import('../pipeline/job-generator.js');
  let totalAdded = 0;
  let totalSkipped = 0;

  for (const cn of configNames) {
    const jobs = generateJobs({
      configName: cn,
      projectRoot: PROJECT_ROOT,
      chartsPath,
      iterations,
      buckets,
      resume,
    });
    const added = addJobs(jobs);
    const skipped = jobs.length - added;
    totalAdded += added;
    totalSkipped += skipped;
    console.log(`[Coordinator] ${cn}: ${added} jobs queued (${skipped} skipped)`);
  }

  console.log();
  console.log(`[Coordinator] TOTAL: ${totalAdded} jobs queued across ${configNames.length} configs (${totalSkipped} skipped)`);
  console.log();
  console.log('Waiting for workers to connect...');
  console.log('Workers should run:');
  console.log(`  npx tsx pipeline.ts worker --server http://<this-ip>:${port}`);
  console.log();

  // Load cluster.env variables (for Notion integration)
  const clusterEnvPath = resolve(PROJECT_ROOT, 'packages/cfr-solver/scripts/cluster.env');
  if (existsSync(clusterEnvPath)) {
    const envContent = readFileSync(clusterEnvPath, 'utf-8');
    for (const line of envContent.split('\n')) {
      const match = line.match(/^([A-Z_]+)="(.+)"/);
      if (match && match[2] && !process.env[match[1]]) {
        process.env[match[1]] = match[2];
      }
    }
  }

  // Start Notion reporter (if configured)
  const { getStatus } = await import('../pipeline/queue-server.js');
  const { tryStartNotionReporter } = await import('../pipeline/notion-reporter.js');
  const notionReporter = tryStartNotionReporter(getStatus);

  // Status printer every 30s
  let completionReported = false;
  setInterval(async () => {
    const s = getStatus();
    const pct = s.total > 0 ? Math.round(s.completed / s.total * 100) : 0;

    // Per-config progress summary
    const configSummary = s.configs
      ? Object.entries(s.configs)
          .map(([cn, cs]: [string, any]) => {
            const t = cs.pending + cs.running + cs.completed + cs.failed;
            return `${cn.replace('hu_', '').replace('pipeline_', 'p_')}: ${cs.completed}/${t}`;
          })
          .join(' | ')
      : '';

    const tp = s.throughput ? ` | 1h: ${s.throughput.last1h} jobs` : '';
    console.log(
      `[Status] ${s.completed}/${s.total} (${pct}%) | ` +
      `pending: ${s.pending} | running: ${s.running} | failed: ${s.failed} | ` +
      `ETA: ${s.etaHuman} | workers: ${s.activeWorkers}${tp}`
    );
    if (configSummary) {
      console.log(`  [Configs] ${configSummary}`);
    }

    // Send final Notion report when all jobs complete
    if (s.pending === 0 && s.running === 0 && s.completed > 0 && !completionReported) {
      completionReported = true;
      if (notionReporter) {
        await notionReporter.report();
        notionReporter.stop();
      }
      console.log('[Coordinator] All jobs completed!');
    }
  }, 30000);
}

// ---------- Status ----------

async function checkStatus(): Promise<void> {
  const serverUrl = getArg('server', 'http://localhost:3500');

  const res = await new Promise<{ status: number; body: string }>((resolve, reject) => {
    const parsed = new URL(`${serverUrl}/status`);
    const req = request({
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname,
      method: 'GET',
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    req.end();
  });

  if (res.status !== 200) {
    console.error(`Server returned ${res.status}`);
    process.exit(1);
  }

  const s = JSON.parse(res.body);
  const pct = s.total > 0 ? Math.round(s.completed / s.total * 100) : 0;

  console.log('═══ Pipeline Status ═══');
  console.log();
  console.log(`Total jobs:     ${s.total}`);
  console.log(`Completed:      ${s.completed} (${pct}%)`);
  console.log(`Pending:        ${s.pending}`);
  console.log(`Running:        ${s.running}`);
  console.log(`Failed:         ${s.failed}`);
  console.log(`Avg solve time: ${(s.avgSolveMs / 1000).toFixed(1)}s`);
  console.log(`ETA:            ${s.etaHuman}`);
  console.log(`Active workers: ${s.activeWorkers}`);
  console.log();

  if (s.workers && Object.keys(s.workers).length > 0) {
    console.log('Per-worker stats:');
    for (const [wid, ws] of Object.entries(s.workers) as any) {
      const avgS = ws.completed > 0 ? (ws.totalMs / ws.completed / 1000).toFixed(1) : '-';
      console.log(`  ${wid}: ${ws.completed} done, ${ws.running} running, avg ${avgS}s/flop`);
    }
    console.log();
  }

  if (s.recentCompleted && s.recentCompleted.length > 0) {
    console.log('Recent completions:');
    for (const c of s.recentCompleted) {
      console.log(`  board ${c.boardId} | ${(c.elapsedMs / 1000).toFixed(1)}s | ${c.infoSets} info sets | by ${c.worker}`);
    }
  }
}

// ---------- Main ----------

async function main(): Promise<void> {
  switch (command) {
    case 'coordinator':
    case 'coord':
      await runCoordinator();
      break;

    case 'worker':
      // Delegate to network-worker.ts (it has its own arg parsing)
      await import('../pipeline/network-worker.js');
      break;

    case 'status':
      await checkStatus();
      break;

    default:
      printUsage();
      process.exit(command ? 1 : 0);
  }
}

main().catch(err => {
  console.error('[FATAL]', err);
  process.exit(1);
});
