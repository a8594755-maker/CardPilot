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

  const files = readdirSync(inputDir).filter(f => f.endsWith('.jsonl')).sort();
  let iterations = 50000;
  let bucketCount = 50;
  let numFlops = 0;

  // Pass 1: scan to count entries and compute total body size
  let totalEntries = 0;
  let totalBodySize = 0;
  for (const file of files) {
    numFlops++;
    const content = readFileSync(join(inputDir, file), 'utf-8');
    for (const line of content.split('\n')) {
      if (!line.trim()) continue;
      const parsed = JSON.parse(line) as { probs: number[] };
      totalEntries++;
      totalBodySize += 1 + parsed.probs.length; // 1B numActions + probs bytes
    }
    const metaPath = join(inputDir, file.replace('.jsonl', '.meta.json'));
    if (existsSync(metaPath)) {
      const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
      iterations = meta.iterations;
      bucketCount = meta.bucketCount;
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
      const parsed = JSON.parse(line) as { key: string; probs: number[] };
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

  // Sort index by hash using an indirection array (4 bytes/entry vs ~50 bytes/object)
  const order = new Uint32Array(totalEntries);
  for (let i = 0; i < totalEntries; i++) order[i] = i;
  order.sort((a, b) => indexBuf.readUInt32LE(a * 12) - indexBuf.readUInt32LE(b * 12));

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

  // Write sorted index
  let off = HEADER_SIZE;
  for (let i = 0; i < totalEntries; i++) {
    const srcOff = order[i] * 12;
    buffer.writeUInt32LE(indexBuf.readUInt32LE(srcOff), off);       // hash
    buffer.writeUInt32LE(indexBuf.readUInt32LE(srcOff + 4), off + 4); // bodyOffset
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

  constructor(filePath: string) {
    const raw = readFileSync(filePath);
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
