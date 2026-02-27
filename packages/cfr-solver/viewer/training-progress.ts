#!/usr/bin/env tsx
/**
 * Training Pipeline Progress Dashboard — serves a live webpage showing:
 *   - Data generation progress (SRP + 3-bet)
 *   - Training status / loss curves
 *   - Calibration results
 */

import { createServer } from 'node:http';
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PROJECT_ROOT = resolve(__dirname, '../../..');

const PORT = parseInt(process.argv[2] || '3456', 10);

interface DatasetStatus {
  name: string;
  config: string;
  cfrDir: string;
  trainingDir: string;
  totalCfrFlops: number;
  generatedFlops: number;
  totalSamples: number;
  generatedAt: string | null;
  filesOnDisk: number;
  totalSizeBytes: number;
}

interface ModelStatus {
  path: string;
  exists: boolean;
  sizeBytes: number;
  modifiedAt: string | null;
  valLoss: number | null;
  architecture: string | null;
  trainingHistory: Array<{ timestamp: string; valLoss: number; samples: number }>;
}

interface CalibrationStatus {
  path: string;
  exists: boolean;
  klDivergence: number | null;
  actionAccuracy: number | null;
  totalPredictions: number | null;
  perStreet: Record<string, { klDivergence: number; actionAccuracy: number; count: number }>;
}

function countFiles(dir: string, ext: string): number {
  if (!existsSync(dir)) return 0;
  return readdirSync(dir).filter(f => f.endsWith(ext)).length;
}

function dirSize(dir: string, ext: string): number {
  if (!existsSync(dir)) return 0;
  let total = 0;
  for (const f of readdirSync(dir)) {
    if (f.endsWith(ext)) {
      total += statSync(join(dir, f)).size;
    }
  }
  return total;
}

function getDatasetStatus(name: string, config: string, cfrDirName: string, trainingDirName: string): DatasetStatus {
  const cfrDir = join(PROJECT_ROOT, 'data/cfr', cfrDirName);
  const trainingDir = join(PROJECT_ROOT, 'data/training', trainingDirName);

  const totalCfrFlops = countFiles(cfrDir, '.meta.json');
  const generatedFlops = countFiles(trainingDir, '.jsonl');
  const filesOnDisk = generatedFlops;
  const totalSizeBytes = dirSize(trainingDir, '.jsonl');

  let totalSamples = 0;
  let generatedAt: string | null = null;
  const manifestPath = join(trainingDir, 'manifest.json');
  if (existsSync(manifestPath)) {
    try {
      const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
      totalSamples = manifest.totalSamples || 0;
      generatedAt = manifest.generatedAt || null;
    } catch {}
  }

  // If manifest not yet written, estimate from files
  if (totalSamples === 0 && generatedFlops > 0) {
    // Count lines in first few files for estimate
    const files = readdirSync(trainingDir).filter(f => f.endsWith('.jsonl')).slice(0, 5);
    let sampleLines = 0;
    let sampledFiles = 0;
    for (const f of files) {
      const content = readFileSync(join(trainingDir, f), 'utf-8');
      sampleLines += content.split('\n').filter(l => l.trim()).length;
      sampledFiles++;
    }
    if (sampledFiles > 0) {
      const avgPerFlop = sampleLines / sampledFiles;
      totalSamples = Math.round(avgPerFlop * generatedFlops);
    }
  }

  return { name, config, cfrDir, trainingDir, totalCfrFlops, generatedFlops, totalSamples, generatedAt, filesOnDisk, totalSizeBytes };
}

function getModelStatus(modelPath: string): ModelStatus {
  const fullPath = join(PROJECT_ROOT, modelPath);
  if (!existsSync(fullPath)) {
    return { path: modelPath, exists: false, sizeBytes: 0, modifiedAt: null, valLoss: null, architecture: null, trainingHistory: [] };
  }
  const stat = statSync(fullPath);
  let valLoss: number | null = null;
  let architecture: string | null = null;
  let trainingHistory: Array<{ timestamp: string; valLoss: number; samples: number }> = [];
  try {
    const model = JSON.parse(readFileSync(fullPath, 'utf-8'));
    if (model.architecture) architecture = JSON.stringify(model.architecture.hiddenSizes);
    if (model.trainingHistory) trainingHistory = model.trainingHistory;
    if (trainingHistory.length > 0) valLoss = trainingHistory[trainingHistory.length - 1].valLoss;
  } catch {}
  return { path: modelPath, exists: true, sizeBytes: stat.size, modifiedAt: stat.mtime.toISOString(), valLoss, architecture, trainingHistory };
}

