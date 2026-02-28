import { readdirSync, readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { execSync } from 'child_process';

const BASE = 'c:/Users/a8594/CardPilot/data/cfr';
const CONFIGS = ['pipeline_hu_srp_50bb', 'pipeline_hu_3bet_50bb'];
const S3_BASE = 's3://cardpilot-cfr-data/meta';
const AWS_ARGS = '--profile idrive-e2 --endpoint-url https://s3.us-east-1.idrivee2.com';

for (const config of CONFIGS) {
  const dir = join(BASE, config);
  console.log(`\n=== Processing ${config} ===`);

  let files;
  try {
    files = readdirSync(dir).filter(f => f.endsWith('.meta.json'));
  } catch (e) {
    console.error(`  ERROR: Could not read directory ${dir}: ${e.message}`);
    continue;
  }

  console.log(`  Found ${files.length} .meta.json files`);

  const entries = [];
  for (const f of files) {
    try {
      const data = JSON.parse(readFileSync(join(dir, f), 'utf-8'));
      entries.push(data);
    } catch (e) {
      console.error(`  WARN: Could not parse ${f}: ${e.message}`);
    }
  }

  console.log(`  Parsed ${entries.length} entries`);

  entries.sort((a, b) => (a.flop || '').localeCompare(b.flop || ''));

  const outPath = join(BASE, config, '_index.json');
  writeFileSync(outPath, JSON.stringify(entries, null, 2));
  console.log(`  Wrote ${outPath}`);

  const s3Path = `${S3_BASE}/${config}/_index.json`;
  const cmd = `aws s3 cp "${outPath}" "${s3Path}" ${AWS_ARGS}`;
  console.log(`  Uploading: ${cmd}`);
  try {
    const result = execSync(cmd, { encoding: 'utf-8', timeout: 60000 });
    console.log(`  ${result.trim()}`);
  } catch (e) {
    console.error(`  Upload failed: ${e.stderr || e.message}`);
  }
}

console.log('\nDone!');
