#!/usr/bin/env tsx
/** CPU-only, resumable Path-1 CFR solver with frozen weighted/texture board selection and per-board QA. */
import { fork, spawn, type ChildProcess } from 'node:child_process';
import { cpus, totalmem } from 'node:os';
import { resolve, dirname, isAbsolute } from 'node:path';
import {
  existsSync,
  mkdirSync,
  appendFileSync,
  createReadStream,
  createWriteStream,
  statSync,
  unlinkSync,
  openSync,
  closeSync,
  readFileSync,
  writeFileSync,
  renameSync,
} from 'node:fs';
import { createGzip } from 'node:zlib';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';
import { enumerateIsomorphicFlops, canonicalFlop } from '../abstraction/suit-isomorphism.js';
import { indexToCard, indexToRank, indexToSuit } from '../abstraction/card-index.js';
import { getConfigOutputDir, getStackLabel } from '../tree/tree-config.js';
import type { FlopTask, WorkerResult, WorkerProgress } from '../orchestration/solve-worker.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WORKER = resolve(__dirname, '../orchestration/solve-worker.ts');
const argv = process.argv.slice(2);
const arg = (n: string, d: string) => {
  const i = argv.indexOf(n);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};
const num = (n: string, d: number) => {
  const v = Number(arg(n, String(d)));
  if (!Number.isFinite(v) || v < 0) throw new Error(`bad ${n}`);
  return Math.trunc(v);
};
const CONFIG = arg('--config', 'pipeline_srp_v3');
const ITERATIONS = num('--iterations', 200000);
const BUCKETS = 50;
const TARGET = num('--target-boards', 1911);
const SELECTION_SEED = num('--selection-seed', 20260712);
const SAMPLES = num('--samples-per-bucket', 1);
const PROJECT = resolve(__dirname, '../../../../');
const defaultOut = resolve(PROJECT, 'data/cfr', getConfigOutputDir(CONFIG as never));
const OUT = arg('--out', defaultOut);
const QA = arg('--qa-script', resolve(PROJECT, 'scripts/qa-200bb-board.mjs'));
const LOG = resolve(OUT, 'parallel-solver.log');
const LOCK = resolve(OUT, 'path1-solver.lock.json');
const MANIFEST = resolve(OUT, 'path1-selection-manifest.json');
const STATUS = resolve(OUT, 'path1-solver-status.json');
if (!isAbsolute(OUT) || !isAbsolute(QA)) throw new Error('--out and --qa-script must be absolute');
if (CONFIG !== 'pipeline_srp_v3_200bb')
  throw new Error('Path-1 runner requires pipeline_srp_v3_200bb');
if (SAMPLES !== 1)
  throw new Error('--samples-per-bucket must be exactly 1 (downstream distillation contract)');

