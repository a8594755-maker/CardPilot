#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const ROOT = process.cwd();
const DATA_DIR = path.join(ROOT, 'data', 'v2');
const TRAINER = 'packages/fast-model/src/trainer.ts';
const OUT_DIR = path.join(ROOT, 'artifacts', 'v2.0-staged');
const LOG_DIR = path.join(OUT_DIR, 'logs');
const STAGE_SIZES = Array.from({ length: 10 }, (_, i) => (i + 1) * 100_000);
const MAX_RETRIES = 3;

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.mkdirSync(LOG_DIR, { recursive: true });

function ts() {
  return new Date().toISOString();
}

function fmt(n) {
  return n.toLocaleString('en-US');
}

function runCmd(args, logPath) {
  return new Promise((resolve, reject) => {
    const out = fs.createWriteStream(logPath, { flags: 'a' });
    out.write(`[${ts()}] cmd: ${args.join(' ')}\n`);

    const child = spawn('cmd.exe', ['/c', ...args], {
      cwd: ROOT,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    child.stdout.on('data', (d) => out.write(d));
    child.stderr.on('data', (d) => out.write(d));
    child.on('error', (err) => {
      out.end();
      reject(err);
    });
    child.on('close', (code) => {
      out.write(`\n[${ts()}] exit=${code}\n`);
      out.end();
      if (code === 0) resolve();
      else reject(new Error(`Command failed with exit code ${code}`));
    });
  });
}

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function isImproved(curr, prev) {
  if (!prev) return true;
  if (curr.valLoss < prev.valLoss) return true;
  if (
    curr.metrics.klDivergence < prev.metrics.klDivergence &&
    curr.metrics.top1Accuracy >= prev.metrics.top1Accuracy
  ) {
    return true;
  }
  return false;
}

async function trainStage(sampleCap, warmStartPath, attempt) {
  const stageTag = `${Math.floor(sampleCap / 1000)}k`;
  const modelPath = path.join(OUT_DIR, `model-v2.0-stage-${stageTag}-attempt${attempt}.json`);
  const metricsPath = modelPath.replace('.json', '-metrics.json');
  const logPath = path.join(LOG_DIR, `train-${stageTag}-attempt${attempt}.log`);

  const args = [
    'npx',
    'tsx',
    TRAINER,
    '--v2',
    '--data',
    'data/v2',
    '--max-samples',
    String(sampleCap),
    '--out',
    path.relative(ROOT, modelPath),
  ];

  if (warmStartPath && fs.existsSync(warmStartPath)) {
    args.push('--warm-start', path.relative(ROOT, warmStartPath));
  }

  await runCmd(args, logPath);

  const model = loadJson(modelPath);
  const metrics = loadJson(metricsPath);
  return {
    sampleCap,
    attempt,
    modelPath,
    metricsPath,
    logPath,
    valLoss: model.valLoss,
    trainingSamples: model.trainingSamples,
    metrics,
  };
}

async function main() {
  if (!fs.existsSync(DATA_DIR)) {
    throw new Error(`Missing data dir: ${DATA_DIR}`);
  }

  const summary = {
    startedAt: ts(),
    stageSizes: STAGE_SIZES,
    maxRetries: MAX_RETRIES,
    accepted: [],
    attempts: [],
  };

  let prev = null;
  let warmStartPath = path.join(ROOT, 'packages', 'fast-model', 'models', 'model-v2-latest.json');
  if (!fs.existsSync(warmStartPath)) warmStartPath = null;

  for (const sampleCap of STAGE_SIZES) {
    let accepted = null;
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      const result = await trainStage(sampleCap, warmStartPath, attempt);
      const improved = isImproved(result, prev);
      summary.attempts.push({
        sampleCap,
        attempt,
        improved,
        valLoss: result.valLoss,
        klDivergence: result.metrics.klDivergence,
        top1Accuracy: result.metrics.top1Accuracy,
        sizingTop1Accuracy: result.metrics.sizingTop1Accuracy ?? null,
        modelPath: result.modelPath,
        metricsPath: result.metricsPath,
        logPath: result.logPath,
      });

      if (improved) {
        accepted = result;
        break;
      }
    }

    if (!accepted) {
      summary.finishedAt = ts();
      summary.status = 'failed';
      summary.failedStage = sampleCap;
      const summaryPath = path.join(OUT_DIR, 'summary.json');
      fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));
      throw new Error(`Stage ${fmt(sampleCap)} failed to improve after ${MAX_RETRIES} attempts.`);
    }

    prev = accepted;
    warmStartPath = accepted.modelPath;
    summary.accepted.push({
      sampleCap,
      valLoss: accepted.valLoss,
      klDivergence: accepted.metrics.klDivergence,
      top1Accuracy: accepted.metrics.top1Accuracy,
      sizingTop1Accuracy: accepted.metrics.sizingTop1Accuracy ?? null,
      modelPath: accepted.modelPath,
      metricsPath: accepted.metricsPath,
      logPath: accepted.logPath,
    });

    console.log(
      `[stage ${fmt(sampleCap)}] accepted: val_loss=${accepted.valLoss.toFixed(4)} ` +
        `KL=${accepted.metrics.klDivergence.toFixed(4)} ` +
        `Top1=${(accepted.metrics.top1Accuracy * 100).toFixed(2)}%`,
    );
  }

  const finalAccepted = summary.accepted[summary.accepted.length - 1];
  const finalModel = path.join(
    ROOT,
    'packages',
    'fast-model',
    'models',
    'model-v2.0-first-million.json',
  );
  const finalMetrics = finalModel.replace('.json', '-metrics.json');
  fs.copyFileSync(finalAccepted.modelPath, finalModel);
  fs.copyFileSync(finalAccepted.metricsPath, finalMetrics);

  summary.finishedAt = ts();
  summary.status = 'completed';
  summary.finalModel = finalModel;
  summary.finalMetrics = finalMetrics;
  const summaryPath = path.join(OUT_DIR, 'summary.json');
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));

  console.log(`Completed 10/10 stages. Final model: ${finalModel}`);
  console.log(`Summary: ${summaryPath}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
