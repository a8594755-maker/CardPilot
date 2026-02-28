// Compact binary format for CFR strategy storage.
//
// Format:
//   Header (32 bytes):
//     [4B] magic "CFR1"  [2B] version  [2B] bucketCount
//     [4B] numFlops  [4B] iterations  [4B] indexOffset
//     [4B] entryCount  [8B] reserved
//
//   Index (entryCount * 8 bytes, sorted by hash for binary search):
//     [4B] fnv1a hash of key  [4B] body offset
//
//   Body (variable):
//     [1B] numActions  [numActions bytes] uint8 quantized probs (0-255)

import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { gzipSync, gunzipSync } from 'node:zlib';

const MAGIC_V1 = Buffer.from('CFR1');
const MAGIC_V2 = Buffer.from('CFR2');
const MAGIC = MAGIC_V2; // New files use V2
const HEADER_SIZE = 32;

export interface BinaryExportConfig {
  inputDir: string;
  outputPath: string;
  compress?: boolean;   // default: true
}

export interface BinaryExportResult {
  entries: number;
  rawSize: number;
  compressedSize: number;
  compressionRatio: number;
}

function quantizeProb(p: number): number {
  return Math.max(0, Math.min(255, Math.round(p * 255)));
}

function dequantizeProb(b: number): number {
  return b / 255;
}

