#!/usr/bin/env tsx
/**
 * Split a large JSONL file into smaller chunks.
 * Usage: npx tsx scripts/split-training.ts --input path/train.jsonl --lines-per-file 200000
 */

import { createReadStream, createWriteStream, mkdirSync, existsSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { dirname, join, basename } from 'node:path';

const argv = process.argv.slice(2);
function getArg(name: string, fallback: string): string {
  const idx = argv.indexOf(name);
  return idx >= 0 && argv[idx + 1] ? argv[idx + 1] : fallback;
}

const inputFile = getArg('--input', 'data/training/cfr_srp_v2_sampled/train.jsonl');
const linesPerFile = parseInt(getArg('--lines-per-file', '200000'), 10);
const outputDir = dirname(inputFile);
const prefix = basename(inputFile, '.jsonl');

async function main() {
  const rl = createInterface({
    input: createReadStream(inputFile, { encoding: 'utf-8' }),
    crlfDelay: Infinity,
  });

  let fileIdx = 0;
  let lineCount = 0;
  let totalLines = 0;
  let writer: ReturnType<typeof createWriteStream> | null = null;

  function openWriter() {
    const outPath = join(outputDir, `${prefix}_${String(fileIdx).padStart(3, '0')}.jsonl`);
    writer = createWriteStream(outPath, { encoding: 'utf-8' });
    console.log(`  Writing ${outPath}`);
  }

  openWriter();

  for await (const line of rl) {
    if (!line.trim()) continue;

    writer!.write(line + '\n');
    lineCount++;
    totalLines++;

    if (lineCount >= linesPerFile) {
      writer!.end();
      fileIdx++;
      lineCount = 0;
      openWriter();
    }
  }

  if (writer) writer.end();

  console.log(`\nSplit ${totalLines.toLocaleString()} lines into ${fileIdx + 1} files`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
