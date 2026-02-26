// Generate pipeline jobs for all isomorphic flops, with resume support.

import { enumerateIsomorphicFlops } from '../abstraction/suit-isomorphism.js';
import { indexToCard } from '../abstraction/card-index.js';
import {
  getTreeConfig, getSolveDefaults, getConfigOutputDir, getStackLabel,
  type TreeConfigName,
} from '../tree/tree-config.js';
import { type PipelineJob, loadCompletedLog } from './queue-server.js';
import { resolve } from 'node:path';
import { existsSync, readdirSync } from 'node:fs';

export interface GenerateOptions {
  configName: TreeConfigName;
  projectRoot: string;
  chartsPath: string;
  iterations?: number;   // override default
  buckets?: number;       // override default
  resume?: boolean;       // skip already-solved flops (checks for .meta.json)
}

/**
 * Generate PipelineJob[] for all isomorphic flops under a given config.
 * With resume=true, skips flops that already have output files.
 */
export function generateJobs(opts: GenerateOptions): PipelineJob[] {
  const defaults = getSolveDefaults(opts.configName);
  const iterations = opts.iterations ?? defaults.iterations;
  const bucketCount = opts.buckets ?? defaults.buckets;
  const outputDir = resolve(opts.projectRoot, 'data/cfr', getConfigOutputDir(opts.configName));
  const stackLabel = getStackLabel(opts.configName);

  console.log(`[Job Generator] Enumerating isomorphic flops...`);
  const allFlops = enumerateIsomorphicFlops();
  console.log(`[Job Generator] ${allFlops.length} isomorphic flops found`);

  // Check for already-completed flops if resuming
  let completedIds = new Set<number>();
  if (opts.resume) {
    // Source 1: local .meta.json files (flops solved on this machine)
    if (existsSync(outputDir)) {
      const files = readdirSync(outputDir);
      for (const f of files) {
        const match = f.match(/^flop_(\d+)\.meta\.json$/);
        if (match) completedIds.add(parseInt(match[1], 10));
      }
    }
    const localCount = completedIds.size;

    // Source 2: completed.jsonl log (flops solved by ANY machine, persisted by coordinator)
    const logPath = resolve(outputDir, 'completed.jsonl');
    const fromLog = loadCompletedLog(logPath);
    for (const id of fromLog) completedIds.add(id);

    if (completedIds.size > 0) {
      console.log(`[Job Generator] Resume: ${completedIds.size} flops already solved, skipping`);
      console.log(`[Job Generator]   (${localCount} from local .meta.json, ${fromLog.size} from completed.jsonl)`);
    }
  }

  const jobs: PipelineJob[] = [];
  for (let index = 0; index < allFlops.length; index++) {
    if (completedIds.has(index)) continue;

    const flop = allFlops[index];
    jobs.push({
      jobId: `${opts.configName}__${String(index).padStart(4, '0')}`,
      flopCards: flop.cards,
      boardId: index,
      label: flop.cards.map(indexToCard).join(' '),
      canonical: flop.canonical,
      iterations,
      bucketCount,
      configName: opts.configName,
      stackLabel,
      outputDir,
      chartsPath: opts.chartsPath,
    });
  }

  console.log(`[Job Generator] ${jobs.length} jobs generated for ${opts.configName} (${completedIds.size} skipped)`);
  console.log(`[Job Generator]   Iterations: ${iterations} | Buckets: ${bucketCount}`);
  console.log(`[Job Generator]   Output dir: ${outputDir}`);

  return jobs;
}