function getCalibrationStatus(calibPath: string): CalibrationStatus {
  const fullPath = join(PROJECT_ROOT, calibPath);
  if (!existsSync(fullPath)) {
    return { path: calibPath, exists: false, klDivergence: null, actionAccuracy: null, totalPredictions: null, perStreet: {} };
  }
  try {
    const data = JSON.parse(readFileSync(fullPath, 'utf-8'));
    return {
      path: calibPath,
      exists: true,
      klDivergence: data.overall?.klDivergence ?? null,
      actionAccuracy: data.overall?.actionAccuracy ?? null,
      totalPredictions: data.overall?.totalPredictions ?? null,
      perStreet: data.perStreet || {},
    };
  } catch {
    return { path: calibPath, exists: false, klDivergence: null, actionAccuracy: null, totalPredictions: null, perStreet: {} };
  }
}

function getStatusJSON(): string {
  const datasets = [
    getDatasetStatus('SRP (50bb)', 'pipeline_srp', 'pipeline_hu_srp_50bb', 'cfr_srp'),
    getDatasetStatus('3-Bet (50bb)', 'pipeline_3bet', 'pipeline_hu_3bet_50bb', 'cfr_3bet'),
  ];
  const models = [
    getModelStatus('models/cfr-srp-v3.json'),
    getModelStatus('models/cfr-3bet-v3.json'),
    getModelStatus('models/cfr-combined-v3.json'),
  ];
  const calibrations = [
    getCalibrationStatus('models/cfr-srp-v3-calibration.json'),
    getCalibrationStatus('models/cfr-3bet-v3-calibration.json'),
    getCalibrationStatus('models/cfr-combined-v3-calibration.json'),
  ];
  return JSON.stringify({ datasets, models, calibrations, timestamp: new Date().toISOString() });
}