function log(x: string) {
  const l = `[${new Date().toISOString()}] ${x}\n`;
  appendFileSync(LOG, l);
  process.stdout.write(l);
}
function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
function atomicJson(path: string, o: unknown) {
  const t = `${path}.${process.pid}.tmp`;
  writeFileSync(t, JSON.stringify(o, null, 2));
  renameSync(t, path);
}
function acquire() {
  mkdirSync(OUT, { recursive: true });
  if (existsSync(LOCK)) {
    let alive = false;
    try {
      const p = JSON.parse(readFileSync(LOCK, 'utf8')).pid;
      process.kill(p, 0);
      alive = true;
    } catch {}
    if (alive) throw new Error(`live lock: ${LOCK}`);
    renameSync(LOCK, `${LOCK}.stale.${Date.now()}`);
  }
  const fd = openSync(LOCK, 'wx');
  writeFileSync(
    fd,
    JSON.stringify(
      { pid: process.pid, startedAt: new Date().toISOString(), config: CONFIG, out: OUT },
      null,
      2,
    ),
  );
  closeSync(fd);
  return () => {
    try {
      const x = JSON.parse(readFileSync(LOCK, 'utf8'));
      if (x.pid === process.pid) unlinkSync(LOCK);
    } catch {}
  };
}
function complete(id: number) {
  const b = resolve(OUT, `flop_${String(id).padStart(3, '0')}`);
  return existsSync(`${b}.meta.json`) && existsSync(`${b}.jsonl.gz`);
}
function texture(cards: [number, number, number]) {
  const rs = cards.map(indexToRank);
  const ss = cards.map(indexToSuit);
  const rc = new Set(rs).size;
  const sc = new Set(ss).size;
  const rp = rc === 1 ? 'trips' : rc === 2 ? 'paired' : 'unpaired';
  const sp = sc === 1 ? 'monotone' : sc === 2 ? 'twotone' : 'rainbow';
  const u = [...new Set(rs)].sort((a, b) => a - b);
  const gap = u[u.length - 1] - u[0];
  return `${rp}_${sp}_${gap <= 2 ? 'connected' : gap <= 5 ? 'medium' : 'disconnected'}`;
}
function hashRand(seed: number, id: number) {
  let x = (seed ^ Math.imul(id + 1, 0x9e3779b1)) >>> 0;
  x ^= x << 13;
  x ^= x >>> 17;
  x ^= x << 5;
  return ((x >>> 0) + 1) / 4294967297;
}
function selectedBoards() {
  const flops = enumerateIsomorphicFlops();
  if (TARGET > flops.length) throw new Error('target exceeds board count');
  if (existsSync(MANIFEST)) {
    const m = JSON.parse(readFileSync(MANIFEST, 'utf8'));
    if (
      m.config !== CONFIG ||
      m.targetBoards !== TARGET ||
      m.selectionSeed !== SELECTION_SEED ||
      m.method !== 'isomorphism_multiplicity_weighted_texture_stratified_v1'
    )
      throw new Error('selection manifest contract mismatch');
    return { flops, ids: m.selectedBoardIds as number[], manifest: m };
  }
  const weights = new Map<string, number>();
  for (let a = 0; a < 52; a++)
    for (let b = a + 1; b < 52; b++)
      for (let c = b + 1; c < 52; c++) {
        const k = canonicalFlop([a, b, c]);
        weights.set(k, (weights.get(k) || 0) + 1);
      }
  const rows = flops.map((f, id) => ({
    id,
    cards: f.cards,
    texture: texture(f.cards),
    weight: weights.get(f.canonical) || 0,
    score: -Math.log(hashRand(SELECTION_SEED, id)) / (weights.get(f.canonical) || 1),
  }));
  const existing = rows.filter((r) => complete(r.id));
  const chosen = new Set(existing.map((r) => r.id));
  const totalW = rows.reduce((s, r) => s + r.weight, 0);
  const byTex = new Map<string, typeof rows>();
  for (const r of rows) {
    const a = byTex.get(r.texture) || [];
    a.push(r);
    byTex.set(r.texture, a);
  }
  const desired = new Map<string, number>();
  let sum = 0;
  for (const [t, a] of byTex) {
    const q = Math.floor((TARGET * a.reduce((s, r) => s + r.weight, 0)) / totalW);
    desired.set(t, q);
    sum += q;
  }
  for (const [t] of [...byTex].sort(
    (a, b) => b[1].reduce((s, r) => s + r.weight, 0) - a[1].reduce((s, r) => s + r.weight, 0),
  )) {
    if (sum++ >= TARGET) break;
    desired.set(t, (desired.get(t) || 0) + 1);
  }
  for (const [t, a] of byTex) {
    let need = Math.max(0, (desired.get(t) || 0) - a.filter((r) => chosen.has(r.id)).length);
    for (const r of a
      .filter((r) => !chosen.has(r.id))
      .sort((x, y) => x.score - y.score || x.id - y.id)) {
      if (need-- <= 0) break;
      chosen.add(r.id);
    }
  }
  for (const r of rows
    .filter((r) => !chosen.has(r.id))
    .sort((x, y) => x.score - y.score || x.id - y.id)) {
    if (chosen.size >= TARGET) break;
    chosen.add(r.id);
  }
  const ids = [...chosen].sort((a, b) => a - b).slice(0, TARGET);
  const counts = Object.fromEntries(
    [...byTex].map(([t]) => [t, ids.filter((id) => rows[id].texture === t).length]),
  );
  const m = {
    schema: 'path1_selection_v1',
    createdAt: new Date().toISOString(),
    config: CONFIG,
    targetBoards: TARGET,
    selectionSeed: SELECTION_SEED,
    method: 'isomorphism_multiplicity_weighted_texture_stratified_v1',
    rawFlops: 22100,
    isomorphismClasses: flops.length,
    existingBoardsPreserved: existing.length,
    samplesPerBucket: SAMPLES,
    samplesPerBucketSemantics:
      'downstream CFR-to-training-data presampling; solve export remains full compressed strategy',
    textureCounts: counts,
    selectedBoardIds: ids,
  };
  atomicJson(MANIFEST, m);
  return { flops, ids, manifest: m };
}
async function gzip(id: number) {
  const raw = resolve(OUT, `flop_${String(id).padStart(3, '0')}.jsonl`),
    gz = `${raw}.gz`,
    part = `${gz}.partial`;
  if (!existsSync(raw)) throw new Error('missing raw export');
  if (existsSync(gz) || existsSync(part)) throw new Error('refusing to overwrite gzip/partial');
  await pipeline(
    createReadStream(raw),
    createGzip({ level: 6 }),
    createWriteStream(part, { flags: 'wx' }),
  );
  renameSync(part, gz);
  unlinkSync(raw);
  return statSync(gz).size;
}
function qa(path: string) {
  return new Promise<boolean>((r) => {
    const p = spawn(process.execPath, [QA, path], {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let o = '';
    p.stdout.on('data', (d) => (o += d));
    p.stderr.on('data', (d) => (o += d));
    p.on('exit', (c) => {
      appendFileSync(resolve(OUT, 'path1-qa.log'), `[${new Date().toISOString()}] ${path}\n${o}\n`);
      r(c === 0);
    });
  });
}
function solve(id: number, cards: [number, number, number], heap: number) {
  return new Promise<WorkerResult>((res, rej) => {
    const p: ChildProcess = fork(WORKER, [], {
      execArgv: ['--import', 'tsx', `--max-old-space-size=${heap}`],
      stdio: ['ignore', 'inherit', 'inherit', 'ipc'],
      env: { ...process.env, CUDA_VISIBLE_DEVICES: '' },
    });
    let settled = false;
    const task: FlopTask = {
      type: 'solve',
      boardId: id,
      flopCards: cards,
      label: cards.map(indexToCard).join(' '),
      iterations: ITERATIONS,
      bucketCount: BUCKETS,
      outputDir: OUT,
      chartsPath: resolve(PROJECT, 'data/preflop_charts.json'),
      configName: CONFIG as never,
      stackLabel: getStackLabel(CONFIG as never),
    };
    p.on('spawn', () => p.send?.(task));
    p.on('message', (m: WorkerResult | WorkerProgress) => {
      if (m.type === 'progress' && m.iteration > 0 && m.iteration % 20000 === 0)
        log(`[board ${id}] iter ${m.iteration}/${m.total}`);
      if (m.type === 'result' && !settled) {
        settled = true;
        p.disconnect();
        res(m);
      }
    });
    p.on('error', (e) => {
      if (!settled) {
        settled = true;
        rej(e);
      }
    });
    p.on('exit', (c, s) => {
      if (!settled) {
        settled = true;
        rej(new Error(`worker exited before result code=${c} signal=${s}`));
      }
    });
  });
}
async function main() {
  const release = acquire();
  let completed = 0,
    failed = 0,
    stop = false;
  try {
    const { flops, ids, manifest } = selectedBoards();
    const incomplete = ids.filter((id) => {
      const b = resolve(OUT, `flop_${String(id).padStart(3, '0')}`);
      return (
        !complete(id) &&
        (existsSync(`${b}.meta.json`) ||
          existsSync(`${b}.jsonl`) ||
          existsSync(`${b}.jsonl.gz`) ||
          existsSync(`${b}.jsonl.gz.partial`))
      );
    });
    if (incomplete.length)
      throw new Error(`incomplete artifacts fail closed: ${incomplete.join(',')}`);
    const queue = ids.filter((id) => !complete(id)).map((id) => ({ id, attempt: 0 }));
    const max = num('--max-boards', 0);
    if (max > 0) queue.length = Math.min(queue.length, max);
    const req = num('--workers', 7),
      heap = num('--heap-mb', 18432),
      workers = Math.max(
        1,
        Math.min(req, Math.floor((totalmem() / 1048576 - 12288) / heap), cpus().length - 2),
      );
    log(
      `START config=${CONFIG} target=${TARGET} selected_missing=${queue.length} iterations=${ITERATIONS} workers=${workers} heapMB=${heap} samples_per_bucket=${SAMPLES} selection_seed=${SELECTION_SEED} cpu_only=true`,
    );
    atomicJson(STATUS, {
      status: 'RUNNING',
      pid: process.pid,
      startedAt: new Date().toISOString(),
      config: CONFIG,
      out: OUT,
      iterations: ITERATIONS,
      targetBoards: TARGET,
      selectedMissing: queue.length,
      workers,
      heapMB: heap,
      selectionSeed: SELECTION_SEED,
      samplesPerBucket: SAMPLES,
      selectionManifest: MANIFEST,
      manifest,
    });
    if (argv.includes('--dry-run')) {
      atomicJson(STATUS, {
        status: 'PREFLIGHT_PASS_NO_LAUNCH',
        pid: process.pid,
        checkedAt: new Date().toISOString(),
        selectedMissing: queue.length,
        targetBoards: TARGET,
        workers,
        heapMB: heap,
        iterations: ITERATIONS,
        selectionSeed: SELECTION_SEED,
        samplesPerBucket: SAMPLES,
      });
      log('PREFLIGHT_PASS_NO_LAUNCH');
      return;
    }
    let qi = 0;
    async function run(w: number) {
      while (!stop && qi < queue.length) {
        const item = queue[qi++],
          f = flops[item.id];
        log(
          `W${w} starting board=${item.id} cards=${f.cards.map(indexToCard).join(' ')} attempt=${item.attempt + 1}`,
        );
        try {
          const result = await solve(item.id, f.cards, heap);
          const bytes = await gzip(item.id);
          const gz = resolve(OUT, `flop_${String(item.id).padStart(3, '0')}.jsonl.gz`);
          if (await qa(gz)) {
            completed++;
            log(`W${w} board=${item.id} QA_PASS infosets=${result.infoSets} gz_bytes=${bytes}`);
          } else {
            failed++;
            const rainbow = texture(f.cards).includes('_rainbow_');
            const tag = `qa_fail_attempt${item.attempt + 1}_${Date.now()}`;
            renameSync(gz, `${gz}.${tag}`);
            const meta = gz.replace('.jsonl.gz', '.meta.json');
            if (existsSync(meta)) renameSync(meta, `${meta}.${tag}`);
            log(`W${w} board=${item.id} QA_FAIL rainbow=${rainbow} preserved_tag=${tag}`);
            if (rainbow && item.attempt < 1) {
              queue.push({ id: item.id, attempt: item.attempt + 1 });
              await sleep(5000);
            }
          }
        } catch (e) {
          if (item.attempt < 2) {
            log(`W${w} board=${item.id} WORKER_FAIL retry=${item.attempt + 2} error=${e}`);
            queue.splice(qi, 0, { id: item.id, attempt: item.attempt + 1 });
            await sleep(5000 * (item.attempt + 1));
          } else {
            failed++;
            stop = true;
            log(`FATAL board=${item.id} exhausted retries; dispatch stopped: ${e}`);
          }
        }
      }
    }
    await Promise.all(Array.from({ length: workers }, (_, w) => run(w)));
    const status = stop
      ? 'FAIL_CLOSED_WORKER_ABORT'
      : failed
        ? 'COMPLETED_WITH_QA_FAILURES'
        : 'COMPLETED';
    atomicJson(STATUS, {
      status,
      pid: process.pid,
      finishedAt: new Date().toISOString(),
      completed,
      failed,
      selectedComplete: ids.filter(complete).length,
      targetBoards: TARGET,
    });
    log(
      `END status=${status} completed=${completed} failed=${failed} selected_complete=${ids.filter(complete).length}/${TARGET}`,
    );
    if (stop) process.exitCode = 2;
  } finally {
    release();
  }
}
main().catch((e) => {
  try {
    log(`FATAL ${e?.stack || e}`);
    atomicJson(STATUS, {
      status: 'FAIL_CLOSED_PREFLIGHT',
      pid: process.pid,
      error: String(e),
      at: new Date().toISOString(),
    });
  } finally {
    process.exitCode = 1;
  }
});