function fnv1a(str: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/**
 * Export all JSONL files from a directory to a single compressed binary file.
 * Memory-efficient: streams entries and keeps only compact (hash, offset) pairs.
 * Typical compression: 513 MB JSONL → ~30 MB gzip binary.
 */
export function exportToBinary(config: BinaryExportConfig): BinaryExportResult {
  const { inputDir, outputPath, compress = true } = config;

  const files = readdirSync(inputDir).filter(f => f.endsWith('.jsonl') && f.startsWith('flop_')).sort();
  let iterations = 50000;
  let bucketCount = 50;
  let numFlops = 0;

  // Pass 1: scan to count entries and compute total body size
  let totalEntries = 0;
  let totalBodySize = 0;
  for (const file of files) {
    numFlops++;
    const content = readFileSync(join(inputDir, file), 'utf-8');
    let skipped = 0;
    for (const line of content.split('\n')) {
      if (!line.trim()) continue;
      try {
        const parsed = JSON.parse(line) as { probs: number[] };
        if (!parsed.probs) { skipped++; continue; }
        totalEntries++;
        totalBodySize += 1 + parsed.probs.length; // 1B numActions + probs bytes
      } catch { skipped++; }
    }
    if (skipped > 0) console.log(`  ${file}: skipped ${skipped} invalid lines`);
    const metaPath = join(inputDir, file.replace('.jsonl', '.meta.json'));
    if (existsSync(metaPath)) {
      try {
        const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
        if (meta.iterations) iterations = meta.iterations;
        if (meta.bucketCount) bucketCount = meta.bucketCount;
      } catch { /* corrupted meta file, skip */ }
    }
  }

  console.log(`  Entries: ${totalEntries}, body size: ${totalBodySize} bytes`);

  // Allocate compact index (12 bytes per entry: 4B hash + 4B bodyOffset + 4B bodyLen)
  // and body buffer upfront
  const indexBuf = Buffer.alloc(totalEntries * 12);
  const bodyBuf = Buffer.alloc(totalBodySize);
  let bodyOffset = 0;
  let entryIdx = 0;

  // Pass 2: fill index and body
  for (const file of files) {
    const content = readFileSync(join(inputDir, file), 'utf-8');
    for (const line of content.split('\n')) {
      if (!line.trim()) continue;
      let parsed: { key: string; probs: number[] };
      try { parsed = JSON.parse(line); } catch { continue; }
      if (!parsed.probs) continue;
      const hash = fnv1a(parsed.key);
      const numActions = parsed.probs.length;

      // Write to index: hash, bodyOffset, bodyLen (for sorting)
      const iOff = entryIdx * 12;
      indexBuf.writeUInt32LE(hash, iOff);
      indexBuf.writeUInt32LE(bodyOffset, iOff + 4);
      indexBuf.writeUInt32LE(numActions, iOff + 8);

      // Write body: [numActions] [quantized probs...]
      bodyBuf[bodyOffset] = numActions;
      for (let i = 0; i < numActions; i++) {
        bodyBuf[bodyOffset + 1 + i] = quantizeProb(parsed.probs[i]);
      }
      bodyOffset += 1 + numActions;
      entryIdx++;
    }
  }

  // Sort index by hash using LSD radix sort on the 12-byte entries.
  // V8 disallows custom comparefn on huge TypedArrays and Array allocation
  // fails for 200M+ elements, so we sort the buffer entries directly.
  console.log('  Radix sorting index...');
  const ENTRY = 12;
  const sortedIdx = Buffer.alloc(totalEntries * ENTRY);
  const counts = new Uint32Array(256);

  // LSD radix sort: 4 passes for 4 hash bytes (little-endian, so byte 0 first)
  let src = indexBuf;
  let dst = sortedIdx;
  for (let bytePos = 0; bytePos < 4; bytePos++) {
    counts.fill(0);
    for (let i = 0; i < totalEntries; i++) counts[src[i * ENTRY + bytePos]]++;
    let sum = 0;
    for (let i = 0; i < 256; i++) { const c = counts[i]; counts[i] = sum; sum += c; }
    for (let i = 0; i < totalEntries; i++) {
      const b = src[i * ENTRY + bytePos];
      const pos = counts[b]++;
      src.copy(dst, pos * ENTRY, i * ENTRY, i * ENTRY + ENTRY);
    }
    [src, dst] = [dst, src];
  }
  // After 4 passes (even), sorted result is back in the original `src` variable
  const sortedResult = src;
  console.log('  Sort complete.');

  // Assemble final binary
  const indexSize = totalEntries * 8;
  const buffer = Buffer.alloc(HEADER_SIZE + indexSize + totalBodySize);

  // Header
  MAGIC.copy(buffer, 0);
  buffer.writeUInt16LE(1, 4);                      // version
  buffer.writeUInt16LE(bucketCount, 6);
  buffer.writeUInt32LE(numFlops, 8);
  buffer.writeUInt32LE(iterations, 12);
  buffer.writeUInt32LE(HEADER_SIZE, 16);            // indexOffset
  buffer.writeUInt32LE(totalEntries, 20);           // entryCount

  // Write sorted index (hash + bodyOffset only, 8 bytes each)
  let off = HEADER_SIZE;
  for (let i = 0; i < totalEntries; i++) {
    const srcOff = i * ENTRY;
    buffer.writeUInt32LE(sortedResult.readUInt32LE(srcOff), off);       // hash
    buffer.writeUInt32LE(sortedResult.readUInt32LE(srcOff + 4), off + 4); // bodyOffset
    off += 8;
  }

  // Copy body
  bodyBuf.copy(buffer, HEADER_SIZE + indexSize);

  // Output
  mkdirSync(dirname(outputPath), { recursive: true });
  if (compress) {
    const compressed = gzipSync(buffer, { level: 9 });
    writeFileSync(outputPath, compressed);
    return { entries: totalEntries, rawSize: buffer.length, compressedSize: compressed.length, compressionRatio: buffer.length / compressed.length };
  }
  writeFileSync(outputPath, buffer);
  return { entries: totalEntries, rawSize: buffer.length, compressedSize: buffer.length, compressionRatio: 1 };
}

/**
 * Binary strategy reader with O(log n) lookup.
 */
export class BinaryStrategyReader {
  private buffer: Buffer;
  private indexStart: number;
  private indexCount: number;
  private bodyStart: number;

  constructor(input: string | Buffer) {
    const raw = typeof input === 'string' ? readFileSync(input) : input;
    this.buffer = (raw[0] === 0x1f && raw[1] === 0x8b) ? gunzipSync(raw) : raw;

    const magic = this.buffer.subarray(0, 4).toString();
    if (magic !== 'CFR1' && magic !== 'CFR2') {
      throw new Error(`Invalid binary format: expected CFR1 or CFR2, got ${magic}`);
    }

    this.indexStart = this.buffer.readUInt32LE(16);
    this.indexCount = this.buffer.readUInt32LE(20);
    this.bodyStart = this.indexStart + this.indexCount * 8;
  }

  /**
   * O(log n) lookup by info-set key string.
   */
  lookup(key: string): number[] | null {
    if (this.indexCount === 0) return null;
    const hash = fnv1a(key);

    let lo = 0;
    let hi = this.indexCount - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      const entryHash = this.buffer.readUInt32LE(this.indexStart + mid * 8);
      if (entryHash === hash) {
        const bodyOff = this.buffer.readUInt32LE(this.indexStart + mid * 8 + 4);
        const abs = this.bodyStart + bodyOff;
        const n = this.buffer[abs];
        const probs: number[] = [];
        for (let i = 0; i < n; i++) probs.push(dequantizeProb(this.buffer[abs + 1 + i]));
        return probs;
      }
      if (entryHash < hash) lo = mid + 1; else hi = mid - 1;
    }
    return null;
  }

  get entryCount(): number { return this.indexCount; }
  get version(): number { return this.buffer.readUInt16LE(4); }
  get numFlops(): number { return this.buffer.readUInt32LE(8); }
  get iterations(): number { return this.buffer.readUInt32LE(12); }
  get bucketCount(): number { return this.buffer.readUInt16LE(6); }
}