const HTML = `<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CardPilot Training Pipeline</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
  h1 { text-align: center; font-size: 1.8em; margin-bottom: 6px; color: #38bdf8; }
  .subtitle { text-align: center; color: #64748b; font-size: 0.9em; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 1200px; margin: 0 auto; }
  .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
  .card.full { grid-column: 1 / -1; }
  .card h2 { font-size: 1.1em; color: #94a3b8; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
  .card h2 .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot.green { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
  .dot.yellow { background: #eab308; box-shadow: 0 0 6px #eab308; animation: pulse 1.5s infinite; }
  .dot.red { background: #ef4444; }
  .dot.gray { background: #475569; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  .stat-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #334155; }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: #94a3b8; font-size: 0.9em; }
  .stat-value { font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat-value.big { font-size: 1.4em; color: #38bdf8; }

  .progress-bar { height: 24px; background: #334155; border-radius: 12px; overflow: hidden; margin: 10px 0; position: relative; }
  .progress-fill { height: 100%; border-radius: 12px; transition: width 0.8s ease; }
  .progress-fill.blue { background: linear-gradient(90deg, #0ea5e9, #38bdf8); }
  .progress-fill.green { background: linear-gradient(90deg, #16a34a, #22c55e); }
  .progress-fill.orange { background: linear-gradient(90deg, #ea580c, #f97316); }
  .progress-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); font-size: 0.8em; font-weight: 700; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }

  .metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 10px; }
  .metric { text-align: center; padding: 12px; background: #0f172a; border-radius: 8px; }
  .metric .val { font-size: 1.5em; font-weight: 700; }
  .metric .label { font-size: 0.75em; color: #64748b; margin-top: 4px; }
  .metric .val.good { color: #22c55e; }
  .metric .val.warn { color: #eab308; }
  .metric .val.bad { color: #ef4444; }
  .metric .val.neutral { color: #38bdf8; }

  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.85em; }
  th { text-align: left; color: #64748b; padding: 6px 8px; border-bottom: 1px solid #334155; }
  td { padding: 6px 8px; border-bottom: 1px solid #1e293b; }

  .updated { text-align: center; color: #475569; font-size: 0.8em; margin-top: 16px; }
  .no-data { color: #475569; font-style: italic; text-align: center; padding: 20px; }
</style>
</head>
<body>
<h1>CardPilot Training Pipeline</h1>
<p class="subtitle">CFR Data → Neural Network → Calibration</p>
<div class="grid" id="root"></div>
<p class="updated" id="updated"></p>

<script>
function fmt(n) { return n != null ? n.toLocaleString() : '—'; }
function fmtBytes(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
  return (b/1073741824).toFixed(2) + ' GB';
}
function pct(a,b) { return b > 0 ? ((a/b)*100).toFixed(1) : '0'; }

function renderDataset(ds) {
  const done = ds.generatedFlops >= ds.totalCfrFlops && ds.totalCfrFlops > 0;
  const inProgress = ds.generatedFlops > 0 && ds.generatedFlops < ds.totalCfrFlops;
  const dotClass = done ? 'green' : inProgress ? 'yellow' : 'gray';
  const fillClass = done ? 'green' : 'blue';
  const p = ds.totalCfrFlops > 0 ? (ds.generatedFlops / ds.totalCfrFlops * 100) : 0;
  return '<div class="card"><h2><span class="dot '+dotClass+'"></span>'+ds.name+' Data Generation</h2>'
    + '<div class="progress-bar"><div class="progress-fill '+fillClass+'" style="width:'+p+'%"></div>'
    + '<span class="progress-text">'+ds.generatedFlops+' / '+ds.totalCfrFlops+' flops ('+p.toFixed(1)+'%)</span></div>'
    + '<div class="stat-row"><span class="stat-label">Config</span><span class="stat-value">'+ds.config+'</span></div>'
    + '<div class="stat-row"><span class="stat-label">Training Samples</span><span class="stat-value big">'+fmt(ds.totalSamples)+'</span></div>'
    + '<div class="stat-row"><span class="stat-label">Files on Disk</span><span class="stat-value">'+ds.filesOnDisk+' .jsonl</span></div>'
    + '<div class="stat-row"><span class="stat-label">Data Size</span><span class="stat-value">'+fmtBytes(ds.totalSizeBytes)+'</span></div>'
    + (ds.generatedAt ? '<div class="stat-row"><span class="stat-label">Completed</span><span class="stat-value">'+new Date(ds.generatedAt).toLocaleString()+'</span></div>' : '')
    + '</div>';
}

function renderModel(m) {
  if (!m.exists) {
    return '<div class="card"><h2><span class="dot gray"></span>Model: '+m.path+'</h2><p class="no-data">Not trained yet</p></div>';
  }
  let html = '<div class="card"><h2><span class="dot green"></span>Model: '+m.path+'</h2>';
  html += '<div class="stat-row"><span class="stat-label">Size</span><span class="stat-value">'+fmtBytes(m.sizeBytes)+'</span></div>';
  if (m.architecture) html += '<div class="stat-row"><span class="stat-label">Architecture</span><span class="stat-value">'+m.architecture+'</span></div>';
  if (m.valLoss != null) html += '<div class="stat-row"><span class="stat-label">Val Loss</span><span class="stat-value big">'+m.valLoss.toFixed(4)+'</span></div>';
  if (m.modifiedAt) html += '<div class="stat-row"><span class="stat-label">Last Updated</span><span class="stat-value">'+new Date(m.modifiedAt).toLocaleString()+'</span></div>';
  if (m.trainingHistory && m.trainingHistory.length > 1) {
    html += '<div style="margin-top:12px"><canvas id="chart_'+m.path.replace(/[^a-z0-9]/gi,'_')+'" height="120"></canvas></div>';
  }
  html += '</div>';
  return html;
}

function renderCalibration(c) {
  if (!c.exists) return '';
  const accClass = c.actionAccuracy >= 0.75 ? 'good' : c.actionAccuracy >= 0.6 ? 'warn' : 'bad';
  const klClass = c.klDivergence <= 0.1 ? 'good' : c.klDivergence <= 0.3 ? 'warn' : 'bad';
  let html = '<div class="card"><h2><span class="dot green"></span>Calibration: '+c.path+'</h2>';
  html += '<div class="metric-grid">';
  html += '<div class="metric"><div class="val '+klClass+'">'+c.klDivergence.toFixed(4)+'</div><div class="label">KL Divergence</div></div>';
  html += '<div class="metric"><div class="val '+accClass+'">'+(c.actionAccuracy*100).toFixed(1)+'%</div><div class="label">Action Accuracy</div></div>';
  html += '<div class="metric"><div class="val neutral">'+fmt(c.totalPredictions)+'</div><div class="label">Predictions</div></div>';
  html += '</div>';
  if (Object.keys(c.perStreet).length > 0) {
    html += '<table><tr><th>Street</th><th>KL Div</th><th>Accuracy</th><th>Samples</th></tr>';
    for (const [street, s] of Object.entries(c.perStreet)) {
      html += '<tr><td>'+street+'</td><td>'+s.klDivergence.toFixed(4)+'</td><td>'+(s.actionAccuracy*100).toFixed(1)+'%</td><td>'+fmt(s.count)+'</td></tr>';
    }
    html += '</table>';
  }
  html += '</div>';
  return html;
}

function drawLossChart(canvasId, history) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth * 2;
  const h = canvas.height = 240;
  ctx.scale(1, 1);

  const losses = history.map(h => h.valLoss);
  const minL = Math.min(...losses) * 0.95;
  const maxL = Math.max(...losses) * 1.05;

  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, w, h);

  // Grid
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = 20 + (h - 40) * (i / 4);
    ctx.beginPath(); ctx.moveTo(40, y); ctx.lineTo(w - 10, y); ctx.stroke();
    ctx.fillStyle = '#475569';
    ctx.font = '18px monospace';
    ctx.fillText((maxL - (maxL - minL) * (i / 4)).toFixed(3), 0, y + 5);
  }

  // Line
  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (let i = 0; i < losses.length; i++) {
    const x = 40 + (w - 50) * (i / Math.max(1, losses.length - 1));
    const y = 20 + (h - 40) * (1 - (losses[i] - minL) / (maxL - minL || 1));
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.stroke();
}

async function refresh() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    let html = '';

    // Datasets
    for (const ds of data.datasets) {
      html += renderDataset(ds);
    }

    // Combined summary
    const totalFlops = data.datasets.reduce((s,d) => s + d.generatedFlops, 0);
    const totalTargetFlops = data.datasets.reduce((s,d) => s + d.totalCfrFlops, 0);
    const totalSamples = data.datasets.reduce((s,d) => s + d.totalSamples, 0);
    const totalSize = data.datasets.reduce((s,d) => s + d.totalSizeBytes, 0);
    const allDone = data.datasets.every(d => d.generatedFlops >= d.totalCfrFlops);
    const p = totalTargetFlops > 0 ? (totalFlops / totalTargetFlops * 100) : 0;

    html += '<div class="card full"><h2><span class="dot '+(allDone?'green':'yellow')+'"></span>Combined Progress</h2>';
    html += '<div class="progress-bar"><div class="progress-fill '+(allDone?'green':'orange')+'" style="width:'+p+'%"></div>';
    html += '<span class="progress-text">'+totalFlops+' / '+totalTargetFlops+' flops ('+p.toFixed(1)+'%)</span></div>';
    html += '<div class="metric-grid">';
    html += '<div class="metric"><div class="val neutral">'+fmt(totalSamples)+'</div><div class="label">Total Samples</div></div>';
    html += '<div class="metric"><div class="val neutral">'+totalFlops+'</div><div class="label">Flops Done</div></div>';
    html += '<div class="metric"><div class="val neutral">'+fmtBytes(totalSize)+'</div><div class="label">Total Size</div></div>';
    html += '</div></div>';

    // Models
    for (const m of data.models) {
      html += renderModel(m);
    }

    // Calibrations
    for (const c of data.calibrations) {
      html += renderCalibration(c);
    }

    document.getElementById('root').innerHTML = html;
    document.getElementById('updated').textContent = 'Last updated: ' + new Date(data.timestamp).toLocaleString() + ' (auto-refresh every 10s)';

    // Draw charts
    for (const m of data.models) {
      if (m.trainingHistory && m.trainingHistory.length > 1) {
        const id = 'chart_' + m.path.replace(/[^a-z0-9]/gi, '_');
        setTimeout(() => drawLossChart(id, m.trainingHistory), 50);
      }
    }
  } catch (err) {
    console.error('Refresh error:', err);
  }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>`;

const server = createServer((req, res) => {
  if (req.url === '/api/status') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(getStatusJSON());
  } else {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(HTML);
  }
});

server.listen(PORT, () => {
  console.log(`Training Pipeline Dashboard: http://localhost:${PORT}`);
});
