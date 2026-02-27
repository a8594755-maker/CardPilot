#!/usr/bin/env tsx
import { exportToBinary } from '../packages/cfr-solver/src/storage/binary-format.js';

const inputDir = 'data/cfr/pipeline_hu_3bet_50bb';
const outputPath = 'data/cfr/pipeline_hu_3bet_50bb.bin.gz';

console.log('Starting binary export...');
console.log('Input:', inputDir);
console.log('Output:', outputPath);
console.log('Memory limit:', process.env.NODE_OPTIONS || 'default');
console.log();

console.time('export');
const result = exportToBinary({ inputDir, outputPath });
console.timeEnd('export');

console.log();
console.log('Result:', JSON.stringify(result, null, 2));
